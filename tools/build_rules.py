#!/usr/bin/env python3
"""Build site/rules.json (clean numeric rules per firm/plan/size/phase) from data/merged.json.
For the Prop Firm Trading Journal (journal.striatumos.consulting). Futures only for now.
Usage: python3 app/build_rules.py [merged.json] [out.json]"""
import json, re, sys, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'data', 'merged.json')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'site', 'rules.json')

# Known overrides (firm-level), checked by hand
OVERRIDES = {
    'IQ Capital': {'commission_per_side_micro_usd': 0.80, 'commission_per_side_mini_usd': 2.88},  # support article 14939071, Nov 3 2026
}

NONE_WORDS = ('none', 'no ', 'n/a', 'sin ', 'removed', 'not required', 'no time limit')
EVAL_W = ('eval', 'challenge', 'practice', 'combine', 'phase 1', 'step')
FUND_W = ('funded', 'pa', 'pro', 'qualified', 'payout', 'live', 'xfa', 'master', 'sim funded', 'reward')


def s(v):
    return '' if v is None else str(v).strip()


def num(v):
    """Leading number of a field ('3000', '$1,250 ...', '129 (monthly...)'); None otherwise."""
    m = re.match(r'^\s*(?:USD\s*)?\$?\s*([\d,]+(?:\.\d+)?)(?!\s*%)', s(v))
    if not m:
        return None
    x = float(m.group(1).replace(',', ''))
    return int(x) if x.is_integer() else x


def is_none(v):
    t = s(v).lower()
    return t.startswith(NONE_WORDS) or t in ('0', '0%')


def dd_type(t):
    t = t.lower()
    if not t:
        return None
    if 'intraday' in t or 'unrealized' in t or 'real-time' in t or 'realtime' in t:
        return 'intraday_trailing'
    if 'static' in t or 'fixed' in t:
        return 'static'
    if 'eod' in t or 'end of day' in t or 'end-of-day' in t or 'fin del d' in t:
        return 'eod_trailing'
    return 'other'


def dd_lock(t):
    t = t.lower()
    if not re.search(r'lock|stops? trailing|stop trailing|freez', t):
        return None
    m = re.search(r'\+\s*\$?\s*([\d,]+)(?![\d,]*\s*%)', t)
    return f"start_balance+{m.group(1).replace(',', '')}" if m else 'start_balance'


def seg_phase(seg):
    l = ' ' + seg.lower() + ' '
    e = any(w in l for w in EVAL_W)
    f = any(re.search(r'\b' + re.escape(w) + r'\b', l) for w in FUND_W)
    if e and f:
        return 'both'
    return 'eval' if e else 'funded' if f else 'both'


def by_phase(text, pick):
    """Split a free-text rule into eval/funded values. pick(seg) -> value or 'NONE' or None."""
    out = {'eval': None, 'funded': None}
    t = s(text)
    if not t:
        return out, False
    m = re.match(r'^\s*(\d+)%\s*/\s*(\d+)%\s*\((\w+)\s*/\s*(\w+)\)', t)  # "50% / 30% (eval / Pro)"
    if m:
        return {'eval': float(m.group(1)), 'funded': float(m.group(2))}, True
    found = False
    for seg in re.split(r'[;|]|\.\s', t):
        if not seg.strip():
            continue
        v = pick(seg)
        if v is None:
            continue
        found = True
        ph = seg_phase(seg)
        for p in (['eval', 'funded'] if ph == 'both' else [ph]):
            if out[p] is None:
                out[p] = v
    for p in out:
        if out[p] == 'NONE':
            out[p] = None
    return out, found


def pick_pct(seg):
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', seg)
    if m:
        return float(m.group(1))
    if re.search(r'\bnone\b|\bno\b|not stated|n/a', seg.lower()):
        return 'NONE'
    return None


def pick_days(seg):
    l = seg.lower()
    if 'duration' in l or 'access' in l or 'expire' in l:
        return None
    m = re.search(r'(\d+)', seg)
    if m:
        return int(m.group(1))
    if re.search(r'\bnone\b|no min|no time limit', l):
        return 'NONE'
    return None


def duration(t):
    m = re.search(r'(\d+)\s*-?\s*(?:day|calendar day)s?\s*(?:duration|access|limit|to pass|expir)', t.lower())
    return int(m.group(1)) if m else None


def split_pct(t):
    m = re.search(r'(\d+)\s*(?:%|/\d+)', s(t))
    return float(m.group(1)) if m else None


def commissions(t):
    t = s(t)
    mi = re.search(r'\bM(?:ES|NQ)\b[^\d]{0,6}(\d+\.\d+|\d+)', t)
    ma = re.search(r'\b(?:ES|NQ)\b[^\d]{0,6}(\d+\.\d+|\d+)', t)
    rt = 'round turn' in t.lower() and 'per side' not in t.lower() and not re.search(r'ES \d', t)
    f = (lambda m: (float(m.group(1)) / (2 if rt else 1)) if m else None)
    return f(mi), f(ma)


def money_or_zero(v):
    n = num(v)
    if n is not None:
        return n
    return 0 if is_none(v) else None


def phases_for(plan):
    p = plan.lower()
    if re.search(r'instant|direct|no evaluation|straight to funded|express funded', p):
        return ['instant']
    return ['eval', 'funded']


def build():
    rows = json.load(open(SRC))
    out = []
    for r in rows:
        if s(r.get('category')).lower() != 'futures':
            continue
        size = num(r.get('account_size_usd'))
        ddt = s(r.get('drawdown_type'))
        cons, _ = by_phase(r.get('consistency_rule'), pick_pct)
        days, _ = by_phase(r.get('min_days'), pick_days)
        dl = s(r.get('daily_loss_usd'))
        daily = num(dl)
        dl_pct = None
        if daily is None:
            m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*%', dl)
            if m and size:
                daily = round(size * float(m.group(1)) / 100)
        mi, ma = commissions(r.get('commission_per_side_usd'))
        cr = s(r.get('consistency_rule')).lower()
        # basis: profit_target only when the rule measures against the target, not total profit
        tgt = re.search(r'of (?:the |your )?(?:total )?(?:profit )?target', cr) and not re.search(r'of (?:total |net |total net )?profits?\b(?! target)', cr)
        basis = 'best_day/profit_target' if tgt else ('best_day/total_profit' if any(v for v in cons.values()) else None)
        mpl = None
        m = re.search(r'max(?:imum)? position loss[^\d]{0,12}(\d+(?:\.\d+)?)\s*%', dl.lower() + ' ' + s(r.get('notes')).lower())
        mpl = float(m.group(1)) if m else None
        raw = []
        for k, lab in (('drawdown_type', 'drawdown'), ('daily_loss_usd', 'daily loss'), ('consistency_rule', 'consistency'),
                       ('min_days', 'days'), ('profit_split', 'split'), ('payout_frequency', 'payouts'),
                       ('commission_per_side_usd', 'commissions'), ('monthly_or_data_fee_funded_usd', 'funded fees'),
                       ('activation_fee_usd', 'activation')):
            v = s(r.get(k))
            if v and not re.fullmatch(r'[\d.,$%]+', v):
                raw.append(f'{lab}: {v}')
        notes = s(r.get('notes'))
        raw = ' | '.join(raw)[:400]
        for ph in phases_for(s(r.get('plan'))):
            key = 'funded' if ph in ('funded', 'instant') else 'eval'
            # the cons % for "mpl 30%" style rules is a max position loss, not consistency
            c = cons[key]
            mpl_v = mpl
            row = {
                'firm': s(r.get('firm')), 'plan': s(r.get('plan')), 'account_size_usd': size, 'phase': ph,
                'profit_target_usd': num(r.get('profit_target_usd')) if ph == 'eval' else None,
                'max_drawdown_usd': num(r.get('max_drawdown_usd')),
                'drawdown_type': dd_type(ddt), 'drawdown_locks_at': dd_lock(ddt),
                'daily_loss_usd': daily,
                'max_position_loss_pct': mpl_v,
                'consistency_pct': c, 'consistency_basis': basis if c else None,
                'min_days': days[key], 'duration_days': duration(s(r.get('min_days')) + ' ' + notes) if ph == 'eval' else None,
                'profit_split_pct': split_pct(r.get('profit_split')) if ph != 'eval' else None,
                'payout_min_usd': num(r.get('payout_min_usd')) if ph != 'eval' else None,
                'commission_per_side_micro_usd': mi, 'commission_per_side_mini_usd': ma,
                'list_price_usd': num(r.get('list_price_usd')),
                'activation_fee_usd': money_or_zero(r.get('activation_fee_usd')),
                'monthly_fee_funded_usd': money_or_zero(r.get('monthly_or_data_fee_funded_usd')),
                'checked_date': s(r.get('checked_date')) or None, 'source_url': s(r.get('source_url')) or None,
                'raw_notes': raw or None,
            }
            row.update(OVERRIDES.get(row['firm'], {}))
            out.append(row)
    doc = {'schema_version': 1, 'updated': datetime.date.today().isoformat(), 'category': 'futures',
           'note': 'Parsed from free text; raw_notes keeps the original wording. null = none or not published.',
           'rows': out}
    with open(OUT, 'w') as f:
        json.dump(doc, f, separators=(',', ':'), ensure_ascii=False)
    return doc


if __name__ == '__main__':
    d = build()
    print(len(d['rows']), 'rows ->', OUT, os.path.getsize(OUT) // 1024, 'KB')
