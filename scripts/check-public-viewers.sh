#!/bin/bash
# Local hidden-paths check for Stage 2 public viewers. Usage: check-public-viewers.sh http://127.0.0.1:PORT
set -euo pipefail
B=${1:-http://127.0.0.1:8803}
fail=0
check() {
  local want="$1" p="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$B$p")
  echo "$code $p"
  if [ "$code" != "$want" ]; then
    echo "  expected $want" >&2
    fail=1
  fi
}
echo "-- 404 expected (no cookie)"
for p in /lab/wind /lab/wind.js /lab/tiles "/wind?model=hrrr" "/api/wind-grid?model=hrrr" "/api/wind-grid?model=hrrr&ahead=3" /api/radar/usage /radar/fixture-tile/7/36/50.png?t=202603080655 /preview /wind.html /wind-viewer.js /wind-lab.js /radar.html /radar-viewer.js /docs/WIND_VIEWER.md /hrrrgrid.py; do
  check 404 "$p"
done
echo "-- 200 expected"
for p in / /wind /wind.css /wind/viewer.js /wind/engine.js /wind/coast.js /wind/coast-lo.json /wind/coast-hi.json /wind/labels.json /api/wind-grid "/api/wind-grid?ahead=3" /radar /radar.css /radar/viewer.js /radar/player.js /api/radar-view /api/radar /dashboard; do
  check 200 "$p"
done
if [ "$fail" -ne 0 ]; then
  echo "HIDDEN PATHS CHECK FAILED" >&2
  exit 1
fi
echo "HIDDEN PATHS CHECK OK"
