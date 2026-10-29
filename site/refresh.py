#!/usr/bin/env python3
"""Daily promo watcher for Prop Firm True Cost. Standard library only.

Reads base.json (verified plan rows), re-reads each firm's own pricing/promo
pages, and writes data.json with a per-firm watch status:
  - codes and "% off" seen on the firm's pages today
  - whether the stored code is still shown
  - an estimated price when a new single % off appears (marked as estimate)
Also appends to changes.json so the app can list what moved.
Never logs in, never buys, never touches Discord.
"""
import json, re, ssl, gzip, html, datetime, pathlib, concurrent.futures as cf
from urllib.request import Request, urlopen

HERE = pathlib.Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
STOP = {"CODE", "COUPON", "PROMO", "DISCOUNT", "THE", "AND", "FOR", "OFF", "NOW", "USE",
        "YOUR", "WITH", "HERE", "APPLY", "CHECKOUT", "GET", "SAVE", "ALL", "FREE", "NEW",
        "USD", "EUR", "GBP", "FAQ", "TERMS", "LIMITED", "TIME", "ONLY", "TODAY", "COPY",
        "COPIED", "CLICK", "BELOW", "ABOVE", "AT", "TO", "ON", "IS", "OR", "IN", "FUNDED",
        "ACCOUNT", "ACCOUNTS", "EVAL", "EVALUATION", "CHALLENGE", "PLAN", "PLANS", "DAY",
        "NOT", "ANY", "EACH", "UNTIL", "TIONS", "BANNER", "PAYMENT", "THREE", "SUPPORT", "TRADERS", "AWARD", "COUNTDOWN", "EXPIRES", "VALID", "BELOW", "LINK", "ENTER", "REQUIRED", "APPLIED", "AUTOMATICALLY", "SITEWIDE", "STACK", "ABOVE", "REDEEM", "SALE", "DEAL", "OFFER", "WHEN", "THIS", "THAT", "FIRST", "BUY"}
CODE_RE = re.compile(r"(?:\bcode|\bcoupon|\bpromo)\s*(?:code)?\s*[:\-–]?\s*[\"'“”‘’«]?\s*([A-Za-z0-9]{3,20})\b", re.I)
PCT_RE = re.compile(r"\b(\d{1,2})\s?%\s*(?:off|discount|de descuento)", re.I)


def fetch(url):
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*",
                                "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"})
    with urlopen(req, timeout=25, context=ctx) as r:
        raw = r.read(4_000_000)
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "ignore")


def to_text(h):
    h = re.sub(r"(?is)<(style|svg|noscript)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h).replace("\\u0025", "%").replace('\\"', '"'))


def scan(text):
    codes = set()
    for m in CODE_RE.finditer(text):
        c = m.group(1)
        if c.upper() in STOP or c.isdigit() or not any(ch.isalpha() for ch in c):
            continue
        if c != c.upper() and not any(ch.isdigit() for ch in c):  # codes are almost always caps or alnum
            continue
        codes.add(c.upper())
    pcts = sorted({int(p) for p in PCT_RE.findall(text) if 5 <= int(p) <= 95}, reverse=True)
    return sorted(codes)[:12], pcts[:8]


def norm_code(c):
    c = (c or "").strip().upper()
    return c if re.fullmatch(r"[A-Z0-9]{3,20}", c) else ""


def check_firm(firm, urls):
    codes, pcts, ok, err = set(), set(), 0, []
    for u in urls[:4]:
        try:
            c, p = scan(to_text(fetch(u)))
            codes |= set(c); pcts |= set(p); ok += 1
        except Exception as e:  # noqa
            err.append(f"{u.split('/')[2]}: {type(e).__name__}")
    return firm, {"read": ok, "tried": len(urls[:4]), "codes": sorted(codes),
                  "pcts": sorted(pcts, reverse=True), "errors": err[:3]}


def num(v):
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def main():
    base = json.load(open(HERE / "base.json"))
    rows = base["rows"]
    urls = {}
    for r in rows:
        for k in ("promo_source_url", "source_url", "buy_url"):
            for u in re.split(r"[;\s]+", r.get(k) or ""):
                u = u.split("#")[0]
                if u.startswith("http") and "tradinglookup" not in u and "discord" not in u:
                    urls.setdefault(r["firm"], [])
                    if u not in urls[r["firm"]]:
                        urls[r["firm"]].append(u)
    today = datetime.date.today().isoformat()
    try:
        from zoneinfo import ZoneInfo
        stamp = datetime.datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    prev = {}
    if (HERE / "data.json").exists():
        try:
            prev = json.load(open(HERE / "data.json")).get("firms", {})
        except Exception:
            prev = {}
    with cf.ThreadPoolExecutor(10) as ex:
        res = dict(ex.map(lambda kv: check_firm(*kv), urls.items()))

    firms, changes = {}, []
    for firm, w in res.items():
        stored = sorted({norm_code(r.get("promo_code")) for r in rows if r["firm"] == firm} - {""})
        w["stored_codes"] = stored
        w["checked"] = stamp
        if w["read"] == 0:
            w["status"] = "unreadable"
        elif not stored:
            w["status"] = "new code" if w["codes"] else "no code"
        elif not set(stored) & set(w["codes"]):
            w["status"] = "code not seen" if not w["codes"] else "new code"
        elif set(w["codes"]) - set(stored):
            w["status"] = "extra code"
        else:
            w["status"] = "ok"
        p = prev.get(firm, {})
        if p and (p.get("codes") != w["codes"] or p.get("pcts") != w["pcts"]) and w["read"]:
            changes.append({"date": today, "firm": firm, "was_codes": p.get("codes", []),
                            "now_codes": w["codes"], "was_pcts": p.get("pcts", []), "now_pcts": w["pcts"]})
        firms[firm] = w

    for r in rows:  # estimate when the page shows exactly one new % off
        w = firms.get(r["firm"], {})
        r["est_price_usd"] = None
        if w.get("status") in ("new code", "extra code") and len(w.get("pcts", [])) == 1:
            lp = num(r.get("list_price_usd"))
            if lp:
                r["est_price_usd"] = round(lp * (1 - w["pcts"][0] / 100), 2)

    log = []
    if (HERE / "changes.json").exists():
        try:
            log = json.load(open(HERE / "changes.json"))
        except Exception:
            log = []
    log = (changes + log)[:500]
    json.dump(log, open(HERE / "changes.json", "w"), indent=0)
    out = {"updated": base.get("updated"), "next_deep": base.get("next_deep"), "watched": stamp, "rows": rows, "firms": firms, "changes": log[:60]}
    tmp = HERE / "data.json.tmp"
    json.dump(out, open(tmp, "w"), separators=(",", ":"))
    tmp.replace(HERE / "data.json")
    st = {}
    for w in firms.values():
        st[w["status"]] = st.get(w["status"], 0) + 1
    print(today, "firms:", len(firms), st, "changes:", len(changes))


if __name__ == "__main__":
    import sys
    if "--at-7" in sys.argv:  # cron runs hourly; only work at 07:00 Chile time
        from zoneinfo import ZoneInfo
        if datetime.datetime.now(ZoneInfo("America/Santiago")).hour != 7:
            sys.exit(0)
    main()
