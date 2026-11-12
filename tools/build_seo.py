#!/usr/bin/env python3
"""Search-engine helpers for Prop Firm True Cost (added Nov 11 2026).
Reads app/site/base.json and:
 1. rewrites the plain-HTML "cheapest challenges" block in app/site/index.html
    (between <!--SEO-TOP--> and <!--/SEO-TOP-->) so search engines see real text;
 2. writes app/site/sitemap.xml with today's date.
Run after build_data.py. Safe to run many times."""
import json, html, re, pathlib, datetime
root = pathlib.Path(__file__).resolve().parent
site = root / 'site'
d = json.load(open(site / 'base.json'))
rows, upd = d['rows'], d.get('updated') or datetime.date.today().isoformat()
URL = 'https://props.striatumos.consulting/'

def top(cat, size, n=10):
    best = {}
    for x in rows:
        c = x.get('cost_to_funded_usd')
        if x.get('category') == cat and x.get('size_num') == size and isinstance(c, (int, float)) and c > 0:
            if x['firm'] not in best or c < best[x['firm']]['cost_to_funded_usd']:
                best[x['firm']] = x
    return sorted(best.values(), key=lambda x: x['cost_to_funded_usd'])[:n]

def money(v):
    return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"

def table(title, L):
    out = [f'<h3>{html.escape(title)}</h3><ol>']
    for x in L:
        code = (x.get('promo_code') or '').strip()
        code = f' with code {html.escape(code)}' if code and ' ' not in code else ''
        bill = 'monthly' if 'month' in (x.get('billing') or '').lower() else 'one-time'
        link = x.get('buy_url') or ''
        name = html.escape(x['firm'])
        if link.startswith('http'):
            name = f'<a href="{html.escape(link)}" target="_blank" rel="noopener">{name}</a>'
        out.append(f'<li>{name}, {html.escape(x.get("plan") or "")}: {money(x["cost_to_funded_usd"])} to get funded ({bill}{code})</li>')
    out.append('</ol>')
    return ''.join(out)

fut, fx = top('futures', 50000), top('forex/CFD', 100000)
block = ('<!--SEO-TOP--><section class="seo-top" id="cheapest"><h2>Cheapest prop firm challenges this week</h2>'
         f'<p>Ranked by true cost to get funded (best price with the current code + activation fee), from each firm\'s own site. Updated {upd}. Always confirm on the firm\'s site before buying.</p>'
         + table('Cheapest $50K futures prop firm challenges', fut)
         + table('Cheapest $100K forex prop firm challenges', fx)
         + '<p>Use the full table above for every account size, drawdown type, platform and country.</p></section><!--/SEO-TOP-->')

p = site / 'index.html'
s = p.read_text(encoding='utf-8')
if '<!--SEO-TOP-->' in s:
    s = re.sub(r'<!--SEO-TOP-->.*?<!--/SEO-TOP-->', lambda m: block, s, flags=re.S)
else:
    s = s.replace('<footer>', block + '\n<footer>', 1)
p.write_text(s, encoding='utf-8')

(site / 'sitemap.xml').write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    f'<url><loc>{URL}</loc><lastmod>{upd}</lastmod><changefreq>daily</changefreq></url>\n</urlset>\n', encoding='utf-8')
print('seo block:', len(fut), 'futures,', len(fx), 'forex; updated', upd)
