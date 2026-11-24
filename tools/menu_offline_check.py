"""Checks the main-menu screenshots of two runs: the offline panel is there with MLB_HIDE_OFFLINE_BANNER=0 and gone with 1.

  python -I tools/menu_offline_check.py CONTROL.png FIXED.png

Both are 1280x720 shots of the same menu frame (MLB_SHOT). The panel sits at x 62..1220, y 152..573. Four checks:
  1. control: the panel region is busy (the picture has text, icons and a bright frame): standard deviation of its
     luminance above 15, and at least 500 yellow pixels (the "YOU ARE CURRENTLY DISCONNECTED!" line, about 255,235,0).
  2. fixed: the same region is nearly flat (standard deviation below 8) with no yellow pixels.
  3. fixed: no bright teal frame line along the panel's top edge (a row of pixels close to 90,225,190).
  4. both: the strip under the panel (the mode buttons, y 640..720) is the same, mean absolute difference below 6.
Needs Pillow (python -I -m pip install pillow --target work/pylib). Exit code 0 when all pass.
"""
import sys

sys.path.insert(0, "work/pylib")
from PIL import Image  # noqa: E402

PANEL = (62, 152, 1220, 573)
STRIP = (0, 640, 1280, 720)


def luma(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def region(img, box):
    return list(img.crop(box).convert("RGB").getdata())


def stdev(vals):
    m = sum(vals) / len(vals)
    return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5


def yellow(px):
    return sum(1 for r, g, b in px if r > 220 and g > 200 and b < 90)


def teal_edge(img):
    top = list(img.crop((PANEL[0], PANEL[1] - 3, PANEL[2], PANEL[1] + 4)).convert("RGB").getdata())
    return sum(1 for r, g, b in top if g > 170 and b > 130 and r < 140)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ctl, fix = (Image.open(p).convert("RGB") for p in sys.argv[1:3])
    cp, fp = region(ctl, PANEL), region(fix, PANEL)
    cs, fs = stdev([luma(p) for p in cp]), stdev([luma(p) for p in fp])
    cy, fy = yellow(cp), yellow(fp)
    ce, fe = teal_edge(ctl), teal_edge(fix)
    a, b = region(ctl, STRIP), region(fix, STRIP)
    diff = sum(abs(luma(x) - luma(y)) for x, y in zip(a, b)) / len(a)
    rows = [
        ("control panel is busy (std > 15)", cs > 15, f"std {cs:.1f}"),
        ("control has the yellow line (>= 500 px)", cy >= 500, f"{cy} px"),
        ("fixed panel is flat (std < 8)", fs < 8, f"std {fs:.1f}"),
        ("fixed has no yellow (0 px)", fy == 0, f"{fy} px"),
        ("fixed has no teal frame edge (< 20 px)", fe < 20, f"{fe} px, control {ce} px"),
        ("mode-button strip unchanged (diff < 6)", diff < 6, f"mean abs diff {diff:.2f}"),
    ]
    for name, ok, val in rows:
        print(("PASS " if ok else "FAIL ") + name + ": " + val)
    sys.exit(0 if all(r[1] for r in rows) else 1)


main()
