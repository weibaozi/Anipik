"""scan(): sources -> new episode jobs.  poll(): advance running jobs through their downloader.

Network I/O (feeds, torrents) never happens inside a write transaction, so the web API can
keep writing to the same SQLite database while a scan runs.
"""
import copy
import logging
import os
import re
import threading
import time
from datetime import datetime

from sqlalchemy import select

from .db import all_settings, get_setting, session_scope, set_setting
from .downloaders import JobSpec, NeedsAttention, TransientError, build_downloader
from .matcher import (info_hash_from_magnet, info_hash_from_torrent, magnet_from_hash, matches_filters,
                      normalize_magnet, parse_episode)
from .models import Episode, Job, Subscription
from .notifiers import build_notifiers, notify
from .sources import Http, SourceError, build_source

log = logging.getLogger(__name__)

ACTIVE_PHASES = ("pending", "running")


def destination_for(root, subscription):
    """save_dir is absolute, or relative to library_root and may hold subfolders ("26年10月/名字")."""
    save_dir = subscription.save_dir or subscription.name
    if os.path.isabs(save_dir):
        return os.path.normpath(save_dir)
    # Strip characters Windows rejects; trailing dots/spaces also removes "." and ".." parts.
    parts = [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p).rstrip(" .") for p in re.split(r"[\\/]+", save_dir)]
    parts = [p for p in parts if p]
    return os.path.join(root, *parts) if parts else root


def is_retryable(episode, max_attempts):
    return episode.status == "failed" and episode.attempts < max_attempts


class Scheduler:
    def __init__(self, session_factory, http=None, downloaders=None, notifiers=None):
        self.factory = session_factory
        self.http = http or Http()
        self._injected = dict(downloaders or {})  # name -> instance (tests); others built from settings
        self._downloaders = dict(self._injected)
        self._notifiers = notifiers
        self._outgoing = []  # (notifiers, message) sent after the poll transaction commits
        self._wake = threading.Event()
        self._scan_requested = threading.Event()
        self._stop = threading.Event()
        # Read by the web API; only this scheduler writes it.
        self.status = {"running": False, "scanning": False, "last_scan_at": None, "last_scan_queued": 0,
                       "last_scan_error": None, "next_scan_at": None, "backends": {}}

    # -- helpers -----------------------------------------------------------------
    def downloader(self, session, name):
        if name not in self._downloaders:
            self._downloaders[name] = build_downloader(name, get_setting(session, f"downloader.{name}", {}))
        return self._downloaders[name]

    def reload_downloaders(self):
        """Settings changed: rebuild downloader instances on next use."""
        self._downloaders = dict(self._injected)

    def notifiers(self, settings):
        return self._notifiers if self._notifiers is not None else build_notifiers(settings, self.factory)

    def _flush_notifications(self):
        outgoing, self._outgoing = self._outgoing, []
        for notifiers, message in outgoing:
            notify(notifiers, message)

    def resolve_magnet(self, release):
        if release.url.startswith("magnet:?"):
            return normalize_magnet(release.url)
        if release.info_hash:
            return magnet_from_hash(release.info_hash)
        return magnet_from_hash(info_hash_from_torrent(self.http.get(release.url)))

    # -- scan --------------------------------------------------------------------
    def scan(self, dry_run=False, subscription_ids=None):
        """Search enabled subscriptions' sources and queue jobs for new episodes."""
        with session_scope(self.factory) as session:
            settings = all_settings(session)
            downloader_name = settings["downloader"]
            self.downloader(session, downloader_name)  # fail early on an unknown name
            query = select(Subscription).where(Subscription.enabled).order_by(Subscription.id)
            if subscription_ids is not None:
                query = query.where(Subscription.id.in_(subscription_ids))
            inputs = [(sub.id, sub.name, [(b.source.name, b.source.kind, dict(b.source.config or {}), dict(b.params or {}))
                                          for b in sub.bindings if b.enabled and b.source.enabled])
                      for sub in session.scalars(query)]
        planned = []
        for sub_id, name, bindings in inputs:
            fetched = []
            for source_name, kind, config, params in bindings:
                try:
                    fetched.append((source_name, params, build_source(kind, config, self.http).search(params)))
                except SourceError as exc:
                    log.warning("%s / %s: %s", name, source_name, exc)
            planned += self._queue(sub_id, fetched, settings, downloader_name, dry_run)
        return planned

    def _queue(self, sub_id, fetched, settings, downloader_name, dry_run):
        max_attempts = int(settings["max_attempts"])
        with session_scope(self.factory) as session:
            sub = session.get(Subscription, sub_id)
            if sub is None:
                return []
            name, destination = sub.name, destination_for(settings["library_root"], sub)
            blocked = {e.number for e in sub.episodes if not is_retryable(e, max_attempts)}

        candidates = {}
        for source_name, params, releases in fetched:  # bindings in priority order
            for release in releases:  # feeds are newest first; first usable match per episode wins
                if not matches_filters(release.title, params.get("include"), params.get("exclude")):
                    continue
                number = parse_episode(release.title)
                if number is None or number in blocked or number in candidates:
                    continue
                try:
                    magnet = self.resolve_magnet(release)
                except Exception as exc:
                    log.warning("%s: cannot resolve %s: %s", name, release.url, exc)
                    continue
                if magnet:
                    candidates[number] = (source_name, release, magnet)

        planned = [{"subscription": name, "episode": n, "source": s, "title": r.title, "magnet": m,
                    "destination": destination} for n, (s, r, m) in sorted(candidates.items())]
        if dry_run or not candidates:
            return planned

        queued = []
        with session_scope(self.factory) as session:
            sub = session.get(Subscription, sub_id)
            if sub is None or not sub.enabled:
                return []
            episodes = {e.number: e for e in sub.episodes}
            for item in planned:
                number, (source_name, release, magnet) = item["episode"], candidates[item["episode"]]
                episode = episodes.get(number)
                if episode and not is_retryable(episode, max_attempts):
                    continue  # changed (e.g. marked in the web UI) while we were fetching
                if episode is None:
                    episode = Episode(subscription=sub, number=number, attempts=0)
                    session.add(episode)
                episode.status = "queued"
                episode.attempts += 1
                episode.release_title = release.title
                episode.source_name = source_name
                episode.info_hash = info_hash_from_magnet(magnet)
                session.add(Job(episode=episode, downloader=downloader_name, url=magnet,
                                destination=destination, phase="pending", state={}))
                log.info("queued %s #%d from %s: %s", name, number, source_name, release.title)
                queued.append(item)
        return queued

    # -- poll --------------------------------------------------------------------
    def poll(self):
        """Promote pending jobs into free slots, then advance every running job once."""
        try:
            self._poll()
        finally:
            # Outbox writes need their own transaction; doing them inside the poll session
            # would wait on the write lock this same thread holds.
            self._flush_notifications()

    def _poll(self):
        with session_scope(self.factory) as session:
            settings = all_settings(session)
            jobs = session.scalars(select(Job).where(Job.phase.in_(ACTIVE_PHASES)).order_by(Job.id)).all()
            running = [j for j in jobs if j.phase == "running"]
            free = max(0, int(settings["max_active_jobs"]) - len(running))
            for job in [j for j in jobs if j.phase == "pending"][:free]:
                job.phase, job.state = "running", {"phase": "new"}
                if job.episode:
                    job.episode.status = "downloading"
                running.append(job)
            session.commit()

            by_downloader = {}
            for job in running:
                by_downloader.setdefault(job.downloader, []).append(job)
            for name, group in by_downloader.items():
                downloader = self.downloader(session, name)
                try:
                    with downloader.connection():
                        self.status["backends"][name] = {"ok": True, "error": None, "at": time.time()}
                        for job in group:
                            self._advance(session, downloader, job, settings)
                except TransientError as exc:
                    # Backend down (e.g. PikPak closed overnight): not the jobs' fault, don't count it.
                    log.warning("%s: %s", name, exc)
                    self.status["backends"][name] = {"ok": False, "error": str(exc), "at": time.time()}
                    for job in group:
                        if job.phase == "running":
                            job.message = str(exc)
                    session.commit()

    def _advance(self, session, downloader, job, settings):
        state = copy.deepcopy(job.state or {})

        def checkpoint():
            job.state = copy.deepcopy(state)
            session.commit()

        try:
            status = downloader.advance(JobSpec(job.id, job.url, job.destination), state, checkpoint)
        except TransientError as exc:
            job.state = copy.deepcopy(state)
            job.transient_errors += 1
            job.error = str(exc)
            if job.transient_errors >= int(settings["max_transient_errors"]):
                self._finish(job, "needs_attention", f"gave up after {job.transient_errors} errors: {exc}", settings)
            session.commit()
            return
        except NeedsAttention as exc:
            job.state = copy.deepcopy(state)
            self._finish(job, "needs_attention", str(exc), settings)
            session.commit()
            return
        except Exception as exc:  # unknown: stop rather than risk a duplicate submission
            log.exception("job %s", job.id)
            job.state = copy.deepcopy(state)
            self._finish(job, "needs_attention", f"{type(exc).__name__}: {exc}", settings)
            session.commit()
            return
        job.state = copy.deepcopy(state)
        job.transient_errors, job.error = 0, None
        if status.message != job.message:
            log.info("job %s: %s (%.0f%%)", job.id, status.message, status.progress)
        job.progress, job.message = status.progress, status.message
        if status.state == "done":
            self._finish(job, "done", None, settings)
        elif status.state == "failed":
            self._finish(job, "failed", status.message, settings)
        session.commit()

    def _finish(self, job, phase, error, settings):
        job.phase, job.error, job.finished_at = phase, error, datetime.now()
        label = f"job {job.id}"
        if job.episode:
            job.episode.status = phase
            label = f"{job.episode.subscription.name} 第{job.episode.number}集"
        if phase == "done":
            job.progress = 100.0
            message = f"完成下载: {label}"
        elif phase == "failed":
            message = f"下载失败: {label}: {error}"
        else:
            message = f"需要处理: {label}: {error}"
        self._outgoing.append((self.notifiers(settings), message))

    # -- loop --------------------------------------------------------------------
    def request_scan(self):
        self._scan_requested.set()
        self._wake.set()

    def wake(self):
        """Poll now instead of waiting for poll_interval (e.g. after a retry)."""
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def _do_scan(self, sync):
        self.status["scanning"] = True
        started = time.time()
        log.info("scan started")
        try:
            if sync:
                sync()
            queued = self.scan()
            self.status.update(last_scan_queued=len(queued), last_scan_error=None)
            log.info("scan finished in %.1fs: %d new episode(s) queued", time.time() - started, len(queued))
        except Exception as exc:
            log.exception("scan failed")
            self.status["last_scan_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            self.status.update(scanning=False, last_scan_at=time.time())

    def run(self, once=False, sync=None):
        """Loop until stop(). sync: optional callable run before each scan (legacy YAML import)."""
        self.status["running"] = True
        last_scan = 0.0
        try:
            with session_scope(self.factory) as session:
                name = get_setting(session, "downloader")
                downloader = self.downloader(session, name)
            note = downloader.ensure_running()  # e.g. start the PikPak client with its debug port
            if note:
                log.info("%s: %s", name, note)
        except Exception:
            log.exception("could not prepare the downloader")
        try:
            while not self._stop.is_set():
                with session_scope(self.factory) as session:
                    settings = all_settings(session)
                    requested = bool(settings.get("scan_requested"))  # set by the CLI from another process
                    if requested:
                        set_setting(session, "scan_requested", False)
                requested = requested or self._scan_requested.is_set()
                self._scan_requested.clear()
                scan_interval = float(settings["scan_interval"])
                if once or requested or time.time() - last_scan >= scan_interval:
                    self._do_scan(sync)
                    last_scan = time.time()
                self.status["next_scan_at"] = last_scan + scan_interval
                try:
                    self.poll()
                except Exception:
                    log.exception("poll failed")
                if once:
                    return
                self._wake.wait(float(settings["poll_interval"]))
                self._wake.clear()
        finally:
            self.status["running"] = False
