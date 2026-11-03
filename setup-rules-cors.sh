#!/usr/bin/env bash
# Lets the trading journal read props.striatumos.consulting/rules.json (CORS), nothing else.
# Run on the server as jen:
#   curl -fsSL https://raw.githubusercontent.com/humbleambition/prop-firm-true-cost/main/setup-rules-cors.sh | bash
set -euo pipefail
cd "$HOME/striatum"
if grep -q "@rules_journal" Caddyfile; then echo "Already set up."; exit 0; fi
cp Caddyfile "Caddyfile.bak.$(date +%Y%m%d%H%M)"
python3 - <<'PY'
p='Caddyfile'; lines=open(p).read().split('\n'); out=[]
add='''	@rules_journal {
		path /rules.json
		header Origin https://journal.striatumos.consulting
	}
	header @rules_journal Access-Control-Allow-Origin "https://journal.striatumos.consulting"
	@rules_local {
		path /rules.json
		header Origin http://localhost:5173
	}
	header @rules_local Access-Control-Allow-Origin "http://localhost:5173"
	header /rules.json Vary Origin
	header /rules.json Cache-Control "no-cache"'''.split('\n')
done=False
for ln in lines:
    out.append(ln)
    if not done and ln.startswith('props.') and ln.rstrip().endswith('{'):
        out += add; done=True
open(p,'w').write('\n'.join(out)); print('added' if done else 'props block NOT found')
PY
if docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 < /dev/null; then
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile < /dev/null
  echo "Done. rules.json is readable by the journal."
else
  echo "Caddy check failed; restoring backup."; cp "$(ls -t Caddyfile.bak.* | head -1)" Caddyfile; exit 1
fi
