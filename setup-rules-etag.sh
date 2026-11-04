#!/usr/bin/env bash
# Adds Access-Control-Expose-Headers: ETag to /rules.json so the journal can skip unchanged downloads.
# Run on the server as jen (after setup-rules-cors.sh):
#   curl -fsSL https://raw.githubusercontent.com/humbleambition/prop-firm-true-cost/main/setup-rules-etag.sh | bash
set -euo pipefail
cd "$HOME/striatum"
if grep -q "Access-Control-Expose-Headers ETag" Caddyfile; then echo "Already set up."; exit 0; fi
grep -q 'header /rules.json Cache-Control "no-cache"' Caddyfile || { echo "CORS block not found; run setup-rules-cors.sh first."; exit 1; }
cp Caddyfile "Caddyfile.bak.$(date +%Y%m%d%H%M)"
sed -i 's|^\(\s*\)header /rules.json Cache-Control "no-cache"$|&\n\1header /rules.json Access-Control-Expose-Headers ETag|' Caddyfile
if docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 < /dev/null; then
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile < /dev/null
  echo "Done. ETag is now visible to the journal."
else
  echo "Caddy check failed; restoring backup."; cp "$(ls -t Caddyfile.bak.* | head -1)" Caddyfile; exit 1
fi
