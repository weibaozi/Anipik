"""System tray app: web UI + scheduler + Discord bot in one process, without a console.

Start with `pythonw -m anipik tray` (the shortcuts from `python -m anipik shortcut` do
that). Logs go to data/anipik.log. A second launch only opens the running instance's UI.
"""
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from sqlalchemy import func, select

from . import config, shortcuts
from .db import all_settings, session_scope
from .instance import single_instance
from .models import Job

log = logging.getLogger(__name__)
ICON_IMAGE = Path(__file__).resolve().parent / "web" / "public" / "icon-192.png"


def log_file():
    return config.DB_PATH.parent / "anipik.log"


def setup_logging():
    """Rotating file log; keep a console handler only when there is a console (python, not pythonw)."""
    path = log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    for existing in list(root.handlers):
        if sys.stderr is None or isinstance(existing, logging.FileHandler):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class TrayApp:
    def __init__(self, factory, host="127.0.0.1", port=8964, open_browser=False):
        self.factory, self.host, self.port, self.open_browser = factory, host, port, open_browser
        self.url = f"http://127.0.0.1:{port}"
        self.restart_requested = False
        self.icon = self.server = self.thread = self.scheduler = None

    # -- lifecycle -------------------------------------------------------------------
    def run(self):
        """Blocks until Quit/Restart. Returns True when a restart was requested."""
        import pystray
        from PIL import Image

        with single_instance() as acquired:
            if not acquired:
                log.info("anipik is already running; opening its web UI")
                webbrowser.open(self.url)
                return False
            from .webbuild import ensure_built
            ensure_built()  # dist is not in git: rebuild it after a pull changed the UI sources
            self._start_server()
            self.icon = pystray.Icon("anipik", Image.open(ICON_IMAGE), "Anipik", menu=self._menu())
            threading.Thread(target=self._watch, name="tray-status", daemon=True).start()
            self.icon.run()  # must run on the main thread
            self._stop_server()
        return self.restart_requested

    def _start_server(self):
        import uvicorn

        from .api import create_app
        from .discord_bot import DiscordBot
        from .scheduler import Scheduler

        self.scheduler = Scheduler(self.factory)
        bot = DiscordBot(self.factory, on_scan=self.scheduler.request_scan)
        app = create_app(self.factory, self.scheduler, run_scheduler=True, bot=bot,
                         server={"host": self.host, "port": self.port}, on_restart=self._restart)
        # log_config=None: uvicorn logs go to the root (file) handler, not a console.
        self.server = uvicorn.Server(uvicorn.Config(app, host=self.host, port=self.port,
                                                    log_config=None, access_log=False))
        self.thread = threading.Thread(target=self.server.run, name="web", daemon=True)
        self.thread.start()
        log.info("tray: serving on http://%s:%s", self.host, self.port)

    def _stop_server(self):
        if self.server:
            self.server.should_exit = True  # runs the app shutdown: stops scheduler + bot
            self.thread.join(timeout=30)
        log.info("tray: stopped")

    def _watch(self):
        """Report startup failures, open the browser once, keep the tooltip current."""
        deadline = time.time() + 30
        while not self.server.started and self.thread.is_alive() and time.time() < deadline:
            time.sleep(0.2)
        if not self.server.started:
            message = f"无法启动 Web 服务（端口 {self.port} 可能被占用），详见日志"
            log.error("tray: %s", message)
            self._notify(message)
            self.icon.title = "Anipik · 启动失败"
            return
        if self.open_browser:
            webbrowser.open(self.url)
        while self.thread.is_alive():
            try:
                self.icon.title = self._tooltip()
            except Exception:
                log.exception("tray: status update failed")
            time.sleep(5)
        if not self.restart_requested and self.icon.visible:
            self._notify("Web 服务意外停止，详见日志")

    def _tooltip(self):
        with session_scope(self.factory) as session:
            counts = dict(session.execute(select(Job.phase, func.count()).group_by(Job.phase)).all())
        active = counts.get("running", 0) + counts.get("pending", 0)
        parts = ["Anipik", f"{active} 个下载中" if active else "空闲"]
        if counts.get("needs_attention"):
            parts.append(f"{counts['needs_attention']} 个需处理")
        backend = next(iter(self.scheduler.status.get("backends", {}).values()), None)
        if backend is not None:
            parts.append("PikPak 已连接" if backend["ok"] else "PikPak 未连接")
        return " · ".join(parts)[:120]  # Windows tooltip limit is 127 characters

    def _notify(self, message):
        try:
            self.icon.notify(message, "Anipik")
        except Exception:
            pass

    # -- menu ------------------------------------------------------------------------
    def _menu(self):
        import pystray

        item = pystray.MenuItem
        return pystray.Menu(
            item("打开 Anipik", self._open, default=True),
            item("立即扫描", self._scan),
            item("打开下载目录", self._open_library),
            item("打开日志", self._open_log),
            pystray.Menu.SEPARATOR,
            item("开机自启", self._toggle_startup, checked=lambda _: shortcuts.exists("startup")),
            pystray.Menu.SEPARATOR,
            item("重启", self._restart),
            item("退出", self._quit),
        )

    def _open(self, icon=None, item=None):
        webbrowser.open(self.url)

    def _scan(self, icon=None, item=None):
        self.scheduler.request_scan()
        self._notify("已开始扫描")

    def _open_library(self, icon=None, item=None):
        with session_scope(self.factory) as session:
            root = all_settings(session)["library_root"]
        if os.path.isdir(root):
            os.startfile(root)
        else:
            self._notify(f"下载目录不存在：{root}")

    def _open_log(self, icon=None, item=None):
        if log_file().exists():
            os.startfile(log_file())

    def _toggle_startup(self, icon=None, item=None):
        try:
            if shortcuts.exists("startup"):
                shortcuts.remove("startup")
            else:
                shortcuts.create("startup")
        except Exception as exc:
            log.exception("tray: startup shortcut")
            self._notify(f"设置开机自启失败：{exc}")

    def _restart(self, icon=None, item=None):
        self.restart_requested = True
        self.icon.stop()

    def _quit(self, icon=None, item=None):
        self.icon.stop()


def relaunch():
    """Start a fresh process with the same arguments (after this one released lock and port)."""
    # Without --open: the page that asked for the restart reconnects by itself.
    args = [str(shortcuts.pythonw()), "-m", "anipik", *(a for a in sys.argv[1:] if a != "--open")]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, cwd=config.ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags)
    log.info("tray: relaunched %s", args)


def main(factory, host, port, open_browser):
    setup_logging()
    try:
        if TrayApp(factory, host, port, open_browser).run():
            relaunch()
    except Exception:
        log.exception("tray crashed")
        raise
