#!/bin/bash
set -euo pipefail

# Start Xvfb on display :99 in the background. Chromium will connect to it.
Xvfb :99 -screen 0 1280x800x24 -ac +extension RANDR &
XVFB_PID=$!
export DISPLAY=:99

# Give Xvfb a beat to come up.
sleep 1

# Run the script. Any non-zero exit propagates out of the container.
python /app/renew.py
EXIT=$?

kill "$XVFB_PID" 2>/dev/null || true
exit "$EXIT"
