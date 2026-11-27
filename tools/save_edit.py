"""Inspect, verify and rewrite the container parts of a game save.

    python -I tools/save_edit.py info   [--profile work/build/profile]
    python -I tools/save_edit.py verify [--profile ...]
    python -I tools/save_edit.py rename --slot FRAN000000006DC0E6E7 --name "My Franchise" [--profile ...] [--write]
    python -I tools/save_edit.py rehash --slot SETT00000000122054E2 [--profile ...] [--write]

What is known about the container (measured on the saves in work/build/profile/save):
  SAVE_000    zlib stream; after decompression it starts with [DESC] (the class schema) and then [DATA] blocks.
  SAVEINFO    168 bytes: display name (96, NUL padded), u64 Unix time at 128, SHA-256 at 136.
              The SHA-256 is over the *compressed* SAVE_000 bytes, not the decompressed archive.
So the display name and the timestamp can be changed without touching the hash, and any edit of SAVE_000 needs
its compressed bytes hashed back into SAVEINFO[136:168].

This tool does the container only. Editing values inside [DATA] is not implemented: the per-field value encoding
is only partly decoded (see the Save schema page) and a wrong length corrupts the archive.
"""
import argparse, hashlib, json, os, struct, sys, time, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
NAME_LEN, TIME_OFF, HASH_OFF, INFO_LEN = 96, 128, 136, 168


def slots(profile):
    out = []
    for fam in sorted(os.listdir(f"{profile}/save")):
        d = f"{profile}/save/{fam}"
        if not os.path.isdir(d):
            continue
        for slot in sorted(os.listdir(d)):
            sd = f"{d}/{slot}"
            if os.path.isfile(f"{sd}/SAVEINFO") and os.path.isfile(f"{sd}/SAVE_000"):
                out.append((slot, sd))
    return out


def read_slot(d):
    info = open(f"{d}/SAVEINFO", "rb").read()
    data = open(f"{d}/SAVE_000", "rb").read()
    name = info[:NAME_LEN].split(b"\0")[0].decode("utf-8", "replace")
    stamp = struct.unpack_from("<Q", info, TIME_OFF)[0]
    return info, data, name, stamp


def set_field(raw, cls, field, string=None, uint=None):
    """Patch one field inside a class's value block. Returns (new_raw, note)."""
    name = cls.encode()
    pos = raw.find(b"[DATA]")
    if pos < 0:
        raise SystemExit("no [DATA] section")
    at = raw.find(name, pos)
    if at < 0:
        raise SystemExit(f"class {cls} not found in the value section")
    slot = ((len(name) + 1 + 15) // 16) * 16
    values = at + slot + 4
    off = 0
    for f in cls_fields(cls):
        if f["name"] == field:
            size = f["desc"][1] * f["desc"][2]
            if string is not None:
                text = string.encode("utf-8")
                if len(text) + 1 > size:
                    raise SystemExit(f"{field} holds {size} bytes; the string needs {len(text) + 1}")
                patch = text.ljust(size, b"\0")
            elif uint is not None:
                if size >= 4:
                    patch = struct.pack("<I", uint) + b"\0" * (size - 4)
                elif size == 2:
                    patch = struct.pack("<H", uint)
                elif size == 1:
                    patch = bytes([uint & 0xFF])
                else:
                    raise SystemExit(f"{field} is {size} bytes; use --string")
            else:
                raise SystemExit("give --string or --uint")
            old = raw[values + off:values + off + size]
            return raw[:values + off] + patch + raw[values + off + size:], \
                f"{cls}.{field}: {old.hex()} -> {patch.hex()} at archive +{values + off:#x} (field {size}B)"
        off += f["desc"][1] * f["desc"][2]
    raise SystemExit(f"{cls} has no field {field}")


def cls_fields(cls):
    schema = json.load(open(ROOT + "/work/map/saves/schema.json"))
    for s in schema["saves"]:
        for c in s["classes"]:
            if c["name"] == cls:
                return c["fields"]
    raise SystemExit(f"class {cls} is not in the schema; run tools/save_schema.py first")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["info", "verify", "rename", "rehash", "recompress", "set-field"])
    ap.add_argument("--profile", default=ROOT + "/work/build/profile")
    ap.add_argument("--slot")
    ap.add_argument("--name")
    ap.add_argument("--write", action="store_true", help="apply the change (otherwise only show it)")
    ap.add_argument("--class", dest="cls", help="class name for set-field, e.g. D_CSTM_SETTINGS")
    ap.add_argument("--field", help="field name for set-field, e.g. PROFILE_NAME")
    ap.add_argument("--string", help="new string value for set-field")
    ap.add_argument("--uint", type=lambda s: int(s, 0), help="new integer value for set-field (decimal or 0x)")
    ap.add_argument("--schema", default=ROOT + "/work/map/saves/schema.json")
    a = ap.parse_args()
    sl = slots(a.profile)
    if not sl:
        sys.exit(f"no saves under {a.profile}/save")
    if a.cmd in ("rename", "rehash", "recompress", "set-field") and not a.slot:
        sys.exit("--slot is required for rename/rehash/recompress/set-field")
    if a.cmd == "set-field" and not (a.cls and a.field):
        sys.exit("--class and --field are required for set-field")
    for fam, d in sl:
        info, data, name, stamp = read_slot(d)
        want = hashlib.sha256(data).hexdigest()
        have = info[HASH_OFF:HASH_OFF + 32].hex()
        ok = want == have
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stamp)) if stamp else "-"
        if a.cmd == "info":
            print(f"{fam}  {name!r}  saved {when}  payload {len(data)}B  hash {'ok' if ok else 'MISMATCH'}")
            continue
        if a.cmd == "verify":
            print(f"{fam}  hash {'ok' if ok else 'MISMATCH'}  ({have[:16]}... vs {want[:16]}...)")
            continue
        if fam != a.slot:
            continue
        if a.cmd == "set-field" and fam == a.slot:
            raw = zlib.decompress(data)
            new, note = set_field(raw, a.cls, a.field, a.string, a.uint)
            print(note)
            if a.write:
                packed = zlib.compress(new, 9)
                open(f"{d}/SAVE_000", "wb").write(packed)
                info = info[:HASH_OFF] + hashlib.sha256(packed).digest() + info[HASH_OFF + 32:]
                open(f"{d}/SAVEINFO", "wb").write(info)
                back = zlib.decompress(open(f"{d}/SAVE_000", "rb").read())
                print(f"  written; archive re-read identical: {back == new}; hash updated")
        if a.cmd == "rename":
            text = (a.name or "").encode("utf-8")
            if not text or len(text) >= NAME_LEN:
                sys.exit(f"name must be 1..{NAME_LEN - 1} bytes")
            print(f"{fam}: {name!r} -> {a.name!r}")
            if a.write:
                info = text.ljust(NAME_LEN, b"\0") + info[NAME_LEN:]
                open(f"{d}/SAVEINFO", "wb").write(info)
                print("  written")
        if a.cmd == "rehash":
            print(f"{fam}: hash {have[:16]}... -> {want[:16]}...")
            if a.write:
                info = info[:HASH_OFF] + bytes.fromhex(want) + info[HASH_OFF + 32:]
                open(f"{d}/SAVEINFO", "wb").write(info)
                print("  written")
        if a.cmd == "recompress":
            raw = zlib.decompress(data)
            packed = zlib.compress(raw, 9)
            print(f"{fam}: {len(data)}B compressed -> {len(packed)}B, {len(raw)}B decompressed")
            if a.write:
                open(f"{d}/SAVE_000", "wb").write(packed)
                info = info[:HASH_OFF] + hashlib.sha256(packed).digest() + info[HASH_OFF + 32:]
                open(f"{d}/SAVEINFO", "wb").write(info)
                back = zlib.decompress(open(f"{d}/SAVE_000", "rb").read())
                print(f"  written; re-read {len(back)}B, identical={back == raw}")


if __name__ == "__main__":
    main()
