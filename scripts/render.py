"""
Render the neofetch-style profile card as dark_mode.svg and light_mode.svg.

Run by .github/workflows/profile.yml. Standard library only.

    GH_TOKEN=... GH_USER=LASR-0 python scripts/render.py

Without GH_TOKEN it renders with placeholder stats (for local previews).
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ART = json.loads((ROOT / "scripts" / "art.json").read_text())
USER = os.environ.get("GH_USER", "LASR-0")
TOKEN = os.environ.get("GH_TOKEN")

# ── Static profile content ────────────────────────────────────────────────
HOST = f"luke@{USER}"
# (title, key colour class, rows)
SECTIONS = [
    (None, "k_id", [
        ("OS", "Arch Linux (Omarchy)"),
        ("WM", "Hyprland"),
        ("Location", "Australia"),
        ("Role", "IT Support @ KSB Australia"),
        ("Builds", "Internal tools, desktop apps"),
    ]),
    ("Stack", "k_stack", [
        ("Main", "TypeScript, React, C#"),
        ("Web", "HTML, CSS, JavaScript"),
        ("Data", "MySQL, SQLite"),
        ("Tools", "Git, Docker, Electron, Figma"),
    ]),
    ("Hobbies", "k_hobby", [
        ("Hardware", "3D printing, ITX builds"),
        ("Tinkering", "Pi, Arduino, Linux ricing"),
        ("Art", "Oil, acrylic, digital, minis"),
    ]),
]

# neofetch-style colour strip: one swatch per class, drawn as rects.
PALETTE = "palette"
PALETTE_CLASSES = ["f1", "f3", "f5", "k_id", "k_hobby", "k_stack", "k_stat", "host", "v_up"]

# ── Layout ────────────────────────────────────────────────────────────────
INFO_COLS = 44          # width of the info panel in characters
FONT_SIZE = 14
CHAR_W = 8.6            # generous monospace advance at 14px (Menlo/DejaVu ~8.43)
LINE_H = 19
PAD_X, PAD_Y = 26, 30
GAP = 26

THEMES = {
    "dark": {
        "bg": "#15131f", "border": "#2b2740",
        "f0": "#36335a", "f1": "#45416f", "f2": "#504c80", "f3": "#65609b",
        "f4": "#7c77b6", "f5": "#9893cf", "f6": "#b6b2e6",
        "E": "#f4a62a", "e": "#c8701c", "p": "#4a3514",
        "c": "#7fa696", "b": "#b4cfc6",
        "dots": "#3a3656", "val": "#e9e4f5", "rule": "#433e66", "at": "#6e6899",
        "host": "#f4a62a",
        "k_id": "#b6a8e8", "k_stack": "#8ec5b0", "k_hobby": "#e2a6d6",
        "k_stat": "#f2877c", "v_stat": "#f6b24e", "v_up": "#f7c98b",
    },
    "light": {
        "bg": "#f4f2fa", "border": "#dcd7ee",
        "f0": "#bdb8de", "f1": "#aca6d6", "f2": "#8e87c3", "f3": "#6f67ad",
        "f4": "#544b94", "f5": "#3d3478", "f6": "#29225c",
        "E": "#d98508", "e": "#a95a0e", "p": "#e2cfa6",
        "c": "#4f7d6c", "b": "#6e958a",
        "dots": "#cfcae3", "val": "#28233f", "rule": "#cfcae3", "at": "#9a93c4",
        "host": "#b86a00",
        "k_id": "#5b4ea3", "k_stack": "#2f7a60", "k_hobby": "#98458f",
        "k_stat": "#c2463b", "v_stat": "#b86a00", "v_up": "#9a5a12",
    },
}


# ── GitHub stats ──────────────────────────────────────────────────────────
def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats():
    if not TOKEN:
        print("GH_TOKEN not set: rendering placeholder stats", file=sys.stderr)
        return {"repos": 0, "stars": 0, "commits": 0, "followers": 0,
                "created": "2023-01-01T00:00:00Z"}

    user = gql(
        """query($login: String!) {
          user(login: $login) {
            createdAt
            followers { totalCount }
            contributionsCollection { contributionYears }
          }
        }""",
        {"login": USER},
    )["user"]

    repos, stars, cursor = 0, 0, None
    while True:
        page = gql(
            """query($login: String!, $cursor: String) {
              user(login: $login) {
                repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                             first: 100, after: $cursor) {
                  totalCount
                  pageInfo { hasNextPage endCursor }
                  nodes { stargazerCount }
                }
              }
            }""",
            {"login": USER, "cursor": cursor},
        )["user"]["repositories"]
        repos = page["totalCount"]
        stars += sum(n["stargazerCount"] for n in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    commits = 0
    for year in user["contributionsCollection"]["contributionYears"]:
        commits += gql(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) { totalCommitContributions }
              }
            }""",
            {"login": USER, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
        )["user"]["contributionsCollection"]["totalCommitContributions"]

    return {"repos": repos, "stars": stars, "commits": commits,
            "followers": user["followers"]["totalCount"], "created": user["createdAt"]}


def uptime(created_iso):
    start = datetime.fromisoformat(created_iso.replace("Z", "+00:00")).date()
    today = datetime.now(timezone.utc).date()
    years = today.year - start.year
    months = today.month - start.month
    days = today.day - start.day
    if days < 0:
        months -= 1
        prev_month_end = date(today.year, today.month, 1).toordinal() - 1
        days += date.fromordinal(prev_month_end).day
    if months < 0:
        years -= 1
        months += 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


# ── Info panel as coloured segments ───────────────────────────────────────
# Each line is a list of (text, class) segments.
def kv(key, value, width, kclass="k_id", vclass="val"):
    dots = max(1, width - len(key) - len(value) - 2)
    return [(key, kclass), (" " + "." * dots + " ", "dots"), (value, vclass)]


def header(title, cls):
    return [("─ ", "rule"), (title, cls), (" " + "─" * (INFO_COLS - len(title) - 3), "rule")]


def info_lines(stats):
    lines = [[("luke", "host"), ("@", "at"), (USER, "val"),
              (" " + "─" * (INFO_COLS - len(HOST) - 1), "rule")]]
    for title, kclass, rows in SECTIONS:
        if title:
            lines += [[], header(title, kclass)]
        lines += [kv(k, v, INFO_COLS, kclass) for k, v in rows]

    half = (INFO_COLS - 3) // 2
    right = INFO_COLS - 3 - half
    pair = lambda a, b: (kv(a[0], a[1], half, "k_stat", "v_stat") + [(" | ", "dots")]
                         + kv(b[0], b[1], right, "k_stat", "v_stat"))
    lines += [
        [], header("GitHub", "k_stat"),
        pair(("Repos", str(stats["repos"])), ("Stars", str(stats["stars"]))),
        pair(("Commits", f"{stats['commits']:,}"), ("Followers", str(stats["followers"]))),
        kv("Uptime", uptime(stats["created"]), INFO_COLS, "k_stat", "v_up"),
        [], PALETTE,
    ]
    return lines


# ── SVG ───────────────────────────────────────────────────────────────────
def tspans(segments):
    return "".join(f'<tspan class="{c}">{escape(t)}</tspan>' for t, c in segments if t)


def art_segments(text, classes):
    segs, cur, cur_cls = [], "", None
    for ch, cl in zip(text, classes):
        cls = "sp" if cl == " " else (f"f{cl}" if cl.isdigit() else cl)
        if cls != cur_cls and cur:
            segs.append((cur, cur_cls))
            cur = ""
        cur, cur_cls = cur + ch, cls
    if cur:
        segs.append((cur, cur_cls))
    return segs


def render(theme, info):
    t = THEMES[theme]
    art_rows = ART["rows"]
    n_rows = max(len(art_rows), len(info))
    art_w = ART["cols"] * CHAR_W
    info_x = PAD_X + art_w + GAP
    width = round(info_x + INFO_COLS * CHAR_W + PAD_X)
    height = round(PAD_Y * 2 + (n_rows - 1) * LINE_H + FONT_SIZE)
    info_top = (n_rows - len(info)) // 2   # centre the panel against the art

    css = "\n".join(f".{k}{{fill:{v}}}" for k, v in t.items() if k not in ("bg", "border"))
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{HOST}">',
        "<style>",
        "text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',"
        f"'Liberation Mono',monospace;font-size:{FONT_SIZE}px;white-space:pre}}",
        ".sp{fill:none}",
        css,
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" '
        f'fill="{t["bg"]}" stroke="{t["border"]}"/>',
    ]
    base = PAD_Y + FONT_SIZE
    for i, (text, classes) in enumerate(art_rows):
        y = base + i * LINE_H
        out.append(f'<text x="{PAD_X}" y="{y}" xml:space="preserve">'
                   f"{tspans(art_segments(text, classes))}</text>")
    for i, segs in enumerate(info):
        y = base + (info_top + i) * LINE_H
        if segs == PALETTE:
            sw = CHAR_W * 3
            for j, cls in enumerate(PALETTE_CLASSES):
                out.append(f'<rect class="{cls}" x="{info_x + j * sw:.1f}" y="{y - FONT_SIZE + 2}" '
                           f'width="{sw - 3:.1f}" height="{FONT_SIZE}" rx="2"/>')
        elif segs:
            out.append(f'<text x="{info_x:.1f}" y="{y}" xml:space="preserve">{tspans(segs)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    info = info_lines(fetch_stats())
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, info), encoding="utf-8")
    print("wrote dark_mode.svg, light_mode.svg")


if __name__ == "__main__":
    main()
