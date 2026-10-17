import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ANIPIK_DATA", ROOT / "data"))
DB_PATH = Path(os.environ.get("ANIPIK_DB", DATA_DIR / "anipik.db"))

LEGACY_RSS = ROOT / "old" / "anime_rss.yaml"  # archived; already imported by `migrate`
LEGACY_SETTING = ROOT / "setting.yaml"

# Defaults for keys in the settings table; the table overrides them.
DEFAULT_SETTINGS = {
    "library_root": str(ROOT / "downloads"),
    "downloader": "pikpak_client",
    # exe_path empty = look in the default install locations; auto_start launches it with the port;
    # start_hidden launches it to the tray only (the client's own --openAsHidden).
    "downloader.pikpak_client": {"port": 19223, "exe_path": "", "auto_start": True, "start_hidden": True},
    "scan_interval": 600,
    "poll_interval": 5,
    "max_active_jobs": 5,
    "max_attempts": 3,
    # A job that keeps failing to reach the downloader is parked after this many ticks.
    "max_transient_errors": 120,
    "notify.discord.enabled": False,
    "notify.discord.token": "",  # empty: fall back to discord_token in setting.yaml
    "notify.discord.ids": {"user_id": [], "channel_id": []},
}
