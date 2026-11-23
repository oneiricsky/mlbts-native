#!/usr/bin/env python3
"""Index of PS5 textures that stand in for the game's Switch ones (runtime/mlb/hdtex.c, MLB_HD_TEXTURES).

The game creates each head texture at its own Switch size and copies the file's decompressed storage into it, so the
port recognises a texture at upload by a hash of the first 16 KiB of its storage and gives it a larger image made from
the PS5 file of the same name (docs/ps5-textures.md). This tool computes those hashes from the Switch files.

  python -I tools/make_hd_index.py --ps5 <PS5 dump folder> --romfs work/build/game/romfs \
      --out work/build/hdtex/index.txt --heads OHTANI_SHOHEI [--scale 4] [--color] [path under NSW/ ...]

One line per Switch variant of a texture: `<hash> <width> <height> <levels> <drop> <PS5 file>`; drop is how many of
the PS5 file's largest levels are left out so the image is about --scale times the Switch one on each side.

  python -I tools/make_hd_index.py --check work/build/hdtex/index.txt [--ps5 <PS5 dump folder>]

checks an existing index against the PS5 files it names (no Switch files needed): one line per problem, a count at
the end, exit status 1 when there is any. docs/ps5-textures.md says what each message means.
"""
import argparse, re, struct, sys
from pathlib import Path

PREFIX = 16384
PS5_HEADER = 1440   # header bytes of every PS5 file looked at (all 11-level BC7 heads, 7,116 index lines)


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


def ps5_header(path):
    """The PS5 file's header as hdtex.c reads it: a dict, or ValueError with the reason."""
    size = Path(path).stat().st_size
    with open(path, "rb") as f:
        d = f.read(0x400)
    if d[:8] != b"TX12PS5\0":
        raise ValueError("not a PS5 TX12 file")
    if size < 0x1a0 + 32 or len(d) < 0x1a0 + 32:
        raise ValueError(f"file is only {size} bytes, shorter than a header")
    data, nm, code = u32(d, 0x0c), u32(d, 0x8c), u32(d, 0x15c) & 0xFFFF
    w, h = struct.unpack_from("<HH", d, 0x84)
    if nm < 2 or nm > 16 or 0x1a0 + 32 * nm > len(d):
        raise ValueError(f"odd header: {nm} levels")
    if size < data:
        raise ValueError(f"file is shorter than its header says ({size} bytes, {data} bytes of texture data)")
    if 0x1a0 + 32 * nm > size - data:
        raise ValueError("odd header: the level table does not fit before the texture data")
    sizes = [u32(d, 0x1a0 + 32 * i + 4) for i in range(nm)]
    if sum(sizes) != data:
        raise ValueError(f"level sizes add up to {sum(sizes)} bytes, the header says {data}")
    return {"size": size, "data": data, "levels": nm, "code": code, "w": w, "h": h, "sizes": sizes, "hs": size - data}


def check_header(hd):
    """Problems of a parsed PS5 header, as the loader would hit them (4x4 blocks, BC1 8 bytes, BC7 16)."""
    out = []
    w, h, sizes, code = hd["w"], hd["h"], hd["sizes"], hd["code"]
    if code not in (13, 22):
        return [f"format code {code} is not BC1 (13) or BC7 (22)"]
    if hd["hs"] != PS5_HEADER:
        # the loader finds the texture data as file size minus data size, so a cut file does not trip its other checks
        out.append(f"header is {hd['hs']} bytes, every PS5 file seen so far has {PS5_HEADER}: the file is probably cut short")
    bpb = 8 if code == 13 else 16
    name = "BC1" if code == 13 else "BC7"
    want0 = ((w + 3) // 4) * ((h + 3) // 4) * bpb
    if sizes[0] != want0:
        out.append(f"largest level is {sizes[0]} bytes, a {w}x{h} {name} level is {want0}")
    for i in range(1, len(sizes)):
        lw, lh = max(1, w >> i), max(1, h >> i)
        want = ((lw + 3) // 4) * ((lh + 3) // 4) * bpb
        if sizes[i] < want:
            out.append(f"level {i} ({lw}x{lh}) is {sizes[i]} bytes, less than the {want} it needs")
    # where the loader finds each level: 0, then 1, then the rest in reverse order at the end
    offs = [0, sizes[0]]
    t, tail, run = sizes[0] + sizes[1], sum(sizes[2:]), 0
    for i in range(2, len(sizes)):
        run += sizes[i]
        offs.append(t + tail - run)
    for i, o in enumerate(offs):
        if hd["hs"] + o + sizes[i] > hd["size"]:
            out.append(f"level {i} lies outside the file")
            break
    return out


def check_index(index_path, ps5_root=None):
    """(number of index lines, [(line number, message)]) for one index file."""
    probs, lines, root, entries, seen = [], 0, ps5_root, [], {}
    for no, raw in enumerate(Path(index_path).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        ln = raw.strip()
        if not ln:
            continue
        if ln.startswith("root "):
            if root is None:
                root = ln[5:].strip()
            continue
        lines += 1
        f = ln.split(None, 5)
        try:
            if len(f) != 6 or not re.fullmatch(r"[0-9a-fA-F]{1,16}", f[0]):
                raise ValueError
            w, h, lv, drop = (int(x) for x in f[1:5])
            if min(w, h, lv) < 1 or drop < 0:
                raise ValueError
        except ValueError:
            probs.append((no, "not a line of the form <hash> <width> <height> <levels> <drop> <PS5 file>"))
            continue
        entries.append((no, int(f[0], 16), w, h, lv, drop, f[5]))
    if root is None:
        probs.append((0, "no root line in the index and no --ps5 folder given"))
        return lines, probs
    for no, hsh, w, h, lv, drop, rel in entries:
        seen.setdefault((hsh, w, h, lv), set()).add(rel)
    for no, hsh, w, h, lv, drop, rel in entries:
        if len(seen[(hsh, w, h, lv)]) > 1:
            probs.append((no, f"{rel}: another PS5 file has the same hash and size, the two cannot be told apart"))
        parts = rel.split("/")
        if parts[0] != "PS5" or ".." in parts or not rel.upper().endswith(".TEX") or len(parts) < 3:
            probs.append((no, f"{rel}: not a path of the form PS5/.../<name>.TEX"))
            continue
        if parts[-1][:-4].rsplit("-", 1)[0] != parts[-2]:
            probs.append((no, f"{rel}: the file name does not start with its folder name {parts[-2]}"))
        path = Path(root) / rel
        if not path.is_file():
            probs.append((no, f"{rel}: file not found under {root}"))
            continue
        try:
            hd = ps5_header(path)
        except (ValueError, OSError) as e:
            probs.append((no, f"{rel}: {e}"))
            continue
        bad = check_header(hd)
        probs += [(no, f"{rel}: {m}") for m in bad]
        if bad:
            continue
        if drop >= hd["levels"]:
            probs.append((no, f"{rel}: drop {drop} leaves no level (the file has {hd['levels']})"))
            continue
        w1, h1 = max(1, hd["w"] >> drop), max(1, hd["h"] >> drop)
        ratio = w1 // w if w1 % w == 0 else 0
        if not ratio or ratio & (ratio - 1) or h1 != h * ratio:
            probs.append((no, f"{rel}: after dropping {drop} levels the image is {w1}x{h1}, "
                              f"which is not the Switch size {w}x{h} times a power of two"))
            continue
        left = hd["levels"] - drop - (ratio.bit_length() - 1)
        if left < lv:
            probs.append((no, f"{rel}: only {left} levels are left at the Switch size, the Switch texture has {lv}"))
    return lines, probs


def run_check(index_path, ps5_root):
    lines, probs = check_index(index_path, ps5_root)
    for no, msg in probs:
        print(f"{index_path}:{no}: {msg}" if no else f"{index_path}: {msg}")
    print(f"{lines} index lines checked, {len(probs)} problems in {len({no for no, _ in probs})} lines")
    return 1 if probs else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="INDEX",
                    help="check an existing index against its PS5 files and exit (needs no Switch files)")
    ap.add_argument("--ps5", help="the PS5 dump's app folder (the one holding PS5/); with --check it replaces the index's root line")
    ap.add_argument("--romfs", help="the extracted Switch RomFS (holding NSW/)")
    ap.add_argument("--out")
    ap.add_argument("--scale", type=int, default=4, help="HD size over the Switch size, per side (default 4)")
    ap.add_argument("--max-dim", type=int, default=1024, help="largest HD side (default 1024)")
    ap.add_argument("--heads", nargs="*", default=[], help="player folders under CHARACTERS/HEADS (their NORMAL maps)")
    ap.add_argument("--color", action="store_true",
                    help="--heads also takes the COLOR maps (checked on two heads so far; docs/ps5-textures.md)")
    ap.add_argument("--all-heads", action="store_true",
                    help="every player folder under CHARACTERS/HEADS that has a NORMAL map in both the Switch files and the PS5 dump")
    ap.add_argument("tex", nargs="*", help="paths under NSW/ (and PS5/)")
    a = ap.parse_args()
    if a.check:
        sys.exit(run_check(a.check, a.ps5))
    if not (a.ps5 and a.romfs and a.out):
        ap.error("--ps5, --romfs and --out are required unless --check is given")
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
