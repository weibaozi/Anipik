from contextlib import contextmanager

import pytest
from sqlalchemy import select

from anipik.db import session_scope, set_setting
from anipik.downloaders import Downloader, NeedsAttention, Status, TransientError
from anipik.models import Episode, Job, Source, SourceBinding, Subscription
from anipik.scheduler import Scheduler
from anipik.sources import SOURCE_KINDS, Release, SourceKind

H1, H2, H3 = "1" * 40, "2" * 40, "3" * 40
FEEDS = {}


class FakeSource(SourceKind):
    kind = "fake"

    def search(self, params):
        return FEEDS[params["feed"]]


class ScriptedDownloader(Downloader):
    """advance() pops the next scripted outcome for the job's URL."""
    name = "scripted"

    def __init__(self):
        super().__init__({})
        self.script, self.calls, self.reachable = {}, [], True

    @contextmanager
    def connection(self):
        if not self.reachable:
            raise TransientError("down")
        yield self

    def advance(self, job, state, checkpoint):
        self.calls.append(job.url)
        outcome = self.script[job.url].pop(0)
        state["ticks"] = state.get("ticks", 0) + 1
        checkpoint()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    monkeypatch.setitem(SOURCE_KINDS, "fake", FakeSource)
    FEEDS.clear()


@pytest.fixture
def setup(factory, tmp_path):
    with session_scope(factory) as s:
        set_setting(s, "downloader", "scripted")
        set_setting(s, "library_root", str(tmp_path / "lib"))
        set_setting(s, "max_active_jobs", 2)
        primary, backup = Source(name="primary", kind="fake"), Source(name="backup", kind="fake")
        sub = Subscription(name="Show", save_dir="Show")
        sub.bindings = [SourceBinding(source=primary, priority=0, params={"feed": "p", "exclude": ["720"]}),
                        SourceBinding(source=backup, priority=1, params={"feed": "b"})]
        sub.episodes = [Episode(number=1, status="done", attempts=0)]
        s.add(sub)
    downloader = ScriptedDownloader()
    return Scheduler(factory, http=None, downloaders={"scripted": downloader}, notifiers=[]), downloader


def jobs(factory):
    with session_scope(factory) as s:
        return [(j.episode.number, j.phase, j.url[-40:], j.state) for j in s.scalars(select(Job).order_by(Job.id))]


def episodes(factory):
    with session_scope(factory) as s:
        return {e.number: (e.status, e.attempts, e.source_name) for e in s.scalars(select(Episode))}


def test_scan_dedupes_and_respects_priority_and_filters(setup, factory):
    scheduler, _ = setup
    FEEDS["p"] = [Release("[A] Show - 03 [720p]", f"magnet:?xt=urn:btih:{H3}"),   # excluded
                  Release("[A] Show - 02 [1080p]", f"magnet:?xt=urn:btih:{H2}"),
                  Release("[A] Show - 02 [1080p] dup", f"magnet:?xt=urn:btih:{'f' * 40}"),
                  Release("[A] Show - 01 [1080p]", f"magnet:?xt=urn:btih:{H1}"),  # already done
                  Release("[A] Show [01-12] Batch", f"magnet:?xt=urn:btih:{'e' * 40}")]
    FEEDS["b"] = [Release("[B] Show - 03 [1080p]", "https://b/3.torrent", info_hash=H3),
                  Release("[B] Show - 02 [1080p]", f"magnet:?xt=urn:btih:{'d' * 40}")]
    assert [p["episode"] for p in scheduler.scan(dry_run=True)] == [2, 3]
    assert jobs(factory) == []  # dry run wrote nothing

    planned = scheduler.scan()
    assert [(p["episode"], p["source"]) for p in planned] == [(2, "primary"), (3, "backup")]
    assert [(n, phase, h) for n, phase, h, _ in jobs(factory)] == [(2, "pending", H2), (3, "pending", H3)]
    assert planned[0]["destination"].endswith("Show")
    assert scheduler.scan() == []  # queued episodes are not queued again


def test_poll_lifecycle_slots_and_retry(setup, factory):
    scheduler, downloader = setup
    FEEDS["p"] = [Release(f"[A] Show - 0{n}", f"magnet:?xt=urn:btih:{h}") for n, h in ((2, H2), (3, H3), (4, H1))]
    FEEDS["b"] = []
    scheduler.scan()
    url = {n: f"magnet:?xt=urn:btih:{h}" for n, h in ((2, H2), (3, H3), (4, H1))}
    downloader.script = {url[2]: [Status("running", 10), Status("done", 100)],
                         url[3]: [Status("failed", 0, "cloud error")],
                         url[4]: [NeedsAttention("unknown submission")]}

    scheduler.poll()  # max_active_jobs=2: episode 4 waits
    assert [(n, p) for n, p, _, _ in jobs(factory)] == [(2, "running"), (3, "failed"), (4, "pending")]
    assert jobs(factory)[0][3] == {"phase": "new", "ticks": 1}  # checkpoint persisted downloader state

    scheduler.poll()
    assert [(n, p) for n, p, _, _ in jobs(factory)] == [(2, "done"), (3, "failed"), (4, "needs_attention")]
    eps = episodes(factory)
    assert eps[2][0] == "done" and eps[3][:2] == ("failed", 1) and eps[4][0] == "needs_attention"

    # failed episodes are retried on the next scan (up to max_attempts); needs_attention is left alone
    planned = scheduler.scan()
    assert [p["episode"] for p in planned] == [3]
    assert episodes(factory)[3][:2] == ("queued", 2)


def test_backend_down_does_not_count_against_jobs(setup, factory):
    scheduler, downloader = setup
    FEEDS["p"], FEEDS["b"] = [Release("[A] Show - 02", f"magnet:?xt=urn:btih:{H2}")], []
    scheduler.scan()
    downloader.reachable = False
    for _ in range(3):
        scheduler.poll()
    with session_scope(factory) as s:
        job = s.scalar(select(Job))
        assert (job.phase, job.transient_errors, job.message) == ("running", 0, "down")
    downloader.reachable = True
    downloader.script = {job.url: [TransientError("blip"), Status("done")]}
    scheduler.poll()
    with session_scope(factory) as s:
        assert s.scalar(select(Job)).transient_errors == 1
    scheduler.poll()
    with session_scope(factory) as s:
        job = s.scalar(select(Job))
        assert (job.phase, job.transient_errors) == ("done", 0)


def test_destination_for_subfolders_and_absolute():
    from types import SimpleNamespace as NS
    from anipik.scheduler import destination_for
    assert destination_for(r"N:\新番", NS(save_dir="26年10月/Show: S2?", name="x")) == r"N:\新番\26年10月\Show_ S2_"
    assert destination_for(r"N:\新番", NS(save_dir="../../escape", name="x")) == r"N:\新番\escape"
    assert destination_for(r"N:\新番", NS(save_dir=None, name="Show")) == r"N:\新番\Show"
    assert destination_for(r"N:\新番", NS(save_dir="D:/Other/Show", name="x")) == r"D:\Other\Show"
