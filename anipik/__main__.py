"""python -m anipik <command>

  migrate            import the legacy old/anime_rss.yaml + old/setting.yaml (re-runnable)
  scan [--dry-run]   search sources now and queue new episodes
  serve              web UI + API on http://127.0.0.1:8964, with the scheduler in-process
  run                scheduler loop only (scan every scan_interval, poll every poll_interval)
  status             subscriptions, active and attention-needing jobs
  probe              check the downloader backend (read-only)
  retry JOB          resume a needs_attention/failed job (--from-scratch resets its state)
  add-source NAME    add an rss_search source (--prefix, --sep, --suffix)
  subscribe NAME     add an anime bound to a source (--source, --keywords, --include, --exclude)
  mark SUB EP...     set episodes done/skipped by hand, or forget them (--status delete)
  set KEY VALUE      change a setting (VALUE parsed as JSON when possible)
  settings           show effective settings
"""
import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import func, select

from . import config
from .db import all_settings, make_session_factory, session_scope, set_setting
from .downloaders import build_downloader
from .migrate import migrate
from .models import Episode, Job, Source, SourceBinding, Subscription
from .scheduler import Scheduler


@contextmanager
def single_instance(path):
    """OS lock released on crash; prevents two schedulers submitting the same jobs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def lock_path():
    return config.DB_PATH.with_suffix(".lock")


def cmd_migrate(factory, args):
    with session_scope(factory) as session:
        stats = migrate(session, args.rss, args.setting)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_scan(factory, args):
    if not args.dry_run:
        with single_instance(lock_path()) as acquired:
            if not acquired:
                with session_scope(factory) as session:
                    set_setting(session, "scan_requested", True)
                print("Scheduler is running; asked it to scan on its next poll.")
                return
            planned = Scheduler(factory).scan()
    else:
        planned = Scheduler(factory).scan(dry_run=True)
    for item in planned:
        print(f"{'would queue' if args.dry_run else 'queued'} {item['subscription']} #{item['episode']} "
              f"[{item['source']}] {item['title']}\n    -> {item['destination']}")
    print(f"{len(planned)} episode(s)")


def cmd_run(factory, args):
    from .discord_bot import DiscordBot

    with single_instance(lock_path()) as acquired:
        if not acquired:
            sys.exit("Another scheduler is already running for this database")
        scheduler = Scheduler(factory)
        bot = DiscordBot(factory, on_scan=scheduler.request_scan)
        bot.apply()  # starts when notify.discord is enabled and a token is configured
        try:
            scheduler.run(once=args.once)
        except KeyboardInterrupt:
            print("Stopped. Downloads already handed to the backend continue; rerun to resume.")
        finally:
            bot.stop()


def cmd_serve(factory, args):
    import uvicorn

    from .api import create_app
    from .discord_bot import DiscordBot

    with single_instance(lock_path()) as acquired:
        run_scheduler = acquired and not args.no_scheduler
        if not acquired and not args.no_scheduler:
            print("Another scheduler holds the lock; serving the UI only (scans are handed to it).")
        scheduler = Scheduler(factory)
        # The bot lives with the scheduler so each notification is delivered by one process only.
        bot = DiscordBot(factory, on_scan=scheduler.request_scan) if run_scheduler else None
        app = create_app(factory, scheduler, run_scheduler=run_scheduler, bot=bot)
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print(f"WARNING: the API has no authentication and is reachable on {args.host}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def cmd_status(factory, args):
    with session_scope(factory) as session:
        print("Subscriptions:")
        for sub in session.scalars(select(Subscription).order_by(Subscription.name)):
            done = [e.number for e in sub.episodes if e.status == "done"]
            other = {e.number: e.status for e in sub.episodes if e.status != "done"}
            sources = ", ".join(b.source.name for b in sub.bindings)
            print(f"  {'*' if sub.enabled else '-'} {sub.name}  [{sources}]  done={len(done)}"
                  f"{' latest=' + str(max(done)) if done else ''}{'  ' + str(other) if other else ''}")
        jobs = session.scalars(select(Job).where(Job.phase.in_(("pending", "running", "needs_attention")))
                               .order_by(Job.id)).all()
        print("Jobs:" if jobs else "Jobs: none active")
        for job in jobs:
            label = f"{job.episode.subscription.name} #{job.episode.number}" if job.episode else job.url[:60]
            print(f"  [{job.id}] {job.phase:<15} {job.progress:5.1f}%  {label}  "
                  f"{job.state.get('phase', '') if job.state else ''}  {job.message or ''}")
            if job.error:
                print(f"        ! {job.error}")
        counts = dict(session.execute(select(Job.phase, func.count()).group_by(Job.phase)).all())
        print("Totals:", counts or {})


def cmd_probe(factory, args):
    with session_scope(factory) as session:
        settings = all_settings(session)
    name = args.downloader or settings["downloader"]
    result = build_downloader(name, settings.get(f"downloader.{name}", {})).health()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def cmd_retry(factory, args):
    with session_scope(factory) as session:
        job = session.get(Job, args.job)
        if job is None:
            sys.exit(f"No job {args.job}")
        if job.phase not in ("needs_attention", "failed"):
            sys.exit(f"Job {job.id} is {job.phase}; only needs_attention/failed jobs can be retried")
        job.phase, job.error, job.transient_errors, job.finished_at = "running", None, 0, None
        if args.from_scratch:
            job.state = {"phase": "new"}
        if job.episode:
            job.episode.status = "downloading"
        print(f"Job {job.id} -> running ({'from scratch' if args.from_scratch else 'resuming ' + str(job.state.get('phase'))})")


def cmd_add_source(factory, args):
    with session_scope(factory) as session:
        source = session.scalar(select(Source).where(Source.name == args.name))
        config_ = {"search_prefix": args.prefix, "keyword_sep": args.sep, "search_suffix": args.suffix}
        if source is None:
            session.add(Source(name=args.name, kind="rss_search", config=config_))
        else:
            source.config = config_
    print(f"source {args.name}: {args.prefix}<keywords joined by {args.sep!r}>{args.suffix}")


def cmd_subscribe(factory, args):
    with session_scope(factory) as session:
        source = session.scalar(select(Source).where(Source.name == args.source))
        if source is None:
            names = ", ".join(session.scalars(select(Source.name))) or "none (use add-source)"
            sys.exit(f"No source {args.source!r}; available: {names}")
        sub = session.scalar(select(Subscription).where(Subscription.name == args.name))
        if sub is None:
            sub = Subscription(name=args.name, save_dir=args.save_dir or args.name)
            session.add(sub)
            session.flush()
        elif args.save_dir:
            sub.save_dir = args.save_dir
        params = {"keywords": args.keywords, "include": args.include or [], "exclude": args.exclude or []}
        binding = next((b for b in sub.bindings if b.source_id == source.id), None)
        if binding is None:
            sub.bindings.append(SourceBinding(source=source, priority=len(sub.bindings), params=params))
        else:
            binding.params, binding.enabled = params, True
    print(f"{args.name} <- {args.source} {json.dumps(params, ensure_ascii=False)}")


def cmd_mark(factory, args):
    with session_scope(factory) as session:
        sub = session.scalar(select(Subscription).where(Subscription.name == args.subscription))
        if sub is None:
            sys.exit(f"No subscription {args.subscription!r}")
        existing = {e.number: e for e in sub.episodes}
        for number in args.episodes:
            episode = existing.get(number)
            if episode is None:
                episode = Episode(subscription=sub, number=number, attempts=0)
                session.add(episode)
            elif any(j.phase in ("pending", "running") for j in episode.jobs):
                sys.exit(f"#{number} has an active job; let it finish first")
            if args.status == "delete":
                if episode.id is not None:
                    session.delete(episode)
            else:
                episode.status = args.status
        print(f"{sub.name}: {args.episodes} -> {args.status}")


def cmd_set(factory, args):
    try:
        value = json.loads(args.value)
    except json.JSONDecodeError:
        value = args.value
    with session_scope(factory) as session:
        set_setting(session, args.key, value)
    print(f"{args.key} = {json.dumps(value, ensure_ascii=False)}")


def cmd_settings(factory, args):
    with session_scope(factory) as session:
        print(json.dumps(all_settings(session), ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m anipik", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--db", help=f"database file (default {config.DB_PATH}; env ANIPIK_DB)")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("migrate")
    p.add_argument("--rss", default=config.LEGACY_RSS)
    p.add_argument("--setting", default=config.LEGACY_SETTING)
    p = commands.add_parser("scan")
    p.add_argument("--dry-run", action="store_true", help="show what would be queued; submits nothing")
    p = commands.add_parser("run")
    p.add_argument("--once", action="store_true", help="one scan + one poll, then exit")
    p = commands.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8964)
    p.add_argument("--no-scheduler", action="store_true", help="UI/API only; a separate `run` does the work")
    commands.add_parser("status")
    p = commands.add_parser("probe")
    p.add_argument("--downloader")
    p = commands.add_parser("retry")
    p.add_argument("job", type=int)
    p.add_argument("--from-scratch", action="store_true",
                   help="forget the job's checkpoint (only after checking the backend for duplicates)")
    p = commands.add_parser("add-source", help="add/update an rss_search source")
    p.add_argument("name")
    p.add_argument("--prefix", required=True, help="e.g. https://share.dmhy.org/topics/rss/rss.xml?keyword=")
    p.add_argument("--sep", default="+")
    p.add_argument("--suffix", default="")
    p = commands.add_parser("subscribe", help="add an anime, or (re)bind it to a source")
    p.add_argument("name")
    p.add_argument("--source", required=True)
    p.add_argument("--keywords", nargs="+", required=True)
    p.add_argument("--include", nargs="+", help="regexes every title must match")
    p.add_argument("--exclude", nargs="+", help="regexes no title may match")
    p.add_argument("--save-dir", help="relative to library_root (default: name) or absolute")
    p = commands.add_parser("mark", help="set episode status by hand")
    p.add_argument("subscription")
    p.add_argument("episodes", type=int, nargs="+")
    p.add_argument("--status", choices=("done", "skipped", "delete"), default="done",
                   help="delete forgets the episode so the next scan may queue it")
    p = commands.add_parser("set")
    p.add_argument("key")
    p.add_argument("value")
    commands.add_parser("settings")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.db:
        config.DB_PATH = Path(args.db).resolve()
    factory = make_session_factory(config.DB_PATH)
    globals()[f"cmd_{args.command.replace('-', '_')}"](factory, args)


if __name__ == "__main__":
    main()
