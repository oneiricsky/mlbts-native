#!/usr/bin/env python3
"""Index of PS5 textures that stand in for the game's Switch ones (runtime/mlb/hdtex.c, MLB_HD_TEXTURES).

The game creates each head texture at its own Switch size and copies the file's decompressed storage into it, so the
port recognises a texture at upload by a hash of the first 16 KiB of its storage and gives it a larger image made from
the PS5 file of the same name (docs/ps5-textures.md). This tool computes those hashes from the Switch files.

  python -I tools/make_hd_index.py --ps5 <PS5 dump folder> --romfs work/build/game/romfs \
      --out work/build/hdtex/index.txt --all-heads [--no-color] [--scale 4]
  ... or --heads OHTANI_SHOHEI [...] or paths under NSW/ in place of --all-heads

One line per Switch variant of a texture: `<hash> <width> <height> <levels> <drop> [=<full>/<bytes>] <PS5 file>`; drop
is how many of the PS5 file's largest levels are left out so the image is about --scale times the Switch one on each
side. <hash> is of the first 16 KiB of the Switch storage. Where several Switch textures share it and they cannot all
take one PS5 file, each of their lines also has <full>, a hash of the whole decompressed storage, <bytes> long.

  python -I tools/make_hd_index.py --check work/build/hdtex/index.txt [--ps5 <PS5 dump folder>]

checks an existing index against the PS5 files it names (no Switch files needed): one line per problem, a count at
the end, exit status 1 when there is any. docs/ps5-textures.md says what each message means.
"""
import argparse, hashlib, re, struct, sys
from pathlib import Path

PREFIX = 16384
KINDS = ("COLOR", "NORMAL")
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


def switch_variants(path, full=False):
    """[(width, height, levels, storage bytes)] of the Switch file's variants: the first 16 KiB, or all of it."""
    d = path.read_bytes()
    if d[:8] != b"TX12NSW\0":
        sys.exit(f"{path}: not a Switch TX12 file")
    hs = u32(d, 0x154)
    nv = u32(d, 0x170)
    if nv not in (1, 2):
        print(f"  {path.name}: {nv} variants, not handled")
        return []
    # One LZ4 block per segment: [(offset after the header, decompressed bytes)]. With two variants the first block is
    # the large level only and the second the half-size variant's whole chain, which is also the rest of the first's.
    blocks = [(0, u32(d, 0x10))]
    if nv == 2:
        blocks = [(0, u32(d, 0x10) - u32(d, 0x104)), (u32(d, 0x10c), u32(d, 0x104))]
    out = []
    for i, (at, mips) in enumerate([(0x84, 0x8c), (0xa4, 0xac)][:nv]):
        w, h = struct.unpack_from("<HH", d, at)
        data = b""
        for off, size in blocks[i:]:
            want = size if full else min(size, PREFIX - len(data))
            if want > 0:
                data += lz4_prefix(d[hs + off:], want)
        out.append((w, h, u32(d, mips), data))
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
        full = ""
        if len(f) == 6 and re.fullmatch(r"=[0-9a-fA-F]{1,16}/[1-9][0-9]* +.*", f[5]):
            full, f[5] = f[5].split(None, 1)
        try:
            if len(f) != 6 or not re.fullmatch(r"[0-9a-fA-F]{1,16}", f[0]):
                raise ValueError
            w, h, lv, drop = (int(x) for x in f[1:5])
            if min(w, h, lv) < 1 or drop < 0:
                raise ValueError
        except ValueError:
            probs.append((no, "not a line of the form <hash> <width> <height> <levels> <drop> [=<full>/<bytes>] <PS5 file>"))
            continue
        entries.append((no, int(f[0], 16), w, h, lv, drop, f[5], full))
    if root is None:
        probs.append((0, "no root line in the index and no --ps5 folder given"))
        return lines, probs
    for no, hsh, w, h, lv, drop, rel, full in entries:
        seen.setdefault((hsh, w, h, lv), {})[rel] = full
    for no, hsh, w, h, lv, drop, rel, full in entries:
        if len(seen[(hsh, w, h, lv)]) > 1 and not all(seen[(hsh, w, h, lv)].values()):
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
    ap.add_argument("--heads", nargs="*", default=[], help="player folders under CHARACTERS/HEADS")
    ap.add_argument("--no-color", action="store_true", help="the normal maps only")
    ap.add_argument("--all-heads", action="store_true", help="every player folder under CHARACTERS/HEADS")
    ap.add_argument("tex", nargs="*", help="paths under NSW/ (and PS5/)")
    a = ap.parse_args()
    if a.check:
        sys.exit(run_check(a.check, a.ps5))
    if not (a.ps5 and a.romfs and a.out):
        ap.error("--ps5, --romfs and --out are required unless --check is given")
    kinds = [k for k in KINDS if k == "NORMAL" or not a.no_color]
    nsw = Path(a.romfs) / "NSW"
    paths = list(a.tex)
    heads = list(a.heads)
    # Every head's Switch file is read, picked or not: one that shares its first 16 KiB with a picked head must not be
    # given that head's PS5 file.
    every = [f"CHARACTERS/HEADS/{d.name}/{d.name}-{k}.TEX" for d in sorted((nsw / "CHARACTERS" / "HEADS").iterdir())
             if d.is_dir() for k in KINDS if (d / f"{d.name}-{k}.TEX").exists()]
    if a.all_heads:
        heads += sorted({r.split("/")[2] for r in every} - set(heads))
    for n in heads:
        for k in kinds:
            rel = f"CHARACTERS/HEADS/{n}/{n}-{k}.TEX"
            if (nsw / rel).exists() or not a.all_heads:
                paths.append(rel)
    entries, report = build_index(Path(a.ps5), nsw, list(dict.fromkeys(paths)), every, a.scale, a.max_dim)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"root {a.ps5}\n" + "".join(ln + "\n" for ln in entries))
    print_report(report, kinds, Path(a.ps5), nsw, a.all_heads)
    print(f"{len(entries)} entries -> {out}")


def build_index(ps5_root, nsw, paths, others, scale=4, max_dim=1024):
    """(index lines, report) for the textures `paths`; `others` are further Switch files that may share their hashes.

    report: {"indexed": {path}, "opened": {path} (told apart only by which file the game opens),
             "unused": {path: reason}}."""
    keys, info, unused = {}, {}, {}
    wanted = set(paths)
    for rel in dict.fromkeys(list(paths) + list(others)):
        ps5 = ps5_root / "PS5" / rel
        try:
            variants = switch_variants(nsw / rel)
        except (SystemExit, OSError, IndexError, struct.error) as e:
            if rel in wanted:
                unused[rel] = f"no readable Switch file ({e})"
            continue
        usable = False
        if rel in wanted:
            if not ps5.is_file():
                unused[rel] = "no PS5 file in the dump"
            else:
                try:
                    hd = ps5_header(ps5)
                    bad = check_header(hd)
                    if bad:
                        raise ValueError(bad[0])
                    usable, info[rel] = True, hd
                except (ValueError, OSError) as e:
                    unused[rel] = str(e)
        for i, (w, h, nm, pre) in enumerate(variants):
            keys.setdefault((fnv64(pre), w, h, nm), []).append((rel, i, usable))

    lines, indexed, by_open = [], set(), set()
    for (hsh, w, h, nm), group in sorted(keys.items(), key=lambda kv: (kv[1][0][0], kv[1][0][1])):
        if not any(u for _, _, u in group):
            continue
        picks = []   # (path, "=full/bytes " or "")
        if len(group) == 1:
            picks = [(group[0][0], "")]
        else:
            rows = []   # (path, usable, full token, the PS5 texture data's digest)
            for rel, i, usable in group:
                store = switch_variants(nsw / rel, full=True)[i][3]
                body = None
                if usable:
                    body = hashlib.sha256((ps5_root / "PS5" / rel).read_bytes()[info[rel]["hs"]:]).digest()
                rows.append((rel, usable, f"={fnv64(store):016x}/{len(store)} ", body))
            if all(u for _, u, _, _ in rows) and len({b for *_, b in rows}) == 1:
                # one PS5 texture under several names: whichever player it is, the picture is right
                picks = [(rows[0][0], "")]
                indexed.update(r for r, *_ in rows)
            else:
                for token in dict.fromkeys(t for _, u, t, _ in rows if u):
                    same = [r for r in rows if r[2] == token]
                    ok = [r for r in same if r[1]]
                    if len({r[3] for r in ok}) == 1 and len(ok) == len(same):
                        picks.append((ok[0][0], token))
                        indexed.update(r[0] for r in ok)
                    elif len(ok) == len(same):
                        picks += [(r[0], token) for r in ok]
                        by_open.update(r[0] for r in ok)
                    else:
                        for r in ok:
                            other = next(x[0] for x in same if not x[1])
                            unused[r[0]] = f"its Switch texture is the same as {other}, which has no PS5 file here"
        for rel, token in picks:
            hd = info[rel]
            pw, ph, pn = hd["w"], hd["h"], hd["levels"]
            drop = 0
            while drop + 1 < pn and (pw >> (drop + 1)) >= w * scale:
                drop += 1
            while drop + 1 < pn and max(pw, ph) >> drop > max_dim:
                drop += 1
            lines.append(f"{hsh:016x} {w} {h} {nm} {drop} {token}PS5/{rel}")
            indexed.add(rel)
    return lines, {"indexed": indexed, "opened": by_open, "unused": unused}


def print_report(report, kinds, ps5_root, nsw, all_heads):
    for kind in kinds:
        end = f"-{kind}.TEX"
        have = sorted(r for r in report["indexed"] if r.endswith(end))
        told = [r for r in report["opened"] if r.endswith(end)]
        unused = {r: why for r, why in report["unused"].items() if r.endswith(end) and r not in report["indexed"]}
        if all_heads:
            for d in sorted((ps5_root / "PS5" / "CHARACTERS" / "HEADS").iterdir()):
                rel = f"CHARACTERS/HEADS/{d.name}/{d.name}{end}"
                if (d / f"{d.name}{end}").is_file() and not (nsw / rel).is_file():
                    unused[rel] = "a PS5 file only: the game has no Switch texture to replace"
        print(f"{kind}: {len(have) + len([r for r in told if r not in have])} heads indexed"
              f" ({len(told)} of them told apart by which file the game opens), {len(unused)} not usable")
        for rel in sorted(told):
            print(f"  by opened file: {rel.split('/')[-1]}")
        for rel, why in sorted(unused.items()):
            print(f"  not used: {rel.split('/')[-1]}: {why}")


if __name__ == "__main__":
    main()
