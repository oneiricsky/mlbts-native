#!/usr/bin/env python3
"""Tests of `make_hd_index.py --check`. Standard library only, no PS5 dump needed:

  python -I -m unittest discover -s tools -p test_hd_index.py

The files are synthetic TX12PS5 headers written to a temporary folder. One extra test runs --check on the real indexes
when the PS5 dump is present (skipped otherwise) and prints the counts; set HD_TEST_INDEXES to a path list (separated
like PATH) to choose which indexes it checks."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import make_hd_index as m  # noqa: E402

HEADER = 0x5a0


def blocks(w, h, bpb):
    return ((w + 3) // 4) * ((h + 3) // 4) * bpb


def ps5_bytes(w=64, h=32, levels=4, code=22, magic=b"TX12PS5\0", cut=0):
    """A TX12PS5 file: header, then zero texture data. BC7 (code 22) 16 bytes a block, BC1 (13) 8."""
    bpb = 16 if code == 22 else 8
    sizes = [blocks(max(1, w >> i), max(1, h >> i), bpb) for i in range(levels)]
    hd = bytearray(HEADER)
    hd[:8] = magic
    struct.pack_into("<I", hd, 0x0c, sum(sizes))
    struct.pack_into("<HH", hd, 0x84, w, h)
    struct.pack_into("<I", hd, 0x8c, levels)
    struct.pack_into("<I", hd, 0x15c, code)
    for i, s in enumerate(sizes):
        struct.pack_into("<I", hd, 0x1a0 + 32 * i + 4, s)
    data = bytes(hd) + bytes(sum(sizes))
    return data[:len(data) - cut] if cut else data


class CheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def put(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def index(self, *lines, root=True):
        p = self.root / "index.txt"
        p.write_text(("root " + str(self.root) + "\n" if root else "") + "\n".join(lines) + "\n")
        return p

    def check(self, *lines, **kw):
        n, probs = m.check_index(self.index(*lines, **kw), None if kw.get("root", True) else str(self.root))
        return n, [msg for _, msg in probs]

    GOOD = "0123456789abcdef 16 8 2 0 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX"

    def test_valid_file_has_no_problems(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        n, probs = self.check(self.GOOD)
        self.assertEqual((n, probs), (1, []))

    def test_valid_bc1_file_has_no_problems(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-COLOR.TEX", ps5_bytes(code=13))
        n, probs = self.check("0123456789abcdef 16 8 2 0 PS5/CHARACTERS/HEADS/AAA/AAA-COLOR.TEX")
        self.assertEqual(probs, [])

    def test_drop_is_counted_from_the_largest_level(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes(w=128, h=64, levels=5))
        self.assertEqual(self.check("0123456789abcdef 16 8 2 1 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX")[1], [])

    def test_truncated_file(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes(cut=500))
        _, probs = self.check(self.GOOD)
        self.assertTrue(probs)
        self.assertIn("cut short", probs[0])

    def test_file_shorter_than_its_texture_data(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes(cut=2500))
        _, probs = self.check(self.GOOD)
        self.assertIn("shorter than its header says", probs[0])

    def test_wrong_magic(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes(magic=b"TX12NSW\0"))
        _, probs = self.check(self.GOOD)
        self.assertIn("not a PS5 TX12 file", probs[0])

    def test_format_code_not_bc1_or_bc7(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes(code=20))
        _, probs = self.check(self.GOOD)
        self.assertIn("format code 20 is not BC1 (13) or BC7 (22)", probs[0])

    def test_index_size_that_is_not_a_power_of_two_times_the_switch_size(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        _, probs = self.check("0123456789abcdef 48 8 2 0 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX")
        self.assertIn("power of two", probs[0])

    def test_wrong_aspect_ratio(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        _, probs = self.check("0123456789abcdef 16 16 2 0 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX")
        self.assertIn("power of two", probs[0])

    def test_drop_that_leaves_no_level(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        _, probs = self.check("0123456789abcdef 16 8 2 4 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX")
        self.assertIn("leaves no level", probs[0])

    def test_too_few_levels_left_at_the_switch_size(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        _, probs = self.check("0123456789abcdef 16 8 4 0 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX")
        self.assertIn("levels are left at the Switch size", probs[0])

    def test_folder_name_must_match_the_file_name(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/BBB-NORMAL.TEX", ps5_bytes())
        _, probs = self.check("0123456789abcdef 16 8 2 0 PS5/CHARACTERS/HEADS/AAA/BBB-NORMAL.TEX")
        self.assertIn("does not start with its folder name AAA", probs[0])

    def test_missing_file(self):
        _, probs = self.check(self.GOOD)
        self.assertIn("file not found", probs[0])

    def test_two_files_with_one_hash_and_size(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        self.put("PS5/CHARACTERS/HEADS/BBB/BBB-NORMAL.TEX", ps5_bytes())
        _, probs = self.check(self.GOOD, "0123456789abcdef 16 8 2 0 PS5/CHARACTERS/HEADS/BBB/BBB-NORMAL.TEX")
        self.assertEqual(len(probs), 2)
        self.assertTrue(all("cannot be told apart" in p for p in probs))

    def test_malformed_line_and_path_outside_ps5(self):
        _, probs = self.check("not an index line", "0123456789abcdef 16 8 2 0 ../x/AAA/AAA-NORMAL.TEX")
        self.assertIn("not a line of the form", probs[0])
        self.assertIn("not a path of the form PS5/", probs[1])

    def test_ps5_option_replaces_the_root_line(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        p = self.root / "index.txt"
        p.write_text("root Z:/nowhere\n" + self.GOOD + "\n")
        self.assertEqual(m.check_index(p, str(self.root))[1], [])
        self.assertEqual(len(m.check_index(p)[1]), 1)

    def test_no_root_at_all(self):
        p = self.root / "bare.txt"
        p.write_text(self.GOOD + "\n")
        self.assertIn("no root line", m.check_index(p)[1][0][1])

    def test_command_line_exit_status(self):
        self.put("PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX", ps5_bytes())
        good = self.index(self.GOOD)
        run = lambda p: subprocess.run([sys.executable, "-I", str(TOOLS / "make_hd_index.py"), "--check", str(p)],
                                       capture_output=True, text=True)
        r = run(good)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "1 index lines checked, 0 problems in 0 lines"))
        bad = self.root / "bad.txt"
        bad.write_text("root " + str(self.root) + "\n0123456789abcdef 48 8 2 0 PS5/CHARACTERS/HEADS/AAA/AAA-NORMAL.TEX\n")
        r = run(bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("1 problems in 1 lines", r.stdout)


class RealIndexTest(unittest.TestCase):
    """Runs --check on the real indexes; needs the PS5 dump, so it is skipped in CI."""

    def test_real_indexes(self):
        repo = TOOLS.parent
        paths = os.environ.get("HD_TEST_INDEXES")
        paths = paths.split(os.pathsep) if paths else [str(repo / "work/build/hdtex/index.txt"),
                                                       str(repo / "work/build/hdtex_allc/index.txt")]
        paths = [p for p in paths if Path(p).is_file()]
        if not paths:
            self.skipTest("no real index found (set HD_TEST_INDEXES to try one)")
        for p in paths:
            root = next((ln[5:].strip() for ln in Path(p).read_text().splitlines() if ln.startswith("root ")), "")
            if not (root and (Path(root) / "PS5").is_dir()):
                self.skipTest(f"the PS5 dump named by {p} is not here")
            lines, probs = m.check_index(p)
            print(f"\n{p}: {lines} lines, {len(probs)} problems")
            for no, msg in probs[:10]:
                print(f"  line {no}: {msg}")
            self.assertGreater(lines, 0)


if __name__ == "__main__":
    unittest.main()
