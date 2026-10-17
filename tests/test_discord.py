import asyncio
import time

import pytest
from sqlalchemy import select

from anipik import discord_bot
from anipik.db import all_settings, session_scope, set_setting
from anipik.discord_bot import MAX_ATTEMPTS, DiscordBot, bot_config, deliver_pending
from anipik.downloaders import Status
from anipik.models import Episode, Job, Notification, Subscription
from anipik.notifiers import OutboxNotifier
from anipik.scheduler import Scheduler


def rows(factory):
    with session_scope(factory) as s:
        return [(n.message, n.sent_at is not None, n.attempts, n.error) for n in s.scalars(select(Notification))]


def test_deliver_pending_marks_sent_and_retries_failures(factory):
    OutboxNotifier(factory).send("完成下载: A 第1集")
    OutboxNotifier(factory).send("完成下载: B 第2集")
    sent, broken = [], {"404"}

    async def send(kind, target, text):
        if target in broken:
            raise LookupError("Unknown Channel")
        sent.append((kind, target, text))

    assert asyncio.run(deliver_pending(factory, send, ("1",), ("404",))) == 0
    assert all(not ok and attempts == 1 and "channel 404" in error for _, ok, attempts, error in rows(factory))
    broken.clear()
    assert asyncio.run(deliver_pending(factory, send, ("1",), ("404",))) == 2
    assert [ok for _, ok, _, _ in rows(factory)] == [True, True]
    assert asyncio.run(deliver_pending(factory, send, ("1",), ())) == 0  # nothing left to send


def test_deliver_pending_gives_up_after_max_attempts(factory):
    OutboxNotifier(factory).send("x")

    async def send(kind, target, text):
        raise RuntimeError("down")

    for _ in range(MAX_ATTEMPTS + 2):
        asyncio.run(deliver_pending(factory, send, ("1",), ()))
    assert rows(factory)[0][2] == MAX_ATTEMPTS


def test_no_targets_is_an_error_not_a_silent_success(factory):
    OutboxNotifier(factory).send("x")

    async def send(kind, target, text):
        pass

    asyncio.run(deliver_pending(factory, send, (), ()))
    assert rows(factory)[0][1:] == (False, 1, "no Discord user_id / channel_id configured")


def test_scheduler_writes_outbox_after_its_transaction(factory, tmp_path):
    """Writing the outbox inside the poll session would block on its own write lock."""
    class Done:
        name = "done"

        def connection(self):
            from contextlib import nullcontext
            return nullcontext(self)

        def advance(self, job, state, checkpoint):
            return Status("done", 100)

    with session_scope(factory) as s:
        set_setting(s, "notify.discord.enabled", True)
        sub = Subscription(name="Show")
        sub.episodes = [Episode(number=3, status="queued", attempts=1)]
        s.add(sub)
        s.flush()
        s.add(Job(episode_id=sub.episodes[0].id, downloader="done", url="magnet:?", destination=str(tmp_path),
                  phase="running", state={"phase": "local_waiting"}))
    started = time.time()
    Scheduler(factory, downloaders={"done": Done()}).poll()
    assert time.time() - started < 5
    assert rows(factory) == [("完成下载: Show 第3集", False, 0, None)]


def test_bot_config_and_states(factory, monkeypatch):
    monkeypatch.setattr(discord_bot, "legacy_token", lambda: "")
    assert bot_config({"notify.discord.enabled": False, "notify.discord.token": "t"}) is None
    assert bot_config({"notify.discord.enabled": True, "notify.discord.token": ""}) is None
    assert bot_config({"notify.discord.enabled": True, "notify.discord.token": "t",
                       "notify.discord.ids": {"user_id": ["1", " "], "channel_id": [2]}}) == ("t", ("1",), ("2",))
    monkeypatch.setattr(discord_bot, "legacy_token", lambda: "from-yaml")
    assert bot_config({"notify.discord.enabled": True, "notify.discord.token": ""})[0] == "from-yaml"
    monkeypatch.undo()

    bot = DiscordBot(factory)
    with session_scope(factory) as s:
        bot.apply(all_settings(s))  # disabled by default: no thread, no network
    assert bot.status["state"] == "disabled" and bot._thread is None


def test_legacy_placeholder_token_is_ignored(tmp_path, monkeypatch):
    from anipik import config
    legacy = tmp_path / "setting.yaml"
    monkeypatch.setattr(config, "LEGACY_SETTING", legacy)
    legacy.write_text("discord_token: 123", encoding="utf-8")  # unquoted: parses as int
    assert discord_bot.legacy_token() == ""
    real = "M" + "x" * 23 + "." + "y" * 6 + "." + "z" * 38
    legacy.write_text(f"discord_token: {real}", encoding="utf-8")
    assert discord_bot.legacy_token() == real


def test_api_never_returns_the_token(factory):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from anipik.api import create_app

    with TestClient(create_app(factory)) as client:
        assert client.patch("/api/settings", json={"notify.discord.token": "secret-token"}).status_code == 200
        got = client.get("/api/settings").json()
        assert got["notify.discord.token"] == "" and got["notify.discord.token_set"] is True
        # The form sends "" back: that must keep the stored token, not clear it.
        client.patch("/api/settings", json={"notify.discord.token": "", "notify.discord.token_set": True,
                                            "max_attempts": 4})
        with session_scope(factory) as s:
            assert all_settings(s)["notify.discord.token"] == "secret-token"
        assert "secret-token" not in client.get("/api/settings").text
        assert client.post("/api/notify/discord/test").json() == {"queued": True}
        assert client.get("/api/notify/discord").json()["outbox"]["pending"] == 1
