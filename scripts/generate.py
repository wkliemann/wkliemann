#!/usr/bin/env python3
"""Profile pipeline: extract GitHub data -> transform -> render animated SVG cards.

Runs daily via .github/workflows/refresh.yml. Stdlib only.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

USER = os.environ.get("GH_USER", "wkliemann")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = Path(__file__).resolve().parent.parent / "assets"

MONO = "ui-monospace,SFMono-Regular,'JetBrains Mono',Menlo,Consolas,monospace"
SANS = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
C = {
    "bg": "#0b0f17", "panel": "#0f1522", "line": "#1e2a3d", "text": "#c9d4e5",
    "dim": "#5f6f89", "cyan": "#22d3ee", "violet": "#a78bfa", "green": "#34d399",
    "amber": "#fbbf24", "pink": "#f472b6",
}


# ---------- extract ----------
def gh(path=None, graphql=None):
    url = "https://api.github.com/graphql" if graphql else f"https://api.github.com/{path}"
    data = json.dumps({"query": graphql}).encode() if graphql else None
    req = urllib.request.Request(url, data=data, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"{USER}-profile-pipeline",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def extract():
    user = gh(f"users/{USER}")
    repos = gh(f"users/{USER}/repos?per_page=100&sort=pushed")
    calendar = None
    if TOKEN:
        try:
            q = f'{{user(login:"{USER}"){{contributionsCollection{{contributionCalendar' \
                f'{{totalContributions weeks{{contributionDays{{date contributionCount}}}}}}}}}}}}'
            calendar = gh(graphql=q)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        except Exception as e:  # keep the pipeline green without GraphQL
            print("graphql failed:", e)
    return user, repos, calendar


# ---------- transform ----------
def transform(user, repos, calendar):
    own = [r for r in repos if not r["fork"]]
    last = max(repos, key=lambda r: r["pushed_at"]) if repos else None
    m = {
        "name": user.get("name") or USER,
        "bio": user.get("bio") or "",
        "company": (user.get("company") or "").lstrip("@"),
        "location": user.get("location") or "",
        "public_repos": user.get("public_repos", 0),
        "own_repos": len(own),
        "followers": user.get("followers", 0),
        "years": datetime.now(timezone.utc).year - int(user["created_at"][:4]),
        "last_repo": last["name"] if last else "-",
        "last_push": last["pushed_at"][:10] if last else "-",
        "weeks": [], "total": 0, "streak": 0, "best_day": ("-", 0), "active_days": 0,
    }
    if calendar:
        days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
        m["total"] = calendar["totalContributions"]
        m["weeks"] = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in calendar["weeks"]]
        m["active_days"] = sum(1 for d in days if d["contributionCount"])
        best = max(days, key=lambda d: d["contributionCount"])
        m["best_day"] = (best["date"], best["contributionCount"])
        streak = 0
        for d in reversed(days):
            if d["contributionCount"]:
                streak += 1
            elif streak or d["date"] != datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                break
        m["streak"] = streak
    return m


# ---------- render ----------
def window(w, h, title, body, css=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
<style>
text{{font-family:{MONO};font-size:13px;fill:{C["text"]}}}
.d{{fill:{C["dim"]}}}.c{{fill:{C["cyan"]}}}.v{{fill:{C["violet"]}}}.g{{fill:{C["green"]}}}.a{{fill:{C["amber"]}}}.p{{fill:{C["pink"]}}}
.ln{{opacity:0;animation:in .35s ease-out forwards}}
@keyframes in{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}
{css}
</style>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="12" fill="{C["bg"]}" stroke="{C["line"]}"/>
<path d="M.5 12.5a12 12 0 0 1 12-12h{w-25}a12 12 0 0 1 12 12v22h-{w-1}z" fill="{C["panel"]}"/>
<line x1="0" y1="34.5" x2="{w}" y2="34.5" stroke="{C["line"]}"/>
<circle cx="22" cy="18" r="5.5" fill="#ff5f57"/><circle cx="40" cy="18" r="5.5" fill="#febc2e"/><circle cx="58" cy="18" r="5.5" fill="#28c840"/>
<text x="{w/2}" y="22" text-anchor="middle" class="d" style="font-size:12px">{escape(title)}</text>
{body}
</svg>'''


def trace_svg(m):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    T = lambda s: escape(str(s))
    lines = [
        f'<tspan class="g">❯</tspan> <tspan class="c">agent</tspan> run --task <tspan class="a">"introduce {T(USER)}"</tspan> --tools github,memory',
        '',
        f'<tspan class="v">◆ plan</tspan>  <tspan class="d">3 tool calls · parallel=true · model=claude</tspan>',
        f'<tspan class="d">↳</tspan> <tspan class="c">github.profile</tspan>(user=<tspan class="a">"{T(USER)}"</tspan>)',
        f'   <tspan class="g">✓</tspan> {T(m["name"])} <tspan class="d">—</tspan> {T(m["bio"])}',
        f'   <tspan class="g">✓</tspan> <tspan class="d">org</tspan> @{T(m["company"])}  <tspan class="d">loc</tspan> {T(m["location"])}  <tspan class="d">on github</tspan> {m["years"]}y',
        f'<tspan class="d">↳</tspan> <tspan class="c">github.activity</tspan>(window=<tspan class="a">"365d"</tspan>)',
        f'   <tspan class="g">✓</tspan> <tspan class="p">{m["total"]}</tspan> contributions · <tspan class="p">{m["active_days"]}</tspan> active days · last push <tspan class="v">{T(m["last_repo"])}</tspan> @ {T(m["last_push"])}',
        f'<tspan class="d">↳</tspan> <tspan class="c">memory.recall</tspan>(key=<tspan class="a">"focus"</tspan>)',
        f'   <tspan class="g">✓</tspan> data platforms · AI agents · MCP · observability · infra as code',
        '',
        f'<tspan class="v">◆ answer</tspan>',
        f'   <tspan class="a">"I build the plumbing that turns raw data into decisions —</tspan>',
        f'   <tspan class="a"> and the agents that act on them."</tspan>',
        '',
        f'<tspan class="g">✔ done</tspan> <tspan class="d">· pipeline refreshed {stamp} · next run in 24h</tspan>',
    ]
    y0, lh, step = 62, 21, 0.45
    body = []
    for i, l in enumerate(lines):
        if l:
            body.append(f'<text x="22" y="{y0 + i*lh}" xml:space="preserve" class="ln" style="animation-delay:{0.3 + i*step:.2f}s">{l}</text>')
    cy = y0 + (len(lines) - 1) * lh
    css = f".cur{{opacity:0;animation:in .1s {0.3 + len(lines)*step:.2f}s forwards,blink 1s {0.4 + len(lines)*step:.2f}s step-end infinite}}" \
          "@keyframes blink{50%{fill-opacity:0}}"
    body.append(f'<rect class="cur" x="22" y="{cy + 12}" width="8" height="15" fill="{C["green"]}"/>')
    return window(860, cy + 44, f"~/{USER} — agent.run", "\n".join(body), css)


def telemetry_svg(m):
    w, h = 860, 210
    weeks = m["weeks"] or [0]
    peak = max(weeks) or 1
    x0, x1, base, top = 24, 540, 178, 78
    dx = (x1 - x0) / max(len(weeks) - 1, 1)
    pts = [(x0 + i * dx, base - (v / peak) * (base - top)) for i, v in enumerate(weeks)]
    path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = f"{path} L{x1} {base} L{x0} {base}Z"
    bars = "".join(
        f'<rect x="{x - dx*0.3:.1f}" y="{y:.1f}" width="{dx*0.6:.1f}" height="{base - y:.1f}" fill="{C["cyan"]}" opacity=".12"/>'
        for x, y in pts)
    lx, ly = pts[-1]
    kpis = [
        ("CONTRIBUTIONS", m["total"], "c"),
        ("ACTIVE DAYS", m["active_days"], "v"),
        ("CURRENT STREAK", f'{m["streak"]}d', "g"),
        ("BEST DAY", f'{m["best_day"][1]}', "p"),
    ]
    tiles = []
    for i, (label, val, cls) in enumerate(kpis):
        tx, ty = 572 + (i % 2) * 140, 58 + (i // 2) * 72
        tiles.append(
            f'<g class="ln" style="animation-delay:{1.2 + i*0.15:.2f}s">'
            f'<rect x="{tx}" y="{ty}" width="128" height="60" rx="8" fill="{C["panel"]}" stroke="{C["line"]}"/>'
            f'<text x="{tx+12}" y="{ty+20}" class="d" style="font-size:10px;letter-spacing:.06em">{label}</text>'
            f'<text x="{tx+12}" y="{ty+47}" class="{cls}" style="font-size:24px;font-weight:700;font-family:{SANS}">{val}</text></g>')
    body = f'''
<defs><linearGradient id="fa" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{C["cyan"]}" stop-opacity=".35"/><stop offset="1" stop-color="{C["cyan"]}" stop-opacity="0"/></linearGradient></defs>
<text x="24" y="60" class="d" style="font-size:11px;letter-spacing:.08em">WEEKLY CONTRIBUTIONS · LAST 52 WEEKS</text>
<text x="540" y="60" text-anchor="end" class="d" style="font-size:11px">peak {peak}/wk</text>
<line x1="{x0}" y1="{base}.5" x2="{x1}" y2="{base}.5" stroke="{C["line"]}"/>
{bars}
<path d="{area}" fill="url(#fa)" class="ln" style="animation-delay:1s"/>
<path d="{path}" fill="none" stroke="{C["cyan"]}" stroke-width="2" stroke-linejoin="round" pathLength="1" class="draw"/>
<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{C["cyan"]}" class="ln pulse" style="animation-delay:1.6s"/>
{"".join(tiles)}
'''
    css = ".draw{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.6s .2s ease-out forwards}" \
          "@keyframes draw{to{stroke-dashoffset:0}}" \
          ".pulse{animation:in .3s 1.6s forwards,pl 2s 2s ease-in-out infinite}@keyframes pl{50%{r:7;fill-opacity:.4}}"
    return window(w, h, "telemetry.live — github → transform → svg", body, css)


def main():
    m = transform(*extract())
    OUT.mkdir(exist_ok=True)
    (OUT / "agent-trace.svg").write_text(trace_svg(m), encoding="utf-8")
    (OUT / "telemetry.svg").write_text(telemetry_svg(m), encoding="utf-8")
    print(json.dumps({k: v for k, v in m.items() if k != "weeks"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
