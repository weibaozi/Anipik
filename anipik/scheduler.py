"""scan(): sources -> new episode jobs.  poll(): advance running jobs through their downloader."""
import copy
import logging
import os
import re
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
    folder = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", subscription.save_dir or subscription.name).rstrip(" .")
    return folder if os.path.isabs(folder) else os.path.join(root, folder)


class Scheduler:
    def __init__(self, session_factory, http=None, downloaders=None, notifiers=None):
        self.factory = session_factory
        self.http = http or Http()
        self._downloaders = downloaders or {}  # name -> instance; built from settings when missing
        self._notifiers = notifiers

    # -- helpers -----------------------------------------------------------------
    def downloader(self, session, name):
        if name not in self._downloaders:
            self._downloaders[name] = build_downloader(name, get_setting(session, f"downloader.{name}", {}))
        return self._downloaders[name]

    def notifiers(self, settings):
        return self._notifiers if self._notifiers is not None else build_notifiers(settings)

    def resolve_magnet(self, release):
        if release.url.startswith("magnet:?"):
            return normalize_magnet(release.url)
        if release.info_hash:
            return magnet_from_hash(release.info_hash)
        return magnet_from_hash(info_hash_from_torrent(self.http.get(release.url)))

    # -- scan --------------------------------------------------------------------
    def scan(self, dry_run=False):
        """Search every enabled subscription's sources and queue jobs for new episodes."""
        planned = []
        with session_scope(self.factory) as session:
            settings = all_settings(session)
            downloader_name = settings["downloader"]
            self.downloader(session, downloader_name)  # fail early on an unknown name
            max_attempts = int(settings["max_attempts"])
            subscriptions = session.scalars(select(Subscription).where(Subscription.enabled)).all()
            for subscription in subscriptions:
                episodes = {e.number: e for e in subscription.episodes}
                taken = set()
                for binding in subscription.bindings:
                    if not (binding.enabled and binding.source.enabled):
                        continue
                    params = binding.params or {}
                    try:
                        releases = build_source(binding.source, self.http).search(params)
                    except SourceError as exc:
                        log.warning("%s / %s: %s", subscription.name, binding.source.name, exc)
                        continue
                    for release in releases:  # feeds are newest first; first match per episode wins
                        if not matches_filters(release.title, params.get("include"), params.get("exclude")):
                            continue
                        number = parse_episode(release.title)
                        if number is None or number in taken:
                            continue
                        episode = episodes.get(number)
                        if episode and not (episode.status == "failed" and episode.attempts < max_attempts):
                            continue
                        try:
                            magnet = self.resolve_magnet(release)
                        except Exception as exc:
                            log.warning("%s: cannot resolve %s: %s", subscription.name, release.url, exc)
                            continue
                        if magnet is None:
                            continue
                        taken.add(number)
                        destination = destination_for(settings["library_root"], subscription)
                        planned.append({"subscription": subscription.name, "episode": number,
                                        "source": binding.source.name, "title": release.title,
                                        "magnet": magnet, "destination": destination})
                        if dry_run:
                            continue
                        if episode is None:
                            episode = Episode(subscription=subscription, number=number, attempts=0)
                            session.add(episode)
                            episodes[number] = episode
                        episode.status = "queued"
                        episode.attempts += 1
                        episode.release_title = release.title
                        episode.source_name = binding.source.name
                        episode.info_hash = info_hash_from_magnet(magnet)
                        session.add(Job(episode=episode, downloader=downloader_name, url=magnet,
                                        destination=destination, phase="pending", state={}))
                        log.info("queued %s #%d from %s: %s", subscription.name, number,
                                 binding.source.name, release.title)
            if dry_run:
                session.rollback()
        return planned

    # -- poll --------------------------------------------------------------------
    def poll(self):
        """Promote pending jobs into free slots, then advance every running job once."""
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
                        for job in group:
                            self._advance(session, downloader, job, settings)
                except TransientError as exc:
                    # Backend down (e.g. PikPak closed overnight): not the jobs' fault, don't count it.
                    log.warning("%s: %s", name, exc)
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
        notify(self.notifiers(settings), message)

    # -- loop --------------------------------------------------------------------
    def run(self, once=False, sync=None):
        """sync: optional callable run before each scan (legacy YAML import)."""
        last_scan = 0.0
        while True:
            with session_scope(self.factory) as session:
                settings = all_settings(session)
                requested = bool(settings.get("scan_requested"))
                if requested:
                    set_setting(session, "scan_requested", False)
            if once or requested or time.time() - last_scan >= float(settings["scan_interval"]):
                if sync:
                    sync()
                try:
                    self.scan()
                except Exception:
                    log.exception("scan failed")
                last_scan = time.time()
            self.poll()
            if once:
                return
            time.sleep(float(settings["poll_interval"]))
