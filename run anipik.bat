@echo off
rem Anipik: tray icon (web UI + scheduler + Discord bot), no console window.
rem Console mode for debugging: .venv\Scripts\python -m anipik serve
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating .venv ...
  python -m venv .venv || (echo Python 3.11+ is required & pause & exit /b 1)
)
rem Picks up new Python dependencies after a git pull; quick when nothing changed.
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt || (echo pip install failed & pause & exit /b 1)
rem The web UI is rebuilt on startup when its sources changed (needs Node.js).
start "" ".venv\Scripts\pythonw.exe" -m anipik tray --open %*
