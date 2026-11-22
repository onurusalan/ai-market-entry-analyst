#!/bin/bash
# Double-click (macOS) to open the Market Entry Analyst web app without internet.
# Serves the docs/ folder on this computer and opens it in the default browser.
cd "$(dirname "$0")/docs" || exit 1
PORT=8765
while lsof -i :$PORT >/dev/null 2>&1; do PORT=$((PORT + 1)); done
echo "Market Entry Analyst is running offline at http://localhost:$PORT"
echo "Close this window (or press Ctrl+C) to stop."
(sleep 1 && open "http://localhost:$PORT/index.html") &
exec python3 -m http.server "$PORT" --bind 127.0.0.1
