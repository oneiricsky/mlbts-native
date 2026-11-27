#!/usr/bin/env python3
"""Tests of make_hd_index.py: building an index and `--check`. Standard library only, no PS5 dump needed:

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


def lz4_literals(data):
    """An LZ4 block holding `data` as one run of literals."""
    out, n = bytearray(), len(data)
    out.append(min(n, 15) << 4)
    if n >= 15:
        n -= 15
        out += b"\xff" * (n // 255) + bytes([n % 255])
    return bytes(out) + data


def nsw_bytes(first, second=None):
    """A TX12NSW file whose storage is `first` (16x8, 2 levels), followed by `second` (the 8x4 half-size variant)."""
    hd = bytearray(0x2A0)
    hd[:8] = b"TX12NSW\0"
    a = lz4_literals(first)
    b = lz4_literals(second) if second is not None else b""
    struct.pack_into("<I", hd, 0x10, len(first) + len(second or b""))
    struct.pack_into("<HH", hd, 0x84, 16, 8)
    struct.pack_into("<I", hd, 0x8c, 2)
    struct.pack_into("<I", hd, 0x154, len(hd))
    struct.pack_into("<I", hd, 0x170, 1 if second is None else 2)
    if second is not None:
        struct.pack_into("<HH", hd, 0xa4, 8, 4)
        struct.pack_into("<I", hd, 0xac, 1)
        struct.pack_into("<I", hd, 0x104, len(second))
        struct.pack_into("<I", hd, 0x10c, len(a))
    return bytes(hd) + a + b


def storage(tail=b"", fill=1):
    return bytes([fill]) * m.PREFIX + tail


class BuildTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.nsw = self.root / "NSW"

    def head(self, name, switch, ps5_fill=None):
        """A Switch head normal map, and its PS5 file unless ps5_fill is None."""
        rel = f"CHARACTERS/HEADS/{name}/{name}-NORMAL.TEX"
        p = self.nsw / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(switch)
        if ps5_fill is not None:
            q = self.root / "PS5" / rel
            q.parent.mkdir(parents=True, exist_ok=True)
            data = bytearray(ps5_bytes())
            data[-1] = ps5_fill
            q.write_bytes(bytes(data))
        return rel

    def build(self, paths, others=()):
        lines, report = m.build_index(self.root, self.nsw, paths, list(others))
        index = self.root / "index.txt"
        index.write_text(f"root {self.root}\n" + "".join(ln + "\n" for ln in lines))
        self.assertEqual(m.check_index(index)[1], [])
        return [ln.split() for ln in lines], report

    def test_two_variants_are_two_blocks(self):
        p = self.root / "v.tex"
        p.write_bytes(nsw_bytes(storage(b"abc"), b"half"))
        got = m.switch_variants(p, full=True)
        self.assertEqual([(w, h, n, d) for w, h, n, d in got],
                         [(16, 8, 2, storage(b"abc") + b"half"), (8, 4, 1, b"half")])
        self.assertEqual(m.switch_variants(p)[0][3], storage()[:m.PREFIX])

    def test_a_texture_of_its_own_needs_no_second_hash(self):
        lines, _ = self.build([self.head("AAA", nsw_bytes(storage()), 1)])
        self.assertEqual([len(x) for x in lines], [6])

    def test_same_start_different_rest_is_told_apart_by_the_whole_storage(self):
        paths = [self.head("AAA", nsw_bytes(storage(b"a")), 1), self.head("BBB", nsw_bytes(storage(b"b")), 2)]
        lines, report = self.build(paths)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][0], lines[1][0])
        self.assertEqual({x[5] for x in lines},
                         {f"={m.fnv64(storage(t)):016x}/{m.PREFIX + 1}" for t in (b"a", b"b")})
        self.assertEqual((len(report["indexed"]), report["opened"]), (2, set()))

    def test_one_ps5_texture_under_two_names_is_one_line(self):
        paths = [self.head("AAA", nsw_bytes(storage(b"a")), 1), self.head("BBB", nsw_bytes(storage(b"a")), 1)]
        lines, report = self.build(paths)
        self.assertEqual([len(x) for x in lines], [6])
        self.assertEqual(report["indexed"], set(paths))

    def test_same_switch_texture_different_ps5_files_wait_for_the_opened_file(self):
        paths = [self.head("AAA", nsw_bytes(storage(b"a")), 1), self.head("BBB", nsw_bytes(storage(b"a")), 2)]
        lines, report = self.build(paths)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][5], lines[1][5])
        self.assertEqual(report["opened"], set(paths))

    def test_a_head_without_a_ps5_file_blocks_the_short_hash(self):
        mine = self.head("AAA", nsw_bytes(storage(b"a")), 1)
        other = self.head("BBB", nsw_bytes(storage(b"b")))
        lines, report = self.build([mine], [other])
        self.assertEqual([len(x) for x in lines], [7])
        self.assertEqual(report["indexed"], {mine})

    def test_same_switch_texture_as_a_head_without_a_ps5_file_is_not_used(self):
        mine = self.head("AAA", nsw_bytes(storage(b"a")), 1)
        other = self.head("BBB", nsw_bytes(storage(b"a")))
        lines, report = self.build([mine, other])
        self.assertEqual(lines, [])
        self.assertIn("is the same as", report["unused"][mine])
        self.assertEqual(report["unused"][other], "no PS5 file in the dump")


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
