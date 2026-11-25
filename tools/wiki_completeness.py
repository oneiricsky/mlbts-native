"""Draw the function map's coverage as an SVG for the wiki home page.

    python -I tools/wiki_completeness.py [--index work/map/index] [--out work/wiki]

Two bars per region: the upper splits every function by the evidence behind its role (C a string, symbol or import;
I the shape of the code; H only the neighbours), the lower splits them by whether the body was read. The SVG is
generated, never hand-edited; tools/wiki_build.py calls this after it writes the pages.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
REGIONS = [("A", 0x7000000000, 0x7000600000), ("B", 0x7000600000, 0x7000C00000),
           ("C", 0x7000C00000, 0x7001000000), ("D", 0x7001000000, 0x7001400000),
           ("E", 0x7001400000, 0x7001800000), ("F", 0x7001800000, 0x7001C22800)]

C_COLOR, I_COLOR, H_COLOR = "#2e7d5b", "#5b7fb5", "#c49a6c"
READ_COLOR, UNREAD_COLOR = "#3b3b3b", "#dcdcdc"
TEXT, MUTED = "#1b1b1b", "#666666"


def rows(index):
    data = [json.loads(l) for l in open(f"{index}/roles.jsonl", encoding="utf-8")]
    out = []
    for name, lo, hi in REGIONS + [("sdk", 0x7004C00000, 0x700524E231)]:
        if name == "sdk":
            rs = [r for r in data if r["module"] == "sdk"]
        else:
            rs = [r for r in data if r["module"] == "main" and lo <= int(r["addr"], 16) < hi]
        c = {t: sum(1 for r in rs if r["tag"] == t) for t in "CIH"}
        read = sum(1 for r in rs if r.get("read"))
        out.append(dict(name=name, total=len(rs), C=c["C"], I=c["I"], H=c["H"], read=read))
    return out


def bar(x, y, w, parts):
    """parts: [(count, color)] over the row total."""
    total = sum(n for n, _ in parts) or 1
    out, cx = [], x
    for n, color in parts:
        if not n:
            continue
        sw = w * n / total
        out.append(f'<rect x="{cx:.1f}" y="{y}" width="{sw:.1f}" height="14" fill="{color}"/>')
        cx += sw
    return out


def svg(rs):
    w, left, bw = 1000, 200, 620
    top = 74
    rowh = 48
    h = top + rowh * len(rs) + 34
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" role="img" aria-label="Function map coverage by region">',
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
           f'<text x="{left}" y="24" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="{TEXT}">'
           f'Function map coverage: 135,060 functions</text>',
           f'<text x="{left}" y="42" font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="{MUTED}">'
           f'upper bar: evidence behind the role (C string or symbol, I code shape, H neighbours); '
           f'lower bar: body read</text>']
    # axis ticks
    for pct in (0, 25, 50, 75, 100):
        x = left + bw * pct / 100
        out.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{h - 24}" stroke="#eeeeee"/>')
        out.append(f'<text x="{x:.1f}" y="{top - 14}" font-family="Arial, sans-serif" font-size="9" '
                   f'fill="{MUTED}" text-anchor="middle">{pct}%</text>')
    for i, r in enumerate(rs):
        y = top + i * rowh
        label = f"{r['name']}" if r["name"] == "sdk" else f"Region {r['name']}"
        out.append(f'<text x="10" y="{y + 13}" font-family="Segoe UI, Arial, sans-serif" font-size="12" '
                   f'fill="{TEXT}">{label}</text>')
        out.append(f'<text x="10" y="{y + 27}" font-family="Arial, sans-serif" font-size="10" '
                   f'fill="{MUTED}">{r["total"]:,} functions</text>')
        out += bar(left, y, bw, [(r["C"], C_COLOR), (r["I"], I_COLOR), (r["H"], H_COLOR)])
        out += bar(left, y + 18, bw, [(r["read"], READ_COLOR), (r["total"] - r["read"], UNREAD_COLOR)])
        pct = lambda n: 100.0 * n / (r["total"] or 1)
        out.append(f'<text x="{left + bw + 10}" y="{y + 12}" font-family="Arial, sans-serif" font-size="10" '
                   f'fill="{MUTED}">C {pct(r["C"]):.0f}% · I {pct(r["I"]):.0f}% · H {pct(r["H"]):.0f}% · '
                   f'read {pct(r["read"]):.0f}%</text>')
    ly = h - 18
    lx = left
    for color, text in ((C_COLOR, "C: string, symbol or import"), (I_COLOR, "I: code shape or call graph"),
                        (H_COLOR, "H: neighbours only"), (READ_COLOR, "body read")):
        out.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" fill="{color}"/>')
        out.append(f'<text x="{lx + 14}" y="{ly}" font-family="Arial, sans-serif" font-size="10" '
                   f'fill="{MUTED}">{text}</text>')
        lx += 14 + 7 * len(text) + 18
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write(index, out):
    """Write completeness.svg into `out`; returns the per-region rows."""
    rs = rows(index)
    os.makedirs(out, exist_ok=True)
    open(f"{out}/completeness.svg", "w", encoding="utf-8", newline="\n").write(svg(rs))
    return rs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--out", default=ROOT + "/work/wiki")
    a = ap.parse_args()
    path = f"{a.index}/roles.jsonl"
    if not os.path.exists(path):
        sys.exit(f"missing {path}: run tools/map_roles.py first")
    rs = write(a.index, a.out)
    for r in rs:
        print(f"{r['name']:>4}: {r['total']:>6,} functions  C {r['C']:>6,}  I {r['I']:>6,}  H {r['H']:>5,}"
              f"  read {r['read']:>6,}")
    print(f"wrote {a.out}/completeness.svg")


if __name__ == "__main__":
    main()
