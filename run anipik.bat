@echo off
rem New anipik web UI + scheduler on http://127.0.0.1:8964
cd /d "%~dp0"
if not exist anipik\web\dist\index.html (cd anipik\web && call npm install && call npm run build && cd /d "%~dp0")
.venv\Scripts\python -m anipik serve %*
