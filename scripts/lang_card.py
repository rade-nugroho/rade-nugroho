"""Render "most used languages" as a market-heatmap treemap (dark + light SVG).

Tile area = bytes of code per language, summed over the user's public non-fork repos plus every
non-fork repo of each --org the token can read (private ones included; only totals are shown).

    python scripts/lang_card.py --login rade-nugroho --org TANTIRA --out assets   # needs GITHUB_TOKEN
    python scripts/lang_card.py --self-test
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

from contrib_candles import MONTHS, THEMES, fmt

REPOS = """pageInfo { hasNextPage endCursor }
    nodes { isPrivate languages(first: 30, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }"""
QUERIES = {
    "user": """query($login: String!, $after: String) { owner: user(login: $login) {
  repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) { %s } } }""" % REPOS,
    "org": """query($login: String!, $after: String) { owner: organization(login: $login) {
  repositories(first: 100, after: $after, isFork: false) { %s } } }""" % REPOS,
}

W, H = 880, 482
TAPE_Y, TAPE_H, SLOT = 116, 26, 124   # ticker tape; every item gets a fixed slot so the loop is seamless
MAP_X, MAP_Y, MAP_W, MAP_H = 24, 154, W - 48, H - 154 - 24
GAP = 3
TOP_N = 10
TAPE_N = 14
ABBR = {"TypeScript": "TS", "JavaScript": "JS", "Python": "PY", "Rust": "RS", "Go": "GO", "Kotlin": "KT",
        "Java": "JV", "TeX": "TEX", "CSS": "CSS", "Shell": "SH", "C++": "C++", "C#": "C#", "Swift": "SW",
        "PHP": "PHP", "PLpgSQL": "SQL", "Dart": "DART", "Solidity": "SOL", "HTML": "HTML", "Handlebars": "HBS"}


def fetch(owners, token):
    """owners: [("user"|"org", login)]. Returns (languages sorted by size, repo count, private repo count)."""
    totals, colors, repos, n_repos, n_private = {}, {}, {}, 0, 0
    for kind, login in owners:
        after = None
        while True:
            body = json.dumps({"query": QUERIES[kind], "variables": {"login": login, "after": after}}).encode()
            req = urllib.request.Request("https://api.github.com/graphql", data=body,
                                         headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            if "errors" in data:
                sys.exit(f"GraphQL error: {data['errors']}")
            page = data["data"]["owner"]["repositories"]
            for repo in page["nodes"]:
                n_repos += 1
                n_private += repo["isPrivate"]
                for e in repo["languages"]["edges"]:
                    name = e["node"]["name"]
                    totals[name] = totals.get(name, 0) + e["size"]
                    colors[name] = e["node"]["color"] or "#8b949e"
                    repos[name] = repos.get(name, 0) + 1
            if not page["pageInfo"]["hasNextPage"]:
                break
            after = page["pageInfo"]["endCursor"]
    langs = [dict(name=n, size=s, color=colors[n], repos=repos[n]) for n, s in totals.items()]
    return sorted(langs, key=lambda l: -l["size"]), n_repos, n_private


def group(langs, top_n=TOP_N):
    head, tail = langs[:top_n], langs[top_n:]
    if tail:
        head.append(dict(name=f"+{len(tail)} more", size=sum(l["size"] for l in tail), color=None,
                         repos=None, other=True))
    return head


def squarify(sizes, x, y, w, h):
    """Bruls et al. squarified treemap: rects (x, y, w, h) in input order, areas proportional to sizes."""
    total = sum(sizes)
    areas = [s * w * h / total for s in sizes]
    rects, i = [], 0
    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        worst = lambda r: max(max(r) * side * side / sum(r) ** 2, sum(r) ** 2 / (min(r) * side * side))
        while i + len(row) < len(areas) and worst(row + [areas[i + len(row)]]) <= worst(row):
            row.append(areas[i + len(row)])
        thick = sum(row) / side
        pos = 0.0
        for a in row:
            length = a / thick
            # wide area: the row is a column on the left; tall area: a row along the top
            rects.append((x, y + pos, thick, length) if w >= h else (x + pos, y, length, thick))
            pos += length
        if w >= h:
            x, w = x + thick, w - thick
        else:
            y, h = y + thick, h - thick
        i += len(row)
    return rects


def mb(n):
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def ink(hex_color):
    """Dark or light label text for a tile colour (WCAG relative luminance)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return ("#0d1117", "rgba(13,17,23,0.62)") if lum > 0.32 else ("#ffffff", "rgba(255,255,255,0.72)")


def render(langs, n_repos, n_private, theme, today):
    t = THEMES[theme]
    total = sum(l["size"] for l in langs)
    tiles = group(langs)
    rects = squarify([l["size"] for l in tiles], MAP_X, MAP_Y, MAP_W, MAP_H)
    lead = langs[0]
    over1 = sum(1 for l in langs if l["size"] / total >= 0.01)
    other_fill = t["grid"] if theme == "dark" else "#eaeef2"

    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">')
    a('<title id="t">Most used languages</title>')
    a('<desc id="d">' + escape("; ".join(f'{l["name"]} {l["size"] / total * 100:.1f}%' for l in langs[:TOP_N]))
      + f' across {n_repos} repositories ({n_private} private).</desc>')
    a('<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;'
      'font-variant-numeric:tabular-nums}'
      # the sheen starts off-canvas, so a renderer that freezes at t=0 or ignores CSS shows nothing extra
      '.sh{animation:sh 7s cubic-bezier(.45,0,.2,1) infinite}'
      f'@keyframes sh{{0%{{transform:translateX(-260px)}}55%,100%{{transform:translateX({W + 260}px)}}}}'
      f'.tp{{animation:tp {TAPE_N * 2.2:.0f}s linear infinite}}'
      f'@keyframes tp{{to{{transform:translateX(-{min(TAPE_N, len(langs)) * SLOT}px)}}}}'
      '@media (prefers-reduced-motion:reduce){.sh,.tp{animation:none}}</style>')
    a('<defs>')
    a('<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.16"/>'
      '<stop offset="0.45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.18"/></linearGradient>')
    a('<linearGradient id="beam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
      '<stop offset="0.5" stop-color="#fff" stop-opacity="0.22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    a(f'<clipPath id="tape"><rect x="{MAP_X}" y="{TAPE_Y}" width="{MAP_W}" height="{TAPE_H}" rx="8"/></clipPath>')
    a(f'<clipPath id="map"><rect x="{MAP_X}" y="{MAP_Y}" width="{MAP_W}" height="{MAP_H}" rx="10"/></clipPath>')
    a(f'<radialGradient id="halo" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{lead["color"]}" stop-opacity="0.35"/>'
      f'<stop offset="1" stop-color="{lead["color"]}" stop-opacity="0"/></radialGradient>')
    a('</defs>')
    a(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="{t["frame"]}" stroke="{t["border"]}"/>')
    a(f'<rect x="4.5" y="4.5" width="{W-9}" height="{H-9}" rx="10" fill="{t["panel"]}" stroke="{t["border"]}"/>')
    # header: market-dominance framing
    a(f'<text x="28" y="40" font-size="13" fill="{t["muted"]}">Most used languages · by code size · {n_repos} repos · {n_private} private</text>')
    a(f'<text x="{W-28}" y="40" font-size="12" text-anchor="end" fill="{t["muted"]}">Updated {MONTHS[today.month-1]} {today.day}, {today.year}</text>')
    a(f'<circle cx="38" cy="68" r="22" fill="url(#halo)"/>')
    a(f'<circle cx="38" cy="68" r="7" fill="{lead["color"]}"/>')
    a(f'<text x="56" y="78" font-size="30" font-weight="500" letter-spacing="-0.6" fill="{t["fg"]}">{escape(lead["name"])}</text>')
    nx = 56 + 15.5 * len(lead["name"]) + 12     # approx. advance of the 30px headline
    a(f'<text x="{nx:.0f}" y="78" font-size="13"><tspan fill="{t["up"]}">{lead["size"] / total * 100:.1f}%</tspan>'
      f'<tspan fill="{t["muted"]}"> dominance</tspan></text>')
    a(f'<text x="28" y="102" font-size="12" fill="{t["muted"]}">{mb(total)} of code · {len(langs)} languages · '
      f'{over1} above 1% · {escape(lead["name"])} in {lead["repos"]} repos</text>')
    # ticker tape: enough copies of the list to cover the strip twice, scrolled by exactly one list width
    tape = langs[:TAPE_N]
    copies = -(-MAP_W // (len(tape) * SLOT)) + 1
    a(f'<rect x="{MAP_X+0.5}" y="{TAPE_Y+0.5}" width="{MAP_W-1}" height="{TAPE_H-1}" rx="8" fill="{t["frame"]}" stroke="{t["border"]}"/>')
    a('<g clip-path="url(#tape)"><g class="tp">')
    for k in range(copies * len(tape)):
        l = tape[k % len(tape)]
        x0 = MAP_X + 14 + k * SLOT
        a(f'<circle cx="{x0+3}" cy="{TAPE_Y+TAPE_H/2:.1f}" r="3.5" fill="{l["color"]}"/>')
        a(f'<text x="{x0+12}" y="{TAPE_Y+17}" font-size="11"><tspan font-weight="600" fill="{t["fg"]}">'
          f'{escape(ABBR.get(l["name"], l["name"][:10]).upper())}</tspan>'
          f'<tspan fill="{t["muted"]}"> {l["size"] / total * 100:.2f}%</tspan></text>')
    a('</g></g>')
    # treemap tiles
    a('<g clip-path="url(#map)">')
    for l, (x, y, w, h) in zip(tiles, rects):
        x, y, w, h = x + GAP / 2, y + GAP / 2, w - GAP, h - GAP
        if w <= 0 or h <= 0:
            continue
        fill = other_fill if l.get("other") else l["color"]
        fg, sub = (t["fg"], t["muted"]) if l.get("other") else ink(fill)
        pct = l["size"] / total * 100
        a(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="{fill}"/>')
        a(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="url(#gloss)"/>')
        a(f'<rect x="{x+0.5:.1f}" y="{y+0.5:.1f}" width="{w-1:.1f}" height="{h-1:.1f}" rx="5.5" fill="none" stroke="#fff" stroke-opacity="0.14"/>')
        ab = ABBR.get(l["name"])
        if ab and w > 150 and h > 110:             # big faint ticker glyph, like a coin logo on a heatmap
            gs = min(h * 0.62, w * 0.9 / len(ab) * 1.6)
            a(f'<text x="{x+w-14:.1f}" y="{y+h-14:.1f}" font-size="{gs:.0f}" font-weight="800" text-anchor="end" '
              f'letter-spacing="-2" fill="{fg}" fill-opacity="0.10">{ab}</text>')
        name = escape(l["name"])
        if w >= 96 and h >= 64:
            big = 30 if (w > 220 and h > 120) else 20
            a(f'<text x="{x+12:.1f}" y="{y+24:.1f}" font-size="13" font-weight="600" fill="{fg}">{name}</text>')
            a(f'<text x="{x+12:.1f}" y="{y+24+big+6:.1f}" font-size="{big}" font-weight="600" letter-spacing="-0.5" fill="{fg}">{pct:.1f}%</text>')
            meta = mb(l["size"]) + (f' · {l["repos"]} repo{"s" * (l["repos"] != 1)}' if l.get("repos") else "")
            if h >= 92 and w >= 120:
                a(f'<text x="{x+12:.1f}" y="{y+h-12:.1f}" font-size="11" fill="{sub}">{meta}</text>')
        elif w >= 44 and h >= 36:
            a(f'<text x="{x+8:.1f}" y="{y+17:.1f}" font-size="11" font-weight="600" fill="{fg}">{escape(ABBR.get(l["name"], l["name"][:8]))}</text>')
            a(f'<text x="{x+8:.1f}" y="{y+31:.1f}" font-size="11" fill="{sub}">{pct:.1f}%</text>')
        elif w >= 18 and h >= 64:                  # narrow sliver: vertical label
            a(f'<text transform="translate({x+w/2+4:.1f} {y+h-8:.1f}) rotate(-90)" font-size="11">'
              f'<tspan font-weight="600" fill="{fg}">{escape(ABBR.get(l["name"], l["name"][:8]))}</tspan>'
              f'<tspan fill="{sub}"> {pct:.1f}%</tspan></text>')
    a(f'<rect class="sh" x="0" y="{MAP_Y}" width="220" height="{MAP_H}" fill="url(#beam)" transform="translate(-260 0)"/>')
    a('</g>')
    a('</svg>')
    return "\n".join(s)


def self_test():
    import xml.etree.ElementTree as ET
    sizes = [60, 14, 8, 8, 4, 2, 1, 3]
    rects = squarify(sizes, 0, 0, 400, 200)
    total_area = 400 * 200
    for s_, (x, y, w, h) in zip(sizes, rects):
        assert abs(w * h - s_ / sum(sizes) * total_area) < 1e-6, "area must be proportional"
        assert -1e-6 <= x and x + w <= 400 + 1e-6 and -1e-6 <= y and y + h <= 200 + 1e-6, "tile out of bounds"
    for i, a_ in enumerate(rects):
        for b in rects[i + 1:]:
            ox = min(a_[0] + a_[2], b[0] + b[2]) - max(a_[0], b[0])
            oy = min(a_[1] + a_[3], b[1] + b[3]) - max(a_[1], b[1])
            assert ox <= 1e-6 or oy <= 1e-6, "tiles overlap"
    langs = [dict(name=n, size=s_, color=c, repos=r) for n, s_, c, r in
             [("TypeScript", 600, "#3178c6", 20), ("Python", 140, "#3572A5", 17), ("JavaScript", 84, "#f1e05a", 15),
              ("Rust", 81, "#dea584", 9), ("TeX", 37, "#3D6117", 2), ("Go", 19, "#00ADD8", 5), ("Kotlin", 11, "#A97BFF", 2),
              ("CSS", 8, "#663399", 15), ("Shell", 4, "#89e051", 13)]]
    g = group(langs, top_n=7)
    assert len(g) == 8 and g[-1]["size"] == 12 and g[-1].get("other")
    assert ink("#f1e05a")[0] == "#0d1117" and ink("#3178c6")[0] == "#ffffff"
    for th in THEMES:
        ET.fromstring(render(langs, 84, 44, th, dt.date(2026, 10, 16)))
    print("self-test ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--login", default="rade-nugroho")
    p.add_argument("--org", action="append", default=[], help="also count this org's repos (repeatable)")
    p.add_argument("--out", default="assets")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required")
    langs, n_repos, n_private = fetch([("user", a.login)] + [("org", o) for o in a.org], token)
    today = dt.datetime.now(dt.timezone.utc).date()
    os.makedirs(a.out, exist_ok=True)
    for th in THEMES:
        path = os.path.join(a.out, f"top-langs-{th}.svg")
        with open(path, "w") as f:
            f.write(render(langs, n_repos, n_private, th, today) + "\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
