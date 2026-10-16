import yaml
from sqlalchemy import select

from anipik.db import all_settings, session_scope
from anipik.migrate import migrate
from anipik.models import Episode, Source, Subscription

LEGACY = {
    "MioBT": {"addon": "https://www.miobt.com/rss-", "expr": "+", "rss_link": "https://www.miobt.com/rss.xml",
              "suffix": ".xml", "tasks": {
                  "Show A": {"rule_name": "Show A", "keywords": ["ani show a "], "downloaded_episodes": [1, 2, "4-5"],
                             "enable": True, "update time": None},
                  "Show B": {"rule_name": "Show B", "keywords": ["b"], "downloaded_episodes": [], "enable": False}}},
    "Nyaa": {"addon": "https://nyaa.si/?page=rss&q=", "expr": "+", "rss_link": "https://nyaa.si/?page=rss",
             "suffix": "", "tasks": {
                 "Show A": {"rule_name": "Show A", "keywords": ["Show A S01"], "downloaded_episodes": [3],
                            "enable": False}}},
    "Empty": {"addon": "x", "expr": "+", "rss_link": "y", "suffix": "", "tasks": {}},
}
SETTING = {"location": "N:/新番", "discord": True, "discord_id": {"user_id": ["1"], "channel_id": ["2"]},
           "pikpak_password": "secret", "discord_token": "secret"}


def write(tmp_path):
    rss, setting = tmp_path / "anime_rss.yaml", tmp_path / "setting.yaml"
    rss.write_text(yaml.safe_dump(LEGACY, allow_unicode=True), encoding="utf-8")
    setting.write_text(yaml.safe_dump(SETTING, allow_unicode=True), encoding="utf-8")
    return rss, setting


def test_migrate_merges_sources_and_is_idempotent(factory, tmp_path):
    rss, setting = write(tmp_path)
    with session_scope(factory) as s:
        stats = migrate(s, rss, setting)
    assert stats["sources"] == 3 and stats["subscriptions"] == 2 and stats["bindings"] == 3
    assert stats["episodes"] == 5

    with session_scope(factory) as s:
        a = s.scalar(select(Subscription).where(Subscription.name == "Show A"))
        assert a.enabled  # enabled in at least one legacy source
        assert [b.source.name for b in a.bindings] == ["MioBT", "Nyaa"]
        assert a.bindings[0].params == {"keywords": ["ani show a"]}
        assert not a.bindings[1].enabled
        assert sorted(e.number for e in a.episodes) == [1, 2, 3, 4, 5]
        assert not s.scalar(select(Subscription).where(Subscription.name == "Show B")).enabled
        settings = all_settings(s)
        assert settings["library_root"] == "N:/新番" and settings["notify.discord.enabled"] is True
        assert "secret" not in str(settings)
        # an episode that later failed must not be reset by a re-import
        s.scalar(select(Episode).where(Episode.number == 1)).status = "failed"

    with session_scope(factory) as s:
        again = migrate(s, rss, setting)
    assert again["subscriptions"] == again["bindings"] == again["episodes"] == again["sources"] == 0
    with session_scope(factory) as s:
        assert s.scalar(select(Episode).where(Episode.number == 1)).status == "failed"
        assert len(s.scalars(select(Source)).all()) == 3
