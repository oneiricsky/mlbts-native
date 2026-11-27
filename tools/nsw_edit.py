"""Looks at the screens in a game layout file (NSW/UI/FRONTEND/FRONTEND.NSW and its siblings) and writes a changed copy.

  python -I tools/nsw_edit.py list   [FILE] [--match TEXT]
  python -I tools/nsw_edit.py strings NAME [FILE]
  python -I tools/nsw_edit.py nodes   NAME [FILE] [--min W]
  python -I tools/nsw_edit.py set     NAME OFFSET VALUE --expect OLD --out DIR [FILE]

FILE defaults to work/build/game/romfs/NSW/UI/FRONTEND/FRONTEND.NSW. `set` copies the file to
DIR/NSW/UI/FRONTEND/FRONTEND.NSW with the float at OFFSET of NAME's block changed from OLD to VALUE; run the game
with MLB_ROMFS_OVERRIDE=DIR (the original is never touched). Nothing here is part of the game's own data.

The format (measured 2026-11-26, see docs/menu-offline-panel.md):
  The file is IFF0ASSH + a run of blocks. A block starts with the 8 bytes "VOIDASS0" (then a hash, a size, a table of
  section offsets) and goes to the next one. Its tail holds the screen's string pool: the 4 bytes 5b 00 00 80, then
  NUL-separated strings, the first being the screen's name. So a block belongs to the pool at its END (an earlier
  version of this reading, pool then block, named every screen after its neighbour).
  The nodes are 0x50 bytes or more: colour (u32), x, y, z, width, height (float32), then flag words. Offsets here
  are from the start of the block's "VOIDASS0". The game's live copy of a block has the same layout with its pointers
  filled in.
"""
import re
import struct
import sys

DEFAULT = "work/build/game/romfs/NSW/UI/FRONTEND/FRONTEND.NSW"
MARK = b"\x5b\x00\x00\x80"


def blocks(d):
    """[(name, start, end, pool_start)] for every VOIDASS0 block."""
    starts = [m.start() for m in re.finditer(b"VOIDASS0", d)]
    out = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(d)
        seg = d[s:e]
        k = seg.rfind(MARK)
        name = "?"
        while k >= 0:
            raw = seg[k + 4:k + 80].split(b"\0")[0]
            if raw and all(32 <= c < 127 for c in raw):
                name = raw.decode("latin1")
                break
            k = seg.rfind(MARK, 0, k)
        out.append((name, s, e, s + k if k >= 0 else e))
    return out


def find(d, name):
    hit = [b for b in blocks(d) if b[0] == name]
    if not hit:
        sys.exit("no screen named %r (try: list --match %s)" % (name, name[:6]))
    if len(hit) > 1:
        print("note: %d blocks are named %s; using the first" % (len(hit), name), file=sys.stderr)
    return hit[0]


def f32(d, o):
    return struct.unpack_from("<f", d, o)[0]


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("list", "strings", "nodes", "set"):
        sys.exit(__doc__)
    cmd = a.pop(0)
    opts = {}
    for k in ("--match", "--min", "--expect", "--out"):
        if k in a:
            i = a.index(k)
            opts[k] = a[i + 1]
            del a[i:i + 2]
    need = {"list": 0, "strings": 1, "nodes": 1, "set": 3}[cmd]
    pos, rest = a[:need], a[need:]
    path = rest[0] if rest else DEFAULT
    d = open(path, "rb").read()
    if cmd == "list":
        for name, s, e, p in blocks(d):
            if "--match" in opts and opts["--match"].lower() not in name.lower():
                continue
            print("%-44s block %9d..%9d (%7d bytes), nodes end %d" % (name, s, e, e - s, p - s))
        return
    name, s, e, p = find(d, pos[0])
    if cmd == "strings":
        o = p + 4
        i = 0
        while o < e:
            end = d.index(b"\0", o)
            t = d[o:end]
            if t and not all(32 <= c < 127 for c in t):
                break
            print("%3d %s" % (i, t.decode("latin1")))
            i += 1
            o = end + 1
        return
    if cmd == "nodes":
        mn = float(opts.get("--min", 20))
        for k in range(0, p - s - 24, 4):
            w = struct.unpack_from("<6I", d, s + k)
            if w[3] != 0:
                continue
            x, y, wd, ht = (struct.unpack("<f", struct.pack("<I", v))[0] for v in (w[1], w[2], w[4], w[5]))
            if not all(abs(v) < 1e5 and v == v for v in (x, y, wd, ht)) or wd < mn or ht < mn or wd > 4000 or ht > 4000:
                continue
            if x != int(x) or y != int(y) or wd != int(wd) or ht != int(ht):
                continue
            print("+%-6d colour %08x  x %6g  y %6g  w %5g  h %5g" % (k, w[0], x, y, wd, ht))
        return
    off, val = int(pos[1], 0), float(pos[2])
    if "--out" not in opts or "--expect" not in opts:
        sys.exit("set needs --expect OLD and --out DIR")
    cur = f32(d, s + off)
    if abs(cur - float(opts["--expect"])) > 1e-6:
        sys.exit("the float at +%d is %g, not %s; nothing written" % (off, cur, opts["--expect"]))
    b = bytearray(d)
    struct.pack_into("<f", b, s + off, val)
    import os
    out = os.path.join(opts["--out"], "NSW", "UI", "FRONTEND")
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, os.path.basename(path))
    open(dst, "wb").write(b)
    print("%s: +%d %g -> %g; run the game with MLB_ROMFS_OVERRIDE=%s" % (name, off, cur, val, opts["--out"]))


main()
