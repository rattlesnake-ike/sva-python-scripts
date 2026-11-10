#!/bin/zsh
# AI Reference Retriever - launcher (Mac). Double-click, or let the Photoshop panel open it.
# Uses .venv next to app.py when it exists, otherwise python3 on the PATH.
cd "$(dirname "$0")"
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" -c "import requests, PIL.Image, reportlab" 2>/dev/null || "$PY" -m pip install requests pillow reportlab
nohup "$PY" app.py >/dev/null 2>&1 &
sleep 1
# close the Terminal window this opened
osascript -e 'tell application "Terminal" to close (every window whose name contains "run.command")' >/dev/null 2>&1 &
exit 0
