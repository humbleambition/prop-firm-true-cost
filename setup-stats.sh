#!/usr/bin/env bash
# StriatumOS: visit logs + private stats pages (GoAccess), no sign-ups.
# Run on the server as jen:
#   curl -fsSL https://raw.githubusercontent.com/humbleambition/prop-firm-true-cost/main/setup-stats.sh | bash
set -euo pipefail
STACK="$HOME/striatum"
cd "$STACK"
mkdir -p logs stats

# 1. Password for the stats page
if [ ! -f "$STACK/.stats_hash" ]; then
  echo "Choose a password for your stats page (nothing shows while you type)."
  read -rsp 'Password: ' PW < /dev/tty; echo
  docker compose exec -T caddy caddy hash-password --plaintext "$PW" | tr -d '\r\n' > "$STACK/.stats_hash"
  unset PW; chmod 600 "$STACK/.stats_hash"
fi
HASH=$(cat "$STACK/.stats_hash")

# 2. Mount logs + stats folders into Caddy
if ! grep -q "./logs:/var/log/caddy" docker-compose.yml; then
  cp docker-compose.yml "docker-compose.yml.bak.$(date +%Y%m%d%H%M)"
  sed -i 's#^\(\s*\)- ./props:/srv/props:ro#&\n\1- ./logs:/var/log/caddy\n\1- ./stats:/srv/stats:ro#' docker-compose.yml
fi
grep -q "./logs:/var/log/caddy" docker-compose.yml || { echo "Could not add the log folder to docker-compose.yml"; exit 1; }

# 3. Turn on visit logs (main site + props) and add props.../stats/ behind a password
cp Caddyfile "Caddyfile.bak.$(date +%Y%m%d%H%M)"
HASH="$HASH" python3 - <<'PY'
import os, re
p = 'Caddyfile'; lines = open(p).read().split('\n'); out = []
other = ('n8n.', 'crm.', 'status.', 'www.')
def logblock(name):
    return ['\tlog {', f'\t\toutput file /var/log/caddy/{name}.log {{', '\t\t\troll_size 200MiB', '\t\t\troll_keep 5', '\t\t}', '\t\tformat json', '\t}']
h = os.environ['HASH']
statsblock = ['\tredir /stats /stats/', '\thandle_path /stats/* {', '\t\tbasic_auth {', f'\t\t\tjen {h}', '\t\t}', '\t\troot * /srv/stats', '\t\tfile_server', '\t}']
i = 0; done = set()
text = '\n'.join(lines)
for ln in lines:
    out.append(ln)
    s = ln.strip()
    if ln and not ln[0].isspace() and s.endswith('{') and s != '{':
        head = s[:-1].strip()
        name = None
        if head.startswith('props.'): name = 'props'
        elif ('{$DOMAIN}' in head or 'striatumos.consulting' in head) and not head.startswith(other):
            if not any(part.strip().startswith(other[:3]) for part in head.split(',')): name = 'main'
        if name and name not in done:
            done.add(name)
            if f'/var/log/caddy/{name}.log' not in text: out += logblock(name)
            if name == 'props' and 'handle_path /stats/*' not in text: out += statsblock
open(p, 'w').write('\n'.join(out))
print('Logging on for:', ', '.join(sorted(done)) or 'NOTHING (check Caddyfile)')
PY

# 4. Hourly stats builder
cat > "$HOME/striatum-stats.sh" <<'SH'
#!/usr/bin/env bash
STACK="$HOME/striatum"; cd "$STACK" || exit 1
for site in main props; do
  [ -s "logs/$site.log" ] || continue
  docker run --rm -v "$STACK/logs:/logs:ro" -v "$STACK/stats:/out" allinurl/goaccess \
    /logs/$site.log --log-format=CADDY --ignore-crawlers -o /out/$site.html >/dev/null 2>&1 || true
done
cat > stats/index.html <<HTML
<!doctype html><meta charset="utf-8"><title>StriatumOS stats</title>
<body style="font-family:sans-serif;background:#000;color:#eee;padding:2em">
<h1>StriatumOS visit stats</h1><p>Updated $(TZ=America/Santiago date '+%Y-%m-%d %H:%M') Chile. Times inside reports are UTC.</p>
<p><a style="color:#6cf" href="props.html">props.striatumos.consulting</a></p>
<p><a style="color:#6cf" href="main.html">striatumos.consulting</a></p></body>
HTML
SH
chmod +x "$HOME/striatum-stats.sh"
LINE="0 * * * * $HOME/striatum-stats.sh"
( crontab -l 2>/dev/null | grep -v "striatum-stats.sh" ; echo "$LINE" ) | crontab -

# 5. Apply
docker compose up -d caddy
sleep 3
if docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
else
  echo "Caddy config check failed; restoring backup."; cp "$(ls -t Caddyfile.bak.* | head -1)" Caddyfile
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile; exit 1
fi
docker pull -q allinurl/goaccess >/dev/null
"$HOME/striatum-stats.sh"
echo
echo "Done. Visits are now logged. Stats (user jen + your password), refreshed hourly:"
echo "  https://props.$(grep '^DOMAIN=' .env | cut -d= -f2)/stats/"
