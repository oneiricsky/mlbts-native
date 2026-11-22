#!/usr/bin/env python3
"""Index of PS5 textures that stand in for the game's Switch ones (runtime/mlb/hdtex.c, MLB_HD_TEXTURES).

The game creates each head texture at its own Switch size and copies the file's decompressed storage into it, so the
port recognises a texture at upload by a hash of the first 16 KiB of its storage and gives it a larger image made from
the PS5 file of the same name (docs/ps5-textures.md). This tool computes those hashes from the Switch files.

  python -I tools/make_hd_index.py --ps5 E:/PPSA30630/PPSA30630-app --romfs work/build/game/romfs \
      --out work/build/hdtex/index.txt --heads OHTANI_SHOHEI [--scale 4] [--color] [path under NSW/ ...]

One line per Switch variant of a texture: `<hash> <width> <height> <levels> <drop> <PS5 file>`; drop is how many of
the PS5 file's largest levels are left out so the image is about --scale times the Switch one on each side.
"""
import argparse, struct, sys
from pathlib import Path

PREFIX = 16384


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def lz4_prefix(src, want):
    out = bytearray()
    i = 0
    while len(out) < want:
        t = src[i]
        i += 1
        lit = t >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if len(out) >= want:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        ml = t & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        for _ in range(ml + 4):
            out.append(out[-off])
    return bytes(out[:want])


def fnv64(b):
    h = 0xcbf29ce484222325
    for x in b:
        h = ((h ^ x) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h


def switch_variants(path):
    """[(width, height, levels, storage prefix bytes)] of the Switch file's variants."""
    d = path.read_bytes()
    if d[:8] != b"TX12NSW\0":
        sys.exit(f"{path}: not a Switch TX12 file")
    hs = u32(d, 0x154)
    nv = u32(d, 0x170)
    w, h = struct.unpack_from("<HH", d, 0x84)
    nm = u32(d, 0x8c)
    out = []
    if nv == 1:
        total = u32(d, 0x10)
        out.append((w, h, nm, lz4_prefix(d[hs:], min(PREFIX, total))))
    elif nv == 2:
        total = u32(d, 0x10)
        out.append((w, h, nm, lz4_prefix(d[hs:], min(PREFIX, total))))
        seg2_unc, seg2_off = u32(d, 0x104), u32(d, 0x10c)
        w2, h2 = struct.unpack_from("<HH", d, 0xa4)
        out.append((w2, h2, u32(d, 0xac), lz4_prefix(d[hs + seg2_off:], min(PREFIX, seg2_unc))))
    else:
        print(f"  {path.name}: {nv} variants, not handled")
    return out


def ps5_info(path):
    with open(path, "rb") as f:
        d = f.read(0x200)
    if d[:8] != b"TX12PS5\0":
        sys.exit(f"{path}: not a PS5 TX12 file")
    return struct.unpack_from("<HH", d, 0x84), u32(d, 0x8c), u32(d, 0x15c) & 0xFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps5", required=True, help="the PS5 dump's app folder (the one holding PS5/)")
    ap.add_argument("--romfs", required=True, help="the extracted Switch RomFS (holding NSW/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=4, help="HD size over the Switch size, per side (default 4)")
    ap.add_argument("--max-dim", type=int, default=1024, help="largest HD side (default 1024)")
    ap.add_argument("--heads", nargs="*", default=[], help="player folders under CHARACTERS/HEADS (their NORMAL maps)")
    ap.add_argument("--color", action="store_true",
                    help="--heads also takes the COLOR maps (checked on two heads so far; docs/ps5-textures.md)")
    ap.add_argument("--all-heads", action="store_true",
                    help="every player folder under CHARACTERS/HEADS that has a NORMAL map in both the Switch files and the PS5 dump")
    ap.add_argument("tex", nargs="*", help="paths under NSW/ (and PS5/)")
    a = ap.parse_args()
    paths = list(a.tex)
    heads = list(a.heads)
    if a.all_heads:
        base = Path(a.romfs) / "NSW" / "CHARACTERS" / "HEADS"
        for d in sorted(x.name for x in base.iterdir() if x.is_dir()):
            if (base / d / f"{d}-NORMAL.TEX").exists() and (Path(a.ps5) / "PS5" / "CHARACTERS" / "HEADS" / d / f"{d}-NORMAL.TEX").exists():
                heads.append(d)
    for n in heads:
        paths += [f"CHARACTERS/HEADS/{n}/{n}-NORMAL.TEX"] + ([f"CHARACTERS/HEADS/{n}/{n}-COLOR.TEX"] if a.color else [])
    lines = []
    for rel in paths:
        try:
            (pw, ph), pn, code = ps5_info(Path(a.ps5) / "PS5" / rel)
            variants = switch_variants(Path(a.romfs) / "NSW" / rel)
        except (SystemExit, OSError) as e:
            print(f"{rel}: skipped ({e})")
            continue
        if code not in (13, 22):
            print(f"{rel}: PS5 format code {code} is not BC1 or BC7, skipped")
            continue
        for w, h, nm, pre in variants:
            drop = 0
            while drop + 1 < pn and (pw >> (drop + 1)) >= w * a.scale:
                drop += 1
            while drop + 1 < pn and max(pw, ph) >> drop > a.max_dim:
                drop += 1
            hd = (max(1, pw >> drop), max(1, ph >> drop))
            lines.append(f"{fnv64(pre):016x} {w} {h} {nm} {drop} PS5/{rel}")
            print(f"{rel}: Switch {w}x{h} ({nm} levels) -> PS5 {hd[0]}x{hd[1]} (drop {drop})")
    seen = {}
    for ln in lines:
        key = tuple(ln.split()[:4])
        seen.setdefault(key, set()).add(ln.split()[5])
    dup = {k for k, v in seen.items() if len(v) > 1}
    if dup:
        n0 = len(lines)
        lines = [ln for ln in lines if tuple(ln.split()[:4]) not in dup]
        print(f"{n0 - len(lines)} entries dropped: their Switch textures share a hash, so the PS5 file could not be told apart")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"root {a.ps5}\n" + "\n".join(lines) + "\n")
    print(f"{len(lines)} entries -> {out}")


if __name__ == "__main__":
    main()
