#!/usr/bin/env python3
"""Run the game in a slot of its own.

Every session that runs the game (a person, an agent, tools/harness.py, tools/bench.py) does it in a slot
work/runs/<id>/: a copy of the game exe and of the files it needs beside it, a copy of the saves, and a log of its
own, so that games can run side by side without stepping on each other. The marker work/game.state/<id>.lock is the
slot's permit, and MLB_RUN_LABEL=<label> puts "[label]" at the end of the game's window title.

  python -I tools/game.py create <id> [--exe PATH] [--support-dir DIR] [--label TEXT]
  python -I tools/game.py update <id> [--exe PATH]
  python -I tools/game.py run <id> [--env KEY=VALUE ...] [--scenario FILE] [--mode shared|exclusive]
                               [--no-wait | --wait SECONDS] [--timeout SECONDS] [--keep-profile] [--detach]
  python -I tools/game.py status [--json]
  python -I tools/game.py stop <id>
  python -I tools/game.py release <id>
  python -I tools/game.py clean [--id ID | --all-finished] [--dry-run]

A slot holds mlb_<id>.exe (a copy of --exe, default work/build/mlb.exe or MLB_GAME_EXE), the support files from
--support-dir (default work/build), profile/ (a copy of the real profile's save, save-tx, playtime.txt and
account.uid; the real profile is never written), slot.json (it says the slot is this tool's) and run-<n>/ per run:
game.out, game.log, env.json, result.json (and dumps/ with --scenario). The game starts with the slot as its working
folder and with MLB_EXEFS, MLB_ROMFS, MLB_PROFILE and MLB_RUN_LABEL set. Slots and markers live in the main
checkout's work/, also when this runs from a research worktree (MLB_GAME_ROOT overrides the checkout, for tests).

Turns: `shared` (the default) starts when fewer than three games are live anywhere on the machine and no exclusive
run is live. `exclusive` (a timing run) starts only when no game is live, and ordinary runs then wait for it. Live
games are counted from the process list: every process under work/runs/ and every mlb*.exe, whoever started it.

Exit status of `run`: 0 the game ended by itself with exit code 0, 1 it ended another way, 2 the run could not happen
(no turn, the slot is missing, released or busy, bad input). The other commands give 2 on a refusal.

Python API (harness.py and bench.py use it): create, update, prepare, run, launch, admission, stop, release, clean,
status, slot_path, exe_path, live_games, window_titles.
Tests: python -I -m unittest discover -s tools -p test_game.py (a fake game, no real game).
Details: docs/dev-config.md, "Run slots"."""
import argparse
import contextlib
import ctypes
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = "tools/game.py"
ID_RULE = re.compile(r"[a-z0-9-]{1,32}")      # a slot id
EXE_FORMAT = "mlb_%s.exe"                     # the slot's copy of the game exe
SUPPORT_FILES = ("totk_xlate.exe", "totk_xlate.id", "SDL3.dll", "mlb.cfg", "pipeline-cache.bin", "pipeline-keys.bin",
                 "shader-answers.bin", "shader-programs.bin")
SUPPORT_DIRS = ("shader-cache",)              # copied into a new slot; the game then adds its own shaders to the copy
PROFILE_ITEMS = ("save", "save-tx", "playtime.txt", "account.uid")   # what is copied from the real profile
MAX_SHARED = 3                                # games on the machine at once, whoever started them
DEFAULT_WAIT = 1800                           # seconds a run waits for its turn
CLOSE_GRACE = 10.0                            # seconds between the close request and the kill
POLL = 0.25                                   # seconds between looks at a running game
LIVE_EVERY = 1.0                              # seconds between looks at who else is live
GAME_NAME = re.compile(r"mlb.*\.exe", re.I)   # a game started outside work/runs/
MARKER_LINE = re.compile(r"\[host\] harness: marker (\S+) frame (\d+) t ([\d.]+)")

if os.name == "nt":
    import ctypes.wintypes as wt
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.GetCurrentProcess.restype = wt.HANDLE
    _k32.QueryFullProcessImageNameW.restype = wt.BOOL
    _k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    _psapi.EnumProcesses.restype = wt.BOOL
    _psapi.EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
    _k32.GetProcessTimes.restype = wt.BOOL
    _k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
    _k32.GetExitCodeProcess.restype = wt.BOOL
    _k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    _k32.WaitForSingleObject.restype = wt.DWORD
    _k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    _k32.GetProcessId.restype = wt.DWORD
    _k32.GetProcessId.argtypes = [wt.HANDLE]
    _k32.TerminateProcess.restype = wt.BOOL
    _k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
    _k32.CreateMutexW.restype = wt.HANDLE
    _k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    _k32.ReleaseMutex.restype = wt.BOOL
    _k32.ReleaseMutex.argtypes = [wt.HANDLE]
    _k32.IsProcessInJob.restype = wt.BOOL
    _k32.IsProcessInJob.argtypes = [wt.HANDLE, wt.HANDLE, ctypes.POINTER(wt.BOOL)]
    _user32.GetWindowThreadProcessId.restype = wt.DWORD
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.IsWindowVisible.restype = wt.BOOL
    _user32.IsWindowVisible.argtypes = [wt.HWND]
    _user32.SendMessageTimeoutW.restype = wt.LPARAM
    _user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                            ctypes.POINTER(ctypes.c_size_t)]
    _ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _user32.EnumWindows.argtypes = [_ENUMPROC, wt.LPARAM]
    _QUERY = 0x1000                             # PROCESS_QUERY_LIMITED_INFORMATION
    _SYNCHRONIZE = 0x00100000
    _TERMINATE = 0x0001
    _WM_CLOSE = 0x0010
    _BREAKAWAY = 0x01000000                     # CREATE_BREAKAWAY_FROM_JOB
    _WAIT_OBJECT_0, _WAIT_TIMEOUT, _WAIT_ABANDONED = 0, 0x102, 0x80


class GameError(Exception):
    """Bad input or a refusal: nothing was started."""


class NoTurn(GameError):
    """The run could not start: no turn within the wait."""


# ---- places ---------------------------------------------------------------------------------------------------------

def root():
    """The main checkout, whose work/ holds the slots and the markers (also when this file runs from a research
    worktree under .claude/worktrees/). MLB_GAME_ROOT overrides it (tests)."""
    env = os.environ.get("MLB_GAME_ROOT")
    if env:
        return os.path.abspath(env)
    parts = os.path.normpath(HERE).split(os.sep)
    for i in range(len(parts) - 2):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return os.sep.join(parts[:i])
    return os.path.dirname(HERE)


def runs_dir():
    return os.path.join(root(), "work", "runs")


def state_dir():
    return os.path.join(root(), "work", "game.state")


def slot_path(id):
    return os.path.join(runs_dir(), id)


def exe_path(id):
    return os.path.join(slot_path(id), EXE_FORMAT % id)


def marker_path(id):
    return os.path.join(state_dir(), id + ".lock")


def default_exe():
    return os.environ.get("MLB_GAME_EXE") or os.path.join(root(), "work", "build", "mlb.exe")


def default_support():
    return os.path.join(root(), "work", "build")


def real_profile_dir(explicit=None):
    return os.path.abspath(explicit or os.path.join(root(), "work", "build", "profile"))


def check_id(id):
    if not ID_RULE.fullmatch(id):
        raise GameError("slot id %r is not allowed: lowercase letters, digits and hyphens, at most 32 characters" % id)
    return id


def fwd(path):
    return path.replace("\\", "/")


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def same_dir(a, b):
    return _norm(a) == _norm(b)


def _remove(path):
    with contextlib.suppress(FileNotFoundError):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def _json_write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")


# ---- live games -----------------------------------------------------------------------------------------------------

def image_path(pid):
    """The full path of the program a process runs, or None (it ended, or it cannot be opened)."""
    h = _k32.OpenProcess(_QUERY, False, pid)
    if not h:
        return None
    try:
        buf, n = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
        return buf.value if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        _k32.CloseHandle(h)


def game_processes():
    """[(pid, image path, slot id or None)]: every process whose image is under work/runs/ or named mlb*.exe, whoever
    started it. One pass over the process list with ctypes (about 15 ms); no other program is run."""
    if os.name != "nt":
        return []
    # A failed look is an error, never "no game is live": that would let a run start over the limit.
    for count in (16384, 65536, 262144):
        arr, got = (wt.DWORD * count)(), wt.DWORD()
        if not _psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(got)):
            raise GameError("could not list the processes (EnumProcesses failed with error %d)" % ctypes.get_last_error())
        if got.value < ctypes.sizeof(arr):
            break
    else:
        raise GameError("could not list the processes: more than 262144 of them")
    runs = _norm(runs_dir()) + os.sep
    out = []
    for pid in arr[:got.value // ctypes.sizeof(wt.DWORD)]:
        path = image_path(pid)
        if not path:
            continue
        low = _norm(path)
        if low.startswith(runs):
            slot = low[len(runs):].split(os.sep)[0] or None
        elif GAME_NAME.fullmatch(os.path.basename(path)):
            slot = None
        else:
            continue
        out.append((int(pid), path, slot))
    return sorted(out)


# Tests replace it: a fixed list, or game_processes() narrowed to the processes they started.
live_source = game_processes


def live_games():
    """[(pid, image path, slot id or None)] of the games live on the machine, this tool's and the others'."""
    return list(live_source())


def slot_is_live(id, live=None):
    """The pids of the games running from slot `id`."""
    live = live_games() if live is None else live
    return sorted(pid for pid, _image, slot in live if slot == id)


def process_start(pid):
    """When a process started, as a Unix time (None when it cannot be opened)."""
    h = _k32.OpenProcess(_QUERY, False, pid)
    if not h:
        return None
    try:
        c, e, k, u = (wt.FILETIME() for _ in range(4))
        if not _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return ((c.dwHighDateTime << 32) | c.dwLowDateTime) / 1e7 - 11644473600
    finally:
        _k32.CloseHandle(h)


def _windows(pid):
    """[(hwnd, title)] of the visible top-level windows with a title that belong to `pid`: the game's window. Hidden
    titled windows are not it: the graphics driver makes one ("Temp Window", 0.9 s after launch, gone when the game's
    window comes 6 s later) and so does the input method ("Default IME"); asking those to close closes nothing.
    The titles come from the operating system; a screenshot is never looked at."""
    out = []

    @_ENUMPROC
    def cb(hwnd, _):
        p = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and _user32.IsWindowVisible(hwnd):
            n = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            _user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value:
                out.append((hwnd, buf.value))
        return True

    _user32.EnumWindows(cb, 0)
    return out


def window_titles(pid):
    """The titles of `pid`'s visible top-level windows, each once."""
    return list(dict.fromkeys(t for _h, t in _windows(pid)))


def request_close(pid):
    """WM_CLOSE to each of `pid`'s visible windows with a title (what the X button sends). Returns how many were
    asked; whether the game then ends is for the caller to wait for."""
    asked, result = 0, ctypes.c_size_t()
    for hwnd, _title in _windows(pid):
        # SMTO_ABORTIFHUNG: the call waits until the window's code has handled the message, at most 2 s, and returns
        # at once when that thread is hung.
        _user32.SendMessageTimeoutW(hwnd, _WM_CLOSE, 0, 0, 0x0002, 2000, ctypes.byref(result))
        asked += 1
    return asked


# ---- turns ----------------------------------------------------------------------------------------------------------

_mutexes = {}


def _mutex():
    """The machine-wide lock starters take around their look and their start, so that two sessions starting at the
    same moment cannot go over the limit. Named after the checkout, so a test's slots have their own."""
    if os.name != "nt":
        return None
    scope = hashlib.sha1(_norm(root()).encode("utf-8")).hexdigest()[:12]
    if scope not in _mutexes:
        _mutexes[scope] = _k32.CreateMutexW(None, False, "fastball.game.admission." + scope)
    return _mutexes[scope]


@contextlib.contextmanager
def _machine_lock():
    m = _mutex()
    if m is None:
        yield
        return
    r = _k32.WaitForSingleObject(m, 60000)
    if r not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):       # abandoned: its last holder died, so it is free now
        raise GameError("could not take the game admission lock (WaitForSingleObject gave %d)" % r)
    try:
        yield
    finally:
        _k32.ReleaseMutex(m)


class Turn:
    def __init__(self, ok, why=""):
        self.ok, self.why = ok, why


def _who(entry):
    pid, image, slot = entry
    return "%s (pid %d)" % (slot or os.path.basename(image), pid)


def can_start(mode):
    """(ok, why not) for starting a game now: `exclusive` needs a machine with no game on it; `shared` a free place
    among the MAX_SHARED and no exclusive run (ordinary runs wait for a timing run)."""
    if mode not in ("shared", "exclusive"):
        raise GameError("mode must be shared or exclusive, not %r" % mode)
    live = live_games()
    if mode == "exclusive":
        if live:
            return False, "%d game(s) live (%s); an exclusive run starts only when no game is live" % (
                len(live), ", ".join(_who(e) for e in live))
        return True, ""
    ex = exclusive_live({pid for pid, _i, _s in live})
    if ex:
        return False, "an exclusive (timing) run is live (%s); ordinary runs wait for it" % ", ".join(ex)
    if len(live) >= MAX_SHARED:
        return False, "%d of %d places used (%s)" % (len(live), MAX_SHARED, ", ".join(_who(e) for e in live))
    return True, ""


def exclusive_live(pids):
    """The ids whose marker declares an exclusive (timing) run with a game among `pids`. The declaration lasts until
    that game exits, whoever launched it, so it also holds for a detached run and survives a crashed starter."""
    out = []
    for id in markers():
        m = read_marker(id)
        if m.get("mode") == "exclusive" and m.get("pid", "").isdigit() and int(m["pid"]) in pids:
            out.append(id)
    return out


@contextlib.contextmanager
def admission(mode="shared", wait=DEFAULT_WAIT, poll=1.0, quiet=False):
    """A turn to start one game. `shared` needs a free place among the three, `exclusive` a machine with no game on
    it. Waits up to `wait` seconds for it (0: does not wait) and yields a Turn; when `turn.ok` is False, `turn.why`
    says why. The turn is held only inside the block: start the game there at once (`launch` does it under the same
    lock). An exclusive game then keeps the machine by its marker until it exits."""
    end = time.time() + max(0.0, wait)
    said = False
    while True:
        with _machine_lock():
            turn = Turn(*can_start(mode))
            if turn.ok or time.time() >= end:
                yield turn
                return
        if not said and not quiet:
            print("waiting for a turn: %s" % turn.why, flush=True)
            said = True
        time.sleep(poll)


# ---- markers --------------------------------------------------------------------------------------------------------

def markers():
    """The ids that have a marker in work/game.state."""
    try:
        return sorted(n[:-5] for n in os.listdir(state_dir()) if n.endswith(".lock"))
    except OSError:
        return []


def read_marker(id):
    """The marker's fields, or None. Ours are `key = value` lines; another session's may be `id exe=... start=...`."""
    try:
        with open(marker_path(id), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    fields = {}
    for line in text.splitlines():
        key, sep, val = line.strip().partition("=")
        key = key.strip()
        if sep and key and " " not in key:
            fields[key] = val.strip()
    if not fields:
        fields = dict(re.findall(r"([A-Za-z_]\w*)=(\S+)", text))
        first = text.split(None, 1)[0] if text.strip() else ""
        if first and "=" not in first:
            fields.setdefault("id", first)
    fields.setdefault("id", id)
    return fields


def write_marker(id, label=None, exe=None, pid=None, start=None, run=None, mode=None):
    """Write (or rewrite) this tool's marker for `id`, whole at once."""
    os.makedirs(state_dir(), exist_ok=True)
    old = read_marker(id) or {}
    lines = ["id = %s" % id, "label = %s" % (label or old.get("label") or id), "exe = %s" % (exe or old.get("exe") or "")]
    if pid:
        lines.append("pid = %d" % pid)
        if run is not None:
            lines.append("run = %d" % run)
    if mode:
        lines.append("mode = %s" % mode)
    lines.append("start = %s" % (start or old.get("start") or now_iso()))
    lines.append("tool = %s" % TOOL)
    tmp = marker_path(id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, marker_path(id))


def our_marker(id):
    """The marker of `id` when this tool wrote it, else None."""
    m = read_marker(id)
    return m if m and m.get("tool") == TOOL else None


# ---- slots ----------------------------------------------------------------------------------------------------------

def read_slot(id):
    """The slot's record when this tool made it (slot.json says so), else None."""
    try:
        with open(os.path.join(slot_path(id), "slot.json"), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) and rec.get("tool") == TOOL else None


def require_slot(id):
    check_id(id)
    rec = read_slot(id)
    if rec is None:
        raise GameError("slot %s was not made by %s (no %s): its files, marker and game are left alone" %
                        (id, TOOL, os.path.join(slot_path(id), "slot.json")))
    return rec


def _write_slot(id, rec):
    _json_write(os.path.join(slot_path(id), "slot.json"), rec)


def _same_file(a, b):
    try:
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return sa.st_size == sb.st_size and abs(sa.st_mtime - sb.st_mtime) < 0.01


def copy_support(src, slot, refresh):
    """Copy the files the game needs beside its exe from `src` into the slot. With `refresh`, a file is copied again
    only when its size or time differs from the slot's, and shader-cache/ only when the slot has none (the game adds
    shaders to its copy). Returns ([copied], [missing in src])."""
    copied, missing = [], []
    for name in SUPPORT_FILES:
        s, d = os.path.join(src, name), os.path.join(slot, name)
        if not os.path.isfile(s):
            missing.append(name)
        elif not (refresh and _same_file(s, d)):
            shutil.copy2(s, d)
            copied.append(name)
    for name in SUPPORT_DIRS:
        s, d = os.path.join(src, name), os.path.join(slot, name)
        if not os.path.isdir(s):
            missing.append(name + "/")
        elif not os.path.isdir(d):
            shutil.copytree(s, d)
            copied.append(name + "/")
    return copied, missing


def refresh_profile(id, source=None):
    """Make the slot's profile hold what the real profile's save, save-tx, playtime.txt and account.uid hold now (a
    file the last run left in the slot's save is gone again). The real profile is only read. Returns (the slot
    profile, the real profile, whether there was a real profile to copy)."""
    source = real_profile_dir(source)
    dst = os.path.join(slot_path(id), "profile")
    os.makedirs(dst, exist_ok=True)
    if not os.path.isdir(source):
        return dst, source, False
    for it in PROFILE_ITEMS:
        s, d = os.path.join(source, it), os.path.join(dst, it)
        _remove(d)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        elif os.path.isfile(s):
            shutil.copy2(s, d)
    return dst, source, True


def create(id, exe=None, support_dir=None, label=None, real_profile=None):
    """A new slot and its marker. Refuses an id whose slot folder or marker already exists."""
    check_id(id)
    exe, support_dir = os.path.abspath(exe or default_exe()), os.path.abspath(support_dir or default_support())
    if not os.path.isfile(exe):
        raise GameError("no game exe at %s (build it, or pass --exe / set MLB_GAME_EXE)" % exe)
    slot = slot_path(id)
    if os.path.exists(slot) or os.path.lexists(marker_path(id)):
        raise GameError("id %s is taken (%s)" % (id, "slot folder %s exists" % slot if os.path.exists(slot)
                                                 else "marker %s exists" % marker_path(id)))
    os.makedirs(runs_dir(), exist_ok=True)
    try:
        os.makedirs(slot)
    except FileExistsError:
        raise GameError("id %s is taken (slot folder %s exists)" % (id, slot))
    try:
        shutil.copy2(exe, exe_path(id))
        copied, missing = copy_support(support_dir, slot, refresh=False)
        profile, real, found = refresh_profile(id, real_profile)
        st = os.stat(exe)
        rec = {"tool": TOOL, "id": id, "label": label or id, "created": now_iso(),
               "exe": {"source": exe, "size": st.st_size, "mtime": st.st_mtime}, "support": support_dir,
               "support_copied": copied, "support_missing": missing,
               "profile": {"slot": profile, "real": real, "real_found": found}}
        _write_slot(id, rec)
        write_marker(id, label=rec["label"], exe=exe_path(id))
    except BaseException:
        shutil.rmtree(slot, ignore_errors=True)       # this call made it, a moment ago
        raise
    return rec


def update(id, exe=None, support_dir=None):
    """Bring a slot this tool made up to date with the build folder: the exe when it differs from slot.json (path,
    size or time), and support files that differ. Returns the slot record plus exe_changed and support_copied."""
    rec = require_slot(id)
    busy = slot_is_live(id)
    if busy:
        raise GameError("slot %s has a live game (pid %d): stop it before updating it" % (id, busy[0]))
    exe = os.path.abspath(exe or rec["exe"]["source"])
    support_dir = os.path.abspath(support_dir or rec.get("support") or default_support())
    if not os.path.isfile(exe):
        raise GameError("no game exe at %s" % exe)
    st, old = os.stat(exe), rec["exe"]
    dst = exe_path(id)
    changed = (old["source"] != exe or old["size"] != st.st_size or abs(old["mtime"] - st.st_mtime) >= 0.01
               or not os.path.isfile(dst))
    if changed:
        shutil.copy2(exe, dst)
    copied, missing = copy_support(support_dir, slot_path(id), refresh=True)
    rec.update({"exe": {"source": exe, "size": st.st_size, "mtime": st.st_mtime}, "support": support_dir,
                "support_missing": missing, "updated": now_iso()})
    _write_slot(id, rec)
    return dict(rec, exe_changed=changed, support_copied=copied)


def prepare(id, exe=None, support_dir=None, label=None, real_profile=None):
    """A slot ready for run(): created when there is none yet, else brought up to date (update)."""
    if read_slot(id) is not None:
        return update(id, exe, support_dir)
    return create(id, exe, support_dir, label, real_profile)


def run_dirs(id):
    """The slot's run folders by number: [(n, path)]."""
    try:
        names = os.listdir(slot_path(id))
    except OSError:
        return []
    out = []
    for n in names:
        m = re.fullmatch(r"run-(\d+)", n)
        if m and os.path.isdir(os.path.join(slot_path(id), n)):
            out.append((int(m.group(1)), os.path.join(slot_path(id), n)))
    return sorted(out)


# ---- environment and start ------------------------------------------------------------------------------------------

def apply_overrides(env, overrides):
    """Put `overrides` over `env`: a value of None removes the variable."""
    for k, v in (overrides or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def game_environment(id, overrides=None, scenario=None, run_dir=None, label=None, real_profile=None):
    """The environment the slot's game starts with: the caller's, with MLB_EXEFS, MLB_ROMFS, MLB_PROFILE (the slot's
    profile), MLB_RUN_LABEL and, with a scenario, MLB_HARNESS and MLB_HARNESS_OUT set, and TOTK_BACKGROUND_WINDOW=1
    unless the caller already gives it. `overrides` (--env) wins over all that, a value of None removes the variable;
    only MLB_PROFILE may not be pointed back at the real profile."""
    overrides = overrides or {}
    mine = {"MLB_EXEFS": fwd(os.path.join(root(), "work", "build", "game", "exefs")),
            "MLB_ROMFS": fwd(os.path.join(root(), "work", "build", "game", "romfs")),
            "MLB_PROFILE": fwd(os.path.join(slot_path(id), "profile")),
            "MLB_RUN_LABEL": label or id}
    if scenario:
        mine["MLB_HARNESS"] = fwd(os.path.abspath(scenario))
        mine["MLB_HARNESS_OUT"] = fwd(os.path.join(run_dir, "dumps"))
    env = apply_overrides(dict(os.environ), mine)
    if "TOTK_BACKGROUND_WINDOW" not in env and "TOTK_BACKGROUND_WINDOW" not in overrides:
        env["TOTK_BACKGROUND_WINDOW"] = "1"
    env = apply_overrides(env, overrides)
    real = real_profile_dir(real_profile)
    if env.get("MLB_PROFILE") is None or same_dir(env["MLB_PROFILE"], real):
        raise GameError("a slot run never writes the real profile (%s): MLB_PROFILE stays on the slot's own profile" % real)
    return env


def env_record(env, overrides=None):
    """What goes into env.json: every MLB_/TOTK_ setting in effect and every variable the caller set."""
    overrides = overrides or {}
    keys = {k for k in env if k.startswith(("MLB_", "TOTK_"))} | set(overrides)
    return {k: env[k] for k in sorted(keys) if k in env}


def is_pe(path):
    with open(path, "rb") as f:
        return f.read(2) == b"MZ"


def start_command(exe):
    """[exe], or Python for a file that is not a Windows program (a test's stand-in for the game)."""
    return [exe] if is_pe(exe) else [sys.executable, "-I", exe]


def _popen(argv, cwd, env, out, detached, startupinfo=None):
    flags = subprocess.CREATE_NO_WINDOW   # no console window appears, and the game does not share this one (Ctrl+C is handled here)
    if detached:
        in_job = wt.BOOL()
        if _k32.IsProcessInJob(_k32.GetCurrentProcess(), None, ctypes.byref(in_job)) and in_job.value:
            flags |= _BREAKAWAY           # the game must outlive the shell or agent that started it
    kw = dict(cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, close_fds=True)
    try:
        return subprocess.Popen(argv, creationflags=flags, startupinfo=startupinfo, **kw)
    except OSError:
        if not flags & _BREAKAWAY:
            raise
        return subprocess.Popen(argv, creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startupinfo, **kw)   # the job forbids leaving it


def _rescue_old_log(id):
    """The game overwrites <slot>/logs/mlb.log at every start. Before that, the newest run folder that has neither a
    game.log nor a result.json (a detached run whose watcher died) gets a copy of the log lying there."""
    src = os.path.join(slot_path(id), "logs", "mlb.log")
    if not os.path.isfile(src):
        return
    for _n, d in reversed(run_dirs(id)):
        if not os.path.isfile(os.path.join(d, "result.json")) and not os.path.isfile(os.path.join(d, "game.log")):
            shutil.copy2(src, os.path.join(d, "game.log"))
            break


def launch(id, env=None, scenario=None, label=None, mode="shared", detach=False, real_profile=None):
    """Start the slot's game now, when it has a turn (else NoTurn), and return (the Popen, the run folder). Makes
    run-<n>/ with env.json and game.out, and puts the pid into the slot's marker. Callers that waited with admission()
    are inside its block: launch takes the same lock, so the look and the start are one step there."""
    rec = require_slot(id)
    marker = our_marker(id)
    if marker is None:
        raise GameError("slot %s has no marker from %s (it was released, or another session holds its id): create it again" %
                        (id, TOOL))
    label = label or marker.get("label") or id
    overrides = env or {}
    with _machine_lock():
        busy = slot_is_live(id)
        if busy:
            raise GameError("slot %s already has a live game (pid %d): stop it or wait for it" % (id, busy[0]))
        ok, why = can_start(mode)
        if not ok:
            raise NoTurn(why)
        n = 1
        while os.path.isdir(os.path.join(slot_path(id), "run-%d" % n)):
            n += 1
        run_dir = os.path.join(slot_path(id), "run-%d" % n)
        full = game_environment(id, overrides, scenario, run_dir, label, real_profile)   # it may refuse: nothing is made yet
        os.makedirs(run_dir)
        if scenario:
            os.makedirs(os.path.join(run_dir, "dumps"))
        _rescue_old_log(id)
        _json_write(os.path.join(run_dir, "env.json"), env_record(full, overrides))
        try:
            with open(os.path.join(run_dir, "game.out"), "wb") as out:
                proc = _popen(start_command(exe_path(id)), slot_path(id), full, out, detach)
        except OSError as e:
            raise GameError("the game did not start: %s" % e)
        write_marker(id, label=label, exe=exe_path(id), pid=proc.pid, run=n, mode=mode)
    if label != rec.get("label"):
        rec["label"] = label
        _write_slot(id, rec)
    return proc, run_dir


class _HandleProc:
    """A started process seen through its handle: the four things `watch` needs of it (a detached run's watcher)."""

    def __init__(self, handle, pid):
        self._h, self.pid, self.returncode = handle, pid, None

    def poll(self):
        if self.returncode is None and _k32.WaitForSingleObject(self._h, 0) == _WAIT_OBJECT_0:
            code = wt.DWORD()
            self.returncode = code.value if _k32.GetExitCodeProcess(self._h, ctypes.byref(code)) else None
        return self.returncode

    def wait(self, timeout=None):
        _k32.WaitForSingleObject(self._h, 0xFFFFFFFF if timeout is None else int(timeout * 1000))
        return self.poll()

    def kill(self):
        if self.poll() is None:
            _k32.TerminateProcess(self._h, 1)
            self.wait(10)


# ---- waiting for a started game -------------------------------------------------------------------------------------

def _stop_game(proc, grace):
    """Ask the game to close (WM_CLOSE to its windows) and wait up to `grace` seconds; kill it when it still runs.
    The request is repeated every half second until it ends: a game that is still starting has no window yet (the
    real game's comes about 6 s after launch in a fresh slot).
    Returns (how it ended: "after a close request" or "killed", how many windows were asked)."""
    killed, asked = False, 0
    try:
        end = time.time() + grace
        while proc.poll() is None and time.time() < end:
            asked = request_close(proc.pid) or asked
            time.sleep(0.5)
        killed = proc.poll() is None
    finally:
        if proc.poll() is None:       # also a second Ctrl+C during the wait: the game is never left running
            proc.kill()
            proc.wait()
    return ("killed" if killed else "after a close request"), asked


def _log_facts(path):
    """(path, [(marker, frame, t)], audio state, whether there is a FATAL line) from a log read line by line, never
    held whole. (None, [], "unknown", False) when there is no log."""
    marks, audio, fatal = [], "unknown", False
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None, marks, audio, fatal
    with f:
        for line in f:
            m = MARKER_LINE.search(line)
            if m:
                marks.append((m.group(1), int(m.group(2)), float(m.group(3))))
            if audio == "unknown":
                audio = audio_state(line)
            if "FATAL:" in line:
                fatal = True
    return path, marks, audio, fatal


def audio_state(line):
    """'none' when the log says the game found no audio output (it then sits at the loading screen), 'ok' when a
    WASAPI device opened, else 'unknown'."""
    if "audout: no output device" in line:
        return "none"
    if "audout: WASAPI device" in line:
        return "ok"
    return "unknown"


def list_sizes(d):
    """{relative path: size} of the files under `d`."""
    out = {}
    for base, _dirs, names in os.walk(d):
        for n in names:
            p = os.path.join(base, n)
            with contextlib.suppress(OSError):
                out[os.path.relpath(p, d).replace("\\", "/")] = os.path.getsize(p)
    return dict(sorted(out.items()))


def _slot_log(run_dir, id, since):
    """The game's log for this run, copied into the run folder as game.log. The game replaces <slot>/logs/mlb.log at
    every start, so a file older than the run is another run's and is not taken."""
    src = os.path.join(slot_path(id), "logs", "mlb.log")
    try:
        if os.path.getmtime(src) < since - 1.0:
            return None
    except OSError:
        return None
    dst = os.path.join(run_dir, "game.log")
    with open(src, "rb") as f, open(dst, "wb") as out:
        shutil.copyfileobj(f, out)
    return dst


def watch(proc, started, id, n, timeout=None, grace=CLOSE_GRACE, quiet=False):
    """Wait for the game of run `n` in slot `id` until it exits, or until `timeout` seconds have passed since
    `started` (then: a close request, and a kill `grace` seconds later; Ctrl+C does the same). While it runs, a look
    every second at who else is live and at the window title. Writes result.json into the run folder and returns what
    it says."""
    run_dir = os.path.join(slot_path(id), "run-%d" % n)
    marker = our_marker(id) or {}
    name, mode = marker.get("label") or id, marker.get("mode") or "shared"
    # The slot's first run pays for filling its caches: the first game after a fresh copy of the exe folder took 37.1 s
    # to reach the field picture where the next three took 22.5 s (2026-11-23). A timing run wants a warmed slot.
    first = not any(os.path.isfile(os.path.join(d, "result.json")) for m, d in run_dirs(id) if m < n)
    deadline = None if timeout is None else started + timeout
    titles, title, visible, others = [], None, False, {}
    close, stop_note, asked, interrupted = None, None, 0, False
    state = {"next_live": 0.0}

    def stop_note_read():
        nonlocal stop_note
        try:
            with open(os.path.join(run_dir, "stop.json"), encoding="utf-8") as f:
                stop_note = json.load(f)
        except (OSError, ValueError):
            pass

    def look():
        nonlocal title, visible
        for _hwnd, t in _windows(proc.pid):
            if t not in titles:
                titles.append(t)
            title, visible = t, True
        if time.time() >= state["next_live"]:
            for pid, image, slot in live_games():
                if pid != proc.pid:
                    o = others.setdefault(pid, {"pid": pid, "slot": slot, "image": image,
                                                "label": (read_marker(slot) or {}).get("label") if slot else None,
                                                "first_s": round(time.time() - started, 1), "last_s": None})
                    o["last_s"] = round(time.time() - started, 1)
            state["next_live"] = time.time() + LIVE_EVERY

    try:
        while proc.poll() is None:
            if deadline is not None and time.time() >= deadline:
                close = (now_iso(), "timeout")
                if not quiet:
                    print("%s: %s s over, asking the game to close (killed %s s later if it keeps running)" %
                          (name, format(timeout, "g"), format(grace, "g")), flush=True)
                break
            stop_note_read()                     # `game.py stop` (another process) says here that it asked or killed
            look()
            time.sleep(POLL)
    except KeyboardInterrupt:
        interrupted, close = True, (now_iso(), "interrupt")
        if not quiet:
            print("%s: interrupted, asking the game to close" % name, flush=True)
    stop_note_read()                             # a game closed by `stop` can exit before the loop saw stop.json
    if close is not None:
        try:
            ended, asked = _stop_game(proc, grace)
        except KeyboardInterrupt:            # a second Ctrl+C: _stop_game's finally has killed the game
            ended = "killed"
    else:
        proc.wait()
        ended = "by itself"
    if ended == "by itself" and stop_note:   # someone else asked it to close, or killed it
        close = (stop_note.get("requested"), "the stop command")
        ended = "killed" if stop_note.get("killed") else "after a close request"
        asked = stop_note.get("windows_asked", asked)
    if our_marker(id):                       # no live run in this slot any more
        write_marker(id, label=marker.get("label"), exe=exe_path(id), start=marker.get("start"), mode=marker.get("mode"))
    log = _slot_log(run_dir, id, started)   # None: this run wrote no log
    log, marks, audio, fatal = _log_facts(log) if log is not None else (None, [], "unknown", False)
    shared = [others[p] for p in sorted(others)]
    res = {"id": id, "label": name, "run": n, "run_dir": run_dir, "mode": mode, "pid": proc.pid, "first_run_of_slot": first,
           "started": datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
           "seconds": round(time.time() - started, 1), "exit_code": proc.returncode, "ended": ended,
           "close_requested": close[0] if close else None, "close_reason": close[1] if close else None,
           "windows_asked": asked, "interrupted": interrupted, "audio": audio, "fatal": fatal,
           "markers": [list(m) for m in marks], "log": log, "out": os.path.join(run_dir, "game.out"),
           "env": os.path.join(run_dir, "env.json"), "window_title": title, "window_visible": visible,
           "window_titles_seen": titles, "shared_with": shared, "contended": bool(shared)}
    dumps = os.path.join(run_dir, "dumps")
    if os.path.isdir(dumps):
        res["dumps"] = list_sizes(dumps)
    _json_write(os.path.join(run_dir, "result.json"), res)
    if not quiet:
        print(summary_line(res), flush=True)
    if interrupted:                          # the game is stopped and the result is written: the interrupt goes on
        raise KeyboardInterrupt
    return res


def summary_line(res):
    window = "" if not res.get("window_title") else ", window %r%s" % (
        res["window_title"], "" if res["window_visible"] else " (hidden)")
    return "%s: %s, exit code %s, %s s, audio %s, %d marker(s)%s, %s. Folder: %s" % (
        res["id"], res["ended"], res["exit_code"], res["seconds"], res["audio"], len(res["markers"]), window,
        "alone on the machine" if not res["contended"] else "shared the machine with %d other game(s)" % len(res["shared_with"]),
        res["run_dir"])


# ---- commands' shared parts -----------------------------------------------------------------------------------------

def _start_watcher(id, n, proc, started, timeout, grace):
    """A detached run's watcher: this file again, `_watch`, with the game's handle inherited (so there is no moment in
    which the exit code could be missed). It writes result.json when the game ends, as a foreground run would."""
    h = _k32.OpenProcess(_SYNCHRONIZE | _QUERY, False, proc.pid)
    if not h:
        return None
    os.set_handle_inheritable(h, True)
    si = subprocess.STARTUPINFO()
    si.lpAttributeList = {"handle_list": [h]}
    argv = [sys.executable, "-I", os.path.abspath(__file__), "_watch", id, str(n), str(h), str(proc.pid), repr(started),
            "-" if timeout is None else repr(timeout), repr(grace)]
    try:
        return _popen(argv, slot_path(id), dict(os.environ), subprocess.DEVNULL, detached=True, startupinfo=si)
    except OSError:
        return None
    finally:
        os.set_handle_inheritable(h, False)
        _k32.CloseHandle(h)


def _watched_process(id, handle, pid):
    """The game as the watcher sees it: through the inherited handle when that really is the game's, else through a
    handle opened by the pid (checked to be a program of the slot `id`). None when the game has already ended, so the
    watcher never waits for something that is not there."""
    if _k32.GetProcessId(handle) == pid:
        return _HandleProc(handle, pid)
    h = _k32.OpenProcess(_SYNCHRONIZE | _QUERY, False, pid)
    if not h:
        return None
    image = image_path(pid) or ""
    if not _norm(image).startswith(_norm(slot_path(id)) + os.sep):
        _k32.CloseHandle(h)                  # the pid was given to another program in the meantime
        return None
    return _HandleProc(h, pid)


def _watch_cmd(argv):
    """`game.py _watch <id> <n> <handle> <pid> <started> <timeout> <grace>`: a detached run's watcher. It waits for
    the game and writes result.json, then ends: it never outlives its game."""
    try:
        id, n, handle, pid = check_id(argv[0]), int(argv[1]), int(argv[2]), int(argv[3])
        started, timeout, grace = float(argv[4]), (None if argv[5] == "-" else float(argv[5])), float(argv[6])
    except (IndexError, ValueError):
        raise GameError("_watch takes: <id> <n> <handle> <pid> <started> <timeout> <grace>")
    path = os.path.join(slot_path(id), "run-%d" % n, "result.json")
    proc = _watched_process(id, handle, pid)
    if proc is None:                         # the game ended before the watcher attached: nothing to wait for
        if not os.path.isfile(path):
            _json_write(path, {"id": id, "run": n, "pid": pid, "ended": "by itself", "exit_code": None,
                               "note": "the game had already ended when its watcher attached, so its exit code was not caught"})
        return
    try:
        watch(proc, started, id, n, timeout, grace, quiet=True)
    except BaseException as e:        # its output goes nowhere: the run folder must still say what happened
        if not os.path.isfile(path):
            with contextlib.suppress(OSError):
                _json_write(path, {"id": id, "run": n, "pid": pid, "ended": "watcher failed", "watch_error": repr(e)})
        if proc.poll() is None:
            proc.kill()
        raise


def run(id, env=None, scenario=None, mode="shared", wait=DEFAULT_WAIT, timeout=None, keep_profile=False, label=None,
        detach=False, grace=CLOSE_GRACE, real_profile=None, quiet=False):
    """Run the slot's game: refresh its profile from the real saves (unless keep_profile), wait for a turn, start the
    game. In the foreground it waits until the game exits or `timeout` seconds pass (then: a close request, a kill
    `grace` seconds later) and returns what result.json says. `detach` starts the game and a watcher and returns at
    once (pid, run_dir, ended "running"). Raises NoTurn when there is no turn within `wait` seconds (0: at once)."""
    rec = require_slot(id)
    if our_marker(id) is None:
        raise GameError("slot %s has no marker from %s (it was released, or another session holds its id): create it again" %
                        (id, TOOL))
    if not keep_profile:
        _dst, real, found = refresh_profile(id, real_profile)
        if not quiet:
            print("slot %s: profile %s" % (id, "refreshed from %s" % real if found else "kept (there is no real profile at %s)" % real),
                  flush=True)
    with admission(mode, wait, quiet=quiet) as turn:
        if not turn.ok:
            raise NoTurn(turn.why)
        started = time.time()
        proc, run_dir = launch(id, env, scenario=scenario, label=label, mode=mode, detach=detach, real_profile=real_profile)
    n = int(os.path.basename(run_dir).split("-")[1])
    if not quiet:
        print("run %s: pid %d, folder %s (label %s, %s)" % (id, proc.pid, run_dir, label or rec.get("label") or id, mode), flush=True)
    if detach:
        w = _start_watcher(id, n, proc, started, timeout, grace)
        if not quiet:
            print("   watcher %s" % ("pid %d" % w.pid if w else "could not start: this run gets no result.json"), flush=True)
        return {"id": id, "label": label or rec.get("label") or id, "run": n, "run_dir": run_dir, "pid": proc.pid,
                "started": datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds"), "detach": True,
                "watcher": w.pid if w else None, "ended": "running"}
    if timeout is not None and not quiet:
        print("   at most %s s, then a close request" % format(timeout, "g"), flush=True)
    return watch(proc, started, id, n, timeout, grace, quiet)


# ---- stop, release, clean, status -----------------------------------------------------------------------------------

def stop(id, grace=CLOSE_GRACE, quiet=False):
    """Close request (WM_CLOSE) to the slot's live game or games; kills them when they still run `grace` seconds
    later. Returns how the game ended, or None when none was live."""
    require_slot(id)
    live = slot_is_live(id)
    if not live:
        if not quiet:
            print("stop %s: no game is live in it" % id, flush=True)
        return None
    m = our_marker(id) or {}
    note = os.path.join(slot_path(id), "run-%s" % m["run"], "stop.json") if m.get("run") else None
    ended = None
    for pid in live:
        info = {"requested": now_iso(), "windows_asked": 0, "killed": False}
        if not quiet:
            print("stop %s: close request to pid %d; killed %s s later if it keeps running" %
                  (id, pid, format(grace, "g")), flush=True)
        h = _k32.OpenProcess(_SYNCHRONIZE | _QUERY | _TERMINATE, False, pid)
        if h:
            try:
                end = time.time() + grace
                while time.time() < end:                           # asked again every half second: a game that
                    info["windows_asked"] = request_close(pid)     # is still starting has no window yet
                    if _k32.WaitForSingleObject(h, 500) != _WAIT_TIMEOUT:
                        break                                      # it ended
                if _k32.WaitForSingleObject(h, 0) == _WAIT_TIMEOUT:
                    _k32.TerminateProcess(h, 1)
                    _k32.WaitForSingleObject(h, 5000)
                    info["killed"] = True
            finally:
                _k32.CloseHandle(h)
        if note:                   # the run that is watching this game reads it and records how the game ended
            with contextlib.suppress(OSError):
                _json_write(note, info)
        ended = "killed" if info["killed"] else "after a close request"
    if our_marker(id):
        write_marker(id, label=m.get("label"), exe=exe_path(id), start=m.get("start"), mode=m.get("mode"))
    if not quiet:
        print("stop %s: %s" % (id, ended), flush=True)
    return ended


def release(id, grace=CLOSE_GRACE, quiet=False):
    """Stop the slot's game if any and remove its marker: the id is given up, the files stay. Only a slot or a marker
    this tool made is released; another session's is left alone."""
    check_id(id)
    mine_slot, m = read_slot(id) is not None, read_marker(id)
    if not mine_slot and not (m and m.get("tool") == TOOL):
        raise GameError("slot %s and its marker were not made by %s: both are left alone (another session's)" % (id, TOOL))
    ended = stop(id, grace, quiet) if mine_slot else None
    if read_marker(id) is None:
        return {"stopped": ended, "released": False}
    m = read_marker(id)
    if m.get("tool") != TOOL:
        raise GameError("marker %s was not written by %s: it is left alone (another session's permit)" % (marker_path(id), TOOL))
    os.remove(marker_path(id))
    if not quiet:
        print("released %s: marker removed, files kept in %s" % (id, slot_path(id)), flush=True)
    return {"stopped": ended, "released": True}


def clean_targets(ids=None):
    """([slot folders clean may delete], [(id, why it is kept)]). Deleted: made by this tool (slot.json), no marker
    and no live game, run folders included. Marked or live slots are only listed; slots another tool made are never
    touched and not even listed."""
    live = live_games()
    live_ids = {slot for _p, _i, slot in live if slot}
    live_images = [_norm(image) + os.sep for _p, image, _s in live]
    try:
        names = list(ids) if ids is not None else sorted(os.listdir(runs_dir()))
    except OSError:
        names = list(ids) if ids is not None else []
    targets, kept = [], []
    for id in names:
        check_id(id)
        if read_slot(id) is None:
            continue
        slot = slot_path(id)
        if os.path.lexists(marker_path(id)):
            kept.append((id, "still marked (release it first)"))
        elif id in live_ids or any(image.startswith(_norm(slot) + os.sep) for image in live_images):
            kept.append((id, "a game is live in it"))
        elif os.path.isdir(slot):
            targets.append(slot)
    return targets, kept


def status():
    """Everything `status` prints: live games, slots with their markers, the shared places in use and whether an
    exclusive run may start now."""
    live = live_games()
    pids = {pid for pid, _i, _s in live}
    marks = {id: read_marker(id) for id in markers()}
    games = []
    for pid, image, slot in live:
        t = process_start(pid)
        titles = window_titles(pid)
        games.append({"slot": slot, "pid": pid, "label": (marks.get(slot) or {}).get("label") if slot else None, "image": image,
                      "title": titles[0] if titles else "", "seconds": None if t is None else int(time.time() - t),
                      "contended": len(live) > 1})
    slots = {}

    def entry(id):
        return slots.setdefault(id, {"id": id, "label": None, "ours": False, "marker": None, "marker_pid": None, "mode": None,
                                     "live": [], "runs": 0, "exe": None, "path": slot_path(id)})
    try:
        names = os.listdir(runs_dir())
    except OSError:
        names = []
    for id in names:
        if os.path.isdir(slot_path(id)):
            e, rec = entry(id), read_slot(id)
            e["ours"] = rec is not None
            if rec:
                e["label"], e["exe"], e["runs"] = rec.get("label"), rec["exe"]["source"], len(run_dirs(id))
    for id, m in marks.items():
        e = entry(id)
        e["marker"] = "ours" if m.get("tool") == TOOL else "another session's"
        e["label"] = e["label"] or m.get("label")
        e["marker_pid"] = int(m["pid"]) if m.get("pid", "").isdigit() else None
        e["mode"] = m.get("mode")
    for pid, _image, slot in live:
        if slot:
            entry(slot)["live"].append(pid)
    for e in slots.values():
        e["finished"] = e["ours"] and not e["marker"] and not e["live"]      # clean deletes it
    return {"root": root(), "runs_dir": runs_dir(), "state_dir": state_dir(), "used": len(live), "max_shared": MAX_SHARED,
            "live": games, "exclusive_live": exclusive_live(pids), "exclusive_allowed": not live,
            "slots": [slots[k] for k in sorted(slots)]}


# ---- command line ---------------------------------------------------------------------------------------------------

def parse_assign(text):
    key, sep, val = text.partition("=")
    if not sep or not key:
        raise GameError("%r must look like KEY=VALUE" % text)
    return key, val


def table(rows, header):
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    line = lambda r: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)).rstrip()
    return "\n".join([line(header), line(["-" * w for w in widths])] + [line(r) for r in rows])


def cut(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 3] + "..."


def cmd_create(a):
    rec = create(a.id, a.exe, a.support_dir, a.label, a.real_profile)
    st = rec["exe"]
    print("slot %s: made %s" % (a.id, slot_path(a.id)))
    print("   exe: %s (%d bytes) copied to %s" % (st["source"], st["size"], os.path.basename(exe_path(a.id))))
    print("   support files from %s: %s%s" % (rec["support"], ", ".join(rec["support_copied"]) or "none",
          "" if not rec["support_missing"] else "; not there: " + ", ".join(rec["support_missing"])))
    print("   profile: %s" % ("copied from %s" % rec["profile"]["real"] if rec["profile"]["real_found"]
                              else "empty (there is no real profile at %s)" % rec["profile"]["real"]))
    print("   label %s (the window title ends with [%s]); marker %s" % (rec["label"], rec["label"], marker_path(a.id)))
    return 0


def cmd_update(a):
    rec = update(a.id, a.exe, a.support_dir)
    st = rec["exe"]
    print("slot %s: exe %s (%s, %d bytes); support files copied again: %s" % (
        a.id, "changed" if rec["exe_changed"] else "unchanged", st["source"], st["size"],
        ", ".join(rec["support_copied"]) or "none"))
    return 0


def cmd_run(a):
    extra = dict(parse_assign(e) for e in a.env)
    wait = 0.0 if a.no_wait else (DEFAULT_WAIT if a.wait is None else a.wait)
    res = run(a.id, extra, scenario=a.scenario, mode=a.mode, wait=wait, timeout=a.timeout, keep_profile=a.keep_profile,
              label=a.label, detach=a.detach, grace=a.grace, real_profile=a.real_profile)
    if res.get("detach"):
        print("started: pid %d, folder %s" % (res["pid"], res["run_dir"]), flush=True)
        return 0
    return 0 if res["ended"] == "by itself" and res["exit_code"] == 0 else 1


def cmd_status(a):
    s = status()
    if a.json:
        print(json.dumps(s, indent=1))
        return 0
    live = s["live"]
    print("live games: %d of %d shared places used" % (s["used"], s["max_shared"]))
    rows = [[g["slot"] or "(outside a slot)", g["pid"], g["label"] or "-", cut(g["title"] or "-", 60),
             "-" if g["seconds"] is None else "%d s" % g["seconds"], "yes" if g["contended"] else "no"] for g in live]
    print(table(rows, ["slot", "pid", "label", "window title", "running", "contended"]) if rows else "  none")
    if s["exclusive_live"]:
        print("an exclusive (timing) run is live in %s: ordinary runs wait for it" % ", ".join(s["exclusive_live"]))
    print("exclusive run allowed now: %s" % ("yes" if s["exclusive_allowed"] else "no (%d game(s) live)" % s["used"]))
    print("\nslots in %s, markers in %s:" % (s["runs_dir"], s["state_dir"]))
    rows = []
    for e in s["slots"]:
        mark = e["marker"] or "none"
        if e["marker"] == "ours":
            mark += ", pid %s" % e["marker_pid"] if e["marker_pid"] else ", no live run"
        rows.append([e["id"], e["label"] or "-", TOOL if e["ours"] else "another tool", mark,
                     ",".join(str(p) for p in e["live"]) or "-", e["runs"], "yes" if e["finished"] else ""])
    print(table(rows, ["slot", "label", "made by", "marker", "live pid", "runs", "finished (clean deletes)"]) if rows else "  none")
    return 0


def cmd_stop(a):
    stop(a.id, a.grace)
    return 0


def cmd_release(a):
    release(a.id, a.grace)
    return 0


def cmd_clean(a):
    if not a.id and not a.all_finished:
        raise GameError("give --id ID or --all-finished")
    ids = [a.id] if a.id else None
    if a.id:
        check_id(a.id)
        if read_slot(a.id) is None:
            raise GameError("slot %s was not made by %s (or does not exist): nothing is deleted" % (a.id, TOOL))
    targets, kept = clean_targets(ids)
    for p in targets:
        size = sum(os.path.getsize(os.path.join(b, n)) for b, _d, ns in os.walk(p) for n in ns)
        print("%sdelete %s (%.1f MB)" % ("[dry-run] " if a.dry_run else "", p, size / 1e6))
    for id, why in kept:
        print("%skeep %s: %s" % ("[dry-run] " if a.dry_run else "", slot_path(id), why))
    if not a.dry_run:
        for p in targets:
            shutil.rmtree(p)
    print("%s %d slot(s)%s" % ("would delete" if a.dry_run else "deleted", len(targets),
                               "" if not kept else ", kept %d (%s)" % (len(kept), ", ".join(id for id, _w in kept))))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="python -I tools/game.py", description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="a new slot and its marker; refuses an id that exists")
    c.add_argument("id")
    c.add_argument("--exe", help="the game exe to copy (default work/build/mlb.exe, or MLB_GAME_EXE)")
    c.add_argument("--support-dir", help="where the files the game needs beside its exe come from (default work/build)")
    c.add_argument("--label", help="the run's name: MLB_RUN_LABEL, so the window title ends with [label] (default the id)")
    c.add_argument("--real-profile", help="the profile whose saves are copied into the slot (default work/build/profile)")
    c.set_defaults(fn=cmd_create)
    u = sub.add_parser("update", help="put the exe into an existing slot when it differs; copy changed support files")
    u.add_argument("id")
    u.add_argument("--exe", help="the game exe (default: the one the slot was made from)")
    u.add_argument("--support-dir", help="default: the folder the slot was made from")
    u.set_defaults(fn=cmd_update)
    r = sub.add_parser("run", help="run the slot's game in a turn (shared by default), then wait for it")
    r.add_argument("id")
    r.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                   help="a setting for the game (repeatable); it wins over the ones run sets")
    r.add_argument("--scenario", help="a scenario file: MLB_HARNESS=<file>; its dumps go to <run folder>/dumps")
    r.add_argument("--mode", choices=("shared", "exclusive"), default="shared",
                   help="shared: start with fewer than 3 games live (default); exclusive: only with no game live (timing runs)")
    w = r.add_mutually_exclusive_group()
    w.add_argument("--no-wait", action="store_true", help="exit with status 2 at once when the run cannot start now")
    w.add_argument("--wait", type=float, metavar="SECONDS", help="how long to wait for a turn (default %d)" % DEFAULT_WAIT)
    r.add_argument("--timeout", type=float, metavar="SECONDS",
                   help="stop the game after this long: a close request, then a kill --grace seconds later")
    r.add_argument("--keep-profile", action="store_true",
                   help="do not copy the real saves into the slot again: go on from the saves the slot has")
    r.add_argument("--detach", action="store_true", help="start the game and return at once; a watcher writes result.json")
    r.add_argument("--label", help="MLB_RUN_LABEL for this slot (default the slot's label, else its id)")
    r.add_argument("--grace", type=float, default=CLOSE_GRACE, help="seconds between a close request and the kill (default %(default)s)")
    r.add_argument("--real-profile", help="the profile whose saves are copied into the slot (default work/build/profile)")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("status", help="live games, slots and markers, free places")
    s.add_argument("--json", action="store_true", help="the same as JSON")
    s.set_defaults(fn=cmd_status)
    t = sub.add_parser("stop", help="close request to the slot's live game; kills it after the grace period")
    t.add_argument("id")
    t.add_argument("--grace", type=float, default=CLOSE_GRACE, help="seconds between the close request and the kill (default %(default)s)")
    t.set_defaults(fn=cmd_stop)
    e = sub.add_parser("release", help="stop its game if any and remove the marker; the files stay")
    e.add_argument("id")
    e.add_argument("--grace", type=float, default=CLOSE_GRACE, help="seconds between the close request and the kill (default %(default)s)")
    e.set_defaults(fn=cmd_release)
    k = sub.add_parser("clean", help="delete finished slots this tool made (no marker, no live game); never anything else")
    g = k.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", help="one slot")
    g.add_argument("--all-finished", action="store_true", help="every finished slot this tool made")
    k.add_argument("--dry-run", action="store_true", help="print what would go; delete nothing")
    k.set_defaults(fn=cmd_clean)
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["_watch"]:                  # the detached run's watcher, started by run --detach: not a command
        try:
            _watch_cmd(argv[1:])
            return 0
        except GameError as e:
            print("ERROR: %s" % e, flush=True)
            return 2
        except KeyboardInterrupt:
            return 2
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except NoTurn as e:
        print("cannot start now: %s" % e, flush=True)
        return 2
    except GameError as e:
        print("ERROR: %s" % e, flush=True)
        return 2
    except KeyboardInterrupt:
        print("interrupted; the game was stopped")
        return 2


if __name__ == "__main__":
    sys.exit(main())
