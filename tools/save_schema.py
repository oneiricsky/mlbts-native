"""Read the class schema out of the game's save files.

    python -I tools/save_schema.py [--profile work/build/profile] [--out work/map/saves]

A save is zlib-compressed and starts with a self-describing Flux archive: `[DESC]`, then one block per saved
class — a 16-byte-padded class name, the record size and the field count as u32, then per field a 22-byte name
slot and a 10-byte descriptor (five u16; the first looks like a type id, the rest dimensions/flags and are not
decoded yet). After the class blocks come the values.

Writes work/map/saves/schema.json (classes, fields, descriptors, where the schema ends in each save) and prints a
summary. The names are the game's own, which is what makes this the cheapest way to name data.
Derived from the player's save files: stays under work/.
"""
import argparse, glob, json, os, struct, sys, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")


def cstr(b, off, limit=64):
    end = b.find(b"\0", off, off + limit)
    if end < 0:
        return None, off
    raw = b[off:end]
    if not raw or not all(32 <= c < 127 for c in raw):
        return None, off
    return raw.decode("ascii"), end + 1


def parse(b, off):
    """Parse consecutive class blocks from `off`; stop when the next header does not validate."""
    classes = []
    while True:
        name, o = cstr(b, off)
        if not name or o + 8 > len(b):
            break
        o = off + ((o - off + 15) & ~15)          # class name slot: a multiple of 16 bytes
        size, nf = struct.unpack_from("<II", b, o)
        if not (0 < size < 10_000_000 and 0 <= nf < 5000):
            break
        o += 8
        fields, ok = [], True
        for _ in range(nf):
            if o + 32 > len(b):
                ok = False
                break
            raw = b[o:o + 22].split(b"\0")[0]
            if not raw or not all(32 <= c < 127 for c in raw):
                ok = False
                break
            desc = struct.unpack_from("<5H", b, o + 22)
            fields.append(dict(name=raw.decode("ascii"), desc=list(desc)))
            o += 32
        if not ok:
            break
        classes.append(dict(name=name, size=size, fields=fields))
        off = o
    return classes, off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=ROOT + "/work/build/profile")
    ap.add_argument("--out", default=ROOT + "/work/map/saves")
    a = ap.parse_args()
    saves = sorted(glob.glob(f"{a.profile}/save/*/*/SAVE_000"))
    out = dict(saves=[])
    for p in saves:
        d = zlib.decompress(open(p, "rb").read())
        start = d.find(b"[DESC]")
        classes, end = parse(d, start + 6) if start >= 0 else ([], 0)
        label = os.path.basename(os.path.dirname(p))
        out["saves"].append(dict(label=label, path=p.replace("\\", "/"), bytes=len(d),
                                 descriptor_end=end, classes=classes))
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(f"{a.out}/schema.json", "w"), indent=1)
    allc = [c for s in out["saves"] for c in s["classes"]]
    names = {c["name"] for c in allc}
    fnames = {f["name"] for c in allc for f in c["fields"]}
    print(f"saves: {len(out['saves'])}, classes: {len(allc)} ({len(names)} distinct), fields: {len(fnames)} distinct")
    for s in out["saves"]:
        print(f"  {s['label']}: {len(s['classes'])} classes, "
              f"{sum(len(c['fields']) for c in s['classes'])} fields, schema ends at {s['descriptor_end']} of {s['bytes']}")
        for c in s["classes"][:3]:
            print(f"    {c['name']} size={c['size']} fields={[f['name'] for f in c['fields'][:5]]}")


if __name__ == "__main__":
    main()
