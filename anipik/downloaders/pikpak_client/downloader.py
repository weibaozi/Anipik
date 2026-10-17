"""magnet -> PikPak cloud task -> official client local download, with checkpoints.

Ported from G:/study/others/pikpak/pikpak_queue.py process_job(). Sub-phases kept in
Job.state["phase"]: new, cloud_submitting, cloud_waiting, local_ready, local_submitting,
local_waiting, done, failed.
"""
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path

import websocket

from ..base import Downloader, JobSpec, NeedsAttention, Status, TransientError
from .bridge import BridgeError, PikPakBridge

log = logging.getLogger(__name__)


def expected_path(destination, file):
    # abspath, not resolve(): resolve() turns a mapped drive (N:\) into its UNC path,
    # which then never matches the path the client reports.
    root = Path(os.path.abspath(destination))
    result = Path(os.path.abspath(root.joinpath(*(p["name"] for p in file["parents"]), file["name"])))
    if not result.is_relative_to(root):
        raise NeedsAttention("File path escapes destination")
    return result


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


_TRANSPORT_ERRORS = (OSError, TimeoutError, websocket.WebSocketException, BridgeError)


class PikPakClientDownloader(Downloader):
    name = "pikpak_client"
    accepts = frozenset({"magnet"})

    def __init__(self, config, bridge_factory=None):
        super().__init__(config)
        self.bridge_factory = bridge_factory or (lambda: PikPakBridge(
            port=self.config.get("port", 19223),
            modules=self.config.get("modules"), exports=self.config.get("exports")))
        self.bridge = None
        self.instance = None  # id of the running client launch, refreshed every poll

    def health(self):
        bridge = self.bridge_factory()
        try:
            info = {"version": bridge.version().get("User-Agent", "")}
            bridge.connect()
            info["modules"] = bridge.probe()
            info["ok"] = all(v is True for v in info["modules"].values())
            return info
        except _TRANSPORT_ERRORS as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            bridge.close()

    @contextmanager
    def connection(self):
        bridge = self.bridge_factory()
        try:
            bridge.connect()
            self.instance = bridge.instance_id()
        except _TRANSPORT_ERRORS as exc:
            bridge.close()
            raise TransientError(f"PikPak client unreachable: {exc}") from exc
        self.bridge = bridge
        try:
            yield self
        finally:
            self.bridge = None
            bridge.close()

    def advance(self, job: JobSpec, state, checkpoint):
        try:
            self._advance(job, state, checkpoint)
        except _TRANSPORT_ERRORS as exc:
            # Safe to retry: any mutation was checkpointed first, and an uncertain
            # submission is detected on the next poll (cloud_submitting / local_submitting).
            raise TransientError(f"{type(exc).__name__}: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise NeedsAttention(f"{type(exc).__name__}: {exc}") from exc
        return self._status(state)

    @staticmethod
    def _status(state):
        # progress is the current stage's own percentage (state["phase"] says which stage):
        # the cloud stage is often instant (cached), so a combined 0-50/50-100 bar was misleading.
        phase = state.get("phase", "new")
        if phase == "done":
            return Status("done", 100.0, "下载完成")
        if phase == "failed":
            return Status("failed", 0.0, state.get("error", "failed"))
        if phase in ("new", "cloud_submitting", "cloud_waiting"):
            cloud = float(state.get("cloud_progress") or 0)
            return Status("running", cloud, f"云端下载 {cloud:.0f}%")
        local = float(state.get("local_progress") or 0)
        message = (f"本地下载 {local:.0f}%（{state.get('local_completed', 0)}/{state.get('local_total', 0)} 个文件）"
                   f" {state.get('wait_reason') or ''}").strip()
        return Status("running", local, message)

    def _advance(self, job, state, checkpoint):
        bridge = self.bridge
        phase = state.setdefault("phase", "new")
        if phase in ("done", "failed"):
            return
        if phase in ("new", "cloud_submitting"):
            task = bridge.find_cloud_task(job.url)
            if task is None:
                if phase == "cloud_submitting":
                    raise NeedsAttention("Previous cloud submission outcome is unknown; check the PikPak "
                                         "cloud task list, then retry from scratch or mark it handled")
                state["phase"] = "cloud_submitting"
                checkpoint()
                response = bridge.add_cloud_task(job.url)
                task = (response or {}).get("task")
                if not task or not task.get("id"):
                    raise NeedsAttention("Cloud submission returned no task ID; do not submit again blindly")
            state.update(phase="cloud_waiting", cloud_task_id=task["id"])
            checkpoint()

        if state["phase"] == "cloud_waiting":
            task = bridge.get_cloud_task(state["cloud_task_id"])
            state["cloud_progress"] = task.get("progress", 0)
            state["cloud_status"] = task.get("phase")
            if task.get("phase") == "PHASE_TYPE_ERROR":
                state.update(phase="failed", error=task.get("message", "Cloud download failed"))
            elif task.get("phase") == "PHASE_TYPE_COMPLETE":
                file_id = task.get("file_id")
                if not file_id:
                    raise NeedsAttention("Completed cloud task has no file ID")
                files = bridge.expand_files(file_id)
                if not files:
                    raise NeedsAttention("No downloadable files found in the cloud task")
                state.update(phase="local_ready", file_id=file_id, files=files)
            checkpoint()
            if state["phase"] != "local_ready":
                return

        files = state["files"]
        tasks = bridge.local_tasks([f["id"] for f in files])
        by_path = {(t["file_id"], _norm(t["path"])): t for t in tasks}
        complete, missing, active, downloaded_bytes = 0, [], [], 0
        for file in files:
            target = expected_path(job.destination, file)
            task = by_path.get((file["id"], _norm(target)))
            exists = target.is_file()
            correct_size = exists and target.stat().st_size == int(file["size"])
            if correct_size and (not task or task["status"] == "COMPLETED"):
                # Existing same-size file without a task: the official client uses this rule too.
                complete += 1
                downloaded_bytes += int(file["size"])
                continue
            if task:
                if task["status"] in ("FAILED", "UNKNOWN"):
                    state.update(phase="failed", error=f"Local task {task['id']}: {task['status']}")
                    checkpoint()
                    return
                if task["status"] == "COMPLETED":
                    raise NeedsAttention(f"Completed task has missing/wrong-size output: {target}")
                active.append(task)
                downloaded_bytes += min(int(file["size"]), max(0, task.get("downloaded", 0)))
                continue
            if exists:
                raise NeedsAttention(f"Refusing to overwrite existing different-size file: {target}")
            conflict = next((t for t in tasks if t["file_id"] == file["id"]
                             and t["status"] in ("PENDING", "DOWNLOADING", "PAUSED")), None)
            if conflict:
                # Client deduplicates active downloads by file ID, even across directories.
                state.update(wait_reason="Same cloud file is downloading in another directory")
                checkpoint()
                return
            missing.append(file)

        # After a restart the client brings unfinished local tasks back paused. Resume those;
        # a pause made while the same client launch kept running was the user's, so leave it.
        paused = [t for t in active if t["status"] == "PAUSED"]
        if paused and state.get("client_instance") != self.instance:
            for task in paused:
                bridge.start_local_task(task["id"])
                task["status"] = "PENDING"
            log.info("job %s: resumed %d local task(s) paused by a client restart", job.id, len(paused))
        state["client_instance"] = self.instance

        total_bytes = max(1, sum(int(f["size"]) for f in files))
        state.update(local_completed=complete, local_total=len(files),
                     local_progress=round(downloaded_bytes / total_bytes * 100, 2),
                     local_task_ids=[t["id"] for t in active],
                     bytes_per_second=sum(t.get("speed", 0) or 0 for t in active), wait_reason="")
        if complete == len(files):
            state.update(phase="done", finished_at=time.time())
        elif missing:
            if state["phase"] in ("local_submitting", "local_waiting"):
                raise NeedsAttention("Local task missing after submission; check the PikPak client "
                                     "before retrying to avoid duplicates")
            for file in missing:
                expected_path(job.destination, file).parent.mkdir(parents=True, exist_ok=True)
            # Fail before the checkpoint if the client can't download at all (e.g. after an
            # update), so the job isn't left looking like an uncertain submission.
            bridge.ensure_module("download_action")
            state["phase"] = "local_submitting"
            checkpoint()
            bridge.download_files(missing, job.destination)
            state["phase"] = "local_waiting"
        else:
            state["phase"] = "local_waiting"
            if any(t["status"] == "PAUSED" for t in active):
                state["wait_reason"] = "已在 PikPak 中手动暂停，继续下载需在客户端里恢复"
        checkpoint()
