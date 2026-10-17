"""Built-in Discord bot: delivers the notifications outbox and answers a few commands.

Runs discord.py in its own thread and event loop inside the anipik process. Config comes
from settings (notify.discord.*); the token falls back to discord_token in setting.yaml.
"""
import asyncio
import logging
import threading
from datetime import datetime, timedelta

import yaml
from sqlalchemy import func, select

from . import config
from .db import all_settings, session_scope
from .models import Job, Notification

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
DELIVERY_INTERVAL = 3  # seconds between outbox checks


def legacy_token():
    try:
        with open(config.LEGACY_SETTING, encoding="utf-8") as f:
            token = (yaml.safe_load(f) or {}).get("discord_token")
    except OSError:
        return ""
    token = str(token).strip() if token else ""  # an unquoted placeholder parses as int
    # Real bot tokens are ~70 characters; anything short is a placeholder left in the old config.
    return token if len(token) >= 50 else ""


def bot_config(settings):
    """(token, user ids, channel ids) when the bot should run, else None."""
    if not settings.get("notify.discord.enabled"):
        return None
    token = str(settings.get("notify.discord.token") or "").strip() or legacy_token()
    if not token:
        return None
    ids = settings.get("notify.discord.ids") or {}
    users = tuple(str(i) for i in ids.get("user_id") or [] if str(i).strip())
    channels = tuple(str(i) for i in ids.get("channel_id") or [] if str(i).strip())
    return token, users, channels


async def deliver_pending(factory, send, users, channels, limit=20):
    """Send undelivered outbox rows to every target. send(kind, target_id, text) is awaited.

    A row is marked sent when every target succeeded; failed rows are retried up to
    MAX_ATTEMPTS times. Returns the number of rows delivered.
    """
    with session_scope(factory) as session:
        rows = [(n.id, n.message) for n in session.scalars(
            select(Notification).where(Notification.channel == "discord", Notification.sent_at.is_(None),
                                       Notification.attempts < MAX_ATTEMPTS).order_by(Notification.id).limit(limit))]
    delivered = 0
    for row_id, text in rows:
        errors = []
        for kind, ids in (("user", users), ("channel", channels)):
            for target in ids:
                try:
                    await send(kind, target, text)
                except Exception as exc:  # NotFound / Forbidden / network
                    errors.append(f"{kind} {target}: {type(exc).__name__}: {exc}")
        if not users and not channels:
            errors.append("no Discord user_id / channel_id configured")
        with session_scope(factory) as session:
            row = session.get(Notification, row_id)
            row.attempts += 1
            row.error = "; ".join(errors) or None
            if not errors:
                row.sent_at = datetime.now()
                delivered += 1
    return delivered


def status_text(factory):
    with session_scope(factory) as session:
        active = session.scalars(select(Job).where(Job.phase.in_(("pending", "running"))).order_by(Job.id)).all()
        attention = session.scalar(select(func.count()).select_from(Job).where(Job.phase == "needs_attention"))
        lines = [f"进行中 {len(active)} 个，需要处理 {attention} 个"]
        for job in active[:10]:
            label = f"{job.episode.subscription.name} 第{job.episode.number}集" if job.episode else f"任务 {job.id}"
            lines.append(f"- {label}：{job.message or job.phase}")
    return "\n".join(lines)


class DiscordBot:
    """Owns the bot thread. apply(settings) starts, restarts or stops it to match settings."""

    def __init__(self, factory, on_scan=None):
        self.factory = factory
        self.on_scan = on_scan
        self.status = {"state": "stopped", "user": None, "error": None, "since": None}
        self._config = None
        self._thread = None
        self._loop = None
        self._client = None
        self._lock = threading.Lock()

    def apply(self, settings=None):
        if settings is None:
            with session_scope(self.factory) as session:
                settings = all_settings(session)
        wanted = bot_config(settings)
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            if wanted == self._config and running:
                return
            if wanted and wanted[0] == (self._config or (None,))[0] and running:
                self._config = wanted  # only targets changed: the delivery loop reads them live
                return
            self._stop_locked()
            self._config = wanted
            if wanted is None:
                self.status.update(state="disabled" if not settings.get("notify.discord.enabled") else "no_token",
                                   user=None, error=None)
                return
            self.status.update(state="starting", user=None, error=None, since=datetime.now().isoformat(timespec="seconds"))
            self._thread = threading.Thread(target=self._run, args=(wanted[0],), name="discord-bot", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_locked()
            self.status.update(state="stopped", user=None)

    def _stop_locked(self):
        if self._loop and self._client and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._client.close(), self._loop).result(timeout=10)
            except Exception:
                log.exception("discord bot did not close cleanly")
        if self._thread:
            self._thread.join(timeout=10)
        self._thread = self._loop = self._client = None

    # -- bot thread ------------------------------------------------------------------
    def _run(self, token):
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            loop.run_until_complete(self._main(token))
        except Exception as exc:
            log.exception("discord bot crashed")
            self.status.update(state="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            loop.close()

    async def _main(self, token):
        import discord

        for message_content in (True, False):
            intents = discord.Intents.default()
            intents.message_content = message_content
            client = discord.Client(intents=intents)
            self._client = client
            self._register(client, commands=message_content)
            try:
                await client.start(token)
                return
            except discord.PrivilegedIntentsRequired:
                # Commands need the Message Content intent (Developer Portal); notifications don't.
                log.warning("discord: Message Content intent not enabled; running without commands")
                await client.close()
            except discord.LoginFailure as exc:
                self.status.update(state="error", error=f"登录失败（token 无效）：{exc}")
                await client.close()
                return
        self.status.update(state="error", error="无法连接 Discord")

    def _register(self, client, commands):
        import discord

        async def send(kind, target, text):
            if kind == "user":
                await (await client.fetch_user(int(target))).send(text)
            else:
                await (await client.fetch_channel(int(target))).send(text)

        async def delivery_loop():
            while not client.is_closed():
                if client.is_ready() and self._config:
                    _, users, channels = self._config
                    try:
                        await deliver_pending(self.factory, send, users, channels)
                    except Exception:
                        log.exception("discord delivery failed")
                await asyncio.sleep(DELIVERY_INTERVAL)

        @client.event
        async def on_ready():
            log.info("discord bot connected as %s", client.user)
            self.status.update(state="connected", user=str(client.user), error=None,
                               commands=commands, since=datetime.now().isoformat(timespec="seconds"))
            if not getattr(client, "_anipik_delivery", None):
                client._anipik_delivery = asyncio.create_task(delivery_loop())

        @client.event
        async def on_disconnect():
            if self.status.get("state") == "connected":
                self.status["state"] = "reconnecting"

        @client.event
        async def on_resumed():
            self.status["state"] = "connected"

        @client.event
        async def on_message(message):
            if message.author == client.user or not message.content.startswith("!"):
                return
            command = message.content[1:].strip().lower()
            if command == "status":
                reply = await asyncio.to_thread(status_text, self.factory)
            elif command == "scan":
                if self.on_scan:
                    self.on_scan()
                    reply = "已开始扫描"
                else:
                    reply = "调度器未在此进程运行"
            elif command in ("help", "hello"):
                reply = "anipik 命令：!status 下载状态 · !scan 立即扫描 · !help 帮助"
            else:
                return
            target = message.author if isinstance(message.channel, discord.DMChannel) else message.channel
            await target.send(reply)


def enqueue_test(factory):
    with session_scope(factory) as session:
        session.add(Notification(channel="discord", message=f"anipik 测试消息 {datetime.now():%H:%M:%S}"))


def outbox_summary(factory):
    since = datetime.now() - timedelta(days=7)
    with session_scope(factory) as session:
        pending = session.scalar(select(func.count()).select_from(Notification).where(
            Notification.sent_at.is_(None), Notification.attempts < MAX_ATTEMPTS))
        failed = session.scalars(select(Notification).where(
            Notification.sent_at.is_(None), Notification.attempts >= MAX_ATTEMPTS,
            Notification.created_at >= since).order_by(Notification.id.desc()).limit(5)).all()
        last = session.scalars(select(Notification).order_by(Notification.id.desc()).limit(1)).first()
        return {"pending": pending,
                "failed": [{"message": n.message, "error": n.error} for n in failed],
                "last": {"message": last.message, "sent": last.sent_at is not None, "error": last.error,
                         "attempts": last.attempts} if last else None}
