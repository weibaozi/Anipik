"""Windows shortcuts that start the tray app without a console (desktop, Start menu, login)."""
import os
import subprocess
import sys
from pathlib import Path

from . import config

NAME = "Anipik"
ICON = Path(__file__).resolve().parent / "web" / "public" / "favicon.ico"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _folders():
    appdata = Path(os.environ.get("APPDATA", ""))
    return {
        "desktop": Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        "startmenu": appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        "startup": appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
    }


def path(where):
    return _folders()[where] / f"{NAME}.lnk"


def pythonw():
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def create(where):
    """Create (or overwrite) the shortcut; returns its path."""
    link = path(where)
    link.parent.mkdir(parents=True, exist_ok=True)
    db = f' --db "{config.DB_PATH}"' if config.DB_PATH != config.DATA_DIR / "anipik.db" else ""
    # Clicking a shortcut should show the UI; logging in should only start the tray quietly.
    args = f"-m anipik{db} tray" + ("" if where == "startup" else " --open")
    script = "; ".join([
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(link)})",
        f"$s.TargetPath = {_ps_quote(pythonw())}",
        f"$s.Arguments = {_ps_quote(args)}",
        f"$s.WorkingDirectory = {_ps_quote(config.ROOT)}",
        f"$s.IconLocation = {_ps_quote(ICON)}",
        "$s.Description = 'Anipik'",
        "$s.Save()",
    ])
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   check=True, capture_output=True, creationflags=_NO_WINDOW)
    return link


def remove(where):
    try:
        path(where).unlink()
    except FileNotFoundError:
        pass


def exists(where):
    return path(where).exists()
