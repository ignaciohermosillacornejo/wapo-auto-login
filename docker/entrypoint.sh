#!/bin/bash
set -euo pipefail

# Start Xvfb on display :99 in the background. Chromium will connect to it.
Xvfb :99 -screen 0 1280x800x24 -ac +extension RANDR &
XVFB_PID=$!
export DISPLAY=:99

# Wait for Xvfb to bind its X11 socket — fixed-sleep readiness gates fail
# under load. Give up after 5s rather than hanging forever.
for _ in {1..50}; do
  [[ -S /tmp/.X11-unix/X99 ]] && break
  sleep 0.1
done
if [[ ! -S /tmp/.X11-unix/X99 ]]; then
  echo "entrypoint: Xvfb failed to bind /tmp/.X11-unix/X99 within 5s" >&2
  exit 3
fi

# Run the script. Any non-zero exit propagates out of the container.
python /app/renew.py
EXIT=$?

kill "$XVFB_PID" 2>/dev/null || true
exit "$EXIT"
