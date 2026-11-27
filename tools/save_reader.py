"""Read and write the settings save archive through a structured model. Proof of concept.

    python -I tools/save_reader.py check <slot folder>
    python -I tools/save_reader.py list  <slot folder>                       # class and field names, no values
    python -I tools/save_reader.py get   <slot folder> CLASS RECORD FIELD
    python -I tools/save_reader.py set   <slot folder> CLASS RECORD FIELD (--int N | --text S) --out <new folder>

`set` never changes the input: it writes a new slot folder. Work on a copy of a profile, not the real one.

Layout ([C] = read from the 1.0.20 code, at main+offset; all numbers little-endian):

  "LE56"  u32 desc_len  "[DESC]"  class...  "[DATA]"  block...          desc_len counts "[DESC]" and the classes
  class:  name[16]  u32 payload (= 4 + 32 * n)  u32 n  field[n]                                  [C] 0xdf1e90
  field:  name[16]  u32 0  u16 0  u16 id  u16 width  u16 count  u32 bytes (= width * count)      [C] 0xdf1e90
  block:  name[16]  u32 records  record...                                                       [C] 0xdf2818
  record: every field of the class in descriptor order, `bytes` each, then the child blocks      [C] 0x181a2f0

  Element widths are 1 to 8 [C] 0xdf1d30. The writer compares width * count with the u32 [C] 0x181a378.
  Nesting is not recorded in the file. Each D_CSTM_SETTINGS record is followed by one D_USER_SETTINGS block and one
  D_FRANOPTIONS block, because the game's writer calls a per-record function that emits them [C] 0x181a170, in a
  loop over the record count [C] 0x18295e8. CHILDREN holds that knowledge.

Not decoded: what the field ids and most values mean, signedness, and whether a one-byte array is text (the
descriptor does not say; the caller decides, with text() and set_text()). Mismatched width * count, which the
game's writer tolerates for width 1 and which other saves use, is refused here.
"""
import argparse
import hashlib
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC, DESC, DATA = b"LE56", b"[DESC]", b"[DATA]"
NAME_LEN, FIELD_LEN, MAX_FIELDS = 16, 32, 250          # 250: the cap the game passes to its block reader/writer
INFO_LEN, HASH_OFF = 168, 136
CHILDREN = {"D_CSTM_SETTINGS": ("D_USER_SETTINGS", "D_FRANOPTIONS")}
KINDS = ("magic", "tag", "name", "length", "descriptor", "zero", "value")


class SaveError(ValueError):
    """The archive is not what the format says, or a value does not fit its field."""


@dataclass(frozen=True)
class Field:
    name: str
    ident: int
    width: int
    count: int

    @property
    def size(self):
        return self.width * self.count


@dataclass
class ClassDef:
    name: str
    fields: list

    @property
    def size(self):
        return sum(f.size for f in self.fields)


@dataclass
class Record:
    values: dict           # field name -> int, bytes (one-byte arrays) or list of int (wider arrays)
    children: list         # of Block


@dataclass
class Block:
    name: str
    records: list


@dataclass
class Archive:
    classes: list
    blocks: list

    def cls(self, name):
        for c in self.classes:
            if c.name == name:
                return c
        raise SaveError(f"no class {name}")

    def field(self, cls, name):
        for f in self.cls(cls).fields:
            if f.name == name:
                return f
        raise SaveError(f"{cls} has no field {name}")

    def records(self, name):
        """Every record of a class, in file order."""
        self.cls(name)
        out = []

        def walk(blocks):
            for b in blocks:
                for r in b.records:
                    if b.name == name:
                        out.append(r)
                    walk(r.children)

        walk(self.blocks)
        return out

    def record(self, cls, index):
        rs = self.records(cls)
        if not 0 <= index < len(rs):
            raise SaveError(f"{cls} has records 0 to {len(rs) - 1}, not {index}")
        return rs[index]

    def set(self, cls, index, field, value):
        f, r = self.field(cls, field), self.record(cls, index)
        r.values[field] = decode_value(f, encode_value(f, value))

    def _string_field(self, cls, name):
        f = self.field(cls, name)
        if f.width != 1 or f.count < 2:
            raise SaveError(f"{name} is not a one-byte array")
        return f

    def text(self, cls, index, field):
        self._string_field(cls, field)
        raw = self.record(cls, index).values[field].split(b"\0")[0]
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError:
            raise SaveError(f"{field} does not hold ASCII text") from None

    def set_text(self, cls, index, field, text):
        """ASCII only (what the game does with other bytes is unknown), NUL padded, at least one NUL kept."""
        f = self._string_field(cls, field)
        if not isinstance(text, str) or not text.isascii() or "\0" in text:
            raise SaveError(f"{field}: text must be ASCII without NUL")
        if len(text) >= f.count:
            raise SaveError(f"{field} holds {f.count - 1} characters, got {len(text)}")
        self.set(cls, index, field, text.encode("ascii").ljust(f.count, b"\0"))


def _int_bytes(f, v):
    if type(v) is not int:
        raise SaveError(f"{f.name} needs an integer, got {type(v).__name__}")
    if not 0 <= v < 1 << (8 * f.width):
        raise SaveError(f"{f.name} holds 0 to {(1 << (8 * f.width)) - 1}")
    return v.to_bytes(f.width, "little")


def encode_value(f, v):
    if f.count == 1:
        return _int_bytes(f, v)
    if f.width == 1:
        if not isinstance(v, bytes) or len(v) != f.count:
            raise SaveError(f"{f.name} needs exactly {f.count} bytes")
        return v
    if not isinstance(v, list) or len(v) != f.count:
        raise SaveError(f"{f.name} needs a list of exactly {f.count} integers")
    return b"".join(_int_bytes(f, x) for x in v)


def decode_value(f, raw):
    if f.count == 1:
        return int.from_bytes(raw, "little")
    if f.width == 1:
        return bytes(raw)
    return [int.from_bytes(raw[i:i + f.width], "little") for i in range(0, len(raw), f.width)]


# ---- reading --------------------------------------------------------------------------------------------------------

class _Reader:
    def __init__(self, raw, spans):
        self.raw, self.at, self.spans = raw, 0, spans

    def take(self, n, kind):
        if n > len(self.raw) - self.at:
            raise SaveError(f"truncated: {n} bytes wanted at {self.at:#x}")
        out = self.raw[self.at:self.at + n]
        if self.spans is not None:
            self.spans.append((self.at, n, kind))
        self.at += n
        return out

    def num(self, fmt, kind):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt), kind))[0]

    def expect(self, want, kind, what):
        at = self.at
        if self.take(len(want), kind) != want:
            raise SaveError(f"bad {what} at {at:#x}")

    def name(self):
        at = self.at
        slot = self.take(NAME_LEN, "name")
        text = slot.split(b"\0")[0]
        if not text or not all(32 < c < 127 for c in text) or any(slot[len(text):]):
            raise SaveError(f"bad name at {at:#x}")
        return text.decode("ascii")


def _read_class(r):
    name = r.name()
    payload, n = r.num("I", "length"), r.num("I", "length")
    if not 1 <= n <= MAX_FIELDS:
        raise SaveError(f"{name}: field count {n} out of range")
    if payload != 4 + FIELD_LEN * n:
        raise SaveError(f"{name}: payload length {payload} does not match {n} fields")
    fields = []
    for _ in range(n):
        fname = r.name()
        r.expect(b"\0" * 6, "zero", f"zero bytes in {name}.{fname}")
        ident, width, count = (r.num("H", "descriptor") for _ in range(3))
        size = r.num("I", "length")
        if not 1 <= width <= 8:
            raise SaveError(f"{name}.{fname}: element width {width}")
        if count < 1:
            raise SaveError(f"{name}.{fname}: element count 0")
        if size != width * count:
            raise SaveError(f"{name}.{fname}: size {size} is not width {width} times count {count}")
        fields.append(Field(fname, ident, width, count))
    if len({f.name for f in fields}) != n:
        raise SaveError(f"{name}: duplicate field name")
    return ClassDef(name, fields)


def _read_block(r, classes, children, want=None, depth=0):
    at = r.at
    name = r.name()
    if want is not None and name != want:
        raise SaveError(f"child block {want} expected at {at:#x}, found another name")
    if name not in classes:
        raise SaveError(f"data block at {at:#x} names a class that is not described")
    if depth > len(classes):
        raise SaveError("child classes nest in a loop")
    cls = classes[name]
    count = r.num("I", "length")
    if count > (len(r.raw) - r.at) // cls.size:
        raise SaveError(f"{name}: record count {count} does not fit in the file")
    records = []
    for _ in range(count):
        values = {f.name: decode_value(f, r.take(f.size, "value")) for f in cls.fields}
        kids = [_read_block(r, classes, children, k, depth + 1) for k in children.get(name, ())]
        records.append(Record(values, kids))
    return Block(name, records)


def parse(raw, children=CHILDREN, spans=None):
    """Decompressed archive -> Archive. Every byte must be explained; `spans` collects (offset, length, kind)."""
    r = _Reader(raw, spans)
    r.expect(MAGIC, "magic", "magic")
    desc_len = r.num("I", "length")
    end = r.at + desc_len
    r.expect(DESC, "tag", "[DESC] tag")
    classes = []
    while r.at < end:
        classes.append(_read_class(r))
    if r.at != end:
        raise SaveError(f"[DESC] length {desc_len} does not end on a class boundary")
    by_name = {c.name: c for c in classes}
    if len(by_name) != len(classes):
        raise SaveError("duplicate class name")
    r.expect(DATA, "tag", "[DATA] tag (or [DESC] length)")
    blocks = []
    while r.at < len(raw):
        blocks.append(_read_block(r, by_name, children))
    return Archive(classes, blocks)


# ---- writing --------------------------------------------------------------------------------------------------------

def _name_bytes(name):
    raw = name.encode("ascii", "strict") if name.isascii() else b""
    if not 1 <= len(raw) <= NAME_LEN or not all(32 < c < 127 for c in raw):
        raise SaveError("bad class or field name")
    return raw.ljust(NAME_LEN, b"\0")


def _write_block(b, classes, children):
    if b.name not in classes:
        raise SaveError(f"block of undescribed class {b.name}")
    cls = classes[b.name]
    out = [_name_bytes(b.name), struct.pack("<I", len(b.records))]
    names = [f.name for f in cls.fields]
    for r in b.records:
        if set(r.values) != set(names):
            raise SaveError(f"{b.name}: a record's fields differ from the class")
        out += [encode_value(f, r.values[f.name]) for f in cls.fields]
        if tuple(k.name for k in r.children) != tuple(children.get(b.name, ())):
            raise SaveError(f"{b.name}: a record's child blocks differ from the expected ones")
        out += [_write_block(k, classes, children) for k in r.children]
    return b"".join(out)


def write(archive, children=CHILDREN):
    """Archive -> decompressed bytes. Lengths and counts are computed here, never carried over."""
    desc = [DESC]
    for c in archive.classes:
        if not 1 <= len(c.fields) <= MAX_FIELDS or len({f.name for f in c.fields}) != len(c.fields):
            raise SaveError(f"{c.name}: bad field list")
        desc.append(_name_bytes(c.name) + struct.pack("<II", 4 + FIELD_LEN * len(c.fields), len(c.fields)))
        for f in c.fields:
            if not (1 <= f.width <= 8 and 1 <= f.count <= 0xFFFF and 0 <= f.ident <= 0xFFFF):
                raise SaveError(f"{c.name}.{f.name}: bad descriptor")
            desc.append(_name_bytes(f.name) + struct.pack("<IHHHHI", 0, 0, f.ident, f.width, f.count, f.size))
    desc = b"".join(desc)
    classes = {c.name: c for c in archive.classes}
    if len(classes) != len(archive.classes):
        raise SaveError("duplicate class name")
    data = b"".join(_write_block(b, classes, children) for b in archive.blocks)
    return MAGIC + struct.pack("<I", len(desc)) + desc + DATA + data


# ---- the slot folder ------------------------------------------------------------------------------------------------

def read_slot(folder):
    """(SAVEINFO bytes, decompressed archive). Refuses a wrong hash or a damaged stream."""
    folder = Path(folder)
    info = (folder / "SAVEINFO").read_bytes()
    packed = (folder / "SAVE_000").read_bytes()
    if len(info) != INFO_LEN:
        raise SaveError(f"SAVEINFO is {len(info)} bytes, not {INFO_LEN}")
    if info[HASH_OFF:] != hashlib.sha256(packed).digest():
        raise SaveError("SAVEINFO hash does not match SAVE_000")
    z = zlib.decompressobj()
    try:
        raw = z.decompress(packed)
    except zlib.error as e:
        raise SaveError(f"zlib: {e}") from None
    if not z.eof or z.unused_data:
        raise SaveError("zlib stream is cut short or has bytes after it")
    return info, raw


def write_slot(folder, info, raw):
    """Create a NEW slot folder. Level 6 gives the same compressed bytes as the game's own settings save."""
    folder = Path(folder)
    if len(info) != INFO_LEN:
        raise SaveError(f"SAVEINFO must be {INFO_LEN} bytes")
    try:
        folder.mkdir(parents=True)
    except FileExistsError:
        raise SaveError(f"{folder} exists; a slot is only written to a new folder") from None
    packed = zlib.compress(raw, 6)
    (folder / "SAVE_000").write_bytes(packed)
    (folder / "SAVEINFO").write_bytes(info[:HASH_OFF] + hashlib.sha256(packed).digest())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("check", "list", "get", "set"):
        p = sub.add_parser(cmd)
        p.add_argument("slot")
        if cmd in ("get", "set"):
            p.add_argument("cls")
            p.add_argument("record", type=int)
            p.add_argument("field")
        if cmd == "set":
            g = p.add_mutually_exclusive_group(required=True)
            g.add_argument("--int", type=lambda s: int(s, 0))
            g.add_argument("--text")
            p.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        info, raw = read_slot(a.slot)
        spans = []
        m = parse(raw, spans=spans)
        if a.cmd == "check":
            kinds = {k: sum(s[1] for s in spans if s[2] == k) for k in KINDS}
            print(f"hash ok; archive {len(raw)} bytes, explained {sum(kinds.values())}, opaque 0")
            print("  " + ", ".join(f"{k} {n}" for k, n in kinds.items()))
            for c in m.classes:
                n = len(m.records(c.name))
                print(f"  {c.name}: {len(c.fields)} fields, {n} records, {c.size} bytes each")
            print(f"round trip identical: {write(m) == raw}")
        elif a.cmd == "list":
            for c in m.classes:
                for f in c.fields:
                    print(f"{c.name} {f.name} id={f.ident} width={f.width} count={f.count}")
        elif a.cmd == "get":
            m.field(a.cls, a.field)
            print(m.record(a.cls, a.record).values[a.field])
        else:
            if a.text is not None:
                m.set_text(a.cls, a.record, a.field, a.text)
            else:
                m.set(a.cls, a.record, a.field, a.int)
            new = write(m)
            write_slot(a.out, info, new)
            diff = sum(x != y for x, y in zip(raw, new))
            ok = parse(read_slot(a.out)[1]) == m
            print(f"written to {a.out}: {diff} bytes differ; re-read matches the model: {ok}; hash ok")
    except (SaveError, OSError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
