#!/usr/bin/env python3
"""Tests of tools/game.py. No real game: a fake game stands in for mlb.exe.

  python -I -m unittest discover -s tools -p test_game.py

The fake game is a copy of python.exe with the name the slot's exe has, plus a `._pth` file beside it that makes it
run FAKE (below) at start. So it is a real process with a real image path under work/runs/, and the process list
game.py reads sees it as it sees a real game. FAKE takes its orders from the environment: FAKE_SECONDS (how long it
runs), FAKE_EXIT (its exit code), FAKE_MODE (nodev, crash, hang, window, stubborn), MLB_RUN_LABEL (its window title)
and MLB_PROFILE (it writes into it, as the game does). It writes its log beside its exe (logs/mlb.log), as the game
does, and prints its working folder and settings.

The slots live in a temporary folder (MLB_GAME_ROOT): the real work/runs and work/game.state are never touched. The
fakes are not named mlb*.exe, and `live_source` is narrowed to the processes a test started, so games other sessions
run neither count here nor are disturbed."""
import contextlib
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("game", TOOLS / "game.py")
g = importlib.util.module_from_spec(spec)
sys.modules["game"] = g
spec.loader.exec_module(g)

FAKE = r'''
import ctypes, os, sys, time, traceback
try:
    import ctypes.wintypes as wt
    import json
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    mode = os.environ.get("FAKE_MODE", "ok")
    secs = float(os.environ.get("FAKE_SECONDS", "2"))
    code = int(os.environ.get("FAKE_EXIT", "7"))
    label = os.environ.get("MLB_RUN_LABEL", "")
    slot = os.path.dirname(sys.executable)          # the game's exe folder: this slot
    log_path = os.environ.get("MLB_LOG") or os.path.join(slot, "logs", "mlb.log")   # MLB_LOG names the file; else beside the exe
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lines = ["audout: no output device (asleep): buffers are recycled without sound" if mode == "nodev"
             else "audout: WASAPI device 'Speakers' opened, 48000 Hz",
             "[host] harness: marker boot frame 10 t 1.500"]
    if mode == "crash":
        lines.append("FATAL: access violation at 0x1234")
    lines.append("[host] harness: marker inning frame 610 t 11.500")
    with open(log_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print("FAKE cwd " + os.getcwd(), flush=True)
    print("FAKE env " + json.dumps({key: v for key, v in os.environ.items() if key.startswith(("MLB_", "TOTK_"))}), flush=True)
    prof = os.environ.get("MLB_PROFILE", "")
    if os.path.isdir(prof):                         # as the game does: play time and save in the profile
        with open(os.path.join(prof, "playtime.txt"), "a") as f:
            f.write(" more")
        os.makedirs(os.path.join(prof, "save"), exist_ok=True)
        with open(os.path.join(prof, "save", "played.bin"), "wb") as f:
            f.write(b"played")
    if mode == "crash":
        code = 3
    closed = []
    if mode in ("window", "stubborn", "late"):
        # The game's top-level window. WM_CLOSE is what the X button sends; the game then stops by itself.
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        class WNDCLASSW(ctypes.Structure):        # ctypes.wintypes does not have it
            _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE), ("lpszMenuName", wt.LPCWSTR),
                        ("lpszClassName", wt.LPCWSTR)]
        u.DefWindowProcW.restype = ctypes.c_ssize_t
        u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        u.CreateWindowExW.restype = wt.HWND
        u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
        k.GetModuleHandleW.restype = wt.HMODULE
        k.GetModuleHandleW.argtypes = [wt.LPCWSTR]

        def wnd(h, m, w, l):
            if m == 0x0010:                         # WM_CLOSE
                closed.append(1)
                if mode != "stubborn":
                    u.DestroyWindow(h)
                    u.PostQuitMessage(0)
                return 0
            return u.DefWindowProcW(h, m, w, l)

        cls = WNDCLASSW()
        cls.lpfnWndProc = WNDPROC(wnd)
        cls.hInstance = k.GetModuleHandleW(None)
        cls.lpszClassName = "fakegame"
        u.RegisterClassW(ctypes.byref(cls))
        if mode == "late":
            # A hidden helper window with a title, as the graphics driver makes one in the real game ("Temp Window").
            helper = u.CreateWindowExW(0, "fakegame", "Temp Window", 0, 0, 0, 0, 0, None, None, cls.hInstance, None)
            print("FAKE helper window %d" % (helper or 0), flush=True)
            time.sleep(2.0)                         # the game's own window comes 2 s later
        # The game's window: visible, but far off every screen, so nothing shows on the desktop (WS_VISIBLE).
        hwnd = u.CreateWindowExW(0, "fakegame", "MLB The Show 26 (fastball) [%s]" % label, 0x10000000, -30000, -30000,
                                 64, 64, None, None, cls.hInstance, None)
        print("FAKE window %d" % (hwnd or 0), flush=True)
        msg = wt.MSG()
        u.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
        end = time.time() + secs
        while time.time() < end and not (mode != "stubborn" and closed):
            if u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):   # PM_REMOVE: handle what was sent to the window
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.02)
        if mode != "stubborn" and closed:
            code = 0                                 # stopped by itself after the close request
    else:
        time.sleep(secs)
    sys.stdout.flush()
    os._exit(code)
except BaseException:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(99)
'''

SUPPORT = ("totk_xlate.exe", "totk_xlate.id", "SDL3.dll", "mlb.cfg", "pipeline-cache.bin", "pipeline-keys.bin",
           "shader-answers.bin", "shader-programs.bin")
PY = sys.base_prefix
PY_DLLS = [n for n in os.listdir(PY) if re.fullmatch(r"(python\d+|vcruntime\d+_?)\.dll", n)]


def install_fake(exe):
    """Make `exe` (a copy of python.exe) run FAKE at start: a <name>._pth file beside it, the script in game/ beside
    it, and Python's own DLLs beside it (a copied python.exe does not find them otherwise)."""
    exe = os.path.abspath(exe)
    folder = os.path.dirname(exe)
    game = os.path.join(folder, "game")
    os.makedirs(game, exist_ok=True)
    with open(os.path.splitext(exe)[0] + "._pth", "w") as f:
        f.write("game\n%s/DLLs\n%s/Lib\nimport site\n" % (PY, PY))
    with open(os.path.join(game, "sitecustomize.py"), "w") as f:
        f.write(FAKE)
    for n in PY_DLLS:
        dst = os.path.join(folder, n)
        if not os.path.exists(dst):
            try:
                os.link(os.path.join(PY, n), dst)
            except OSError:
                shutil.copy2(os.path.join(PY, n), dst)


def tree_hashes(root):
    out = {}
    for base, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, root)] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return out


def read(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def fake_env(text):
    """What the fake printed as its settings: the line 'FAKE env {...}'."""
    for line in text.splitlines():
        if line.startswith("FAKE env "):
            return json.loads(line[len("FAKE env "):])
    return {}


def fake_cwd(text):
    for line in text.splitlines():
        if line.startswith("FAKE cwd "):
            return line[len("FAKE cwd "):]
    return None


class BG(threading.Thread):
    """Runs something in the background and keeps its result or its exception."""

    def __init__(self, fn, *a, **k):
        super().__init__(daemon=True)
        self.fn, self.a, self.k = fn, a, k
        self.result = self.error = None

    def run(self):
        try:
            self.result = self.fn(*self.a, **self.k)
        except BaseException as e:      # the test reads it
            self.error = e


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        os.environ["MLB_GAME_ROOT"] = str(self.dir)
        self.addCleanup(os.environ.pop, "MLB_GAME_ROOT", None)
        os.environ["FAKE_SECONDS"] = "0.6"
        os.environ["FAKE_EXIT"] = "7"
        self.addCleanup(os.environ.pop, "FAKE_SECONDS", None)
        self.addCleanup(os.environ.pop, "FAKE_EXIT", None)
        # A build folder: the "game" is a copy of python.exe; the support files are small stand-ins.
        self.build = self.dir / "build"
        (self.build / "shader-cache").mkdir(parents=True)
        shutil.copy2(sys.executable, self.build / "mlb.exe")
        for n in SUPPORT:
            (self.build / n).write_text("stand-in for " + n + "\n")
        (self.build / "shader-cache" / "a.spv").write_bytes(b"shader")
        # The real profile: the owner's saves, and a cache that must not be copied.
        self.real = self.dir / "real-profile"
        (self.real / "save").mkdir(parents=True)
        (self.real / "save-tx").mkdir()
        (self.real / "cache").mkdir()
        (self.real / "save" / "slot1.bin").write_bytes(b"original")
        (self.real / "save-tx" / "tx.bin").write_bytes(b"tx")
        (self.real / "playtime.txt").write_text("123")
        (self.real / "account.uid").write_text("uid")
        (self.real / "cache" / "big.bin").write_bytes(b"x" * 100)
        # Only this test's own processes count as live games (others' fakes and real games are left out of it).
        self.made, self.threads, self.extra_pids = [], [], set()
        real_enum, real_format = g.game_processes, g.EXE_FORMAT
        runs = os.path.normcase(str(g.runs_dir())) + os.sep

        def ours_only():
            return [e for e in real_enum() if e[0] in self.extra_pids or os.path.normcase(os.path.abspath(e[1])).startswith(runs)]
        self.ours_only = ours_only
        g.live_source = ours_only
        g.EXE_FORMAT = "fakegame_%s.exe"        # not mlb*.exe: other sessions' tools do not count these fakes
        self.addCleanup(setattr, g, "live_source", real_enum)
        self.addCleanup(setattr, g, "EXE_FORMAT", real_format)
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        for id in self.made:
            if g.read_slot(id) is not None:
                with contextlib.suppress(Exception):
                    g.stop(id, grace=1.0, quiet=True)
        for t in self.threads:
            t.join(15)
        runs = os.path.normcase(str(g.runs_dir())) + os.sep
        left = [e for e in g.game_processes() if os.path.normcase(os.path.abspath(e[1])).startswith(runs)]
        self.assertEqual(left, [], "a process started by this test is still running")

    def make(self, id="alpha", name=None, **kw):
        """A slot with the fake game installed."""
        if name:
            g.EXE_FORMAT = name
        try:
            g.create(id, exe=str(self.build / "mlb.exe"), support_dir=str(self.build), real_profile=str(self.real), **kw)
        finally:
            g.EXE_FORMAT = "fakegame_%s.exe"
        self.made.append(id)
        install_fake(g.exe_path(id) if not name else os.path.join(g.slot_path(id), name % id))
        return g.slot_path(id)

    def go(self, id="alpha", **kw):
        """A foreground run with the usual test settings."""
        kw.setdefault("wait", 30)
        kw.setdefault("grace", 1.0)
        return g.run(id, real_profile=str(self.real), quiet=True, **kw)

    def start(self, fn, *a, **k):
        t = BG(fn, *a, **k)
        self.threads.append(t)
        t.start()
        return t

    def start_run(self, id="alpha", **kw):
        kw.setdefault("wait", 30)
        kw.setdefault("grace", 1.0)
        return self.start(g.run, id, real_profile=str(self.real), quiet=True, **kw)

    def wait_live(self, *ids, gone=False, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if all(bool(g.slot_is_live(i)) != gone for i in ids):
                return True
            time.sleep(0.05)
        return False

    def hand_slot(self, id, text=None):
        """A slot folder another tool made (no slot.json of this tool), with its marker."""
        p = Path(g.slot_path(id))
        p.mkdir(parents=True)
        (p / "slot.json").write_text(text or '{"tool": "another tool"}')
        Path(g.marker_path(id)).parent.mkdir(parents=True, exist_ok=True)
        Path(g.marker_path(id)).write_text("%s exe=D:/elsewhere/mlb.exe start=2026-11-23T10:41:10-06:00\n" % id)
        return p

    def cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = g.main(argv)
        return code, buf.getvalue()

    def out_env(self, res):
        return fake_env(read(res["out"]))


class IdRule(unittest.TestCase):
    def test_bad_ids_are_refused(self):
        for bad in ("Upper", "a_b", "x" * 33, "", "../x", "a b", "a.exe", "a/b"):
            with self.subTest(id=bad), self.assertRaises(g.GameError):
                g.check_id(bad)

    def test_good_ids_pass(self):
        for ok in ("a", "run-1", "x" * 32):
            self.assertEqual(g.check_id(ok), ok)


class Markers(Base):
    def test_another_sessions_marker_is_read_but_is_not_ours(self):
        self.assertIsNone(g.read_marker("theirs"))
        Path(g.marker_path("theirs")).parent.mkdir(parents=True)
        Path(g.marker_path("theirs")).write_text(
            "theirs exe=D:/runs/theirs/mlb_theirs.exe start=2026-11-23T10:41:10-06:00\n")   # as another session writes it
        m = g.read_marker("theirs")
        self.assertEqual((m["id"], m["exe"], m["start"]), ("theirs", "D:/runs/theirs/mlb_theirs.exe", "2026-11-23T10:41:10-06:00"))
        self.assertIsNone(g.our_marker("theirs"))                                   # so it is never removed by this tool
        self.assertEqual(g.markers(), ["theirs"])

    def test_our_marker_goes_back_and_forth_field_by_field(self):
        g.write_marker("mine", label="lab", exe="D:/d/mlb_mine.exe", pid=4321, run=3, mode="exclusive")
        m = g.read_marker("mine")
        self.assertEqual((m["id"], m["label"], m["exe"], m["pid"], m["run"], m["mode"], m["tool"]),
                         ("mine", "lab", "D:/d/mlb_mine.exe", "4321", "3", "exclusive", g.TOOL))
        start = m["start"]
        g.write_marker("mine", exe="D:/d/mlb_mine.exe")                             # the run ended: no pid, the rest kept
        m = g.read_marker("mine")
        self.assertEqual((m["label"], m["start"], m["tool"]), ("lab", start, g.TOOL))
        self.assertFalse({"pid", "run", "mode"} & set(m))


class Create(Base):
    def test_create_copies_exe_support_and_profile_and_writes_slot_json_and_marker(self):
        self.make("alpha", label="my label")
        slot = Path(g.slot_path("alpha"))
        exe = Path(g.exe_path("alpha"))
        self.assertEqual(os.path.basename(exe), "fakegame_alpha.exe")          # a copy of the exe, renamed
        self.assertEqual(exe.read_bytes()[:2], b"MZ")
        self.assertEqual(exe.stat().st_size, (self.build / "mlb.exe").stat().st_size)
        for n in SUPPORT:
            self.assertEqual(read(slot / n), "stand-in for " + n + "\n", n)
        self.assertEqual((slot / "shader-cache" / "a.spv").read_bytes(), b"shader")
        prof = slot / "profile"
        self.assertEqual((prof / "save" / "slot1.bin").read_bytes(), b"original")
        self.assertEqual((prof / "save-tx" / "tx.bin").read_bytes(), b"tx")
        self.assertEqual((prof / "playtime.txt").read_text(), "123")
        self.assertEqual((prof / "account.uid").read_text(), "uid")
        self.assertFalse((prof / "cache").exists())                            # caches are not copied
        rec = g.read_slot("alpha")
        st = (self.build / "mlb.exe").stat()
        self.assertEqual((rec["tool"], rec["id"], rec["label"]), (g.TOOL, "alpha", "my label"))
        self.assertEqual(rec["exe"], {"source": str(self.build / "mlb.exe"), "size": st.st_size, "mtime": st.st_mtime})
        self.assertEqual(os.path.normcase(rec["support"]), os.path.normcase(str(self.build)))
        self.assertIn("created", rec)
        m = g.read_marker("alpha")
        self.assertEqual((m["id"], m["label"], m["exe"], m["tool"]), ("alpha", "my label", str(exe), g.TOOL))
        self.assertIn("start", m)
        self.assertNotIn("pid", m)                                             # no run is live
        self.assertEqual(g.our_marker("alpha"), m)

    def test_the_slot_exe_is_named_mlb_id_exe(self):
        self.assertIn('EXE_FORMAT = "mlb_%s.exe"', read(TOOLS / "game.py"))          # what the tool ships
        g.EXE_FORMAT = "mlb_%s.exe"                                                 # (the tests narrow it, see setUp)
        self.assertEqual(g.exe_path("ab"), os.path.join(g.slot_path("ab"), "mlb_ab.exe"))

    def test_a_taken_id_is_refused_and_nothing_changes(self):
        self.make("alpha")
        before = tree_hashes(g.slot_path("alpha")), read(g.marker_path("alpha"))
        with self.assertRaisesRegex(g.GameError, "alpha is taken.*slot folder"):
            self.make("alpha")
        self.assertEqual((tree_hashes(g.slot_path("alpha")), read(g.marker_path("alpha"))), before)

    def test_an_id_whose_marker_alone_exists_is_refused(self):
        Path(g.marker_path("beta")).parent.mkdir(parents=True)
        Path(g.marker_path("beta")).write_text("beta exe=D:/elsewhere/mlb_beta.exe start=2026-11-23T10:41:10-06:00\n")
        with self.assertRaisesRegex(g.GameError, "beta is taken.*marker"):
            self.make("beta")
        self.assertFalse(os.path.exists(g.slot_path("beta")))

    def test_a_missing_exe_leaves_nothing_behind(self):
        with self.assertRaisesRegex(g.GameError, "no game exe"):
            g.create("alpha", exe=str(self.build / "missing.exe"), support_dir=str(self.build))
        self.assertFalse(os.path.exists(g.slot_path("alpha")))
        self.assertFalse(os.path.exists(g.marker_path("alpha")))

    def test_create_without_a_real_profile_makes_an_empty_one(self):
        g.create("alpha", exe=str(self.build / "mlb.exe"), support_dir=str(self.build), real_profile=str(self.dir / "none"))
        self.assertTrue(os.path.isdir(os.path.join(g.slot_path("alpha"), "profile")))
        self.assertEqual(os.listdir(os.path.join(g.slot_path("alpha"), "profile")), [])
        self.assertFalse(g.read_slot("alpha")["profile"]["real_found"])


class Update(Base):
    def test_update_copies_a_changed_exe_and_changed_support_files(self):
        self.make("alpha")
        time.sleep(0.02)
        (self.build / "mlb.exe").write_bytes(b"MZ" + b"x" * 5000)             # a new build
        (self.build / "mlb.cfg").write_text("changed\n")
        (self.build / "shader-cache" / "b.spv").write_bytes(b"new shader")
        Path(g.slot_path("alpha"), "shader-cache", "a.spv").unlink()          # the slot's own cache copy is left alone
        r = g.update("alpha", support_dir=str(self.build))
        self.assertTrue(r["exe_changed"])
        self.assertEqual(Path(g.exe_path("alpha")).read_bytes(), b"MZ" + b"x" * 5000)
        self.assertEqual(g.read_slot("alpha")["exe"]["size"], 5002)
        self.assertIn("mlb.cfg", r["support_copied"])
        self.assertEqual(read(Path(g.slot_path("alpha"), "mlb.cfg")), "changed\n")
        self.assertFalse(Path(g.slot_path("alpha"), "shader-cache", "a.spv").exists())
        self.assertFalse(Path(g.slot_path("alpha"), "shader-cache", "b.spv").exists())
        self.assertTrue(Path(g.marker_path("alpha")).exists())                # the marker stays

    def test_update_with_an_unchanged_exe_says_so(self):
        self.make("alpha")
        r = g.update("alpha", support_dir=str(self.build))
        self.assertFalse(r["exe_changed"])
        self.assertEqual(r["support_copied"], [])

    def test_update_takes_another_exe_and_refuses_a_missing_one(self):
        other = self.dir / "other.exe"
        shutil.copy2(sys.executable, other)
        self.make("alpha")
        r = g.update("alpha", exe=str(other))
        self.assertTrue(r["exe_changed"])
        self.assertEqual(g.read_slot("alpha")["exe"]["source"], str(other))
        with self.assertRaisesRegex(g.GameError, "no game exe"):
            g.update("alpha", exe=str(self.dir / "nope.exe"))

    def test_prepare_creates_once_then_updates(self):
        g.prepare("alpha", exe=str(self.build / "mlb.exe"), support_dir=str(self.build))
        self.made.append("alpha")
        self.assertEqual(g.prepare("alpha", exe=str(self.build / "mlb.exe"), support_dir=str(self.build))["exe_changed"], False)
        (self.build / "mlb.exe").write_bytes(b"MZ" + b"y" * 10)
        self.assertTrue(g.prepare("alpha")["exe_changed"])

    def test_update_refuses_a_slot_that_is_not_ours(self):
        self.hand_slot("hand")
        with self.assertRaisesRegex(g.GameError, "not made by"):
            g.update("hand")
        self.assertTrue(Path(g.slot_path("hand"), "slot.json").exists())

    def test_update_refuses_a_slot_with_a_live_game(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_SECONDS": "30", "FAKE_MODE": "hang"})
        self.assertTrue(self.wait_live("alpha"))
        with self.assertRaisesRegex(g.GameError, "live game"):
            g.update("alpha", support_dir=str(self.build))
        g.stop("alpha", grace=1.0, quiet=True)
        t.join(10)
        self.assertFalse(g.slot_is_live("alpha"))
        self.assertFalse(g.update("alpha")["exe_changed"])


class Run(Base):
    def test_a_foreground_run_writes_result_json_and_the_game_runs_in_the_slot(self):
        self.make("alpha", label="al")
        res = self.go(env={"MLB_X": "1", "FAKE_SECONDS": "1"})
        run_dir = Path(res["run_dir"])
        self.assertEqual(run_dir, Path(g.slot_path("alpha"), "run-1"))
        for f in ("game.out", "mlb.log", "env.json", "result.json"):
            self.assertTrue((run_dir / f).is_file(), f)
        self.assertEqual((res["log"], res["log_source"]), (str(run_dir / "mlb.log"), "run folder"))   # the game wrote it there
        self.assertFalse((run_dir.parent / "logs").exists())        # not beside the exe: runs of a slot would share that
        self.assertEqual(json.loads(read(run_dir / "result.json")), res)
        self.assertEqual((res["id"], res["label"], res["run"], res["mode"]), ("alpha", "al", 1, "shared"))
        self.assertIsInstance(res["pid"], int)
        self.assertRegex(res["started"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        self.assertGreaterEqual(res["seconds"], 0.9)
        self.assertEqual((res["exit_code"], res["ended"]), (7, "by itself"))
        self.assertEqual(res["audio"], "ok")
        self.assertEqual(res["markers"], [["boot", 10, 1.5], ["inning", 610, 11.5]])
        self.assertEqual((res["fatal"], res["contended"], res["shared_with"], res["window_title"]), (False, False, [], None))
        self.assertTrue(res["first_run_of_slot"])
        self.assertIsNone(res["close_requested"])
        self.assertEqual(res["log"], str(run_dir / "mlb.log"))
        self.assertIn("[host] harness: marker boot", read(res["log"]))
        self.assertNotIn("pid", g.read_marker("alpha"))                       # no live run any more
        self.assertEqual(read(run_dir / "game.out").count("audout: WASAPI"), 1)

    def test_the_game_gets_the_slots_paths_its_label_and_the_slot_as_working_folder(self):
        self.make("alpha", label="al")
        res = self.go(env={"MLB_X": "1", "FAKE_SECONDS": "1"})
        slot = Path(g.slot_path("alpha"))
        env = self.out_env(res)
        self.assertEqual(fake_cwd(read(res["out"])), str(slot))
        self.assertEqual(env["MLB_RUN_LABEL"], "al")
        self.assertEqual(env["MLB_PROFILE"], str(slot / "profile").replace("\\", "/"))
        self.assertEqual(env["MLB_EXEFS"], str(self.dir / "work" / "build" / "game" / "exefs").replace("\\", "/"))
        self.assertEqual(env["MLB_ROMFS"], str(self.dir / "work" / "build" / "game" / "romfs").replace("\\", "/"))
        self.assertEqual((env["TOTK_BACKGROUND_WINDOW"], env["MLB_X"]), ("1", "1"))
        recorded = json.loads(read(Path(res["run_dir"], "env.json")))
        self.assertEqual({k: recorded.get(k) for k in env}, env)               # every setting the game got is written down

    def test_the_label_defaults_to_the_id(self):
        self.make("alpha")
        env = self.out_env(self.go())
        self.assertEqual(env["MLB_RUN_LABEL"], "alpha")

    def test_settings_inherited_from_the_shell_do_not_push_the_game_off_its_slot(self):
        self.make("alpha")
        for k, v in {"MLB_PROFILE": str(self.real), "MLB_RUN_LABEL": "stale", "MLB_EXEFS": "D:/stale/exefs",
                     "MLB_ROMFS": "D:/stale/romfs"}.items():
            os.environ[k] = v
            self.addCleanup(os.environ.pop, k, None)
        before = tree_hashes(self.real)
        env = self.out_env(self.go())
        slot = Path(g.slot_path("alpha"))

        def here(p):
            return str(p).replace("\\", "/")
        self.assertEqual(env["MLB_PROFILE"], here(slot / "profile"))
        self.assertEqual(env["MLB_RUN_LABEL"], "alpha")
        self.assertEqual(env["MLB_EXEFS"], here(self.dir / "work" / "build" / "game" / "exefs"))
        self.assertEqual(env["MLB_ROMFS"], here(self.dir / "work" / "build" / "game" / "romfs"))
        self.assertEqual(tree_hashes(self.real), before)

    def test_the_background_window_setting_is_kept_when_the_caller_gives_it(self):
        self.make("alpha")
        os.environ["TOTK_BACKGROUND_WINDOW"] = "0"
        self.addCleanup(os.environ.pop, "TOTK_BACKGROUND_WINDOW", None)
        self.assertEqual(self.out_env(self.go())["TOTK_BACKGROUND_WINDOW"], "0")
        self.assertEqual(self.out_env(self.go(env={"TOTK_BACKGROUND_WINDOW": "1"}))["TOTK_BACKGROUND_WINDOW"], "1")

    def test_an_exe_without_the_log_setting_gets_the_slots_log_copied_in(self):
        self.make("alpha")
        res = self.go(env={"MLB_LOG": None})          # as an exe without the setting: no MLB_LOG reaches the game
        self.assertEqual(res["log_source"], "slot folder, exe has no MLB_LOG")
        self.assertEqual(res["log"], str(Path(res["run_dir"], "mlb.log")))
        self.assertEqual(Path(res["log"]).read_text(), Path(g.slot_path("alpha"), "logs", "mlb.log").read_text())
        self.assertEqual([m[0] for m in res["markers"]], ["boot", "inning"])

    def test_each_run_logs_into_its_own_folder(self):
        self.make("alpha")
        first, second = self.go(env={"FAKE_SECONDS": "0.3"}), self.go(env={"FAKE_SECONDS": "0.3"})
        self.assertEqual([Path(r["log"]).parent.name for r in (first, second)], ["run-1", "run-2"])
        self.assertEqual(self.out_env(second)["MLB_LOG"], second["log"].replace("\\", "/"))

    def test_a_second_run_of_a_slot_with_a_live_game_is_refused_before_anything_is_written(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_SECONDS": "20", "FAKE_MODE": "hang"})
        self.assertTrue(self.wait_live("alpha"))
        playtime = Path(g.slot_path("alpha"), "profile", "playtime.txt")
        before = playtime.read_text()                                  # "123 more": the live game's own state
        (self.real / "playtime.txt").write_text("changed")             # a refresh would push this into the shared profile
        with self.assertRaisesRegex(g.GameError, "live game.*shared"):
            self.go("alpha")
        code, out = self.cli(["run", "alpha", "--real-profile", str(self.real)])
        self.assertEqual(code, 2)
        self.assertIn("shared", out)
        self.assertEqual((playtime.read_text(), [n for n, _p in g.run_dirs("alpha")]), (before, [1]))
        g.stop("alpha", grace=1.0, quiet=True)
        t.join(10)

    def test_env_wins_over_the_tool_and_none_removes_a_setting(self):
        self.make("alpha")
        res = self.go(env={"MLB_TRACE": "all", "TOTK_BACKGROUND_WINDOW": None})
        env = self.out_env(res)
        self.assertEqual(env["MLB_TRACE"], "all")
        self.assertNotIn("TOTK_BACKGROUND_WINDOW", env)
        self.assertNotIn("TOTK_BACKGROUND_WINDOW", json.loads(read(Path(res["run_dir"], "env.json"))))

    def test_pointing_the_profile_at_the_real_one_is_refused_and_nothing_starts(self):
        self.make("alpha")
        before = tree_hashes(self.real)
        with self.assertRaisesRegex(g.GameError, "never writes the real profile"):
            self.go(env={"MLB_PROFILE": str(self.real)})
        with self.assertRaisesRegex(g.GameError, "never writes the real profile"):
            self.go(env={"MLB_PROFILE": None})
        self.assertEqual(g.run_dirs("alpha"), [])
        self.assertEqual(tree_hashes(self.real), before)

    def test_a_scenario_sets_the_harness_variables_and_the_dumps_folder(self):
        self.make("alpha")
        scn = self.dir / "x.scn"
        scn.write_text("name = x\nstop_after_s = 5\n")
        res = self.go(scenario=str(scn))
        env = self.out_env(res)
        self.assertEqual(env["MLB_HARNESS"], str(scn).replace("\\", "/"))
        self.assertEqual(env["MLB_HARNESS_OUT"], str(Path(res["run_dir"], "dumps")).replace("\\", "/"))
        self.assertTrue(Path(res["run_dir"], "dumps").is_dir())

    def test_each_run_gets_its_own_number_and_log_copy(self):
        self.make("alpha")
        first, second = self.go(env={"FAKE_SECONDS": "0.3"}), self.go(env={"FAKE_SECONDS": "0.3"})
        self.assertEqual((first["run"], second["run"]), (1, 2))
        self.assertEqual((first["first_run_of_slot"], second["first_run_of_slot"]), (True, False))
        self.assertNotEqual(first["pid"], second["pid"])
        self.assertTrue(all(Path(r["log"]).is_file() for r in (first, second)))
        self.assertEqual([n for n, _p in g.run_dirs("alpha")], [1, 2])

    def test_exit_status_follows_how_the_game_ended(self):
        self.make("alpha")
        cases = [("ok", 0, 0, False, "ok"), ("crash", 3, 1, True, "ok"), ("nodev", 7, 1, False, "none")]   # mode, exit code, status, fatal, audio
        for n, (mode, exit_code, status, fatal, audio) in enumerate(cases, 1):
            with self.subTest(mode=mode):
                os.environ.update({"FAKE_MODE": mode, "FAKE_SECONDS": "0.3", "FAKE_EXIT": "0" if mode == "ok" else "7"})
                code, out = self.cli(["run", "alpha", "--real-profile", str(self.real)])
                self.assertEqual(code, status, out)
                res = json.loads(read(Path(g.slot_path("alpha"), "run-%d" % n, "result.json")))
                self.assertEqual((res["exit_code"], res["ended"], res["fatal"], res["audio"]), (exit_code, "by itself", fatal, audio))
        os.environ.pop("FAKE_MODE")
        self.assertEqual([n for n, _p in g.run_dirs("alpha")], [1, 2, 3])

    def test_run_refuses_a_slot_that_was_not_made_by_the_tool(self):
        self.hand_slot("hand")
        with self.assertRaisesRegex(g.GameError, "not made by"):
            self.go("hand")
        self.assertFalse(g.run_dirs("hand"))

    def test_run_refuses_a_slot_whose_marker_is_gone(self):
        self.make("alpha")
        os.remove(g.marker_path("alpha"))                                      # this test's own marker
        with self.assertRaisesRegex(g.GameError, "no marker"):
            self.go()
        self.assertEqual(g.run_dirs("alpha"), [])

    def test_a_python_script_stands_in_for_the_game_too(self):
        script = self.dir / "stand.py"
        script.write_text("import os, sys\nprint('stand-in in', os.getcwd(), os.environ.get('MLB_RUN_LABEL'))\nsys.exit(5)\n")
        g.create("beta", exe=str(script), support_dir=str(self.build), real_profile=str(self.real))
        self.made.append("beta")
        res = g.run("beta", real_profile=str(self.real), quiet=True, wait=30)
        self.assertEqual((res["exit_code"], res["ended"]), (5, "by itself"))
        self.assertIn("stand-in in", read(res["out"]))

    def test_ctrl_c_stops_the_game_before_the_error_comes_out(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_MODE": "window", "FAKE_SECONDS": "60"})
        self.assertTrue(self.wait_live("alpha"))
        tid = t.ident
        ctypes.pythonapi.PyThreadState_SetAsyncExc.argtypes = [ctypes.c_ulong, ctypes.py_object]
        ctypes.pythonapi.PyThreadState_SetAsyncExc.restype = ctypes.c_int
        self.assertEqual(ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(KeyboardInterrupt)), 1)
        t.join(15)
        self.assertIsInstance(t.error, KeyboardInterrupt)
        self.assertFalse(g.slot_is_live("alpha"))
        res = json.loads(read(Path(g.slot_path("alpha"), "run-1", "result.json")))
        self.assertEqual((res["ended"], res["close_reason"], res["interrupted"]), ("after a close request", "interrupt", True))
        self.assertNotIn("pid", g.read_marker("alpha"))


class Profile(Base):
    def test_the_real_profile_is_never_written_and_each_run_starts_from_its_saves(self):
        self.make("alpha")
        before = tree_hashes(self.real)
        prof = Path(g.slot_path("alpha"), "profile")
        self.go()
        self.assertEqual((prof / "save" / "slot1.bin").read_bytes(), b"original")   # it started from the real saves
        self.assertEqual((prof / "playtime.txt").read_text(), "123 more")           # and the game wrote into the copy
        self.assertTrue((prof / "save" / "played.bin").exists())
        self.assertEqual(tree_hashes(self.real), before)
        self.go()
        self.assertEqual((prof / "playtime.txt").read_text(), "123 more")           # reset to the real saves first
        self.assertEqual((prof / "save" / "played.bin").read_bytes(), b"played")     # ...and written again by the run
        (self.real / "save" / "new-real.bin").write_bytes(b"newer save")
        self.go()
        self.assertEqual((prof / "save" / "new-real.bin").read_bytes(), b"newer save")

    def test_keep_profile_goes_on_from_the_saves_the_slot_has(self):
        self.make("alpha")
        prof = Path(g.slot_path("alpha"), "profile")
        self.go()
        (prof / "save" / "progress.bin").write_bytes(b"progress made in the slot")
        self.go(keep_profile=True)
        self.assertEqual((prof / "playtime.txt").read_text(), "123 more more")
        self.assertEqual((prof / "save" / "progress.bin").read_bytes(), b"progress made in the slot")
        self.go()
        self.assertFalse((prof / "save" / "progress.bin").exists())
        self.assertEqual((prof / "playtime.txt").read_text(), "123 more")


class Turns(Base):
    """The rules for a turn, with a fixed list of live games (no process is started)."""

    def fake_live(self, entries):
        g.live_source = lambda: list(entries)

    def test_shared_needs_a_free_place_among_three(self):
        three = [(101, "D:/d/mlb_a.exe", "a"), (102, "D:/d/mlb_b.exe", "b"), (103, "D:/work/build/mlb.exe", None)]
        self.fake_live(three[:2])
        self.assertEqual(g.can_start("shared"), (True, ""))
        self.fake_live(three)
        ok, why = g.can_start("shared")
        self.assertFalse(ok)
        self.assertIn("3 of 3 places used", why)
        with g.admission("shared", wait=0) as turn:
            self.assertFalse(turn.ok)
            self.assertEqual(turn.why, why)

    def test_exclusive_refuses_while_any_game_is_live_even_one_outside_game_py(self):
        self.fake_live([(4242, "D:/elsewhere/mlb.exe", None)])
        with g.admission("exclusive", wait=0) as turn:
            self.assertFalse(turn.ok)
            self.assertIn("1 game(s) live (mlb.exe (pid 4242))", turn.why)
        self.fake_live([])
        with g.admission("exclusive", wait=0) as turn:
            self.assertTrue(turn.ok)

    def test_ordinary_runs_wait_while_an_exclusive_run_is_live(self):
        g.write_marker("tim", exe="D:/d/mlb.exe", pid=555, mode="exclusive")
        self.fake_live([(555, "D:/d/mlb.exe", "tim")])
        ok, why = g.can_start("shared")
        self.assertFalse(ok)
        self.assertIn("exclusive (timing) run is live (tim)", why)
        self.assertEqual(g.exclusive_live({555}), ["tim"])
        self.fake_live([(556, "D:/d/mlb_b.exe", "b")])                           # its game is gone: the wait is over
        self.assertEqual(g.can_start("shared"), (True, ""))
        self.assertEqual(g.exclusive_live({556}), [])

    def test_no_wait_gives_status_2_at_once(self):
        self.make("alpha")
        self.fake_live([(1, "D:/d/mlb_a.exe", "a"), (2, "D:/d/mlb_b.exe", "b"), (3, "D:/d/mlb_c.exe", "c")])
        t = time.time()
        code, out = self.cli(["run", "alpha", "--no-wait", "--real-profile", str(self.real)])
        self.assertEqual(code, 2)
        self.assertLess(time.time() - t, 3)
        self.assertIn("cannot start now: 3 of 3 places used", out)
        self.assertEqual(g.run_dirs("alpha"), [])

    def test_a_run_waits_for_a_place_and_starts_when_one_frees(self):
        self.make("alpha")
        entries = [(900 + i, "D:/d/mlb_%d.exe" % i, "other%d" % i) for i in range(3)]
        g.live_source = lambda: list(entries)
        t0 = time.time()
        t = self.start(self.go)
        time.sleep(1.5)
        self.assertIsNone(t.result)                                             # still waiting
        self.assertEqual(g.run_dirs("alpha"), [])
        entries.pop()
        t.join(20)
        self.assertIsNone(t.error)
        self.assertEqual(t.result["ended"], "by itself")
        self.assertGreaterEqual(time.time() - t0, 2.0)

    def test_a_bad_mode_is_refused(self):
        self.make("alpha")
        with self.assertRaisesRegex(g.GameError, "mode must be"):
            self.go(mode="solo")


class RealProcesses(Base):
    """Real fake-game processes: the process list game.py reads is the real one, narrowed to this test's own."""

    def probe(self, folder, name, seconds=30):
        """A process started by hand (not through game.py): a copy of python.exe that runs FAKE."""
        folder.mkdir(parents=True, exist_ok=True)
        exe = folder / name
        shutil.copy2(sys.executable, exe)
        install_fake(str(exe))
        p = subprocess.Popen([str(exe)], env=dict(os.environ, FAKE_SECONDS=str(seconds), FAKE_MODE="hang"),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        self.addCleanup(lambda: (p.kill() if p.poll() is None else None, p.wait()))
        return p

    def test_live_games_counts_a_process_under_runs_by_its_path_and_an_mlb_exe_anywhere(self):
        loose = self.probe(Path(g.runs_dir(), "loose"), "anything.exe")        # any name under work/runs/ counts
        named = self.probe(self.dir / "elsewhere", "mlb_probe.exe")            # an mlb*.exe outside work/runs/ counts
        other = self.probe(self.dir / "elsewhere2", "other.exe")               # neither: not a game
        self.extra_pids.update([loose.pid, named.pid, other.pid])
        found = {pid: (image, slot) for pid, image, slot in g.game_processes()}
        self.assertEqual(found[loose.pid][1], "loose")
        self.assertEqual(os.path.normcase(found[loose.pid][0]), os.path.normcase(str(loose.args[0])))
        self.assertEqual(found[named.pid][1], None)
        self.assertEqual(os.path.normcase(found[named.pid][0]), os.path.normcase(str(named.args[0])))
        self.assertNotIn(other.pid, found)
        self.assertNotIn(os.getpid(), found)
        self.assertEqual(g.window_titles(os.getpid()), [])                        # the test runner has no window
        self.assertLess(abs(time.time() - g.process_start(loose.pid)), 60)         # when it started, from the OS
        for p in (loose, named, other):                                         # a game that ended is not live any more
            p.kill()
            p.wait()
        after = {pid for pid, _i, _s in g.game_processes()}
        self.assertFalse({loose.pid, named.pid, other.pid} & after)

    def test_three_share_the_machine_and_the_fourth_waits_for_a_place(self):
        for i in range(1, 5):
            self.make("s%d" % i)
        runs = [self.start_run("s%d" % i, wait=0, env={"FAKE_SECONDS": "5"}) for i in range(1, 4)]
        self.assertTrue(self.wait_live("s1", "s2", "s3"))
        with self.assertRaises(g.NoTurn) as cm:
            self.go("s4", wait=0)
        for text in ("3 of 3 places used", "s1 (pid", "s2 (pid", "s3 (pid"):
            self.assertIn(text, str(cm.exception))
        code, out = self.cli(["run", "s4", "--no-wait", "--real-profile", str(self.real)])
        self.assertEqual((code, g.run_dirs("s4")), (2, []))
        self.assertIn("3 of 3 places used", out)
        with self.assertRaisesRegex(g.NoTurn, "3 game\\(s\\) live"):
            self.go("s4", wait=0, mode="exclusive")
        t0 = time.time()
        fourth = self.start_run("s4", wait=30)                                  # waits; s1 to s3 end by themselves at about 5 s
        for t in runs:                                                          # the three ran side by side
            t.join(20)
            self.assertIsNone(t.error)
            self.assertEqual(t.result["ended"], "by itself")
            self.assertEqual(sorted(o["slot"] for o in t.result["shared_with"]),
                             sorted({"s1", "s2", "s3"} - {t.result["id"]}))
            self.assertTrue(t.result["contended"])
        fourth.join(20)
        self.assertIsNone(fourth.error)
        self.assertEqual(fourth.result["ended"], "by itself")
        first_start = min(datetime.fromisoformat(t.result["started"]) for t in runs)
        self.assertGreaterEqual(datetime.fromisoformat(fourth.result["started"]), first_start + timedelta(seconds=4))
        self.assertLessEqual({o["slot"] for o in fourth.result["shared_with"]}, {"s1", "s2", "s3"})

    def test_exclusive_starts_only_on_an_empty_machine_and_ordinary_runs_wait_for_it(self):
        self.make("alpha")
        self.make("beta")
        self.assertEqual(g.can_start("exclusive"), (True, ""))
        other = self.start_run("beta", wait=0, env={"FAKE_SECONDS": "2.5"})
        self.assertTrue(self.wait_live("beta"))
        with self.assertRaisesRegex(g.NoTurn, "1 game\\(s\\) live \\(beta"):
            self.go("alpha", wait=0, mode="exclusive")
        other.join(20)
        self.assertFalse(g.slot_is_live("beta"))
        t = self.start_run("alpha", wait=30, mode="exclusive", env={"FAKE_SECONDS": "4", "FAKE_MODE": "window"})
        self.assertTrue(self.wait_live("alpha"))
        m = g.read_marker("alpha")
        self.assertEqual((m["mode"], m["pid"], m["run"]), ("exclusive", str(g.slot_is_live("alpha")[0]), "1"))
        with self.assertRaisesRegex(g.NoTurn, "exclusive \\(timing\\) run is live \\(alpha\\)"):
            self.go("beta", wait=0)
        code, _out = self.cli(["run", "beta", "--no-wait", "--real-profile", str(self.real)])
        self.assertEqual(code, 2)
        s = g.status()
        self.assertEqual((s["used"], s["exclusive_live"], s["exclusive_allowed"]), (1, ["alpha"], False))
        t.join(20)
        self.assertIsNone(t.error)
        self.assertEqual((t.result["ended"], t.result["mode"]), ("by itself", "exclusive"))
        self.assertNotIn("pid", g.read_marker("alpha"))
        self.assertEqual(g.can_start("shared"), (True, ""))

    def test_a_timeout_asks_the_game_to_close_first(self):
        self.make("alpha")
        res = self.go(env={"FAKE_MODE": "window", "FAKE_SECONDS": "60"}, timeout=1.2, grace=3)
        self.assertEqual((res["ended"], res["exit_code"], res["close_reason"], res["windows_asked"]),
                         ("after a close request", 0, "timeout", 1))
        self.assertLess(res["seconds"], 1.2 + 3)
        self.assertEqual(res["window_title"], "MLB The Show 26 (fastball) [alpha]")   # read from the operating system
        self.assertTrue(res["window_visible"])
        self.assertEqual(g.window_titles(res["pid"]), [])                             # the window is gone with the game

    def test_a_game_that_ignores_the_close_request_is_killed_after_the_grace(self):
        self.make("alpha")
        t0 = time.time()
        res = self.go(env={"FAKE_MODE": "stubborn", "FAKE_SECONDS": "60"}, timeout=1.0, grace=1.0)
        self.assertEqual((res["ended"], res["windows_asked"], res["close_reason"]), ("killed", 1, "timeout"))
        self.assertAlmostEqual(time.time() - t0, 2.0, delta=1.5)

    def test_a_game_without_a_window_is_killed_after_the_grace(self):
        self.make("alpha")
        res = self.go(env={"FAKE_MODE": "hang", "FAKE_SECONDS": "60"}, timeout=0.8, grace=0.5)
        self.assertEqual((res["ended"], res["windows_asked"]), ("killed", 0))
        self.assertFalse(g.slot_is_live("alpha"))

    def test_the_window_title_is_read_while_the_game_runs(self):
        self.make("alpha", label="t9")
        res = self.go(env={"FAKE_MODE": "window", "FAKE_SECONDS": "1.2"})
        self.assertEqual(res["window_titles_seen"], ["MLB The Show 26 (fastball) [t9]"])
        self.assertEqual(res["exit_code"], 7)                                        # nobody closed it: it ran its time

    def test_launch_alone_needs_a_turn_and_a_free_slot(self):
        self.make("alpha")
        g.live_source = lambda: [(1, "D:/d/mlb_a.exe", "a"), (2, "D:/d/mlb_b.exe", "b"), (3, "D:/d/mlb_c.exe", "c")]
        with self.assertRaises(g.NoTurn):
            g.launch("alpha", real_profile=str(self.real))
        g.live_source = self.ours_only
        t = self.start_run(env={"FAKE_SECONDS": "30", "FAKE_MODE": "hang"})
        self.assertTrue(self.wait_live("alpha"))
        with self.assertRaisesRegex(g.GameError, "live game.*shared"):
            g.launch("alpha", real_profile=str(self.real))
        self.assertEqual([n for n, _p in g.run_dirs("alpha")], [1])
        g.stop("alpha", grace=1.0, quiet=True)
        t.join(10)


class StopRelease(Base):
    def test_stop_closes_a_game_that_listens(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_MODE": "window", "FAKE_SECONDS": "60"})
        self.assertTrue(self.wait_live("alpha"))
        pid = g.read_marker("alpha")["pid"]
        self.assertEqual(g.status()["live"][0]["pid"], int(pid))
        t0 = time.time()
        self.assertEqual(g.stop("alpha", grace=5, quiet=True), "after a close request")
        self.assertLess(time.time() - t0, 5)
        t.join(10)
        self.assertEqual((t.result["ended"], t.result["exit_code"], t.result["close_reason"]),
                         ("after a close request", 0, "the stop command"))
        self.assertNotIn("pid", g.read_marker("alpha"))
        self.assertFalse(g.slot_is_live("alpha"))

    def test_stop_kills_a_game_that_ignores_the_request(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_MODE": "stubborn", "FAKE_SECONDS": "60"})
        self.assertTrue(self.wait_live("alpha"))
        self.assertEqual(g.stop("alpha", grace=1.0, quiet=True), "killed")
        t.join(10)
        self.assertEqual((t.result["ended"], t.result["close_reason"]), ("killed", "the stop command"))
        self.assertNotIn("pid", g.read_marker("alpha"))

    def test_stop_reaches_a_game_whose_own_window_comes_late(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_MODE": "late", "FAKE_SECONDS": "30"})
        self.assertTrue(self.wait_live("alpha"))
        pid = g.slot_is_live("alpha")[0]
        out = os.path.join(g.slot_path("alpha"), "run-1", "game.out")
        end = time.time() + 10
        while "FAKE helper window" not in (read(out) if os.path.isfile(out) else "") and time.time() < end:
            time.sleep(0.05)
        self.assertEqual(g.window_titles(pid), [])          # the hidden "Temp Window" is not the game's window
        self.assertEqual(g.stop("alpha", grace=8, quiet=True), "after a close request")
        t.join(15)
        self.assertEqual((t.result["ended"], t.result["exit_code"], t.result["windows_asked"]),
                         ("after a close request", 0, 1))           # its window lived under one look, so no title is promised

    def test_stop_with_no_game_live_says_so_and_leaves_the_files(self):
        self.make("alpha")
        self.assertIsNone(g.stop("alpha", quiet=True))
        code, out = self.cli(["stop", "alpha"])
        self.assertEqual(code, 0)
        self.assertIn("no game is live", out)
        self.assertTrue(os.path.exists(g.marker_path("alpha")))

    def test_stop_leaves_another_tools_slot_alone(self):
        self.hand_slot("hand")
        with self.assertRaisesRegex(g.GameError, "not made by"):
            g.stop("hand", quiet=True)
        self.assertTrue(Path(g.marker_path("hand")).exists())

    def test_release_stops_the_game_removes_the_marker_and_keeps_the_files(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_MODE": "window", "FAKE_SECONDS": "60"})
        self.assertTrue(self.wait_live("alpha"))
        self.assertEqual(g.release("alpha", grace=5, quiet=True), {"stopped": "after a close request", "released": True})
        t.join(10)
        self.assertFalse(os.path.exists(g.marker_path("alpha")))
        self.assertTrue(os.path.isfile(g.exe_path("alpha")))
        self.assertTrue(os.path.isfile(os.path.join(g.slot_path("alpha"), "run-1", "result.json")))
        with self.assertRaisesRegex(g.GameError, "no marker"):
            self.go()

    def test_release_of_a_released_slot_says_so(self):
        self.make("alpha")
        self.assertEqual(g.release("alpha", quiet=True)["released"], True)
        self.assertEqual(g.release("alpha", quiet=True), {"stopped": None, "released": False})

    def test_release_leaves_another_sessions_marker_and_slot_alone(self):
        p = self.hand_slot("theirs")
        with self.assertRaisesRegex(g.GameError, "left alone"):
            g.release("theirs", quiet=True)
        self.assertTrue(Path(g.marker_path("theirs")).exists())
        self.assertTrue((p / "slot.json").exists())


class Clean(Base):
    def test_clean_deletes_only_this_tools_finished_slots(self):
        self.make("done")
        g.release("done", quiet=True)
        self.make("marked")
        hand = self.hand_slot("hand")
        (hand / "keep.txt").write_text("x")
        targets, kept = g.clean_targets()
        self.assertEqual(targets, [g.slot_path("done")])
        self.assertEqual(kept, [("marked", "still marked (release it first)")])
        code, out = self.cli(["clean", "--all-finished", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("[dry-run] delete %s" % g.slot_path("done"), out)
        self.assertIn("[dry-run] keep %s: still marked" % g.slot_path("marked"), out)
        self.assertTrue(os.path.isdir(g.slot_path("done")))                      # a dry run deletes nothing
        code, out = self.cli(["clean", "--all-finished"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(g.slot_path("done")))
        self.assertTrue(os.path.isdir(g.slot_path("marked")))
        self.assertEqual(tree_hashes(hand), {"keep.txt": hashlib.sha256(b"x").hexdigest(), "slot.json": hashlib.sha256((hand / "slot.json").read_bytes()).hexdigest()})
        self.assertTrue(Path(g.marker_path("hand")).exists())
        self.assertEqual(self.cli(["clean", "--id", "marked", "--dry-run"])[1].count("[dry-run] delete"), 0)

    def test_clean_refuses_a_slot_with_a_live_game(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_SECONDS": "30", "FAKE_MODE": "hang"})
        self.assertTrue(self.wait_live("alpha"))
        os.remove(g.marker_path("alpha"))                                         # this test's own marker
        targets, kept = g.clean_targets()
        self.assertEqual((targets, kept), ([], [("alpha", "a game is live in it")]))
        g.stop("alpha", grace=1.0, quiet=True)
        t.join(10)
        self.assertEqual(g.clean_targets(), ([g.slot_path("alpha")], []))

    def test_clean_with_the_id_of_a_slot_that_is_not_ours_deletes_nothing(self):
        self.hand_slot("hand")
        code, out = self.cli(["clean", "--id", "hand"])
        self.assertEqual(code, 2)
        self.assertIn("not made by", out)
        self.assertTrue(Path(g.slot_path("hand"), "slot.json").exists())

    def test_clean_needs_an_id_or_all(self):
        with self.assertRaises(SystemExit) as cm:
            self.cli(["clean"])
        self.assertEqual(cm.exception.code, 2)


class Status(Base):
    def test_status_lists_live_games_slots_and_markers(self):
        self.make("alpha", label="al")
        self.hand_slot("hand")
        self.make("done")
        g.release("done", quiet=True)
        t = self.start_run(env={"FAKE_MODE": "window", "FAKE_SECONDS": "6"})
        self.assertTrue(self.wait_live("alpha"))
        pid = g.slot_is_live("alpha")[0]
        code, out = self.cli(["status"])
        self.assertEqual(code, 0)
        for text in ("1 of 3 shared places used", "alpha", str(pid), "al", "MLB The Show 26 (fastball) [al]",
                     "exclusive run allowed now: no (1 game(s) live)", "hand", "another session's", "done",
                     g.TOOL, "yes"):
            self.assertIn(text, out)
        s = json.loads(self.cli(["status", "--json"])[1])
        self.assertEqual((s["used"], s["max_shared"], s["exclusive_allowed"], s["exclusive_live"]), (1, 3, False, []))
        self.assertEqual((s["live"][0]["slot"], s["live"][0]["pid"], s["live"][0]["contended"]), ("alpha", pid, False))
        self.assertGreaterEqual(s["live"][0]["seconds"], 0)
        rows = {e["id"]: e for e in s["slots"]}
        self.assertEqual((rows["alpha"]["marker"], rows["alpha"]["marker_pid"], rows["alpha"]["live"]), ("ours", pid, [pid]))
        self.assertEqual((rows["hand"]["ours"], rows["hand"]["marker"]), (False, "another session's"))
        self.assertEqual((rows["done"]["marker"], rows["done"]["finished"]), (None, True))
        g.stop("alpha", grace=1.0, quiet=True)
        t.join(10)
        self.assertEqual(g.status()["used"], 0)

    def test_status_with_nothing_there(self):
        s = g.status()
        self.assertEqual((s["live"], s["slots"], s["used"], s["exclusive_allowed"]), ([], [], 0, True))
        code, out = self.cli(["status"])
        self.assertEqual(code, 0)
        self.assertIn("0 of 3 shared places used", out)
        self.assertIn("exclusive run allowed now: yes", out)


class Detach(Base):
    def watch_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(TOOLS / "game.py"), "_watch", *args], capture_output=True,
                              text=True, timeout=60)

    def gone(self, *pids, timeout=15):
        """True when none of `pids` is a process any more (looked for up to `timeout` seconds)."""
        end = time.time() + timeout
        while time.time() < end:
            if all(g.image_path(pid) is None for pid in pids):
                return True
            time.sleep(0.1)
        return False

    def test_detach_returns_at_once_a_watcher_writes_the_result_and_nothing_is_left_behind(self):
        self.make("alpha", name="mlb_%s.exe")                                     # the real name: the CLI is another process
        t0 = time.time()
        p = subprocess.run([sys.executable, "-I", str(TOOLS / "game.py"), "run", "alpha", "--detach",
                            "--real-profile", str(self.real)], env=dict(os.environ, FAKE_SECONDS="3"),
                           capture_output=True, text=True, timeout=60)
        took = time.time() - t0
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertLess(took, 2.5, p.stdout)                                      # it did not wait for the game
        m = re.search(r"started: pid (\d+), folder (.+)", p.stdout)
        w = re.search(r"watcher pid (\d+)", p.stdout)
        self.assertIsNotNone(m, p.stdout)
        self.assertIsNotNone(w, p.stdout)
        pid, watcher = int(m.group(1)), int(w.group(1))
        self.assertEqual(g.slot_is_live("alpha"), [pid])                           # the game outlives the command
        self.assertEqual(Path(m.group(2).strip()), Path(g.slot_path("alpha"), "run-1"))
        end = time.time() + 20
        while not os.path.isfile(Path(g.slot_path("alpha"), "run-1", "result.json")) and time.time() < end:
            time.sleep(0.1)
        res = json.loads(read(Path(g.slot_path("alpha"), "run-1", "result.json")))
        self.assertEqual((res["pid"], res["ended"], res["exit_code"]), (pid, "by itself", 7))
        # This run is counted by another process, which sees every game on the machine, other sessions' included.
        self.assertEqual(res["contended"], bool(res["shared_with"]))
        self.assertTrue(all(o["slot"] != "alpha" and o["pid"] != pid for o in res["shared_with"]))
        self.assertEqual(res["markers"][0][0], "boot")
        self.assertTrue(res["first_run_of_slot"])
        self.assertNotIn("pid", g.read_marker("alpha"))
        self.assertTrue(self.gone(pid, watcher))                                  # nor the game nor its watcher is left behind

    def test_a_watcher_whose_handle_is_not_the_games_attaches_by_the_pid(self):
        self.make("alpha")
        t = self.start_run(env={"FAKE_SECONDS": "4", "FAKE_MODE": "hang"})
        self.assertTrue(self.wait_live("alpha"))
        pid = g.slot_is_live("alpha")[0]
        t0 = time.time()
        p = self.watch_cli("alpha", "1", "999999", str(pid), repr(time.time() - 1), "-", "1.0")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""), p.stdout + p.stderr)
        self.assertLess(time.time() - t0, 12)                                     # it ended with its game, about 4 s
        t.join(15)
        self.assertTrue(self.gone(pid))

    def test_a_watcher_whose_game_is_already_gone_exits_at_once(self):
        self.make("alpha")
        self.go(env={"FAKE_SECONDS": "0.3"})
        path = Path(g.slot_path("alpha"), "run-1", "result.json")
        before = path.read_text()
        t0 = time.time()
        p = self.watch_cli("alpha", "1", "999999", "999999", repr(time.time()), "-", "1.0")
        self.assertEqual((p.returncode, path.read_text()), (0, before))
        self.assertLess(time.time() - t0, 5)

    def test_bad_watch_arguments_give_2(self):
        self.assertEqual(self.cli(["_watch"])[0], 2)
        self.assertEqual(self.cli(["_watch", "alpha"])[0], 2)
        self.assertEqual(self.cli(["_watch", "Bad_Id", "1", "2", "3", "4", "-", "5"])[0], 2)


class CommandLine(Base):
    def test_bad_input_gives_2(self):
        self.assertEqual(self.cli(["run", "Bad_Id"])[0], 2)
        self.assertEqual(self.cli(["create", "a", "--exe", str(self.dir / "no.exe")])[0], 2)
        self.assertEqual(self.cli(["stop", "nobody"])[0], 2)
        self.assertEqual(self.cli(["run", "a", "--env", "NOEQUALS"])[0], 2)
        self.assertEqual(g.main(["_watch"]), 2)

    def test_create_and_update_print_what_they_did(self):
        code, out = self.cli(["create", "alpha", "--exe", str(self.build / "mlb.exe"), "--support-dir", str(self.build),
                              "--label", "lab", "--real-profile", str(self.real)])
        self.made.append("alpha")
        self.assertEqual(code, 0, out)
        self.assertIn("copied to fakegame_alpha.exe", out)                      # the tests' name; the tool ships mlb_alpha.exe
        self.assertIn("copied from %s" % self.real, out)
        self.assertIn("[lab]", out)
        self.assertIn(str(g.marker_path("alpha")), out)
        code, out = self.cli(["update", "alpha"])
        self.assertEqual(code, 0, out)
        self.assertIn("exe unchanged", out)
        (self.build / "mlb.exe").write_bytes(b"MZ" + b"z" * 9)
        code, out = self.cli(["update", "alpha"])
        self.assertIn("exe changed", out)


if __name__ == "__main__":
    unittest.main()
