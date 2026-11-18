"""Draw runtime/mlb/mlb.ico, the icon of mlb.exe, Fastball.exe and the setup window: a baseball (our own drawing).

    python -I tools/make_icon.py [--out runtime/mlb/mlb.ico]

Needs Pillow (the dev venv has it). The .ico is committed, so builds and releases do not run this.
"""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024   # drawn large, then scaled down to each icon size


def ball():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r, c = S * 0.46, S / 2
    d.ellipse([c - r - 14, c - r - 14, c + r + 14, c + r + 14], fill=(40, 44, 52, 255))      # outline
    d.ellipse([c - r, c - r, c + r, c + r], fill=(246, 244, 238, 255))
    d.ellipse([c - r * 0.92, c - r * 0.92, c + r * 0.6, c + r * 0.6], fill=(255, 255, 252, 255))   # highlight
    red = (200, 30, 40, 255)
    seams = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ball_img, d = img, ImageDraw.Draw(seams)
    for side in (-1, 1):
        # one seam: an arc bulging towards the centre, with stitches across it
        cx = c + side * r * 1.55
        rr = r * 1.05
        pts = []
        for i in range(61):
            a = math.radians((180 if side > 0 else 0) + (-48 + 96 * i / 60))
            pts.append((cx + rr * math.cos(a), c + rr * math.sin(a)))
        d.line(pts, fill=red, width=int(S * 0.022), joint='curve')
        for i in range(4, 58, 6):
            (x0, y0), (x1, y1) = pts[i - 1], pts[i + 1]
            nx, ny = -(y1 - y0), x1 - x0
            n = math.hypot(nx, ny) or 1
            nx, ny = nx / n * S * 0.045, ny / n * S * 0.045
            x, y = pts[i]
            d.line([(x - nx + (x1 - x0) * 0.6, y - ny + (y1 - y0) * 0.6), (x + nx - (x1 - x0) * 0.6, y + ny - (y1 - y0) * 0.6)],
                   fill=red, width=int(S * 0.016))
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).ellipse([c - r + 6, c - r + 6, c + r - 6, c + r - 6], fill=255)
    ball_img.paste(seams, (0, 0), Image.composite(seams, Image.new('RGBA', (S, S)), mask))
    return ball_img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'runtime' / 'mlb' / 'mlb.ico')
    a = ap.parse_args()
    img = ball()
    img.save(a.out, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    img.resize((256, 256), Image.LANCZOS).save(a.out.with_suffix('.png'))
    print(a.out)


if __name__ == '__main__':
    main()
