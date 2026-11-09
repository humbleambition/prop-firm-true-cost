#!/usr/bin/env bash
# Adds https://omniview.striatumos.consulting to the CORS allow list on /rules.json (props block only).
# Keeps journal.striatumos.consulting and localhost:5173. Also exposes ETag if not done yet.
set -euo pipefail
cd "$HOME/striatum"
grep -q "@rules_journal" Caddyfile || { echo "CORS block not found; nothing changed."; exit 1; }
cp Caddyfile "Caddyfile.bak.$(date +%Y%m%d%H%M)"
python3 - <<'PY'
p='Caddyfile'; s=open(p).read()
anchor='\theader /rules.json Vary Origin'
if '@rules_omniview' not in s:
    add=('\t@rules_omniview {\n\t\tpath /rules.json\n\t\theader Origin https://omniview.striatumos.consulting\n\t}\n'
         '\theader @rules_omniview Access-Control-Allow-Origin "https://omniview.striatumos.consulting"\n')
    assert anchor in s, 'Vary line not found'
    s=s.replace(anchor, add+anchor, 1); print('omniview added')
else: print('omniview already there')
if 'Access-Control-Expose-Headers ETag' not in s:
    s=s.replace(anchor, anchor+'\n\theader /rules.json Access-Control-Expose-Headers ETag', 1); print('ETag exposed')
open(p,'w').write(s)
PY
if docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 < /dev/null; then
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile < /dev/null
  echo "Done."
else
  echo "Caddy check failed; restoring backup."; cp "$(ls -t Caddyfile.bak.* | head -1)" Caddyfile; exit 1
fi
