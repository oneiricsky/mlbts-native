"""Shows what the window displays while the main menu starts, from the screenshots of a run.

  python -I tools/menu_startup_check.py <profile folder> [--allow-gap N] [--allow-box N]

The folder holds shot-<frame>.png (MLB_SHOT=<frames>, 1280x720; the shot is the window's picture, so the black hold
shows as black). Each shot is classified:
  black   nothing lit (brightest pixel below 20)
  box     the "NETWORK ERROR" panel (more than half of x 1022..1280 is deep blue)
  gap     the menu with the offline panel hidden and the page unscrolled: the header is lit, the old panel region
          (x 62..1220, y 152..573) is flat (luminance std below 8)
  hero    the scrolled menu: the same region is busy (std above 25) and the header is lit
  other   anything else (title screen, loading)
Prints the runs in frame order, e.g. "other x12, black x40, hero x30". Exit code 1 when more than --allow-gap (default 0)
shots are gap, or more than --allow-box (default 0) are box. Needs Pillow (python -I -m pip install pillow --target
work/pylib).
"""
import glob
import sys

sys.path.insert(0, "work/pylib")
from PIL import Image  # noqa: E402


def px(im, box):
    c = im.crop(box)
    return list(c.get_flattened_data()) if hasattr(c, "get_flattened_data") else list(c.getdata())


def luma(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def std(vals):
    m = sum(vals) / len(vals)
    return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5


def classify(path):
    im = Image.open(path).convert("RGB")
    whole = px(im.resize((160, 90)), (0, 0, 160, 90))
    if max(max(p) for p in whole) < 20:
        return "black"
    strip = px(im, (1022, 0, 1280, 720))
    if sum(1 for r, g, b in strip if b > r + 25 and b > 35 and r < 40) / len(strip) > 0.5:
        return "box"
    header = sum(luma(p) for p in px(im, (60, 40, 330, 140))) / (270 * 100)
    region = std([luma(p) for p in px(im, (62, 152, 1220, 573))])
    if header > 25 and region < 8:
        return "gap"
    if header > 25 and region > 25:
        return "hero"
    return "other"


def main():
    args = sys.argv[1:]
    lim = {"gap": 0, "box": 0}
    for k, name in (("--allow-gap", "gap"), ("--allow-box", "box")):
        if k in args:
            i = args.index(k)
            lim[name] = int(args[i + 1])
            del args[i:i + 2]
    if len(args) != 1:
        sys.exit(__doc__)
    shots = sorted(glob.glob(args[0].rstrip("/\\") + "/shot-*.png"), key=lambda p: int(p.replace("\\", "/").rsplit("-", 1)[1][:-4]))
    if not shots:
        sys.exit("no shot-*.png in " + args[0])
    seq = [(int(p.replace("\\", "/").rsplit("-", 1)[1][:-4]), classify(p)) for p in shots]
    runs = []
    for fr, k in seq:
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
            runs[-1][3] = fr
        else:
            runs.append([k, 1, fr, fr])
    print(", ".join("%s x%d (%d-%d)" % (k, n, a, b) for k, n, a, b in runs))
    counts = {k: sum(1 for _, c in seq if c == k) for k in ("gap", "box")}
    bad = [k for k in ("gap", "box") if counts[k] > lim[k]]
    for k in bad:
        print("FAIL: %d %s shots (allowed %d)" % (counts[k], k, lim[k]))
    sys.exit(1 if bad else 0)


main()
