"""Find, start and restart the PikPak desktop client with the local debugging port (Windows).

The client is single-instance: launching it again while it already runs (e.g. started
normally from the Start menu, without the debug port) only focuses that window, so the
port stays closed. That case needs a restart, which only happens on an explicit request.
"""
import logging
import os
import subprocess
import time

log = logging.getLogger(__name__)

CANDIDATES = [
    r"%ProgramFiles%\PikPak\PikPak.exe",
    r"%ProgramFiles(x86)%\PikPak\PikPak.exe",
    r"%LOCALAPPDATA%\Programs\PikPak\PikPak.exe",
]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# The client must outlive anipik: own process group, not attached to our console.
_DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def find_exe(configured=None):
    """The configured PikPak.exe if it exists, else the first default install location found."""
    for path in ([configured] if configured else []) + [os.path.expandvars(c) for c in CANDIDATES]:
        if path and os.path.isfile(path):
            return os.path.normpath(path)
    return None


def running_pids(image="PikPak.exe"):
    if os.name != "nt":
        return []
    result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, creationflags=_NO_WINDOW)
    pids = []
    for line in result.stdout.splitlines():  # '"PikPak.exe","64892","Console",...'; else a localized notice
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == image.lower() and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def launch(exe, port, hidden=True):
    """Start the client with the debugging port bound to localhost only.

    hidden: --openAsHidden is the flag the client's own "start at login" uses; the main
    window is created (so the page and its modules load) but not shown, only the tray icon.
    """
    args = [exe, f"--remote-debugging-port={int(port)}", "--remote-debugging-address=127.0.0.1"]
    if hidden:
        args.append("--openAsHidden")
    subprocess.Popen(args, cwd=os.path.dirname(exe), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=_DETACHED)
    log.info("launched %s with debug port %s%s", exe, port, " (tray only)" if hidden else "")


def stop(image="PikPak.exe", timeout=15):
    """Ask the client to exit; force it if it is still running after `timeout` seconds."""
    if not running_pids(image):
        return
    subprocess.run(["taskkill", "/IM", image, "/T"], capture_output=True, creationflags=_NO_WINDOW)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not running_pids(image):
            return
        time.sleep(0.5)
    log.warning("%s did not exit in %ss; terminating", image, timeout)
    subprocess.run(["taskkill", "/IM", image, "/T", "/F"], capture_output=True, creationflags=_NO_WINDOW)
    while running_pids(image) and time.time() < deadline + 10:
        time.sleep(0.5)
