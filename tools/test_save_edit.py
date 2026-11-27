"""Checks tools/save_edit.py on made-up saves. Run: python -I -m unittest discover -s tools -p test_save_edit.py"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import save_edit  # noqa: E402


class Rename(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.profile = tmp.name
        slot = os.path.join(self.profile, "save", "FRAN", "FRAN01")
        os.makedirs(slot)
        self.info = os.path.join(slot, "SAVEINFO")
        self.before = b"Old".ljust(96, b"\0") + b"u" * 32 + struct.pack("<Q", 1700000000) + b"h" * 32
        with open(self.info, "wb") as f:
            f.write(self.before)
        with open(os.path.join(slot, "SAVE_000"), "wb") as f:
            f.write(zlib.compress(b"[DESC][DATA]"))

    def rename(self, name):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "save_edit.py"), "rename", "--profile",
                            self.profile, "--slot", "FRAN01", "--name", name, "--write"], capture_output=True)
        self.stderr = r.stderr.decode(errors="replace")
        with open(self.info, "rb") as f:
            return r.returncode, f.read()

    def test_a_name_over_95_bytes_is_refused_and_nothing_is_written(self):
        code, after = self.rename("é" * 48)   # 48 characters, 96 bytes
        self.assertNotEqual(code, 0)
        self.assertEqual(after, self.before)

    def test_a_95_byte_name_keeps_the_layout(self):
        code, after = self.rename("é" * 47 + "x")
        self.assertEqual(code, 0, self.stderr)
        self.assertEqual(after[:96], ("é" * 47 + "x").encode() + b"\0")
        self.assertEqual(after[96:], self.before[96:])


class SetString(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "work", "map", "saves"))
        schema = {"saves": [{"classes": [{"name": "D_X", "fields": [{"name": "NAME", "desc": [0, 1, 8]}]}]}]}
        with open(os.path.join(tmp.name, "work", "map", "saves", "schema.json"), "w") as f:
            json.dump(schema, f)
        old = save_edit.ROOT
        self.addCleanup(setattr, save_edit, "ROOT", old)
        save_edit.ROOT = tmp.name
        # class name in a 16-byte slot, four bytes, then the 8-byte field and what follows it
        self.raw = b"[DATA]" + b"D_X".ljust(16, b"\0") + b"\0" * 4 + b"AAAAAAAA" + b"TAIL"

    def test_a_string_over_the_field_in_bytes_is_refused(self):
        with self.assertRaises(SystemExit):
            save_edit.set_field(self.raw, "D_X", "NAME", string="é" * 4)   # 4 characters, 8 bytes + NUL

    def test_a_string_that_fits_keeps_the_length(self):
        new, _ = save_edit.set_field(self.raw, "D_X", "NAME", string="éab")
        self.assertEqual(len(new), len(self.raw))
        self.assertEqual(new[-12:], "éab".encode().ljust(8, b"\0") + b"TAIL")


if __name__ == "__main__":
    unittest.main()
