"""Notifications: written to the notifications outbox table, delivered by the Discord bot thread."""
import logging

from .db import session_scope
from .models import Notification

log = logging.getLogger(__name__)


class OutboxNotifier:
    def __init__(self, factory, channel="discord"):
        self.factory, self.channel = factory, channel

    def send(self, message):
        with session_scope(self.factory) as session:
            session.add(Notification(channel=self.channel, message=message))


def build_notifiers(settings, factory):
    notifiers = []
    if settings.get("notify.discord.enabled"):
        notifiers.append(OutboxNotifier(factory, "discord"))
    return notifiers


def notify(notifiers, message):
    log.info("notify: %s", message)
    for notifier in notifiers:
        try:
            notifier.send(message)
        except Exception:
            log.exception("notifier %s failed", type(notifier).__name__)
