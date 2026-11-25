"""Check the wiki's SVG charts against the WCAG 2.2 criteria that can be asserted for a static image.

    python -I tools/wiki_wcag_check.py [--wiki work/wiki]

Asserts contrast ratios from the palette (1.4.3 AA for text, 1.4.11 for bars), and the structural bits that decide
whether the image has an accessible name (1.1.1 AA): role="img", aria-label, <title> and <desc>. Also checks that
every <text> element carries a fill class, so no label falls back to black on the dark card.

Criterion 1.4.5 (images of text, AA) is not something a palette fix can satisfy: the labels are vector text inside the
image. They are treated as essential chart labelling, and the counts the chart shows are also in text on the wiki
(Function map and Function census).
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from wiki_completeness import PALETTE


def lum(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


TEXT = 4.5
GRAPHIC = 3.0
PAIRS = [
    ("body text on background", PALETTE["fg"], PALETTE["bg"], TEXT),
    ("muted text on background", PALETTE["fg2"], PALETTE["bg"], TEXT),
    ("percentage inside a bar", PALETTE["onbar"], PALETTE["accent"], TEXT),
    ("C segment against background", PALETTE["c"], PALETTE["bg"], GRAPHIC),
    ("I segment against background", PALETTE["i"], PALETTE["bg"], GRAPHIC),
    ("H segment against background", PALETTE["h"], PALETTE["bg"], GRAPHIC),
    ("read segment against background", PALETTE["read"], PALETTE["bg"], GRAPHIC),
    ("bar against its track", PALETTE["accent"], PALETTE["track"], GRAPHIC),
    ("card edge against background", PALETTE["border"], PALETTE["bg"], 1.0),
]


def check_svg(path):
    text = open(path, encoding="utf-8").read()
    problems = []
    if 'role="img"' not in text:
        problems.append("no role=img")
    if "aria-label=" not in text:
        problems.append("no aria-label")
    if "<title>" not in text:
        problems.append("no <title>")
    if "<desc>" not in text:
        problems.append("no <desc>")
    if "viewBox=" not in text:
        problems.append("no viewBox, so the image cannot scale cleanly")
    if "color-scheme: dark" not in text:
        problems.append("does not declare color-scheme: dark, so a browser may auto-invert it")
    for line in text.split("\n"):
        if line.startswith("<text") and "class=" not in line:
            problems.append(f"text without a fill class: {line[:60]}")
        m = re.search(r"font-size=\"([0-9.]+)\"", line)
        if m and float(m.group(1)) < 9:
            problems.append(f"text under 9 px: {line[:60]}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default=ROOT + "/work/wiki")
    a = ap.parse_args()
    ok = True
    print("contrast ratios (WCAG 2.2 1.4.3 AA for text, 1.4.11 for graphics):")
    for name, fg, bg, need in PAIRS:
        r = contrast(fg, bg)
        verdict = "pass" if r >= need else "FAIL"
        if r < need:
            ok = False
        print(f"  {name:34s} {fg} on {bg}  {r:5.2f}:1  needs {need:.1f}  {verdict}")
    for name in ("completeness.svg", "aspects.svg"):
        path = f"{a.wiki}/{name}"
        if not os.path.exists(path):
            print(f"missing {path}")
            ok = False
            continue
        problems = check_svg(path)
        print(f"{name}: " + ("structure ok" if not problems else "; ".join(problems)))
        ok = ok and not problems
    home = f"{a.wiki}/Home.md"
    if os.path.exists(home):
        text = open(home, encoding="utf-8").read()
        for m in re.finditer(r"!\[([^\]]*)\]\(([^)]*\.svg)\)", text):
            alt, src = m.group(1), m.group(2)
            print(f"Home.md image {src}: alt {'ok' if alt.strip() else 'EMPTY'}")
            ok = ok and bool(alt.strip())
    print("result:", "pass" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
