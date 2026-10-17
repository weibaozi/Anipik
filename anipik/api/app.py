"""HTTP API (/api) + the built web UI. Sync handlers: FastAPI runs them in a thread pool."""
import logging
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .. import bangumi, config, discord_bot
from ..config import DEFAULT_SETTINGS
from ..db import all_settings, session_scope, set_setting
from ..downloaders import DOWNLOADERS, build_downloader
from ..matcher import is_batch, matches_filters, parse_episode
from ..models import Episode, Job, Source, SourceBinding, Subscription
from ..scheduler import destination_for
from ..sources import SOURCE_KINDS, Http, SourceError, build_source
from .schemas import (EpisodesPatch, JobAction, PreviewIn, SourceIn, SourcePatch, SubscriptionIn,
                      SubscriptionPatch)

log = logging.getLogger(__name__)
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
ACTIVE = ("pending", "running")
EDITABLE_SETTINGS = set(DEFAULT_SETTINGS)
_GROUP = re.compile(r"^\s*[\[【]([^\]】]+)[\]】]")


def _ts(value):
    return value.isoformat(timespec="seconds") if isinstance(value, datetime) else value


# -- serializers ---------------------------------------------------------------------
def job_out(job):
    state = job.state or {}
    episode = job.episode
    sub = episode.subscription if episode else None
    return {
        "id": job.id, "phase": job.phase, "progress": round(job.progress or 0, 1), "message": job.message,
        "error": job.error, "downloader": job.downloader, "destination": job.destination, "url": job.url,
        "backend_phase": state.get("phase"), "speed": state.get("bytes_per_second"),
        "files_done": state.get("local_completed"), "files_total": state.get("local_total"),
        "created_at": _ts(job.created_at), "updated_at": _ts(job.updated_at), "finished_at": _ts(job.finished_at),
        "episode": episode.number if episode else None,
        "release_title": episode.release_title if episode else None,
        "subscription": {"id": sub.id, "name": sub.name, "cover_url": sub.cover_url} if sub else None,
    }


def binding_out(binding):
    params = binding.params or {}
    return {"id": binding.id, "source_id": binding.source_id, "source_name": binding.source.name,
            "priority": binding.priority, "enabled": binding.enabled, "keywords": params.get("keywords", []),
            "include": params.get("include", []), "exclude": params.get("exclude", [])}


def subscription_out(sub, detail=False, root=None):
    counts = {}
    for episode in sub.episodes:
        counts[episode.status] = counts.get(episode.status, 0) + 1
    done = [e.number for e in sub.episodes if e.status == "done"]
    active = [j for e in sub.episodes for j in e.jobs if j.phase in ACTIVE]
    out = {
        "id": sub.id, "name": sub.name, "enabled": sub.enabled, "save_dir": sub.save_dir,
        "bangumi_id": sub.bangumi_id, "original_name": sub.original_name, "cover_url": sub.cover_url,
        "air_date": sub.air_date, "total_episodes": sub.total_episodes,
        "sources": [b.source.name for b in sub.bindings if b.enabled],
        "counts": counts, "latest_done": max(done) if done else None,
        "active_jobs": len(active),
        "active_progress": round(sum(j.progress or 0 for j in active) / len(active), 1) if active else None,
        "updated_at": _ts(sub.updated_at),
    }
    if detail:
        latest_job = {}
        for episode in sub.episodes:
            if episode.jobs:
                latest_job[episode.number] = job_out(episode.jobs[-1])
        out.update(
            summary=sub.summary,
            destination=destination_for(root, sub) if root else None,
            bindings=[binding_out(b) for b in sub.bindings],
            episodes=[{"number": e.number, "status": e.status, "attempts": e.attempts,
                       "release_title": e.release_title, "source_name": e.source_name,
                       "updated_at": _ts(e.updated_at), "job": latest_job.get(e.number)} for e in sub.episodes],
        )
    return out


def source_out(source, binding_count=0):
    return {"id": source.id, "name": source.name, "kind": source.kind, "config": source.config or {},
            "enabled": source.enabled, "subscriptions": binding_count}


# -- app -----------------------------------------------------------------------------
def create_app(factory, scheduler=None, run_scheduler=False, sync=None, bot=None):
    """scheduler: shared Scheduler (for status / scan requests). run_scheduler: run its loop in a thread.
    bot: DiscordBot to run in this process (only where the scheduler runs, so messages go out once)."""
    http = Http(retries=1, timeout=20)
    thread_holder = {}

    def request_scan():
        if scheduler is not None and run_scheduler:
            scheduler.request_scan()
        else:
            with session_scope(factory) as session:  # picked up by a scheduler in another process
                set_setting(session, "scan_requested", True)

    if bot is not None and bot.on_scan is None:
        bot.on_scan = request_scan

    @asynccontextmanager
    async def lifespan(_app):
        if scheduler is not None and run_scheduler:
            thread = threading.Thread(target=scheduler.run, kwargs={"sync": sync}, name="scheduler", daemon=True)
            thread.start()
            thread_holder["thread"] = thread
        if bot is not None:
            bot.apply()
        yield
        if bot is not None:
            bot.stop()
        if "thread" in thread_holder:
            scheduler.stop()
            thread_holder["thread"].join(timeout=10)

    app = FastAPI(title="Anipik", lifespan=lifespan)
    api = APIRouter(prefix="/api")

    def get_or_404(session, model, object_id):
        obj = session.get(model, object_id)
        if obj is None:
            raise HTTPException(404, f"{model.__name__} {object_id} not found")
        return obj

    def wake():
        if scheduler is not None:
            scheduler.wake()

    # -- status --------------------------------------------------------------------
    @api.get("/status")
    def status():
        with session_scope(factory) as session:
            settings = all_settings(session)
            jobs = dict(session.execute(select(Job.phase, func.count()).group_by(Job.phase)).all())
            subs = session.scalar(select(func.count()).select_from(Subscription).where(Subscription.enabled))
        sched = dict(scheduler.status) if scheduler is not None else {"running": False}
        return {"scheduler": sched, "scheduler_in_process": scheduler is not None and run_scheduler,
                "downloader": settings["downloader"], "jobs": jobs, "subscriptions": subs, "db": str(config.DB_PATH)}

    @api.post("/scan")
    def scan_now():
        request_scan()
        return {"requested": True}

    # -- subscriptions -------------------------------------------------------------
    def apply_bindings(session, sub, bindings):
        sources = {s.id for s in session.scalars(select(Source))}
        missing = [b.source_id for b in bindings if b.source_id not in sources]
        if missing:
            raise HTTPException(422, f"unknown source ids {missing}")
        if len({b.source_id for b in bindings}) != len(bindings):
            raise HTTPException(422, "a source can be bound only once per subscription")
        sub.bindings.clear()
        session.flush()
        for priority, b in enumerate(bindings):
            sub.bindings.append(SourceBinding(
                source_id=b.source_id, priority=priority, enabled=b.enabled,
                params={"keywords": [k.strip() for k in b.keywords if k.strip()],
                        "include": [p for p in b.include if p], "exclude": [p for p in b.exclude if p]}))

    def check_name(session, name, current_id=None):
        other = session.scalar(select(Subscription).where(Subscription.name == name))
        if other is not None and other.id != current_id:
            raise HTTPException(409, f"subscription {name!r} already exists")

    @api.get("/subscriptions")
    def list_subscriptions():
        with session_scope(factory) as session:
            subs = session.scalars(select(Subscription).order_by(Subscription.enabled.desc(),
                                                                 Subscription.updated_at.desc())).all()
            return [subscription_out(s) for s in subs]

    @api.post("/subscriptions", status_code=201)
    def create_subscription(body: SubscriptionIn):
        with session_scope(factory) as session:
            check_name(session, body.name)
            data = body.model_dump(exclude={"bindings", "start_episode"})
            data["save_dir"] = data.get("save_dir") or body.name
            sub = Subscription(**data)
            session.add(sub)
            session.flush()
            apply_bindings(session, sub, body.bindings)
            for number in range(1, (body.start_episode or 1)):
                session.add(Episode(subscription=sub, number=number, status="skipped", attempts=0))
            session.flush()
            session.refresh(sub)
            result = subscription_out(sub, detail=True, root=all_settings(session)["library_root"])
        if scheduler is not None and run_scheduler and body.enabled:
            scheduler.request_scan()
        return result

    @api.get("/subscriptions/{sub_id}")
    def get_subscription(sub_id: int):
        with session_scope(factory) as session:
            sub = get_or_404(session, Subscription, sub_id)
            return subscription_out(sub, detail=True, root=all_settings(session)["library_root"])

    @api.patch("/subscriptions/{sub_id}")
    def update_subscription(sub_id: int, body: SubscriptionPatch):
        with session_scope(factory) as session:
            sub = get_or_404(session, Subscription, sub_id)
            data = body.model_dump(exclude_unset=True, exclude={"bindings"})
            if "name" in data:
                check_name(session, data["name"], sub.id)
            for key, value in data.items():
                setattr(sub, key, value)
            if body.bindings is not None:
                apply_bindings(session, sub, body.bindings)
            sub.updated_at = datetime.now()
            session.flush()
            session.refresh(sub)
            return subscription_out(sub, detail=True, root=all_settings(session)["library_root"])

    @api.delete("/subscriptions/{sub_id}", status_code=204)
    def delete_subscription(sub_id: int):
        with session_scope(factory) as session:
            sub = get_or_404(session, Subscription, sub_id)
            jobs = [j for e in sub.episodes for j in e.jobs]
            if any(j.phase in ACTIVE for j in jobs):
                raise HTTPException(409, "subscription has active downloads; wait for them to finish")
            for job in jobs:
                session.delete(job)
            session.flush()
            session.delete(sub)

    @api.post("/subscriptions/{sub_id}/episodes")
    def mark_episodes(sub_id: int, body: EpisodesPatch):
        with session_scope(factory) as session:
            sub = get_or_404(session, Subscription, sub_id)
            existing = {e.number: e for e in sub.episodes}
            busy = [n for n in body.numbers if n in existing and any(j.phase in ACTIVE for j in existing[n].jobs)]
            if busy:
                raise HTTPException(409, f"episodes {busy} are downloading")
            for number in body.numbers:
                episode = existing.get(number)
                if body.status == "delete":
                    if episode is not None:
                        for job in episode.jobs:
                            job.episode = None  # keep the job history row
                        session.delete(episode)
                    continue
                if episode is None:
                    episode = Episode(subscription=sub, number=number, attempts=0)
                    session.add(episode)
                episode.status = body.status
            session.flush()
            session.refresh(sub)
            return subscription_out(sub, detail=True, root=all_settings(session)["library_root"])

    # -- sources -------------------------------------------------------------------
    @api.get("/sources")
    def list_sources():
        with session_scope(factory) as session:
            counts = dict(session.execute(select(SourceBinding.source_id, func.count())
                                          .group_by(SourceBinding.source_id)).all())
            return [source_out(s, counts.get(s.id, 0)) for s in session.scalars(select(Source).order_by(Source.id))]

    @api.get("/source-kinds")
    def source_kinds():
        return [{"kind": kind, "fields": list(cls.fields)} for kind, cls in SOURCE_KINDS.items()]

    @api.post("/sources", status_code=201)
    def create_source(body: SourceIn):
        if body.kind not in SOURCE_KINDS:
            raise HTTPException(422, f"unknown source kind {body.kind!r}")
        with session_scope(factory) as session:
            if session.scalar(select(Source).where(Source.name == body.name)):
                raise HTTPException(409, f"source {body.name!r} already exists")
            source = Source(**body.model_dump())
            session.add(source)
            session.flush()
            return source_out(source)

    @api.patch("/sources/{source_id}")
    def update_source(source_id: int, body: SourcePatch):
        with session_scope(factory) as session:
            source = get_or_404(session, Source, source_id)
            data = body.model_dump(exclude_unset=True)
            if "name" in data:
                other = session.scalar(select(Source).where(Source.name == data["name"]))
                if other is not None and other.id != source.id:
                    raise HTTPException(409, f"source {data['name']!r} already exists")
            for key, value in data.items():
                setattr(source, key, value)
            session.flush()
            count = session.scalar(select(func.count()).select_from(SourceBinding)
                                   .where(SourceBinding.source_id == source.id))
            return source_out(source, count)

    @api.delete("/sources/{source_id}", status_code=204)
    def delete_source(source_id: int):
        with session_scope(factory) as session:
            source = get_or_404(session, Source, source_id)
            used = session.scalars(select(SourceBinding).where(SourceBinding.source_id == source.id)).all()
            if used:
                names = ", ".join(b.subscription.name for b in used)
                raise HTTPException(409, f"source is used by: {names}")
            session.delete(source)

    @api.post("/sources/preview")
    def preview(body: PreviewIn):
        """Run a search without saving anything; shows how titles parse and filter."""
        with session_scope(factory) as session:
            if body.source_id is not None:
                source = get_or_404(session, Source, body.source_id)
                kind, config = source.kind, dict(source.config or {})
            elif body.config is not None:
                kind, config = body.kind, body.config
            else:
                raise HTTPException(422, "give source_id or config")
            statuses = {}
            if body.subscription_id is not None:
                sub = get_or_404(session, Subscription, body.subscription_id)
                statuses = {e.number: e.status for e in sub.episodes}
        params = {"keywords": body.keywords}
        try:
            source_kind = build_source(kind, config, http)
            url = getattr(source_kind, "search_url", lambda p: None)(params)
            releases = source_kind.search(params)
        except SourceError as exc:
            raise HTTPException(502, str(exc))
        try:
            items = []
            for r in releases:
                episode = parse_episode(r.title)
                group = _GROUP.match(r.title)
                items.append({"title": r.title, "episode": episode, "batch": is_batch(r.title),
                              "matched": matches_filters(r.title, body.include, body.exclude),
                              "group": group.group(1).strip() if group else None,
                              "published": r.published, "page_link": r.page_link,
                              "status": statuses.get(episode) if episode is not None else None})
        except re.error as exc:
            raise HTTPException(422, f"invalid regex: {exc}")
        return {"url": url, "count": len(items), "items": items}

    # -- jobs ----------------------------------------------------------------------
    @api.get("/jobs")
    def list_jobs(view: str = Query("active", pattern="^(active|attention|history|all)$"),
                  limit: int = Query(100, ge=1, le=1000)):
        phases = {"active": ACTIVE, "attention": ("needs_attention",),
                  "history": ("done", "failed", "cancelled")}.get(view)
        with session_scope(factory) as session:
            query = select(Job)
            if phases:
                query = query.where(Job.phase.in_(phases))
            order = Job.id.asc() if view == "active" else Job.updated_at.desc()
            return [job_out(j) for j in session.scalars(query.order_by(order).limit(limit))]

    @api.post("/jobs/{job_id}")
    def job_action(job_id: int, body: JobAction):
        with session_scope(factory) as session:
            job = get_or_404(session, Job, job_id)
            if job.phase not in ("needs_attention", "failed"):
                raise HTTPException(409, f"job is {job.phase}; only failed / needs_attention jobs can be changed")
            if body.action in ("retry", "retry_from_scratch"):
                job.phase, job.error, job.transient_errors, job.finished_at = "running", None, 0, None
                if body.action == "retry_from_scratch":
                    job.state, job.progress = {"phase": "new"}, 0.0
                episode_status = "downloading"
            elif body.action == "mark_done":
                job.phase, job.finished_at, job.progress = "done", datetime.now(), 100.0
                job.message = "marked done by hand"
                episode_status = "done"
            else:
                job.phase, job.finished_at, job.message = "cancelled", datetime.now(), "abandoned by hand"
                episode_status = "skipped"
            if job.episode:
                job.episode.status = episode_status
            session.flush()
            result = job_out(job)
        wake()
        return result

    # -- settings / backend --------------------------------------------------------
    def public_settings(values):
        out = {k: v for k, v in values.items() if k in EDITABLE_SETTINGS}
        # Never echo the bot token; the form sends "" to keep it unchanged.
        out["notify.discord.token_set"] = bool(out.get("notify.discord.token"))
        out["notify.discord.token"] = ""
        return out

    @api.get("/settings")
    def get_settings():
        with session_scope(factory) as session:
            values = all_settings(session)
        return public_settings(values)

    @api.patch("/settings")
    def patch_settings(body: dict):
        body.pop("notify.discord.token_set", None)
        if body.get("notify.discord.token") == "":
            body.pop("notify.discord.token")
        unknown = sorted(set(body) - EDITABLE_SETTINGS)
        if unknown:
            raise HTTPException(422, f"unknown settings: {unknown}")
        for key, value in body.items():
            default = DEFAULT_SETTINGS[key]
            if isinstance(default, bool) != isinstance(value, bool) or \
                    (isinstance(default, (int, float)) and not isinstance(value, (int, float))) or \
                    (isinstance(default, (str, dict)) and not isinstance(value, type(default))):
                raise HTTPException(422, f"{key}: expected {type(default).__name__}")
        if "downloader" in body and body["downloader"] not in DOWNLOADERS:
            raise HTTPException(422, f"unknown downloader {body['downloader']!r}")
        with session_scope(factory) as session:
            for key, value in body.items():
                set_setting(session, key, value)
            values = all_settings(session)
        if scheduler is not None:
            scheduler.reload_downloaders()
            scheduler.wake()
        if bot is not None:
            bot.apply(values)
        return public_settings(values)

    def current_downloader():
        with session_scope(factory) as session:
            settings = all_settings(session)
        name = settings["downloader"]
        return name, build_downloader(name, settings.get(f"downloader.{name}", {}))

    @api.get("/downloader/health")
    def downloader_health():
        name, downloader = current_downloader()
        return {"downloader": name, **downloader.health()}

    @api.post("/downloader/start")
    def downloader_start():
        """Start the backend if it isn't running (no-op when it already is)."""
        _, downloader = current_downloader()
        note = downloader.ensure_running()
        wake()
        return {"message": note or "已在运行"}

    @api.post("/downloader/restart")
    def downloader_restart():
        """Exit and relaunch the client with its debug port; paused downloads resume on the next poll."""
        _, downloader = current_downloader()
        if not hasattr(downloader, "restart"):
            raise HTTPException(422, "this downloader cannot be restarted")
        try:
            downloader.restart()
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        wake()
        return {"message": "已重启，等待客户端登录"}

    # -- discord bot ---------------------------------------------------------------
    @api.get("/notify/discord")
    def discord_status():
        status = dict(bot.status) if bot is not None else {"state": "not_in_process", "user": None, "error": None}
        return {"status": status, "outbox": discord_bot.outbox_summary(factory),
                "legacy_token": bool(discord_bot.legacy_token())}

    @api.post("/notify/discord/test")
    def discord_test():
        discord_bot.enqueue_test(factory)
        return {"queued": True}

    # -- metadata ------------------------------------------------------------------
    @api.get("/bangumi/search")
    def bangumi_search(q: str = Query(min_length=1)):
        try:
            return bangumi.search(q)
        except Exception as exc:
            raise HTTPException(502, f"bgm.tv: {exc}")

    @api.get("/bangumi/subject/{subject_id}")
    def bangumi_subject(subject_id: int):
        try:
            return bangumi.subject(subject_id)
        except Exception as exc:
            raise HTTPException(502, f"bgm.tv: {exc}")

    app.include_router(api)

    # -- web UI --------------------------------------------------------------------
    if WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            file = (WEB_DIST / path).resolve()
            if path and file.is_file() and file.is_relative_to(WEB_DIST):
                return FileResponse(file)
            return FileResponse(WEB_DIST / "index.html")
    return app
