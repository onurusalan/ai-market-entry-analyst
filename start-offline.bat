@echo off
REM Double-click (Windows) to open the Market Entry Analyst web app without internet.
cd /d "%~dp0docs"
echo Market Entry Analyst is running offline at http://localhost:8765
echo Close this window to stop.
start "" http://localhost:8765/index.html
python -m http.server 8765 --bind 127.0.0.1
