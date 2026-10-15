"""Render GitHub stats as a dashboard KPI card (dark + light SVG).

    python scripts/stats_card.py --login rade-nugroho --out assets   # needs GITHUB_TOKEN
    python scripts/stats_card.py --self-test
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request

from contrib_candles import MONTHS, THEMES, fmt

# shortcut: stars cover the first 100 owned repos, add pagination past that
QUERY = """query($login: String!) { user(login: $login) {
  createdAt followers { totalCount }
  repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) { nodes { stargazerCount forkCount } }
  repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, PULL_REQUEST_REVIEW]) { totalCount }
  contributionsCollection { totalCommitContributions totalPullRequestContributions totalIssueContributions
    totalPullRequestReviewContributions contributionCalendar { totalContributions
      weeks { contributionDays { date contributionCount } } } } } }"""

W, H = 880, 300
MIX = [("Commits", "commits", "#3fb950"), ("Pull requests", "prs", "#58a6ff"),
       ("Issues", "issues", "#d29922"), ("Reviews", "reviews", "#bc8cff")]


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body,
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(f"GraphQL error: {data['errors']}")
    u = data["data"]["user"]
    c = u["contributionsCollection"]
    days = [d["contributionCount"] for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return dict(since=u["createdAt"][:10], followers=u["followers"]["totalCount"],
                stars=sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
                forks=sum(r["forkCount"] for r in u["repositories"]["nodes"]),
                contributed=u["repositoriesContributedTo"]["totalCount"],
                commits=c["totalCommitContributions"], prs=c["totalPullRequestContributions"],
                issues=c["totalIssueContributions"], reviews=c["totalPullRequestReviewContributions"],
                total=c["contributionCalendar"]["totalContributions"], days=days)


def streaks(days):
    """(current, longest) runs of days with contributions; a quiet today doesn't break the current run."""
    longest = run = 0
    for n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    tail = days[:-1] if days and not days[-1] else days
    current = 0
    for n in reversed(tail):
        if not n:
            break
        current += 1
    return current, longest


def render(s, theme, today):
    t = THEMES[theme]
    cur, best = streaks(s["days"])
    since = dt.date.fromisoformat(s["since"])
    mix_total = sum(s[k] for _, k, _ in MIX) or 1

    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">')
    a('<title id="t">GitHub stats</title>')
    a(f'<desc id="d">{fmt(s["commits"])} commits, {fmt(s["prs"])} pull requests, {fmt(s["issues"])} issues, '
      f'{fmt(s["reviews"])} reviews; contributed to {s["contributed"]} repositories; {s["stars"]} stars; '
      f'{s["followers"]} followers; current streak {cur} days, longest {best} days.</desc>')
    a('<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;'
      'font-variant-numeric:tabular-nums}</style>')
    a(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="{t["frame"]}" stroke="{t["border"]}"/>')
    a(f'<rect x="4.5" y="4.5" width="{W-9}" height="{H-9}" rx="10" fill="{t["panel"]}" stroke="{t["border"]}"/>')
    # header
    a(f'<text x="28" y="40" font-size="13" fill="{t["muted"]}">GitHub stats · member since '
      f'{MONTHS[since.month-1]} {since.year}</text>')
    a(f'<text x="{W-28}" y="40" font-size="12" text-anchor="end" fill="{t["muted"]}">Updated {MONTHS[today.month-1]} {today.day}, {today.year}</text>')
    a(f'<text x="28" y="78" font-size="30" font-weight="500" letter-spacing="-0.6" fill="{t["fg"]}">{fmt(s["commits"])}</text>')
    nx = 28 + 16.5 * len(fmt(s["commits"])) + 12
    a(f'<text x="{nx:.0f}" y="78" font-size="13" fill="{t["muted"]}">commits · '
      f'<tspan fill="{t["fg"]}">{fmt(s["prs"])}</tspan> pull requests in the last year</text>')
    # contribution mix: allocation bar + legend
    x0, bw, by = 28, W - 56, 100
    a(f'<rect x="{x0}" y="{by}" width="{bw}" height="10" rx="5" fill="{t["grid"]}"/>')
    a(f'<clipPath id="mix"><rect x="{x0}" y="{by}" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#mix)">')
    x = x0
    for _, k, col in MIX:
        w = s[k] / mix_total * bw
        a(f'<rect x="{x:.1f}" y="{by}" width="{max(0.0, w - 2):.1f}" height="10" fill="{col}"/>')
        x += w
    a('</g>')
    lx = x0
    for label, k, col in MIX:
        txt = f'{label} {s[k] / mix_total * 100:.0f}%'
        a(f'<circle cx="{lx+4}" cy="{by+27}" r="4" fill="{col}"/>')
        a(f'<text x="{lx+13}" y="{by+31}" font-size="12" fill="{t["muted"]}">{txt}</text>')
        lx += 13 + len(txt) * 6.6 + 22
    # KPI tiles
    tiles = [("Contributed to", fmt(s["contributed"]), "repositories"),
             ("Stars earned", fmt(s["stars"]), f'{fmt(s["forks"])} forks'),
             ("Followers", fmt(s["followers"]), "on GitHub"),
             ("Current streak", f"{cur}d", "days in a row"),
             ("Longest streak", f"{best}d", "best run")]
    gap, ty, th = 10, 156, 112
    tw = (W - 56 - gap * (len(tiles) - 1)) / len(tiles)
    recent = s["days"][-14:]
    for i, (label, value, sub) in enumerate(tiles):
        tx = 28 + i * (tw + gap)
        a(f'<rect x="{tx:.1f}" y="{ty}" width="{tw:.1f}" height="{th}" rx="10" fill="{t["frame"]}" stroke="{t["border"]}"/>')
        a(f'<text x="{tx+14:.1f}" y="{ty+26}" font-size="12" fill="{t["muted"]}">{label}</text>')
        a(f'<text x="{tx+14:.1f}" y="{ty+62}" font-size="28" font-weight="500" letter-spacing="-0.5" fill="{t["fg"]}">{value}</text>')
        if label == "Current streak":       # last 14 days as contribution cells, today on the right
            cw = (tw - 28 - 13 * 3) / 14
            for j, n in enumerate(recent):
                op = 0.18 if not n else min(1.0, 0.35 + n / max(recent) * 0.65)
                a(f'<rect x="{tx+14+j*(cw+3):.1f}" y="{ty+82}" width="{cw:.1f}" height="{cw:.1f}" rx="2" '
                  f'fill="{t["up"] if n else t["muted"]}" fill-opacity="{op:.2f}"/>')
        else:
            a(f'<text x="{tx+14:.1f}" y="{ty+94}" font-size="12" fill="{t["muted"]}">{sub}</text>')
    a('</svg>')
    return "\n".join(o)


def self_test():
    import xml.etree.ElementTree as ET
    assert streaks([1, 1, 0, 1, 1, 1, 0]) == (3, 3)          # quiet today keeps yesterday's run
    assert streaks([1, 1, 0, 1, 1, 1, 1]) == (4, 4)
    assert streaks([1, 1, 1, 0, 0, 1, 0]) == (1, 3)
    assert streaks([0, 0, 0]) == (0, 0)
    s = dict(since="2026-05-02", followers=14, stars=46, forks=18, contributed=122, commits=2864, prs=1657,
             issues=446, reviews=32, total=5112, days=[(i * 7) % 5 for i in range(120)])
    for th in THEMES:
        ET.fromstring(render(s, th, dt.date(2026, 10, 16)))
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
    s = fetch(a.login, token)
    today = dt.datetime.now(dt.timezone.utc).date()
    os.makedirs(a.out, exist_ok=True)
    for th in THEMES:
        path = os.path.join(a.out, f"github-stats-{th}.svg")
        with open(path, "w") as f:
            f.write(render(s, th, today) + "\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
