#!/usr/bin/env python3
"""Tests of tools/harness.py. No real game needed: a fake game script stands in for mlb.exe.

  python -I -m unittest discover -s tools -p test_harness.py

The fake game reads the scenario named by MLB_HARNESS, writes a dump into MLB_HARNESS_OUT and prints the log lines the
real runtime prints (audout, marker lines, perf lines). FAKE_MODE picks a failure: nodev, crash, hang, stall, slow."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("harness", TOOLS / "harness.py")
h = importlib.util.module_from_spec(spec)
sys.modules["harness"] = h
spec.loader.exec_module(h)

FAKE = r'''
import os, sys, time
sc = dict(l.split("=", 1) for l in open(os.environ["MLB_HARNESS"]).read().splitlines() if "=" in l)
out = os.environ["MLB_HARNESS_OUT"]
mode = os.environ.get("FAKE_MODE", "ok")
fps = 20.0 if mode == "slow" else 60.0
if mode == "nodev":
    print("audout: no output device (asleep): buffers are recycled without sound", flush=True)
    time.sleep(0.2)
    sys.exit(0)
print("audout: WASAPI device 'Speakers' opened, 48000 Hz", flush=True)
print("[host] harness: marker boot frame 10 t 1.500", flush=True)
data = bytearray(range(256)) * 4
if os.environ.get("MLB_X") == "1":
    data[5] ^= 0xFF
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "texture_0x25_32x32.raw"), "wb") as f:
    f.write(data)
if mode == "hang":
    time.sleep(60)
if mode == "crash":
    print("FATAL: access violation at 0x1234", flush=True)
    sys.exit(3)
if mode == "stall":
    print("frametime:   worst frame 77: 5000.0 ms", flush=True)
print("[host] harness: marker inning frame %d t %.3f" % (10 + int(10 * fps), 11.5), flush=True)
print("frametime: 60 s: 3600 frames in 60.0 s, mean 60.0 fps, 1%% low 55.0 fps, over 25 ms 0, 50 ms 0, 100 ms 0", flush=True)
'''

SCENARIO = """# a test scenario
name = unit
home = 3
away = 7
seed = 42
fixed_clock = 1
stop_after_s = 5
dump = texture:fmt=0x25,size=512x512
dump = texture:fmt=0x26,size=64x64
markers = boot,inning
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.fake = self.dir / "fake_game.py"
        self.fake.write_text(FAKE)
        self.scn = self.dir / "unit.scn"
        self.scn.write_text(SCENARIO)
        self.lock = self.dir / "game.lock"
        os.environ["MLB_GAME_LOCK"] = str(self.lock)
        self.addCleanup(os.environ.pop, "MLB_GAME_LOCK", None)
        real = h.stray_game_processes     # tasklist takes about 2 s; the fake game is not an mlb*.exe anyway
        h.stray_game_processes = lambda: []
        self.addCleanup(setattr, h, "stray_game_processes", real)

    def run_quiet(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                code = h.main(argv)
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
                if isinstance(e.code, str):
                    buf.write(e.code)
        return code, buf.getvalue()

    def common(self, *more):
        return ["--exe", str(self.fake), "--out", str(self.dir / "out"), "--grace", "10", *more]


class ScenarioParsing(Base):
    def test_reads_every_key_and_repeated_dump(self):
        s = h.parse_scenario(SCENARIO)
        self.assertEqual((s["name"], s["home"], s["away"], s["seed"]), ("unit", 3, 7, 42))
        self.assertEqual(s["fixed_clock"], 1)
        self.assertEqual(s["stop_after_s"], 5.0)
        self.assertEqual(s["dump"], ["texture:fmt=0x25,size=512x512", "texture:fmt=0x26,size=64x64"])
        self.assertEqual(s["markers"], "boot,inning")

    def test_team_out_of_range_is_refused(self):
        with self.assertRaisesRegex(h.ScenarioError, "home.*0.*29"):
            h.parse_scenario("home = 30\n")

    def test_bad_line_names_its_number(self):
        with self.assertRaisesRegex(h.ScenarioError, "line 2"):
            h.parse_scenario("name = x\nnonsense\n")

    def test_fixed_clock_must_be_0_or_1(self):
        with self.assertRaises(h.ScenarioError):
            h.parse_scenario("fixed_clock = 2\n")

    def test_unknown_key_is_kept_not_fatal(self):
        s = h.parse_scenario("name = x\nfuture_key = 9\n")
        self.assertEqual(s["extra"], {"future_key": "9"})


class Lock(Base):
    def test_second_taker_waits_then_times_out_with_clear_message(self):
        with h.game_lock(str(self.lock), timeout=5, poll=0.05):
            with self.assertRaisesRegex(h.HarnessError, "game.lock.*held"):
                with h.game_lock(str(self.lock), timeout=0.2, poll=0.05):
                    pass
        self.assertFalse(self.lock.exists())

    def test_released_on_exception(self):
        with self.assertRaises(RuntimeError):
            with h.game_lock(str(self.lock), timeout=1, poll=0.05):
                raise RuntimeError("boom")
        self.assertFalse(self.lock.exists())

    def test_waits_for_a_holder_that_lets_go(self):
        self.lock.mkdir()
        threading.Timer(0.3, self.lock.rmdir).start()
        t = time.time()
        with h.game_lock(str(self.lock), timeout=5, poll=0.05):
            self.assertGreaterEqual(time.time() - t, 0.25)
        self.assertFalse(self.lock.exists())


class LogParsing(unittest.TestCase):
    def test_markers_and_audio(self):
        log = ("audout: WASAPI device 'X' opened\n[host] harness: marker boot frame 10 t 1.5\n"
               "[host] harness: marker inning frame 70 t 2.5\n")
        self.assertEqual(h.parse_markers(log), [("boot", 10, 1.5), ("inning", 70, 2.5)])
        self.assertEqual(h.audio_state(log), "ok")
        self.assertEqual(h.audio_state("audout: no output device (x)\n"), "none")
        self.assertEqual(h.audio_state("nothing\n"), "unknown")

    def test_fps_from_markers(self):
        self.assertAlmostEqual(h.marker_fps([("a", 10, 1.5), ("b", 610, 11.5)]), 60.0)
        self.assertIsNone(h.marker_fps([("a", 10, 1.5)]))


class DumpCompare(Base):
    def make(self, name, data, sub="a"):
        d = self.dir / sub
        d.mkdir(exist_ok=True)
        (d / name).write_bytes(data)
        return d

    def test_identical_dirs(self):
        a = self.make("t_32x32.raw", bytes(1024), "a")
        b = self.make("t_32x32.raw", bytes(1024), "b")
        self.assertEqual(h.compare_dumps(a, b), [])

    def test_one_byte_difference_is_counted(self):
        x = bytearray(1024)
        y = bytearray(1024)
        y[7] = 1
        a = self.make("t_32x32.raw", bytes(x), "a")
        b = self.make("t_32x32.raw", bytes(y), "b")
        diffs = h.compare_dumps(a, b)
        self.assertEqual(len(diffs), 1)
        self.assertEqual((diffs[0]["file"], diffs[0]["kind"], diffs[0]["bytes_differ"]), ("t_32x32.raw", "content", 1))

    def test_missing_and_size_mismatch(self):
        a = self.make("only_a.raw", b"1", "a")
        self.make("both.raw", b"12", "a")
        b = self.make("both.raw", b"123", "b")
        kinds = {d["file"]: d["kind"] for d in h.compare_dumps(a, b)}
        self.assertEqual(kinds, {"only_a.raw": "missing in B", "both.raw": "size"})

    def test_diff_image_marks_the_differing_pixels(self):
        from PIL import Image
        x = bytearray(1024)
        y = bytearray(1024)
        y[33] = 9                      # row 1, column 1 of a 32x32 one-byte-per-pixel image
        a = self.make("t_32x32.raw", bytes(x), "a")
        b = self.make("t_32x32.raw", bytes(y), "b")
        png = self.dir / "d.png"
        n = h.write_diff_image(a / "t_32x32.raw", b / "t_32x32.raw", png)
        self.assertEqual(n, 1)
        im = Image.open(png).convert("L")
        self.assertEqual(im.size, (32, 32))
        self.assertGreater(im.getpixel((1, 1)), 0)
        self.assertEqual(im.getpixel((0, 0)), 0)


class Verdict(unittest.TestCase):
    def test_same_says_identical(self):
        text = h.ab_verdict("MLB_X=0", "MLB_X=1", [], [], [], {}, {})
        self.assertIn("identical", text.lower())

    def test_difference_names_files(self):
        d = [{"file": "t.raw", "kind": "content", "bytes_differ": 12}]
        text = h.ab_verdict("MLB_X=0", "MLB_X=1", d, [], [], {}, {})
        self.assertIn("DIFFERENT", text)
        self.assertIn("t.raw", text)
        self.assertIn("12", text)

    def test_noise_between_repeats_is_called_out(self):
        d = [{"file": "t.raw", "kind": "content", "bytes_differ": 3}]
        text = h.ab_verdict("a", "b", d, d, [], {}, {})
        self.assertIn("not repeatable", text.lower())

    def test_marker_sets_that_differ_are_a_difference(self):
        text = h.ab_verdict("a", "b", [], [], ["inning"], {}, {})
        self.assertIn("inning", text)
        self.assertIn("DIFFERENT", text)


class EndToEnd(Base):
    def test_run_collects_log_dump_and_summary(self):
        code, out = self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertEqual(code, 0, out)
        runs = sorted((self.dir / "out").glob("unit-*"))
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertTrue((r / "game.log").is_file())
        self.assertEqual((r / "dumps" / "texture_0x25_32x32.raw").stat().st_size, 1024)
        s = json.loads((r / "summary.json").read_text())
        self.assertEqual(s["audio"], "ok")
        self.assertEqual([m[0] for m in s["markers"]], ["boot", "inning"])
        self.assertEqual(s["exit"], "stopped by itself")
        self.assertFalse(self.lock.exists())

    def test_run_numbers_do_not_collide(self):
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertEqual(len(list((self.dir / "out").glob("unit-*"))), 2)

    def test_no_audio_device_is_reported_plainly(self):
        os.environ["FAKE_MODE"] = "nodev"
        self.addCleanup(os.environ.pop, "FAKE_MODE", None)
        code, out = self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertNotEqual(code, 0)
        self.assertIn("no audio output device", out)
        self.assertFalse(self.lock.exists())

    def test_hang_is_killed_and_lock_freed(self):
        os.environ["FAKE_MODE"] = "hang"
        self.addCleanup(os.environ.pop, "FAKE_MODE", None)
        self.scn.write_text(SCENARIO.replace("stop_after_s = 5", "stop_after_s = 1"))
        t = time.time()
        code, out = self.run_quiet(["run", str(self.scn), "--exe", str(self.fake), "--out", str(self.dir / "out"), "--grace", "1"])
        self.assertLess(time.time() - t, 30)
        self.assertNotEqual(code, 0)
        self.assertIn("did not stop", out)
        self.assertFalse(self.lock.exists())

    def test_env_reaches_the_game(self):
        code, out = self.run_quiet(["run", str(self.scn), *self.common("--env", "MLB_X=1")])
        r = next((self.dir / "out").glob("unit-*"))
        self.assertEqual((r / "dumps" / "texture_0x25_32x32.raw").read_bytes()[5], 5 ^ 0xFF)

    def test_ab_same_setting_is_identical_and_exits_zero(self):
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=0", *self.common()])
        self.assertEqual(code, 0, out)
        self.assertIn("identical", out.lower())

    def test_ab_difference_exits_nonzero_and_leaves_a_diff_image(self):
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=1", *self.common()])
        self.assertEqual(code, 1, out)
        self.assertIn("DIFFERENT", out)
        pngs = list((self.dir / "out").rglob("*.png"))
        self.assertEqual(len(pngs), 1, pngs)
        self.assertFalse(self.lock.exists())

    def test_ab_runs_alternate(self):
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=0", "--runs", "2", *self.common()])
        order = [ln.split()[1] for ln in out.splitlines() if ln.startswith("== ")]
        self.assertEqual(order, ["a-1", "b-1", "a-2", "b-2"])

    def test_compare_two_run_folders(self):
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.run_quiet(["run", str(self.scn), *self.common("--env", "MLB_X=1")])
        runs = sorted((self.dir / "out").glob("unit-*"))
        code, out = self.run_quiet(["compare", str(runs[0]), str(runs[1])])
        self.assertEqual(code, 1, out)
        self.assertIn("DIFFERENT", out)

    def test_smoke_passes_on_a_healthy_game(self):
        code, out = self.run_quiet(["smoke", *self.common()])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_smoke_fails_on_each_fault(self):
        for mode, words in (("crash", "crash"), ("stall", "stall"), ("slow", "frame rate"), ("nodev", "audio")):
            with self.subTest(mode=mode):
                os.environ["FAKE_MODE"] = mode
                self.addCleanup(os.environ.pop, "FAKE_MODE", None)
                code, out = self.run_quiet(["smoke", *self.common()])
                self.assertEqual(code if code != 2 else 1, 1, out)
                self.assertIn("FAIL", out)
                self.assertIn(words, out.lower())


if __name__ == "__main__":
    unittest.main()
