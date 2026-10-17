"""Keep the built web UI (anipik/web/dist, not in git) in step with its sources.

After a `git pull` the sources are newer than dist; serve / tray rebuild it on startup
so a pull never leaves the old UI running. Needs Node.js (npm) on PATH; without it the
existing dist is served and a warning is logged.
"""
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)
WEB = Path(__file__).resolve().parent / "web"
DIST_INDEX = WEB / "dist" / "index.html"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _newest(paths):
    newest = 0.0
    for path in paths:
        if path.is_dir():
            newest = max([newest] + [p.stat().st_mtime for p in path.rglob("*") if p.is_file()])
        elif path.exists():
            newest = max(newest, path.stat().st_mtime)
    return newest


def sources_mtime(web=WEB):
    return _newest([web / "src", web / "public", web / "index.html", web / "package.json",
                    web / "package-lock.json", web / "vite.config.ts", web / "tsconfig.json"])


def is_stale(web=WEB):
    index = web / "dist" / "index.html"
    return not index.exists() or sources_mtime(web) > index.stat().st_mtime


def needs_install(web=WEB):
    marker = web / "node_modules" / ".package-lock.json"  # written by npm install
    lock = web / "package-lock.json"
    return not marker.exists() or (lock.exists() and lock.stat().st_mtime > marker.stat().st_mtime)


def _npm(args, web):
    npm = shutil.which("npm")
    if not npm:
        raise FileNotFoundError("npm not found on PATH (install Node.js)")
    result = subprocess.run([npm, *args], cwd=web, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f"npm {' '.join(args)} failed:\n{(result.stdout + result.stderr)[-2000:]}")


def ensure_built(web=WEB):
    """Rebuild dist when the sources changed. Returns "fresh", "built" or "stale" (could not build)."""
    if not is_stale(web):
        return "fresh"
    log.info("web UI sources changed since the last build; rebuilding (npm run build)")
    try:
        if needs_install(web):
            _npm(["install", "--no-fund", "--no-audit"], web)
        _npm(["run", "build"], web)
    except (OSError, RuntimeError) as exc:
        log.warning("could not rebuild the web UI, serving the existing build: %s", exc)
        return "stale"
    log.info("web UI rebuilt")
    return "built"
