"""Import legacy anime_rss.yaml / setting.yaml into the database.

Idempotent upsert, so it can be re-run (or run on every scan with --sync-yaml)
while the old streamlit page is still the editor. It never deletes rows and never
downgrades an episode that already exists. Secrets (PikPak password, Discord token)
are not imported.
"""
import logging
from pathlib import Path

import yaml
from sqlalchemy import select

from .db import set_setting
from .models import Episode, Source, SourceBinding, Subscription

log = logging.getLogger(__name__)


def parse_episode_list(values):
    """[1, 2, '5-7'] -> {1, 2, 5, 6, 7}"""
    result = set()
    for value in values or []:
        value = str(value).strip()
        if "-" in value:
            start, end = value.split("-", 1)
            result.update(range(int(start), int(end) + 1))
        elif value:
            result.add(int(value))
    return result


def _load(path):
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def import_settings(session, setting_path):
    legacy = _load(setting_path)
    imported = []
    if legacy.get("location"):
        set_setting(session, "library_root", legacy["location"])
        imported.append("library_root")
    if "discord" in legacy:
        set_setting(session, "notify.discord.enabled", bool(legacy["discord"]))
        imported.append("notify.discord.enabled")
    if legacy.get("discord_id"):
        ids = legacy["discord_id"]
        set_setting(session, "notify.discord.ids",
                    {"user_id": list(ids.get("user_id") or []), "channel_id": list(ids.get("channel_id") or [])})
        imported.append("notify.discord.ids")
    return imported


def import_rss(session, rss_path):
    legacy = _load(rss_path)
    stats = {"sources": 0, "subscriptions": 0, "bindings": 0, "episodes": 0}
    enabled_by_name = {}
    for content in legacy.values():
        for key, task in ((content or {}).get("tasks") or {}).items():
            name = (task.get("rule_name") or key).strip()
            enabled_by_name[name] = enabled_by_name.get(name, False) or task.get("enable", True) is not False
    for source_name, content in legacy.items():
        content = content or {}
        config = {
            "search_prefix": content.get("addon") or "",
            "keyword_sep": content.get("expr") or "+",
            "search_suffix": content.get("suffix") or "",
            "rss_link": content.get("rss_link") or "",
        }
        source = session.scalar(select(Source).where(Source.name == source_name))
        if source is None:
            source = Source(name=source_name, kind="rss_search", config=config)
            session.add(source)
            stats["sources"] += 1
        else:
            source.config = config
        session.flush()

        for key, task in (content.get("tasks") or {}).items():
            name = (task.get("rule_name") or key).strip()
            subscription = session.scalar(select(Subscription).where(Subscription.name == name))
            if subscription is None:
                subscription = Subscription(name=name, save_dir=name)
                session.add(subscription)
                stats["subscriptions"] += 1
            # The same anime under several legacy sources becomes one subscription;
            # it is enabled if any of its legacy tasks is enabled.
            enabled = task.get("enable", True) is not False
            subscription.enabled = enabled_by_name[name]
            session.flush()

            params = {"keywords": [k.strip() for k in task.get("keywords") or [] if k and k.strip()]}
            binding = session.scalar(select(SourceBinding).where(
                SourceBinding.subscription_id == subscription.id, SourceBinding.source_id == source.id))
            if binding is None:
                priority = len(subscription.bindings)
                binding = SourceBinding(subscription=subscription, source=source, priority=priority,
                                        params=params, enabled=enabled)
                session.add(binding)
                stats["bindings"] += 1
            else:
                binding.params = {**(binding.params or {}), **params}
                binding.enabled = enabled

            existing = {e.number for e in subscription.episodes}
            for number in sorted(parse_episode_list(task.get("downloaded_episodes")) - existing):
                session.add(Episode(subscription=subscription, number=number, status="done",
                                    source_name=source_name, release_title="(imported from anime_rss.yaml)"))
                stats["episodes"] += 1
            session.flush()
    return stats


def migrate(session, rss_path, setting_path=None):
    stats = import_rss(session, rss_path)
    if setting_path:
        stats["settings"] = import_settings(session, setting_path)
    log.info("migration: %s", stats)
    return stats
