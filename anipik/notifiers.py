"""Notifications. For now: hand messages to the existing Discord bot via its YAML queue."""
import logging

log = logging.getLogger(__name__)


class DiscordQueueNotifier:
    def __init__(self, ids):
        self.setting = {"discord_id": {"user_id": list(ids.get("user_id") or []),
                                       "channel_id": list(ids.get("channel_id") or [])}}

    def send(self, message):
        from chatbot.notify import notify_discord  # writes chatbot/notify_queue.yaml for the bot
        notify_discord(message, self.setting)


def build_notifiers(settings):
    notifiers = []
    if settings.get("notify.discord.enabled"):
        notifiers.append(DiscordQueueNotifier(settings.get("notify.discord.ids") or {}))
    return notifiers


def notify(notifiers, message):
    log.info("notify: %s", message)
    for notifier in notifiers:
        try:
            notifier.send(message)
        except Exception:
            log.exception("notifier %s failed", type(notifier).__name__)
