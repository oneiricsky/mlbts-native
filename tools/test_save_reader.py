#!/usr/bin/env python3
"""Tests of tools/save_reader.py. The game is never started.

  python -I -m unittest discover -s tools -p test_save_reader.py -v

Most tests build small synthetic archives with struct (not with the module's writer), so they run anywhere.
The RealSave tests use a COPY of a settings slot and are skipped when there is none:

  work/scratch/savepoc/profile/save/u/SETT00000000122054E2   (or MLB_SAVE_COPY=<slot folder>)
  work/scratch/savepoc/proven/SETT00000000122054E2           optional: the edit that was seen loading in game

Assertions on real data compare booleans and offsets only, so a failure does not print save contents.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sr = load("save_reader")

# ---- a synthetic archive, packed by hand --------------------------------------------------------------------------

KIDS = {"PARENT": ("CHILD",)}
CLASSES = [
    ("PARENT", [("LABEL", 3, 1, 8), ("TEAM", 1, 1, 1)]),
    ("CHILD", [("FLAG", 0, 1, 1), ("WIDE", 1, 4, 1), ("LIST", 2, 2, 3)]),
    ("SIXTEEN_CHARS_AB", [("BLOB", 0, 1, 5)]),
]


def name16(s):
    return s.encode().ljust(16, b"\0")


def desc_block(name, fields, payload=None, nfields=None, dim2=None, zero=0):
    body = b""
    for fname, ident, width, count in fields:
        size = width * count if dim2 is None else dim2
        body += name16(fname) + struct.pack("<IHHHHI", zero, 0, ident, width, count, size)
    n = len(fields) if nfields is None else nfields
    p = 4 + len(body) if payload is None else payload
    return name16(name) + struct.pack("<II", p, n) + body


def data_head(name, count):
    return name16(name) + struct.pack("<I", count)


def parent(label, team):
    return label.ljust(8, b"\0") + bytes([team])


def child(flag, wide, items):
    return struct.pack("<BI3H", flag, wide, *items)


def child_block(*c):
    return data_head("CHILD", 1) + child(*c)


def default_data():
    return (data_head("PARENT", 2)
            + parent(b"ALPHA", 7) + child_block(1, 0x01020304, [10, 20, 30])
            + parent(b"BETA", 8) + child_block(0, 5, [1, 2, 65535])
            + data_head("SIXTEEN_CHARS_AB", 1) + bytes([9, 0, 255, 0, 1]))


def synth(classes=CLASSES, data=None, desc=None, desc_len=None):
    if desc is None:
        desc = b"".join(desc_block(n, f) for n, f in classes)
    desc = b"[DESC]" + desc
    n = len(desc) if desc_len is None else desc_len
    return b"LE56" + struct.pack("<I", n) + desc + b"[DATA]" + (default_data() if data is None else data)


def changed(a, b):
    assert len(a) == len(b), "lengths differ"
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


class Parse(unittest.TestCase):
    def test_model_holds_every_class_record_and_value(self):
        a = sr.parse(synth(), KIDS)
        self.assertEqual([c.name for c in a.classes], ["PARENT", "CHILD", "SIXTEEN_CHARS_AB"])
        self.assertEqual([(f.name, f.ident, f.width, f.count) for f in a.cls("CHILD").fields],
                         [("FLAG", 0, 1, 1), ("WIDE", 1, 4, 1), ("LIST", 2, 2, 3)])
        self.assertEqual(len(a.records("PARENT")), 2)
        self.assertEqual(len(a.records("CHILD")), 2)
        second = a.records("CHILD")[1]
        self.assertEqual(second.values, {"FLAG": 0, "WIDE": 5, "LIST": [1, 2, 65535]})
        self.assertEqual(a.records("PARENT")[1].values["LABEL"], b"BETA\0\0\0\0")
        self.assertEqual(a.text("PARENT", 1, "LABEL"), "BETA")
        self.assertEqual(a.records("SIXTEEN_CHARS_AB")[0].values["BLOB"], bytes([9, 0, 255, 0, 1]))

    def test_every_byte_is_accounted_for_once(self):
        raw, spans = synth(), []
        sr.parse(raw, KIDS, spans)
        at = 0
        for start, length, kind in spans:
            self.assertEqual(start, at)
            self.assertGreater(length, 0)
            self.assertIn(kind, sr.KINDS)
            at += length
        self.assertEqual(at, len(raw))
        self.assertNotIn("opaque", sr.KINDS)


class RoundTrip(unittest.TestCase):
    def test_identical(self):
        raw = synth()
        self.assertEqual(sr.write(sr.parse(raw, KIDS), KIDS), raw)

    def test_writer_uses_only_the_model(self):
        """An archive made from objects, never parsed, must equal the hand-packed bytes."""
        f = lambda *t: sr.Field(*t)
        classes = [sr.ClassDef(n, [f(*x) for x in fl]) for n, fl in CLASSES]
        kid = lambda fl, w, li: [sr.Block("CHILD", [sr.Record({"FLAG": fl, "WIDE": w, "LIST": li}, [])])]
        blocks = [
            sr.Block("PARENT", [
                sr.Record({"LABEL": b"ALPHA\0\0\0", "TEAM": 7}, kid(1, 0x01020304, [10, 20, 30])),
                sr.Record({"LABEL": b"BETA\0\0\0\0", "TEAM": 8}, kid(0, 5, [1, 2, 65535]))]),
            sr.Block("SIXTEEN_CHARS_AB", [sr.Record({"BLOB": bytes([9, 0, 255, 0, 1])}, [])])]
        self.assertEqual(sr.write(sr.Archive(classes, blocks), KIDS), synth())

    def test_every_single_byte_change_is_either_refused_or_reproduced(self):
        """No byte is ignored: if a changed archive still parses, writing it gives the changed bytes back."""
        raw = synth()
        accepted = 0
        for i in range(len(raw)):
            for v in (raw[i] ^ 0x01, raw[i] ^ 0x80):
                bad = raw[:i] + bytes([v]) + raw[i + 1:]
                try:
                    model = sr.parse(bad, KIDS)
                except sr.SaveError:
                    continue
                accepted += 1
                self.assertEqual(sr.write(model, KIDS), bad, f"byte {i}")
        self.assertGreater(accepted, 0)


class Edit(unittest.TestCase):
    def test_value_in_second_record_and_a_string(self):
        raw = synth()
        a = sr.parse(raw, KIDS)
        a.set("CHILD", 1, "WIDE", 0xAABBCCDD)
        a.set_text("PARENT", 1, "LABEL", "GAMMA")
        out = sr.write(a, KIDS)
        wide = raw.index(child(0, 5, [1, 2, 65535])) + 1
        label = raw.index(b"BETA")
        want = set(range(wide, wide + 4))
        want |= {label + i for i, (x, y) in enumerate(zip(b"BETA\0\0\0\0", b"GAMMA\0\0\0")) if x != y}
        self.assertEqual(set(changed(raw, out)), want)
        back = sr.parse(out, KIDS)
        self.assertEqual(back.records("CHILD")[1].values["WIDE"], 0xAABBCCDD)
        self.assertEqual(back.text("PARENT", 1, "LABEL"), "GAMMA")
        self.assertEqual(back.records("CHILD")[0], sr.parse(raw, KIDS).records("CHILD")[0])


class Refusal(unittest.TestCase):
    def setUp(self):
        self.a = sr.parse(synth(), KIDS)

    def refused(self, *args, text=False):
        before = sr.write(self.a, KIDS)
        with self.assertRaises(sr.SaveError):
            (self.a.set_text if text else self.a.set)(*args)
        self.assertEqual(sr.write(self.a, KIDS), before, "a refused edit changed the model")

    def test_integer_range(self):
        self.refused("CHILD", 0, "FLAG", 256)
        self.refused("CHILD", 0, "FLAG", -1)
        self.refused("CHILD", 0, "WIDE", 1 << 32)
        self.a.set("CHILD", 0, "WIDE", (1 << 32) - 1)

    def test_wrong_python_type(self):
        self.refused("CHILD", 0, "FLAG", "1")
        self.refused("CHILD", 0, "FLAG", 1.0)
        self.refused("CHILD", 0, "FLAG", True)
        self.refused("PARENT", 0, "LABEL", "ALPHA")
        self.refused("CHILD", 0, "LIST", 3)

    def test_wrong_length(self):
        self.refused("PARENT", 0, "LABEL", b"1234567")
        self.refused("PARENT", 0, "LABEL", b"123456789")
        self.refused("CHILD", 0, "LIST", [1, 2])
        self.refused("CHILD", 0, "LIST", [1, 2, 65536])

    def test_strings(self):
        self.a.set_text("PARENT", 0, "LABEL", "1234567")
        self.refused("PARENT", 0, "LABEL", "12345678", text=True)       # no room for the NUL
        self.refused("PARENT", 0, "LABEL", "a\0b", text=True)
        self.refused("PARENT", 0, "LABEL", "café", text=True)
        self.refused("CHILD", 0, "LIST", "ab", text=True)               # 2-byte elements are not a string
        self.refused("PARENT", 0, "TEAM", "a", text=True)

    def test_unknown_names(self):
        self.refused("PARENT", 2, "TEAM", 1)
        self.refused("PARENT", -1, "TEAM", 1)
        self.refused("PARENT", 0, "NOPE", 1)
        self.refused("NOPE", 0, "TEAM", 1)

    def test_writer_checks_a_model_changed_directly(self):
        for breakage in (lambda r: r.values.__setitem__("TEAM", 999),
                         lambda r: r.values.__setitem__("LABEL", b"x"),
                         lambda r: r.values.pop("TEAM"),
                         lambda r: r.values.__setitem__("EXTRA", 1),
                         lambda r: r.children.clear()):
            a = sr.parse(synth(), KIDS)
            breakage(a.records("PARENT")[1])
            with self.assertRaises(sr.SaveError):
                sr.write(a, KIDS)


class BrokenControls(unittest.TestCase):
    """Deliberately damaged archives. Each must be rejected, with a reason."""

    def bad(self, raw, why):
        with self.assertRaisesRegex(sr.SaveError, why):
            sr.parse(raw, KIDS)

    def test_one_value_byte_too_many_or_too_few(self):
        raw = synth()
        at = raw.index(b"ALPHA")
        self.bad(raw[:at] + b"X" + raw[at:], "name|count|child|trailing|class")
        self.bad(raw[:at] + raw[at + 1:], "name|count|child|truncated|class")
        self.bad(raw + b"\0", "trailing|truncated|name")
        self.bad(raw[:-1], "truncated|fit")

    def test_wrong_type_width_in_the_descriptor(self):
        wrong = [CLASSES[0], ("CHILD", [("FLAG", 0, 1, 1), ("WIDE", 1, 2, 1), ("LIST", 2, 2, 3)]), CLASSES[2]]
        self.bad(synth(wrong), "name|count|child|class")          # self-consistent descriptor, data no longer fits

    def test_descriptor_inconsistencies(self):
        good = [desc_block(n, f) for n, f in CLASSES]
        n, f = CLASSES[0]
        for block, why in ((desc_block(n, f, dim2=2), "size"),
                           (desc_block(n, f, payload=4), "payload"),
                           (desc_block(n, f, zero=1), "zero"),
                           (desc_block(n, [("LABEL", 3, 9, 1)]), "width"),
                           (desc_block(n, [("LABEL", 3, 1, 0)]), "count"),
                           (desc_block(n, [f[0], f[0]]), "duplicate")):
            self.bad(synth(desc=block + good[1] + good[2]), why)
        self.bad(synth(desc_len=10), "DESC")

    def test_data_inconsistencies(self):
        self.bad(synth(data=default_data().replace(data_head("PARENT", 2), data_head("PARENT", 3))),
                 "truncated|name|count|child")
        self.bad(synth(data=data_head("MISSING", 0)), "class")
        self.bad(synth(data=data_head("PARENT", 1) + parent(b"A", 1)), "truncated|child")
        self.bad(synth(data=data_head("PARENT", 0xFFFFFFFF)), "count")
        self.bad(b"XX56" + synth()[4:], "magic")

    def test_the_comparison_catches_a_writer_that_writes_the_wrong_length(self):
        """Control for the round-trip check itself: a writer one byte long or short must not compare equal."""
        raw = synth()
        a = sr.parse(raw, KIDS)
        real = sr.encode_value
        for broken in (lambda f, v: real(f, v) + (b"\0" if f.name == "TEAM" else b""),
                       lambda f, v: real(f, v)[:-1] if f.name == "LIST" else real(f, v)):
            sr.encode_value = broken
            try:
                out = sr.write(a, KIDS)
            finally:
                sr.encode_value = real
            self.assertNotEqual(out, raw)
            with self.assertRaises(sr.SaveError):
                sr.parse(out, KIDS)


class Slot(unittest.TestCase):
    def make(self, d, raw):
        d.mkdir()
        packed = zlib.compress(raw, 6)
        info = b"Name".ljust(96, b"\0") + b"\x11" * 32 + struct.pack("<Q", 1000) + hashlib.sha256(packed).digest()
        (d / "SAVE_000").write_bytes(packed)
        (d / "SAVEINFO").write_bytes(info)
        return info, packed

    def test_write_new_slot_updates_only_the_hash(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = Path(t) / "a", Path(t) / "b"
            info, packed = self.make(src, synth())
            got_info, raw = sr.read_slot(src)
            a = sr.parse(raw, KIDS)
            a.set("PARENT", 1, "TEAM", 99)
            sr.write_slot(dst, got_info, sr.write(a, KIDS))
            new_info = (dst / "SAVEINFO").read_bytes()
            self.assertEqual(new_info[:136], info[:136])
            self.assertEqual(new_info[136:], hashlib.sha256((dst / "SAVE_000").read_bytes()).digest())
            self.assertNotEqual(new_info[136:], info[136:])
            self.assertEqual(sr.parse(sr.read_slot(dst)[1], KIDS).records("PARENT")[1].values["TEAM"], 99)
            self.assertEqual((src / "SAVE_000").read_bytes(), packed)

    def test_refuses_to_overwrite_and_detects_damage(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "a"
            info, packed = self.make(src, synth())
            with self.assertRaises(sr.SaveError):
                sr.write_slot(src, info, synth())
            self.assertEqual((src / "SAVE_000").read_bytes(), packed)
            (src / "SAVE_000").write_bytes(packed + b"\0")
            with self.assertRaisesRegex(sr.SaveError, "hash"):
                sr.read_slot(src)
            (src / "SAVEINFO").write_bytes(info[:136] + hashlib.sha256(packed + b"\0").digest())
            with self.assertRaisesRegex(sr.SaveError, "zlib"):
                sr.read_slot(src)


# ---- the copy of a real settings slot ------------------------------------------------------------------------------

SLOT = "SETT00000000122054E2"
COPY = Path(os.environ.get("MLB_SAVE_COPY") or ROOT / "work/scratch/savepoc/profile/save/u" / SLOT)
PROVEN = ROOT / "work/scratch/savepoc/proven" / SLOT


@unittest.skipUnless((COPY / "SAVE_000").is_file(), "no copy of a settings slot")
class RealSave(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info, cls.raw = sr.read_slot(COPY)
        cls.spans = []
        cls.model = sr.parse(cls.raw, spans=cls.spans)

    def field_offset(self, cls_name, index, field):
        """Independent of save_reader: the older schema parser plus a search for the class's block headers."""
        old = load("save_schema")
        classes, _ = old.parse(self.raw, self.raw.index(b"[DESC]") + 6)
        fields = next(c for c in classes if c["name"] == cls_name)["fields"]
        before = 0
        for f in fields:
            if f["name"] == field:
                break
            before += f["desc"][1] * f["desc"][2]
        if cls_name == "D_CSTM_SETTINGS":                       # one block; records are separated by their children
            first = self.raw.index(b"[DATA]") + 6 + 20
            second = self.raw.index(b"D_FRANOPTIONS", first) + 20 + 12
            return first + before + index * (second - first)
        at = self.raw.index(b"[DATA]")
        for _ in range(index + 1):
            at = self.raw.index(cls_name.encode(), at + 1)
        return at + 20 + before

    def test_round_trip_and_accounting(self):
        self.assertTrue(sr.write(self.model) == self.raw, "round trip differs")
        self.assertEqual(sum(s[1] for s in self.spans), len(self.raw))
        self.assertTrue(all(a[0] + a[1] == b[0] for a, b in zip(self.spans, self.spans[1:])))
        values = sum(c.size * len(self.model.records(c.name)) for c in self.model.classes)
        self.assertEqual(sum(s[1] for s in self.spans if s[2] == "value"), values)

    def test_every_byte_of_the_real_archive_matters(self):
        """Flip one bit in every byte in turn: refused, or reproduced exactly by the writer."""
        refused = 0
        for i in range(len(self.raw)):
            bad = self.raw[:i] + bytes([self.raw[i] ^ 1]) + self.raw[i + 1:]
            try:
                m = sr.parse(bad)
            except sr.SaveError:
                refused += 1
                continue
            self.assertTrue(sr.write(m) == bad, f"byte {i} was ignored")
        values = sum(s[1] for s in self.spans if s[2] == "value")
        ids = 2 * sum(len(c.fields) for c in self.model.classes)
        # Values and field ids are free to change; at least the rest of the structure must be checked.
        self.assertGreater(refused, 0)
        self.assertLessEqual(refused, len(self.raw) - values - ids)

    def test_counts(self):
        counts = {c.name: (len(c.fields), len(self.model.records(c.name))) for c in self.model.classes}
        self.assertEqual(counts, {"D_CSTM_SETTINGS": (4, 30), "D_USER_SETTINGS": (222, 30),
                                  "D_FRANOPTIONS": (12, 30), "D_ORTCOUNTERS": (1, 1)})

    def test_slot_rewrite_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as t:
            dst = Path(t) / "out"
            sr.write_slot(dst, self.info, sr.write(self.model))
            for n in ("SAVE_000", "SAVEINFO"):
                self.assertTrue((dst / n).read_bytes() == (COPY / n).read_bytes(), f"{n} differs")

    def test_edit_non_first_records_changes_only_those_bytes(self):
        m = sr.parse(self.raw)
        cls, index = "D_USER_SETTINGS", 17
        field = m.cls(cls).fields[5].name
        new = m.records(cls)[index].values[field] ^ 1
        m.set(cls, index, field, new)
        old_name = m.records("D_CSTM_SETTINGS")[17].values["PROFILE_NAME"]
        m.set_text("D_CSTM_SETTINGS", 17, "PROFILE_NAME", "POC_NAME")
        out = sr.write(m)
        a = self.field_offset(cls, index, field)
        s = self.field_offset("D_CSTM_SETTINGS", 17, "PROFILE_NAME")
        want = {a} | {s + i for i, (x, y) in enumerate(zip(old_name, b"POC_NAME".ljust(16, b"\0"))) if x != y}
        self.assertEqual(set(changed(self.raw, out)), want)
        with tempfile.TemporaryDirectory() as t:
            dst = Path(t) / "out"
            sr.write_slot(dst, self.info, out)
            info = (dst / "SAVEINFO").read_bytes()
            self.assertTrue(info[136:] == hashlib.sha256((dst / "SAVE_000").read_bytes()).digest())
            self.assertTrue(info[:136] == self.info[:136])
            back = sr.parse(sr.read_slot(dst)[1])
        self.assertEqual(back.records(cls)[index].values[field], new)
        self.assertEqual(back.text("D_CSTM_SETTINGS", 17, "PROFILE_NAME"), "POC_NAME")

    def test_broken_controls(self):
        at = self.field_offset("D_CSTM_SETTINGS", 17, "PROFILE_NAME")
        for bad in (self.raw[:at] + b"X" + self.raw[at:], self.raw[:at] + self.raw[at + 1:],
                    self.raw[:-1], self.raw + b"\0"):
            with self.assertRaises(sr.SaveError):
                sr.parse(bad)
        d = self.raw.index(b"PROFILE_NAME") + 16 + 8           # the descriptor's element width
        with self.assertRaisesRegex(sr.SaveError, "size"):
            sr.parse(self.raw[:d] + b"\x02" + self.raw[d + 1:])
        with self.assertRaises(sr.SaveError):
            sr.parse(self.raw).set("D_USER_SETTINGS", 1, self.model.cls("D_USER_SETTINGS").fields[0].name, 256)
        with self.assertRaises(sr.SaveError):
            sr.parse(self.raw).set_text("D_CSTM_SETTINGS", 1, "PROFILE_NAME", "X" * 16)

    @unittest.skipUnless((ROOT / "work/map/saves/schema.json").is_file(), "no schema.json")
    def test_same_bytes_as_save_edit(self):
        old = load("save_edit")
        with contextlib.redirect_stdout(io.StringIO()):
            theirs, _ = old.set_field(self.raw, "D_CSTM_SETTINGS", "PROFILE_NAME", string="TESTNAME")
        m = sr.parse(self.raw)
        m.set_text("D_CSTM_SETTINGS", 0, "PROFILE_NAME", "TESTNAME")
        self.assertTrue(sr.write(m) == theirs, "differs from save_edit.set_field")

    @unittest.skipUnless((PROVEN / "SAVE_000").is_file(), "no copy of the edit that loaded in game")
    def test_reproduces_the_edit_that_loaded_in_game(self):
        _, proven = sr.read_slot(PROVEN)
        m = sr.parse(self.raw)
        m.set_text("D_CSTM_SETTINGS", 0, "PROFILE_NAME", "TESTNAME")
        self.assertTrue(sr.write(m) == proven, "differs from the proven archive")


if __name__ == "__main__":
    unittest.main()
