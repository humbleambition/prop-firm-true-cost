#!/usr/bin/env bash
# Prop Firm True Cost: one-time switch to automatic updates + public site.
# Run on the server as jen:
#   curl -fsSL https://raw.githubusercontent.com/humbleambition/prop-firm-true-cost/main/setup-vps.sh | bash
set -euo pipefail
REPO="https://github.com/humbleambition/prop-firm-true-cost.git"
SRC="$HOME/props-src"
STACK="$HOME/striatum"
cd "$HOME"

# 1. Get the app from GitHub
if [ -d "$SRC/.git" ]; then git -C "$SRC" pull -q; else git clone -q "$REPO" "$SRC"; fi
mkdir -p "$STACK/props"
cp "$SRC/update.sh" "$HOME/props-update.sh"; chmod +x "$HOME/props-update.sh"

# 2. Make the props site public (removes the password) and hide the scripts
cd "$STACK"
cp Caddyfile "Caddyfile.bak.$(date +%Y%m%d%H%M)"
python3 - <<'PY'
import re
p='Caddyfile'; s=open(p).read()
block='''props.{$DOMAIN} {
	@scripts path *.py *.sh
	respond @scripts 404
	root * /srv/props
	encode gzip
	header /data.json Cache-Control "no-cache"
	file_server
}'''
new,n=re.subn(r'props\.\{\$DOMAIN\}\s*\{.*?\n\}', block, s, flags=re.S)
if n==0: new=s.rstrip()+'\n\n'+block+'\n'
open(p,'w').write(new)
PY
grep -q "./props:/srv/props" docker-compose.yml || { cp docker-compose.yml docker-compose.yml.bak; sed -i 's#^\(\s*\)- ./site:/srv/site:ro#&\n\1- ./props:/srv/props:ro#' docker-compose.yml; }

# 3. One cron line: every hour at :05; at 07:00 Chile it pulls the weekly data from GitHub and runs the daily code check
LINE="5 * * * * $HOME/props-update.sh >> $HOME/props-refresh.log 2>&1"
( crontab -l 2>/dev/null | grep -v "refresh.py" | grep -v "props-update.sh" ; echo "$LINE" ) | crontab -

# 4. Update now, then reload Caddy
"$HOME/props-update.sh" --now
docker compose up -d caddy
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
echo
echo "Done. Public at https://props.$(grep '^DOMAIN=' .env | cut -d= -f2) and it now updates itself."
