#!/usr/bin/env python3
"""Tests of tools/harness.py. No real game needed: a fake game script stands in for mlb.exe.

  python -I -m unittest discover -s tools -p test_harness.py

The fake game reads the scenario named by MLB_HARNESS, writes a dump into MLB_HARNESS_OUT and prints the log lines the
real runtime prints (audout, marker lines, perf lines). FAKE_MODE picks a failure: nodev, crash, hang, stall, slow.
Runs go through tools/game.py in a slot of a temporary folder (MLB_GAME_ROOT); games other sessions run are left out
of the count, so they cannot change these tests."""
import importlib.util
import io
import json
import os
import sys
import tempfile
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
prof = os.environ.get("MLB_PROFILE", "")
if os.path.isdir(prof):
    with open(os.path.join(prof, "playtime.txt"), "a") as f:
        f.write("more")
    with open(os.path.join(prof, "save", "slot1.bin"), "wb") as f:
        f.write(b"played")
    with open(os.path.join(prof, "save", "new.bin"), "wb") as f:
        f.write(b"new")
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
        self.fake.write_text(FAKE, newline="\n")
        self.scn = self.dir / "unit.scn"
        self.scn.write_text(SCENARIO)
        os.environ["MLB_GAME_ROOT"] = str(self.dir)                 # slots and markers live in the temporary folder
        self.addCleanup(os.environ.pop, "MLB_GAME_ROOT", None)
        self.profile = self.dir / "profile"
        (self.profile / "save").mkdir(parents=True)
        (self.profile / "save-tx").mkdir()
        (self.profile / "cache").mkdir()
        (self.profile / "save" / "slot1.bin").write_bytes(b"original")
        (self.profile / "save-tx" / "tx.bin").write_bytes(b"tx")
        (self.profile / "playtime.txt").write_text("123")
        (self.profile / "account.uid").write_text("uid")
        (self.profile / "cache" / "big.bin").write_bytes(b"x" * 100)
        os.environ["MLB_HARNESS_PROFILE"] = str(self.profile)
        os.environ["MLB_HARNESS_BACKUPS"] = str(self.dir / "backups")
        self.addCleanup(os.environ.pop, "MLB_HARNESS_PROFILE", None)
        self.addCleanup(os.environ.pop, "MLB_HARNESS_BACKUPS", None)
        real = h.game.live_source                 # games other sessions run right now must not count in these tests
        h.game.live_source = lambda: []
        self.addCleanup(setattr, h.game, "live_source", real)

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

    def slot(self, name="harness"):
        return Path(h.game.slot_path(name))


class ScenarioParsing(Base):
    def test_reads_every_key_and_repeated_dump(self):
        s = h.parse_scenario(SCENARIO)
        self.assertEqual((s["name"], s["home"], s["away"], s["seed"]), ("unit", 3, 7, 42))
        self.assertEqual(s["fixed_clock"], 1)
        self.assertEqual(s["stop_after_s"], 5.0)
        self.assertEqual(s["dump"], ["texture:fmt=0x25,size=512x512", "texture:fmt=0x26,size=64x64"])
        self.assertEqual(s["markers"], "boot,inning")

    def test_framelog_is_a_known_key_and_an_unknown_one_is_kept(self):
        s = h.parse_scenario("name = x\nframelog = frames.txt\nfuture_key = 9\n")
        self.assertEqual((s["framelog"], s["extra"]), ("frames.txt", {"future_key": "9"}))

    def test_team_out_of_range_is_refused(self):
        with self.assertRaisesRegex(h.ScenarioError, "home.*0.*29"):
            h.parse_scenario("home = 30\n")

    def test_bad_line_names_its_number(self):
        with self.assertRaisesRegex(h.ScenarioError, "line 2"):
            h.parse_scenario("name = x\nnonsense\n")

    def test_fixed_clock_must_be_0_or_1(self):
        with self.assertRaises(h.ScenarioError):
            h.parse_scenario("fixed_clock = 2\n")


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
        diffs = h.compare_dumps(self.make("t_32x32.raw", bytes(x), "a"), self.make("t_32x32.raw", bytes(y), "b"))
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
        self.assertEqual(h.write_diff_image(a / "t_32x32.raw", b / "t_32x32.raw", png), 1)
        im = Image.open(png).convert("L")
        self.assertEqual(im.size, (32, 32))
        self.assertGreater(im.getpixel((1, 1)), 0)
        self.assertEqual(im.getpixel((0, 0)), 0)


class Verdict(unittest.TestCase):
    def test_same_says_identical(self):
        self.assertIn("identical", h.ab_verdict("MLB_X=0", "MLB_X=1", [], [], [], {}, {}).lower())

    def test_difference_names_files(self):
        text = h.ab_verdict("MLB_X=0", "MLB_X=1", [{"file": "t.raw", "kind": "content", "bytes_differ": 12}], [], [], {}, {})
        for word in ("DIFFERENT", "t.raw", "12"):
            self.assertIn(word, text)

    def test_noise_between_repeats_is_called_out(self):
        d = [{"file": "t.raw", "kind": "content", "bytes_differ": 3}]
        self.assertIn("not repeatable", h.ab_verdict("a", "b", d, d, [], {}, {}).lower())

    def test_marker_sets_that_differ_are_a_difference(self):
        text = h.ab_verdict("a", "b", [], [], ["inning"], {}, {})
        self.assertIn("inning", text)
        self.assertIn("DIFFERENT", text)


def tree_hashes(root):
    import hashlib
    out = {}
    for base, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, root)] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return out


class Profile(Base):
    def test_a_run_goes_through_a_slot_and_never_writes_the_real_profile(self):
        before = tree_hashes(self.profile)
        code, out = self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertEqual(code, 0, out)
        s = json.loads(next((self.dir / "out").glob("unit-*")).joinpath("summary.json").read_text())
        slot = self.slot()
        self.assertEqual(Path(s["profile"]), slot / "profile")
        self.assertIsNone(s["backup"])                                            # nothing to back up: the real profile is not used
        self.assertEqual((slot / "mlb_harness.exe").read_bytes(), FAKE.encode())  # the exe of --exe, copied and renamed
        self.assertEqual(Path(s["slot_run"]), slot / "run-1")
        for f in ("game.out", "env.json", "result.json"):                         # game.log is the real game's; a stand-in prints
            self.assertTrue((slot / "run-1" / f).is_file(), f)
        self.assertEqual(Path(s["dumps_dir"]), slot / "run-1" / "dumps")
        self.assertEqual((slot / "run-1" / "dumps" / "texture_0x25_32x32.raw").stat().st_size, 1024)
        self.assertEqual(s["ended"] if "ended" in s else json.loads((slot / "run-1" / "result.json").read_text())["ended"],
                         "by itself")
        self.assertEqual((slot / "profile" / "playtime.txt").read_text(), "123more")    # the game wrote into the copy
        self.assertEqual(tree_hashes(self.profile), before)                        # and not into the real one
        self.assertTrue(Path(h.game.marker_path("harness")).is_file())             # the slot keeps its permit
        self.assertFalse((self.dir / "backups").exists())

    def test_the_second_run_of_the_slot_starts_again_from_the_real_saves(self):
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertTrue((self.slot() / "run-2").is_dir())
        self.assertEqual((self.slot() / "profile" / "playtime.txt").read_text(), "123more")   # reset, then written once

    def test_real_profile_run_writes_the_real_profile_after_a_backup(self):
        before = tree_hashes(self.profile)
        code, out = self.run_quiet(["run", str(self.scn), *self.common("--real-profile")])
        self.assertEqual(code, 0, out)
        s = json.loads(next((self.dir / "out").glob("unit-*")).joinpath("summary.json").read_text())
        self.assertEqual(Path(s["profile"]), self.profile)
        self.assertIn("profile: REAL", out)
        self.assertIn(s["backup"], out)
        b = Path(s["backup"])
        self.assertEqual((b / "save" / "slot1.bin").read_bytes(), b"original")      # the state before the run
        self.assertEqual((b / "playtime.txt").read_text(), "123")
        self.assertTrue((b / "save-tx" / "tx.bin").is_file())
        self.assertFalse((b / "cache").exists())                                      # caches are not copied
        self.assertNotEqual(tree_hashes(self.profile), before)                       # the game did write to the real profile
        self.assertFalse(self.slot().exists())                                        # no slot in the old way

    def test_real_profile_run_waits_until_no_game_is_live(self):
        h.game.live_source = lambda: [(4242, "D:/elsewhere/mlb.exe", None)]           # another session's game
        code, out = self.run_quiet(["run", str(self.scn), *self.common("--real-profile", "--wait", "0")])
        self.assertEqual((code, self.slot().exists()), (2, False))
        self.assertIn("no turn for a run on the real profile", out)
        self.assertIn("mlb.exe (pid 4242)", out)

    def test_restore_puts_hashes_back(self):
        before = tree_hashes(self.profile)
        self.run_quiet(["run", str(self.scn), *self.common("--real-profile")])
        self.assertNotEqual(tree_hashes(self.profile), before)
        name = next(p.name for p in (self.dir / "backups").iterdir())
        code, out = self.run_quiet(["restore", name])
        self.assertEqual(code, 1)                                                    # not confirmed: changes nothing
        self.assertIn("--confirm " + name, out)
        self.assertNotEqual(tree_hashes(self.profile), before)
        h.game.live_source = lambda: [(4242, "D:/elsewhere/mlb.exe", None)]           # a game is running: not now
        code, out = self.run_quiet(["restore", name, "--confirm", name, "--wait", "0"])
        self.assertEqual(code, 2)
        self.assertIn("a game is running", out)
        h.game.live_source = lambda: []
        code, out = self.run_quiet(["restore", name, "--confirm", name])
        self.assertEqual(code, 0, out)
        after = tree_hashes(self.profile)
        for k, v in before.items():
            self.assertEqual(after.get(k), v, k)
        self.assertNotIn(os.path.join("save", "new.bin"), after)                     # a file made by the run is removed
        self.assertTrue(any("pre-restore" in p.name for p in (self.dir / "backups").iterdir()))

    def test_restore_refuses_a_folder_this_tool_did_not_make(self):
        (self.dir / "backups" / "mine").mkdir(parents=True)
        code, out = self.run_quiet(["restore", "mine", "--confirm", "mine"])
        self.assertEqual(code, 2)
        self.assertIn("not a backup made by this tool", out)

    def test_only_the_newest_ten_of_our_backups_are_kept_and_others_survive(self):
        root = self.dir / "backups"
        (root / "owners-own-folder").mkdir(parents=True)
        for i in range(13):
            d = root / ("20200101-0000%02d" % i)
            d.mkdir()
            (d / h.BACKUP_MARK).write_text("x")
        h.backup_profile(str(self.profile))
        names = sorted(p.name for p in root.iterdir())
        self.assertIn("owners-own-folder", names)
        ours = [n for n in names if n != "owners-own-folder"]
        self.assertEqual(len(ours), 10)
        self.assertNotIn("20200101-000000", ours)
        self.assertIn("20200101-000012", ours)


class EndToEnd(Base):
    def summary(self, n=0):
        folder = sorted((self.dir / "out").glob("unit-*"))[n]
        return folder, json.loads(folder.joinpath("summary.json").read_text())

    def test_run_collects_log_dump_and_summary(self):
        code, out = self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertEqual(code, 0, out)
        folder, s = self.summary()
        self.assertTrue(folder.joinpath("scenario.scn").is_file())
        self.assertEqual((s["audio"], [m[0] for m in s["markers"]], s["exit"]), ("ok", ["boot", "inning"], "stopped by itself"))
        self.assertEqual({n: (Path(s["dumps_dir"], n).stat().st_size, size) for n, size in s["dumps"].items()},
                         {"texture_0x25_32x32.raw": (1024, 1024)})
        self.assertIn("[host] harness: marker boot", Path(s["out"]).read_text())
        self.assertFalse(s["hung"])
        self.assertIsNone(s["window_title"])

    def test_run_numbers_do_not_collide(self):
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertEqual(len(list((self.dir / "out").glob("unit-*"))), 2)
        self.assertTrue((self.slot() / "run-2" / "result.json").is_file())             # game.py numbers them too

    def test_no_audio_device_is_reported_plainly(self):
        os.environ["FAKE_MODE"] = "nodev"
        self.addCleanup(os.environ.pop, "FAKE_MODE", None)
        code, out = self.run_quiet(["run", str(self.scn), *self.common()])
        self.assertNotEqual(code, 0)
        self.assertIn("no audio output device", out)

    def test_hang_is_asked_to_close_and_then_killed(self):
        os.environ["FAKE_MODE"] = "hang"
        self.addCleanup(os.environ.pop, "FAKE_MODE", None)
        self.scn.write_text(SCENARIO.replace("stop_after_s = 5", "stop_after_s = 1"))
        t = time.time()
        code, out = self.run_quiet(["run", str(self.scn), "--exe", str(self.fake), "--out", str(self.dir / "out"), "--grace", "1"])
        self.assertLess(time.time() - t, 30)
        self.assertNotEqual(code, 0)
        self.assertIn("did not stop by itself within 2 s; killed", out)
        self.assertEqual(h.game.slot_is_live("harness"), [])

    def test_env_reaches_the_game(self):
        code, out = self.run_quiet(["run", str(self.scn), *self.common("--env", "MLB_X=1")])
        _folder, s = self.summary()
        self.assertEqual(Path(s["dumps_dir"], "texture_0x25_32x32.raw").read_bytes()[5], 5 ^ 0xFF)

    def test_ab_same_setting_is_identical_and_exits_zero(self):
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=0", *self.common()])
        self.assertEqual(code, 0, out)
        self.assertIn("identical", out.lower())

    def test_ab_difference_exits_nonzero_and_leaves_a_diff_image(self):
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=1", *self.common()])
        self.assertEqual(code, 1, out)
        self.assertIn("DIFFERENT", out)
        self.assertEqual(len(list((self.dir / "out").rglob("*.png"))), 1)

    def test_ab_runs_alternate_in_the_same_slot(self):
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=0", "--runs", "2", *self.common()])
        self.assertEqual([ln.split()[1] for ln in out.splitlines() if ln.startswith("== ")], ["a-1", "b-1", "a-2", "b-2"])
        self.assertEqual(len(h.game.run_dirs("harness")), 4)

    def test_ab_can_run_exclusive_and_refuses_at_once_without_a_turn(self):
        h.game.live_source = lambda: [(4242, "D:/elsewhere/mlb.exe", None)]
        code, out = self.run_quiet(["ab", str(self.scn), "--a", "MLB_X=0", "--b", "MLB_X=0", *self.common("--mode", "exclusive", "--wait", "0")])
        self.assertEqual(code, 2, out)
        self.assertIn("1 game(s) live", out)
        self.assertFalse(self.slot().joinpath("run-1").exists())

    def test_compare_two_run_folders(self):
        self.run_quiet(["run", str(self.scn), *self.common()])
        self.run_quiet(["run", str(self.scn), *self.common("--env", "MLB_X=1")])
        a, b = sorted((self.dir / "out").glob("unit-*"))
        code, out = self.run_quiet(["compare", str(a), str(b)])
        self.assertEqual(code, 1, out)
        self.assertIn("DIFFERENT", out)

    def test_compare_reads_an_old_run_folder_with_its_own_dumps(self):
        a, b = self.dir / "old-a", self.dir / "old-b"
        for d, data in ((a, bytes(16)), (b, bytes(15) + b"\x01")):
            (d / "dumps").mkdir(parents=True)
            (d / "dumps" / "t.raw").write_bytes(data)
            (d / "summary.json").write_text(json.dumps({"markers": [["boot", 10, 1.5]]}))
        code, out = self.run_quiet(["compare", str(a), str(b)])
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
