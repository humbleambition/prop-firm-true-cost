#!/usr/bin/env bash
# Runs hourly from cron; does its work at 07:00 Chile time (or now with --now).
set -euo pipefail
if [ "${1:-}" != "--now" ] && [ "$(TZ=America/Santiago date +%H)" != "07" ]; then exit 0; fi
SRC="$HOME/props-src"; DEST="$HOME/striatum/props"
git -C "$SRC" pull -q
# copy app files, keep the server's own data.json and change log
find "$SRC/site" -maxdepth 1 -type f ! -name data.json ! -name changes.json -exec cp {} "$DEST/" \;
cd "$DEST" && /usr/bin/python3 refresh.py
echo "$(date -Is) updated"
