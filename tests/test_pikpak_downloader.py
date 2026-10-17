"""PikPak client downloader state machine against a fake bridge (no client needed)."""
import pytest

from anipik.downloaders import JobSpec, NeedsAttention, TransientError
from anipik.downloaders.pikpak_client import PikPakClientDownloader
from anipik.downloaders.pikpak_client.bridge import BridgeError

MAGNET = "magnet:?xt=urn:btih:" + "a" * 40


class FakeBridge:
    def __init__(self):
        self.cloud = {}      # task id -> task
        self.local = []      # local task dicts
        self.submissions = []
        self.started = []
        self.instance = "launch-1"
        self.fail_next = None
        self.files = [{"id": "f1", "size": 4, "name": "ep01.mkv", "parents": []},
                      {"id": "f2", "size": 2, "name": "sub.ass", "parents": [{"id": "d", "name": "Subs"}]}]

    def connect(self):
        return self

    def close(self):
        pass

    def instance_id(self):
        return self.instance

    def start_local_task(self, task_id):
        self.started.append(task_id)
        next(t for t in self.local if t["id"] == task_id)["status"] = "PENDING"
        return True

    def _maybe_fail(self):
        if self.fail_next:
            error, self.fail_next = self.fail_next, None
            raise error

    def find_cloud_task(self, url):
        self._maybe_fail()
        return next((t for t in self.cloud.values() if t["params"]["url"] == url), None)

    def add_cloud_task(self, url):
        self.submissions.append(url)
        task = {"id": f"t{len(self.cloud)}", "params": {"url": url}, "phase": "PHASE_TYPE_RUNNING", "progress": 30}
        self.cloud[task["id"]] = task
        self._maybe_fail()
        return {"task": task}

    def get_cloud_task(self, task_id):
        return self.cloud[task_id]

    def expand_files(self, file_id):
        return self.files

    def local_tasks(self, file_ids):
        return [t for t in self.local if t["file_id"] in file_ids]

    def download_files(self, files, destination):
        import os
        for f in files:
            path = os.path.join(destination, *(p["name"] for p in f["parents"]), f["name"])
            self.local.append({"id": "L" + f["id"], "file_id": f["id"], "path": path, "status": "DOWNLOADING",
                               "speed": 1, "size": f["size"], "downloaded": 1})


@pytest.fixture
def env(tmp_path):
    bridge = FakeBridge()
    downloader = PikPakClientDownloader({}, bridge_factory=lambda: bridge)
    job = JobSpec(1, MAGNET, str(tmp_path / "Show"))
    state, checkpoints = {}, []

    def tick():
        with downloader.connection():
            return downloader.advance(job, state, lambda: checkpoints.append(dict(state)))
    return bridge, job, state, checkpoints, tick


def test_full_flow(env, tmp_path):
    bridge, job, state, checkpoints, tick = env
    status = tick()
    assert state["phase"] == "cloud_waiting" and bridge.submissions == [MAGNET]
    assert any(c["phase"] == "cloud_submitting" for c in checkpoints)  # checkpoint before the mutation
    assert (status.state, status.progress, status.message) == ("running", 30, "云端下载 30%")

    bridge.cloud["t0"].update(phase="PHASE_TYPE_COMPLETE", file_id="root", progress=100)
    tick()
    assert state["phase"] == "local_waiting" and len(bridge.local) == 2
    status = tick()  # progress is the local stage's own percentage: 2 of 6 bytes, not 50 + x/2
    assert status.progress == pytest.approx(33.33) and status.message.startswith("本地下载 33%")
    assert (tmp_path / "Show" / "Subs").is_dir()

    for task in bridge.local:
        task["status"] = "COMPLETED"
    (tmp_path / "Show" / "ep01.mkv").write_bytes(b"1234")
    (tmp_path / "Show" / "Subs" / "sub.ass").write_bytes(b"12")
    status = tick()
    assert status.state == "done" and state["phase"] == "done"
    assert bridge.submissions == [MAGNET]


def _to_local_stage(bridge, tick):
    tick()
    bridge.cloud["t0"].update(phase="PHASE_TYPE_COMPLETE", file_id="root", progress=100)
    tick()
    assert len(bridge.local) == 2


def test_resumes_tasks_paused_by_client_restart(env):
    bridge, job, state, _, tick = env
    _to_local_stage(bridge, tick)
    for task in bridge.local:
        task["status"] = "PAUSED"
    bridge.instance = "launch-2"  # PikPak was restarted: unfinished tasks come back paused
    tick()
    assert sorted(bridge.started) == ["Lf1", "Lf2"] and state["client_instance"] == "launch-2"
    assert state["phase"] == "local_waiting" and not state["wait_reason"]


def test_respects_manual_pause(env):
    bridge, job, state, _, tick = env
    _to_local_stage(bridge, tick)
    bridge.local[0]["status"] = "PAUSED"  # same client launch: the user paused it
    tick()
    tick()
    assert bridge.started == [] and "手动暂停" in state["wait_reason"]


def test_reuses_existing_cloud_task(env):
    bridge, job, state, _, tick = env
    bridge.cloud["old"] = {"id": "old", "params": {"url": MAGNET}, "phase": "PHASE_TYPE_RUNNING", "progress": 5}
    tick()
    assert bridge.submissions == [] and state["cloud_task_id"] == "old"


def test_uncertain_submission_is_detected_not_repeated(env):
    bridge, job, state, _, tick = env
    bridge.add_cloud_task = lambda url: (_ for _ in ()).throw(BridgeError("timeout after send"))
    with pytest.raises(TransientError):
        tick()
    assert state["phase"] == "cloud_submitting"
    with pytest.raises(NeedsAttention):  # nothing found in the cloud list: don't resubmit blindly
        tick()


def test_submission_that_succeeded_despite_error_is_picked_up(env):
    bridge, job, state, _, tick = env
    bridge.fail_next = BridgeError("reply lost")
    with pytest.raises(TransientError):
        tick()  # fails inside find_cloud_task before submitting
    assert bridge.submissions == []
    tick()
    assert state["phase"] == "cloud_waiting" and bridge.submissions == [MAGNET]


def test_cloud_failure_and_overwrite_protection(env, tmp_path):
    bridge, job, state, _, tick = env
    tick()
    bridge.cloud["t0"].update(phase="PHASE_TYPE_ERROR", message="no seeds")
    status = tick()
    assert status.state == "failed" and status.message == "no seeds"

    state.clear()
    bridge.cloud.clear()
    tick()
    bridge.cloud["t0"].update(phase="PHASE_TYPE_COMPLETE", file_id="root")
    (tmp_path / "Show").mkdir()
    (tmp_path / "Show" / "ep01.mkv").write_bytes(b"different size")
    with pytest.raises(NeedsAttention, match="overwrite"):
        tick()


def test_expected_path_keeps_drive_letter():
    from anipik.downloaders.pikpak_client.downloader import expected_path
    path = expected_path("N:/新番/Show", {"name": "ep.mp4", "parents": [{"name": "Sub"}]})
    assert str(path) == r"N:\新番\Show\Sub\ep.mp4"  # not \\server\share\... for mapped drives
    with pytest.raises(NeedsAttention):
        expected_path("N:/新番/Show", {"name": "x", "parents": [{"name": ".."}, {"name": ".."}]})


def test_unreachable_client_is_transient():
    class Down(FakeBridge):
        def connect(self):
            raise ConnectionRefusedError("refused")
    downloader = PikPakClientDownloader({}, bridge_factory=Down)
    with pytest.raises(TransientError):
        with downloader.connection():
            pass
