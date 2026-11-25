"""Draw the function map's coverage and its aspects as SVGs for the wiki home page.

    python -I tools/wiki_completeness.py [--index work/map/index] [--out work/wiki]

coverage.svg: two bars per region, one for the evidence behind each role (C string or symbol, I code shape, H
neighbours) and one for the share of bodies read.
aspects.svg: functions grouped by the aspect of the game their 256 KB window's theme names (the themes are the ones
the region pages give each window). Only windows whose strings name a theme are grouped; the subtitle says how many
functions that covers.

Both use CSS variables and a prefers-color-scheme rule, so they follow the reader's light or dark setting. The SVGs
are generated, never hand-edited; tools/wiki_build.py calls this after it writes the pages.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
REGIONS = [("A", 0x7000000000, 0x7000600000), ("B", 0x7000600000, 0x7000C00000),
           ("C", 0x7000C00000, 0x7001000000), ("D", 0x7001000000, 0x7001400000),
           ("E", 0x7001400000, 0x7001800000), ("F", 0x7001800000, 0x7001C22800)]

PALETTES = {
    False: dict(bg="#ffffff", fg="#16181d", fg2="#6b7280", grid="#e9ecef", track="#eef0f3",
                accent="#3f6fb0", none="#c9ced6", c="#2f7d5c", i="#5b7fb5", h="#c49a6c",
                read="#3b3b3b", unread="#e6e8eb"),
    True: dict(bg="#0d1117", fg="#e6edf3", fg2="#8b949e", grid="#21262d", track="#161b22",
               accent="#6f9bd6", none="#30363d", c="#3fa172", i="#6f9bd6", h="#c9a071",
               read="#c9d1d9", unread="#21262d"),
}

CLASSES = """.bg { fill: var(--bg); }
  .f1 { fill: var(--fg); }
  .f2 { fill: var(--fg2); }
  .grid { stroke: var(--grid); stroke-width: 1; }
  .c { fill: var(--c); } .i { fill: var(--i); } .h { fill: var(--h); }
  .read { fill: var(--read); } .unread { fill: var(--unread); }
  .bar { fill: var(--accent); }
  .track { fill: var(--track); }
  .onbar { fill: #ffffff; }
  text { font-family: ui-sans-serif, "Segoe UI", system-ui, Arial, sans-serif; }"""


def style(dark):
    root = " ".join(f"--{k}:{v};" for k, v in PALETTES[dark].items())
    return f"<style>\n  {CLASSES}\n  :root {{ {root} }}\n</style>"


def head(w, h, title, subtitle, aria, dark):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{aria}">', style(dark), f'<rect class="bg" width="{w}" height="{h}"/>',
            f'<text x="{LEFT}" y="26" font-size="16" font-weight="600" class="f1">{title}</text>',
            f'<text x="{LEFT}" y="45" font-size="11" class="f2">{subtitle}</text>']


LEFT, BW = 210, 600


def bar(x, y, w, h, parts):
    out, cx = [], x
    total = sum(n for n, _ in parts) or 1
    for n, color in parts:
        if not n:
            continue
        sw = w * n / total
        out.append(f'<rect x="{cx:.1f}" y="{y}" width="{sw:.1f}" height="{h}" rx="3" class="{color}"/>')
        cx += sw
    return out


def legend(y, items):
    out, x = [], LEFT
    for cls, text in items:
        out.append(f'<rect x="{x}" y="{y - 9}" width="10" height="10" rx="2" class="{cls}"/>')
        out.append(f'<text x="{x + 15}" y="{y}" font-size="10" class="f2">{text}</text>')
        x += 15 + 6 * len(text) + 20
    return out


def rows(index):
    data = [json.loads(l) for l in open(f"{index}/roles.jsonl", encoding="utf-8")]
    out = []
    for name, lo, hi in REGIONS + [("sdk", 0x7004C00000, 0x700524E231)]:
        rs = [r for r in data if r["module"] == ("sdk" if name == "sdk" else "main")
              and (name == "sdk" or lo <= int(r["addr"], 16) < hi)]
        c = {t: sum(1 for r in rs if r["tag"] == t) for t in "CIH"}
        out.append(dict(name=name, total=len(rs), C=c["C"], I=c["I"], H=c["H"],
                        read=sum(1 for r in rs if r.get("read"))))
    return out


def svg_coverage(rs, dark):
    w, top, rowh = 1000, 78, 50
    h = top + rowh * len(rs) + 44
    out = head(w, h, "Function map coverage",
               "upper bar: evidence behind the role (C string or symbol, I code shape, H neighbours). "
               "lower bar: body read.", "Function map coverage by region", dark)
    for pct in (0, 25, 50, 75, 100):
        x = LEFT + BW * pct / 100
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{h - 34}"/>')
        out.append(f'<text x="{x:.1f}" y="{top - 16}" font-size="9" class="f2" text-anchor="middle">{pct}%</text>')
    for i, r in enumerate(rs):
        y = top + i * rowh
        label = "sdk" if r["name"] == "sdk" else f"Region {r['name']}"
        out.append(f'<text x="10" y="{y + 13}" font-size="12" font-weight="600" class="f1">{label}</text>')
        out.append(f'<text x="10" y="{y + 28}" font-size="10" class="f2">{r["total"]:,} functions</text>')
        out += bar(LEFT, y, BW, 15, [(r["C"], "c"), (r["I"], "i"), (r["H"], "h")])
        out += bar(LEFT, y + 20, BW, 6, [(r["read"], "read"), (r["total"] - r["read"], "unread")])
        pct = lambda n: 100.0 * n / (r["total"] or 1)
        out.append(f'<text x="{LEFT + BW + 12}" y="{y + 12}" font-size="10" class="f2">'
                   f'C {pct(r["C"]):.0f}%   I {pct(r["I"]):.0f}%   H {pct(r["H"]):.0f}%</text>')
        out.append(f'<text x="{LEFT + BW + 12}" y="{y + 26}" font-size="10" class="f2">'
                   f'read {pct(r["read"]):.0f}%</text>')
    out += legend(h - 20, [("c", "C: string, symbol or import"), ("i", "I: code shape or call graph"),
                           ("h", "H: neighbours only"), ("read", "body read")])
    out.append("</svg>")
    return "\n".join(out) + "\n"

# Each window theme the region pages name, mapped to one aspect of the game. The order matters: the first
# substring found in the theme wins, so the more specific entries come first.
ASPECT_OF_THEME = [
    ("Player search and list screens", "Online and Diamond Dynasty"),
    ("Diamond Dynasty", "Online and Diamond Dynasty"),
    ("Content downloader", "Online and Diamond Dynasty"),
    ("Online network session", "Online and Diamond Dynasty"),
    ("Online party", "Online and Diamond Dynasty"),
    ("Vault:", "Online and Diamond Dynasty"),
    ("Online account login", "Online and Diamond Dynasty"),
    ("Online roster cache", "Online and Diamond Dynasty"),
    ("Texture and face-scan download", "Online and Diamond Dynasty"),
    ("Franchise and career setup", "Franchise, league and roster"),
    ("League and player data", "Franchise, league and roster"),
    ("Player database tables", "Franchise, league and roster"),
    ("Roster moves", "Franchise, league and roster"),
    ("Trades, team strategy", "Franchise, league and roster"),
    ("Player, team and stadium database", "Franchise, league and roster"),
    ("Road to the Show", "Road to the Show"),
    ("Road To The Show", "Road to the Show"),
    ("Create-player", "Road to the Show"),
    ("Options menus", "Menus and UI"),
    ("Dear ImGui", "Menus and UI"),
    ("UI widgets", "Menus and UI"),
    ("UI rendering", "Menus and UI"),
    ("Game-mode settings", "Menus and UI"),
    ("Presentation engine", "Presentation and animation"),
    ("Player animation", "Presentation and animation"),
    ("Play-event names", "Presentation and animation"),
    ("Scene/mesh loading", "Graphics and textures"),
    ("Texture decoding", "Graphics and textures"),
    ("NVN graphics device", "Graphics and textures"),
    ("Audio system", "Audio"),
    ("JSON parsing", "Data and serialization"),
    ("Reflection and serialization", "Data and serialization"),
    ("nlohmann JSON", "Data and serialization"),
    ("Generic parsers", "Data and serialization"),
    ("Class registration framework", "Data and serialization"),
    ("Stats, training", "Stats and records"),
    ("Game-record bookkeeping", "Stats and records"),
    ("Pitch and play analysis", "Gameplay: pitching"),
    ("Pickoffs, play-result text", "Gameplay: pitching"),
    ("Batting and catcher reactions", "Gameplay: batting"),
    ("Fielding: choosing fly-ball", "Gameplay: fielding"),
    ("Fielder catch and throw decisions", "Gameplay: fielding"),
    ("Fielder and runner avoidance", "Gameplay: fielding"),
    ("Runner and fielder work rings", "Gameplay: baserunning"),
    ("Runner leadoff", "Gameplay: baserunning"),
    ("In-play stance states", "Gameplay: in-play"),
]


def aspect_of(theme):
    for key, aspect in ASPECT_OF_THEME:
        if key in theme:
            return aspect
    return "Other themes"


def aspects(index):
    data = [json.loads(l) for l in open(f"{index}/roles.jsonl", encoding="utf-8")]
    themes = Counter(r["sub"] for r in data if r.get("sub") and not r["sub"].isdigit())
    out = Counter()
    for theme, n in themes.items():
        out[aspect_of(theme)] += n
    return out, sum(themes.values()), len(data)


def svg_aspects(counts, themed, total, dark):
    items = sorted(counts.items(), key=lambda kv: -kv[1])
    w, top, rowh = 1000, 148, 38
    h = top + rowh * len(items) + 14
    share = 100.0 * themed / (total or 1)
    subtitle = (f"{themed:,} of {total:,} functions ({share:.1f}%) carry a window theme; the bars split that "
                f"themed share. The strip shows how much of the whole map the themes cover.")
    out = head(w, h, "Functions by aspect of the game", subtitle, "Functions grouped by aspect of the game", dark)
    # coverage strip: themed against the whole map
    sy = 70
    out.append(f'<text x="{LEFT - 12}" y="{sy + 12}" font-size="11" class="f1" text-anchor="end">Map coverage</text>')
    out.append(f'<rect x="{LEFT}" y="{sy}" width="{BW}" height="16" rx="3" class="track"/>')
    out.append(f'<rect x="{LEFT}" y="{sy}" width="{BW * share / 100:.1f}" height="16" rx="3" class="bar"/>')
    if BW * share / 100 >= 60:
        out.append(f'<text x="{LEFT + BW * share / 100 - 7:.1f}" y="{sy + 12}" font-size="10" class="onbar" '
                   f'text-anchor="end">{share:.1f}% themed</text>')
    out.append(f'<text x="{LEFT + BW * share / 100 + 8:.1f}" y="{sy + 12}" font-size="10" class="f2">'
               f'no theme yet: {100 - share:.1f}%</text>')
    # aspect bars, shaded to the share of the themed functions
    for pct in (0, 25, 50, 75, 100):
        x = LEFT + BW * pct / 100
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{h - 32}"/>')
        out.append(f'<text x="{x:.1f}" y="{top - 14}" font-size="9" class="f2" text-anchor="middle">{pct}%</text>')
    for i, (name, n) in enumerate(items):
        y = top + i * rowh
        pct = 100.0 * n / (themed or 1)
        shade = BW * pct / 100
        out.append(f'<text x="{LEFT - 12}" y="{y + 13}" font-size="11" class="f1" text-anchor="end">{name}</text>')
        out.append(f'<rect x="{LEFT}" y="{y + 1}" width="{BW}" height="16" rx="3" class="track"/>')
        out.append(f'<rect x="{LEFT}" y="{y + 1}" width="{shade:.1f}" height="16" rx="3" class="bar"/>')
        label = f"{pct:.1f}%"
        if shade >= 42:
            out.append(f'<text x="{LEFT + shade - 7:.1f}" y="{y + 13}" font-size="10" class="onbar" '
                       f'text-anchor="end">{label}</text>')
        else:
            out.append(f'<text x="{LEFT + shade + 7:.1f}" y="{y + 13}" font-size="10" class="f2">{label}</text>')
        out.append(f'<text x="{LEFT + BW + 10}" y="{y + 13}" font-size="10" class="f2">{n:,} functions</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write(index, out):
    """Write completeness.svg and aspects.svg into `out`."""
    os.makedirs(out, exist_ok=True)
    rs = rows(index)
    c, themed, total = aspects(index)
    for dark, suffix in ((False, "light"), (True, "dark")):
        open(f"{out}/completeness-{suffix}.svg", "w", encoding="utf-8", newline="\n").write(
            svg_coverage(rs, dark))
        open(f"{out}/aspects-{suffix}.svg", "w", encoding="utf-8", newline="\n").write(
            svg_aspects(c, themed, total, dark))
    return rows(index), c, themed, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--out", default=ROOT + "/work/wiki")
    a = ap.parse_args()
    if not os.path.exists(f"{a.index}/roles.jsonl"):
        sys.exit(f"missing {a.index}/roles.jsonl: run tools/map_roles.py first")
    rs, c, themed, total = write(a.index, a.out)
    for r in rs:
        print(f"{r['name']:>4}: {r['total']:>6,} functions  read {r['read']:>6,}")
    print(f"aspects: {themed:,} of {total:,} themed")
    for name, n in c.most_common():
        print(f"  {n:>6,}  {name}")
    print(f"wrote {a.out}/completeness-{{light,dark}}.svg and {a.out}/aspects-{{light,dark}}.svg")


if __name__ == "__main__":
    main()
