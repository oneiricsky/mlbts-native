"""Counts the screenshots of a run that show the "NETWORK ERROR" box.

  python -I tools/network_error_check.py <profile folder> [--max N]

The folder holds shot-<frame>.png files (MLB_SHOT=<frames>, 1280x720). The box is a deep blue panel on the right
(x 1022..1280): a shot shows it when more than half of that strip is blue (b > r + 25, b > 35, r < 40); the menu behind
it gives 0.08 at most and the Diamond Dynasty screen 0.34. Prints the frames with the box and the number of shots.
With --max N the exit code is 1 when more than N shots show it (a fixed run should show it for a few shots, a run with
MLB_NO_NETWORK_ERROR=0 for hundreds). Needs Pillow (python -I -m pip install pillow --target work/pylib).
"""
import glob
import sys

sys.path.insert(0, "work/pylib")
from PIL import Image  # noqa: E402


def box_fraction(path):
    im = Image.open(path).convert("RGB").crop((1022, 0, 1280, 720))
    px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
    return sum(1 for r, g, b in px if b > r + 25 and b > 35 and r < 40) / len(px)


def main():
    args = sys.argv[1:]
    mx = None
    if "--max" in args:
        i = args.index("--max")
        mx = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit(__doc__)
    shots = sorted(glob.glob(args[0].rstrip("/\\") + "/shot-*.png"), key=lambda p: int(p.replace("\\", "/").rsplit("-", 1)[1][:-4]))
    if not shots:
        sys.exit("no shot-*.png in " + args[0])
    hits = [int(p.replace("\\", "/").rsplit("-", 1)[1][:-4]) for p in shots if box_fraction(p) > 0.5]
    print("%d shots, %d show the box: %s" % (len(shots), len(hits), hits))
    sys.exit(1 if mx is not None and len(hits) > mx else 0)


main()
