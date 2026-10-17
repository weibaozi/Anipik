@echo off
rem Anipik: tray icon (web UI + scheduler + Discord bot), no console window.
rem Console mode for debugging: .venv\Scripts\python -m anipik serve
cd /d "%~dp0"
if not exist anipik\web\dist\index.html (cd anipik\web && call npm install && call npm run build && cd /d "%~dp0")
start "" ".venv\Scripts\pythonw.exe" -m anipik tray --open %*
