"""Render GitHub contributions as a weekly candlestick chart with volume (dark + light SVG).

One candle per calendar week: open = first day, close = last day, high/low = busiest/quietest
day, volume = weekly total. Data comes from the GraphQL contribution calendar.

    python scripts/contrib_candles.py --login rade-nugroho --out assets   # needs GITHUB_TOKEN
    python scripts/contrib_candles.py --self-test
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

QUERY = """query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  weeks { contributionDays { date contributionCount } } } } } }"""

THEMES = {
    "dark": dict(frame="#010409", panel="#0d1117", border="#30363d", grid="#21262d", fg="#f0f6fc",
                 muted="#9198a1", up="#3fb950", down="#f85149", ref="#3d444d", tag_fg="#0d1117"),
    "light": dict(frame="#f6f8fa", panel="#ffffff", border="#d0d7de", grid="#eaeef2", fg="#1f2328",
                  muted="#59636e", up="#1a7f37", down="#cf222e", ref="#c9d1d9", tag_fg="#ffffff"),
}
# full = desktop README width; compact = phones (served via <picture media="(max-width: 600px)">)
LAYOUTS = {
    "full": dict(W=880, H=470, LEFT=64, RIGHT=72, PRICE_TOP=132, PRICE_H=220, VOL_TOP=376, VOL_H=56, weeks=None),
    "compact": dict(W=360, H=372, LEFT=40, RIGHT=56, PRICE_TOP=124, PRICE_H=150, VOL_TOP=290, VOL_H=44, weeks=13),
}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body,
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(f"GraphQL error: {data['errors']}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in weeks]


def candles(weeks):
    out = []
    for days in weeks:
        if not days:
            continue
        counts = [c for _, c in days]
        out.append(dict(start=days[0][0], open=counts[0], close=counts[-1],
                        high=max(counts), low=min(counts), volume=sum(counts)))
    return out


def trim(weeks, min_weeks=26):
    """Drop the quiet lead-in so active weeks get the width, but keep at least `min_weeks`."""
    vols = [sum(c for _, c in w) for w in weeks]
    floor = max(vols) * 0.02
    first = next((i for i, v in enumerate(vols) if v > floor), 0)
    return weeks[max(0, min(first, len(weeks) - min_weeks)):]


def nice_ticks(top, count=4):
    if top <= 0:
        return 1, [0, 1]
    raw = top / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s for s in (1, 2, 2.5, 5, 10) if raw / mag <= s) * mag
    hi = math.ceil(top / step) * step
    n = int(round(hi / step))
    return hi, [round(i * step, 6) for i in range(n + 1)]


def fmt(n):
    return f"{n:,.0f}" if abs(n) >= 1000 or float(n).is_integer() else f"{n:,.1f}"


def render(weeks, theme, today, size="full"):
    t = THEMES[theme]
    L = LAYOUTS[size]
    W, H, LEFT, RIGHT = L["W"], L["H"], L["LEFT"], L["RIGHT"]
    PRICE_TOP, PRICE_H, VOL_TOP, VOL_H = L["PRICE_TOP"], L["PRICE_H"], L["VOL_TOP"], L["VOL_H"]
    compact = size == "compact"
    all_days = [c for w in weeks for _, c in w]   # headline numbers cover the whole year, whatever the chart shows
    weeks = trim(weeks)[-L["weeks"]:] if L["weeks"] else trim(weeks)
    cs = candles(weeks)
    days = [c for w in weeks for _, c in w]
    n = len(cs)
    inner = W - LEFT - RIGHT
    slot = inner / n
    body = max(2.0, min(slot * 0.62, 14.0))
    top, ticks = nice_ticks(max(c["high"] for c in cs))
    vtop, _ = nice_ticks(max(c["volume"] for c in cs))
    x = lambda i: LEFT + slot * (i + 0.5)
    y = lambda v: PRICE_TOP + PRICE_H - v / top * PRICE_H
    vy = lambda v: VOL_TOP + VOL_H - v / vtop * (VOL_H - 14)

    total = sum(all_days)
    last7, prev7 = sum(all_days[-7:]), sum(all_days[-14:-7])
    delta = last7 - prev7
    pct = delta / prev7 * 100 if prev7 else 0.0
    sign = "+" if delta >= 0 else "−"
    delta_col = t["up"] if delta >= 0 else t["down"]
    peak_week = max(c["volume"] for c in cs)
    active = sum(1 for d in all_days if d)
    avg = sum(days) / len(days)                  # average over the charted weeks, drawn on the chart
    last = cs[-1]

    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'role="img" aria-labelledby="t d">')
    a(f'<title id="t">Weekly contribution candles for the last {n} weeks</title>')
    a(f'<desc id="d">{fmt(total)} contributions; last 7 days {fmt(last7)} ({sign}{abs(pct):.1f}% vs the 7 days before). '
      f'Peak day {fmt(max(all_days))}, peak week {fmt(peak_week)}.</desc>')
    a('<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;'
      'font-variant-numeric:tabular-nums}</style>')
    # frame + panel, like a dashboard card
    a(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="{t["frame"]}" stroke="{t["border"]}"/>')
    a(f'<rect x="4.5" y="4.5" width="{W-9}" height="{H-9}" rx="10" fill="{t["panel"]}" stroke="{t["border"]}"/>')
    # header
    a(f'<text x="28" y="40" font-size="13" fill="{t["muted"]}">Contributions · weekly candles · {n}W</text>')
    a(f'<text x="28" y="78" font-size="30" font-weight="500" letter-spacing="-0.6" fill="{t["fg"]}">{fmt(total)}</text>')
    delta_txt = (f'<tspan fill="{delta_col}">{sign}{fmt(abs(delta))} ({sign}{abs(pct):.1f}%)</tspan>'
                 f'<tspan fill="{t["muted"]}"> last 7 days</tspan>')
    if compact:   # narrow card: delta drops below the headline, secondary lines go
        a(f'<text x="28" y="100" font-size="13">{delta_txt}</text>')
    else:
        nx = 28 + 16.5 * len(fmt(total)) + 12      # approx. advance of the 30px headline digits
        a(f'<text x="{nx:.0f}" y="78" font-size="13">{delta_txt}</text>')
        a(f'<text x="28" y="100" font-size="12" fill="{t["muted"]}">Peak day {fmt(max(all_days))} · peak week {fmt(peak_week)} · '
          f'{active} active days</text>')
        a(f'<text x="{W-28}" y="40" font-size="12" text-anchor="end" fill="{t["muted"]}">Updated {MONTHS[today.month-1]} {today.day}, {today.year}</text>')
    # price grid
    for v in ticks:
        a(f'<line x1="{LEFT}" x2="{W-RIGHT}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{t["grid"]}" shape-rendering="crispEdges"/>')
        a(f'<text x="{LEFT-10}" y="{y(v)+4:.1f}" font-size="11" text-anchor="end" fill="{t["muted"]}">{fmt(v)}</text>')
    a(f'<line x1="{LEFT}" x2="{W-RIGHT}" y1="{y(avg):.1f}" y2="{y(avg):.1f}" stroke="{t["ref"]}" stroke-dasharray="4 4" shape-rendering="crispEdges"/>')
    if not compact:   # no room for the label among narrow candles
        a(f'<text x="{LEFT+6}" y="{y(avg)-5:.1f}" font-size="11" fill="{t["muted"]}">Avg {avg:.1f}/day</text>')
    # candles
    a('<g>')
    for i, c in enumerate(cs):
        col = t["up"] if c["close"] >= c["open"] else t["down"]
        b0, b1 = y(max(c["open"], c["close"])), y(min(c["open"], c["close"]))
        a(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(c["high"]):.1f}" y2="{y(c["low"]):.1f}" stroke="{col}" stroke-width="1.25"/>')
        a(f'<rect x="{x(i)-body/2:.1f}" y="{b0:.1f}" width="{body:.1f}" height="{max(1.0, b1-b0):.1f}" rx="1" fill="{col}"/>')
        bar_y = vy(c["volume"])
        op = 1 if i == n - 1 else 0.45
        a(f'<rect x="{x(i)-body/2:.1f}" y="{bar_y:.1f}" width="{body:.1f}" height="{max(1.0, VOL_TOP+VOL_H-bar_y):.1f}" '
          f'rx="1" fill="{col}" fill-opacity="{op}"/>')
    a('</g>')
    # last-close marker, trading-terminal style
    lc = t["up"] if last["close"] >= last["open"] else t["down"]
    ly = y(last["close"])
    a(f'<line x1="{x(n-1):.1f}" x2="{W-RIGHT+4}" y1="{ly:.1f}" y2="{ly:.1f}" stroke="{lc}" stroke-dasharray="2 3"/>')
    a(f'<rect x="{W-RIGHT+4}" y="{ly-10:.1f}" width="44" height="20" rx="5" fill="{lc}"/>')
    a(f'<text x="{W-RIGHT+26}" y="{ly+4:.1f}" font-size="11" font-weight="600" text-anchor="middle" fill="{t["tag_fg"]}">{fmt(last["close"])}</text>')
    # volume label + month axis
    a(f'<text x="{LEFT-10}" y="{VOL_TOP+10}" font-size="11" text-anchor="end" fill="{t["muted"]}">Vol</text>')
    a(f'<text x="{LEFT-10}" y="{VOL_TOP+24}" font-size="11" text-anchor="end" fill="{t["muted"]}">{fmt(vtop)}</text>')
    prev_month, last_x = None, -99
    for i, c in enumerate(cs):
        m = int(c["start"][5:7])
        if m != prev_month and x(i) - last_x >= 44:
            a(f'<text x="{x(i):.1f}" y="{VOL_TOP+VOL_H+20}" font-size="11" text-anchor="middle" fill="{t["muted"]}">{MONTHS[m-1]}</text>')
            last_x = x(i)
        prev_month = m
    a('</svg>')
    return "\n".join(s)


def self_test():
    import xml.etree.ElementTree as ET
    start = dt.date(2026, 1, 4)
    weeks = [[((start + dt.timedelta(days=w * 7 + d)).isoformat(), (w * 3 + d * 5) % 11) for d in range(7)] for w in range(20)]
    weeks[-1] = weeks[-1][:3]                     # partial current week
    c = candles(weeks)
    assert len(c) == 20
    assert c[0] == dict(start="2026-01-04", open=0, close=8, high=10, low=0, volume=sum((d * 5) % 11 for d in range(7)))
    assert c[-1]["volume"] == sum(n for _, n in weeks[-1]) and c[-1]["close"] == weeks[-1][-1][1]
    assert nice_ticks(275) == (300, [0, 100, 200, 300])
    quiet = [[("d", 0)] * 7] * 30 + [[("d", 50)] * 7] * 10
    assert len(trim(quiet)) == 26 and len(trim(quiet, min_weeks=5)) == 10
    for th in THEMES:
        for size in LAYOUTS:
            ET.fromstring(render(weeks, th, dt.date(2026, 5, 20), size))   # well-formed XML
    assert 'width="360"' in render(weeks, "dark", dt.date(2026, 5, 20), "compact")
    print("self-test ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--login", default="rade-nugroho")
    p.add_argument("--out", default="assets")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required")
    weeks = fetch(a.login, token)
    today = dt.date.fromisoformat(weeks[-1][-1][0])
    os.makedirs(a.out, exist_ok=True)
    for th in THEMES:
        for size in LAYOUTS:
            path = os.path.join(a.out, f"contrib-candles-{th}{'-compact' * (size == 'compact')}.svg")
            with open(path, "w") as f:
                f.write(render(weeks, th, today, size) + "\n")
            print("wrote", path)


if __name__ == "__main__":
    main()
