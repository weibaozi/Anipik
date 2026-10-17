import sys

import pytest

pytest.importorskip("pystray")

from anipik import shortcuts, tray  # noqa: E402
from anipik.db import session_scope  # noqa: E402
from anipik.models import Job  # noqa: E402


class FakeIcon:
    def __init__(self):
        self.stopped, self.notes, self.title, self.visible = 0, [], "", True

    def stop(self):
        self.stopped += 1

    def notify(self, message, title=None):
        self.notes.append(message)


class FakeScheduler:
    def __init__(self, ok=True):
        self.status = {"backends": {"pikpak_client": {"ok": ok}}}
        self.scans = 0

    def request_scan(self):
        self.scans += 1


def make_app(factory, ok=True):
    app = tray.TrayApp(factory)
    app.icon, app.scheduler = FakeIcon(), FakeScheduler(ok)
    return app


def test_tooltip_summarizes_jobs_and_backend(factory):
    app = make_app(factory)
    assert app._tooltip() == "Anipik · 空闲 · PikPak 已连接"
    with session_scope(factory) as s:
        for phase in ("running", "pending", "needs_attention"):
            s.add(Job(downloader="pikpak_client", url="magnet:?", destination="D:/x", phase=phase, state={}))
    app.scheduler = FakeScheduler(ok=False)
    assert app._tooltip() == "Anipik · 2 个下载中 · 1 个需处理 · PikPak 未连接"


def test_menu_actions(factory):
    app = make_app(factory)
    app._scan()
    assert app.scheduler.scans == 1 and app.icon.notes == ["已开始扫描"]
    app._quit()
    assert app.icon.stopped == 1 and not app.restart_requested
    app._restart()
    assert app.icon.stopped == 2 and app.restart_requested
    assert [str(i) for i in app._menu().items if str(i)][:2] == ["打开 Anipik", "立即扫描"]


def test_relaunch_reuses_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["G:/x/anipik/__main__.py", "--db", "data/a.db", "tray", "--port", "9000"])
    monkeypatch.setattr(tray.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    tray.relaunch()
    args, kw = calls[0]
    assert args[1:] == ["-m", "anipik", "--db", "data/a.db", "tray", "--port", "9000"]
    assert args[0].lower().endswith(("pythonw.exe", "python.exe")) and kw["stdout"] is tray.subprocess.DEVNULL


def test_second_instance_only_opens_the_ui(factory, monkeypatch, tmp_path):
    from anipik import config
    from anipik.instance import single_instance

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "x.db")
    opened = []
    monkeypatch.setattr(tray.webbrowser, "open", opened.append)
    with single_instance() as held:
        assert held
        assert tray.TrayApp(factory, port=9123).run() is False
    assert opened == ["http://127.0.0.1:9123"]


def test_shortcut_quoting():
    assert shortcuts._ps_quote("C:/it's here") == "'C:/it''s here'"
    assert shortcuts.path("startup").name == "Anipik.lnk"
