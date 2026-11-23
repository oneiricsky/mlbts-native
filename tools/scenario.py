"""Put a running game (1.0.20) into a chosen match situation from a scenario file.

    python -I tools/scenario.py SCENARIO.txt [--exe mlb_scenario_search] [--verify 60]

Start the game yourself first (AIvAI + GameOnly in BOOT/CONFIG_MAIN_USER.TXT), from a run slot, with its own profile.
The tool attaches by process name (without .exe), waits for the match settings block, writes the teams, then applies the
situation and prints one line per field with the value read back. Scenario file: `key = value` lines, `#` comments.

    home = 0            team id 0..29 (0 BAL ... 27 LAD ... 29 SF); default stays as the game made it
    away = 1            CAUTION: this changes the stadium and the uniforms only. The players, lineups and scoreboard
                        names were loaded at boot for the default teams (LAD home, TOR away) and do not change.
    inning = 9          1..
    half = bottom       top | bottom
    away_score = 4
    home_score = 3
    outs = 2            0..2
    balls = 3           0..3
    strikes = 2         0..2
    runners = ...       NOT APPLIED: the real runner storage is not found yet (see work notes); logged as a warning

How the half-inning is set: writing the half-inning counter mid-play leaves the old team batting. So the tool writes
(target - 1) with 2 outs and lets the game make the next out and the transition itself, then writes outs, count and
scores. Give scores that do not end the game at that transition. Offsets are for game 1.0.20 (main + 0x227e6b8 count
object, + 0x4651350 settings block, + 0x3aebb60 play-by-play); a 1.0.15 build needs `tools/addrmap.py`.
"""
import argparse
import ctypes
import ctypes.wintypes as W
import struct
import subprocess
import sys
import time

BASE = 0x7000000000
COUNT_PTR, SETTINGS_PTR, LOG_PTR = BASE + 0x227E6B8, BASE + 0x4651350, BASE + 0x3AEBB60
HOME_COPIES, AWAY_COPIES = (0x3F, 0x47, 0x59), (0x40, 0x52, 0x54, 0x56)
K = ctypes.WinDLL("kernel32", use_last_error=True)
K.OpenProcess.restype = W.HANDLE
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
K.WriteProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def find_pid(name):
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        p = [x.strip('"') for x in line.split('","')]
        if len(p) > 1 and p[0].lower() == name.lower() + ".exe":
            return int(p[1])
    return None


class Game:
    def __init__(self, pid):
        self.pid, self.h = pid, K.OpenProcess(0x1F0FFF, False, pid)

    def rd(self, a, n):
        b = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        K.ReadProcessMemory(self.h, a, b, n, ctypes.byref(got))
        return b.raw[: got.value] if got.value == n else None

    def wr(self, a, data):
        got = ctypes.c_size_t()
        return bool(K.WriteProcessMemory(self.h, a, data, len(data), ctypes.byref(got)))

    def u32(self, a):
        b = self.rd(a, 4)
        return struct.unpack("<I", b)[0] if b else None

    def u64(self, a):
        b = self.rd(a, 8)
        return struct.unpack("<Q", b)[0] if b else 0

    def alive(self):
        return find_pid_by_pid(self.pid)

    def counts_obj(self):
        g = self.u64(COUNT_PTR)
        return self.u64(g) if g else 0

    def log_count(self):
        p = self.u64(LOG_PTR)
        return self.u32(p + 0x6A0) if p else 0

    def last_entry(self):
        p = self.u64(LOG_PTR)
        n = self.u32(p + 0x6A0) if p else 0
        arr = self.u64(p + 0x6A8) if p else 0
        if not n or not arr:
            return None
        r = self.rd(arr + (n - 1) * 0x1B4, 0x1B4)
        return None if r is None else dict(n=n, inning=r[9], half="top" if r[0xA] == 1 else "bottom", outs=r[0xD], balls=r[0xE], strikes=r[0xF])


def find_pid_by_pid(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def read_scenario(path):
    sc = {}
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if "=" in line:
            k, v = (x.strip() for x in line.split("=", 1))
            sc[k] = v
    return sc


def state(g):
    o = g.counts_obj()
    d = struct.unpack("<12I", g.rd(o, 0x30))
    return dict(away_score=d[2], home_score=d[3], balls=d[4], strikes=d[5], outs=d[6], half_index=d[8],
                inning=d[8] // 2 + 1, half="bottom" if d[8] & 1 else "top")


def put(g, off, val):
    g.wr(g.counts_obj() + off, struct.pack("<I", val))


RUNNER_SETS = {"": [], "first": ["first"], "first,second": ["first", "second"], "first,second,third": ["first", "second", "third"]}


def norm_runners(spec):
    spec = spec.strip().lower().replace(" ", "")
    if spec in ("none", ""):
        return ""
    if spec in ("loaded", "basesloaded"):
        return "first,second,third"
    return ",".join(x for x in ("first", "second", "third") if x in spec.split(","))


def occupied(g):
    o = g.counts_obj()
    return [n for n, off in (("first", 0x19C), ("second", 0x1AC), ("third", 0x1BC)) if g.u32(o + off) != 0xFFFFFFFF]


def apply_runners(g, spec):
    """Runners come from the game itself: forcing 3-0 counts makes the next pitch a walk, which puts a batter on first and
    pushes the others along. Only none, first, first+second and bases loaded can be made this way."""
    key = norm_runners(spec)
    if key not in RUNNER_SETS or (spec.strip().lower().replace(" ", "").split(",") != key.split(",") and key != "" and
                                  spec.strip().lower() not in ("loaded", "basesloaded")):
        log("WARNING runners =", spec, "not supported (only none, first, first,second, first,second,third / loaded)")
        return False
    need = len(RUNNER_SETS[key])
    if need == 0 and not occupied(g):
        return True
    t0 = time.time()
    while time.time() - t0 < 240:
        if not g.alive():
            return False
        have = len(occupied(g))
        if have == need:
            log("runners", key or "none", "reached after %.0f s" % (time.time() - t0))
            return True
        if have > need:
            log("WARNING too many runners (%d) for %s; cannot remove them" % (have, key))
            return False
        o = g.counts_obj()
        if g.u32(o + 0x10) != 3 or g.u32(o + 0x14) != 0 or g.u32(o + 0x18) != 0:
            put(g, 0x18, 0)
            put(g, 0x10, 3)
            put(g, 0x14, 0)
        time.sleep(0.3)
    log("WARNING runners not reached in 120 s")
    return False


def half_index_of(sc):
    if "inning" in sc or "half" in sc:
        return (int(sc.get("inning", 1)) - 1) * 2 + (1 if sc.get("half", "top") == "bottom" else 0)
    return None


def apply_one(g, sc, a, watch):
    """Apply one scenario to the live game, print a line per field, then watch the match for `watch` seconds."""
    name = sc.get("name", "scenario")
    log("=== scenario", name)
    for k in sc:
        if k not in KNOWN_KEYS:
            log("WARNING unknown key", k)
    for key, off in (("away_score", 0x8), ("home_score", 0xC)):
        if key in sc:
            put(g, off, int(sc[key]))
    want_half_index = half_index_of(sc)
    if want_half_index is not None:
        cur = state(g)["half_index"]
        if want_half_index < cur:
            log("ERROR: cannot go back from half-inning %d to %d; put the scenarios in order" % (cur, want_half_index))
            return False
        if want_half_index > cur:
            put(g, 0x20, want_half_index - 1)
            put(g, 0x18, 2)
            log("half-inning index set to", want_half_index - 1, "with 2 outs; waiting for the game's own transition")
            t0 = time.time()
            while time.time() - t0 < a.transition_timeout and state(g)["half_index"] != want_half_index:
                if not g.alive():
                    log("ERROR: the game exited during the transition")
                    return False
                time.sleep(0.2)
            log("transition", "seen" if state(g)["half_index"] == want_half_index else "NOT seen", "after %.0f s" % (time.time() - t0))
            time.sleep(2.5)
    if "runners" in sc:
        apply_runners(g, sc["runners"])
    for key, off in (("outs", 0x18), ("balls", 0x10), ("strikes", 0x14), ("away_score", 0x8), ("home_score", 0xC)):
        if key in sc:
            put(g, off, int(sc[key]))
    time.sleep(0.25)   # FastPlay pitches every few seconds: read back before the game moves on
    st = state(g)
    ok = True
    for key in ("away_score", "home_score", "outs", "balls", "strikes", "inning", "half"):
        if key in sc:
            got = st[key]
            want = int(sc[key]) if key != "half" else sc[key]
            same = got == want
            ok &= same
            log("FIELD %-11s want %-6s got %-6s %s" % (key, want, got, "OK" if same else "MISMATCH"))
    if "runners" in sc:
        occ = occupied(g)
        want = RUNNER_SETS.get(norm_runners(sc["runners"]))
        same = want is not None and occ == want
        ok &= same
        log("FIELD %-11s want %-6s got %-6s %s" % ("runners", sc["runners"], ",".join(occ) or "none", "OK" if same else "MISMATCH"))
    n0 = g.log_count()
    t0 = time.time()
    while time.time() - t0 < watch and g.alive():
        time.sleep(1)
    log("play-on check: alive=%s after %d s; log entries %d -> %d; last entry %s" % (g.alive(), watch, n0, g.log_count(), g.last_entry()))
    ok &= g.alive()
    log("RESULT", name, "PASS" if ok else "FAIL")
    return ok


KNOWN_KEYS = {"home", "away", "inning", "half", "away_score", "home_score", "outs", "balls", "strikes", "runners", "name"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", nargs="+", help="one or more scenario files, in increasing half-inning order")
    ap.add_argument("--exe", default="mlb_scenario_search", help="process name without .exe")
    ap.add_argument("--verify", type=int, default=60, help="seconds to watch the match after the LAST scenario")
    ap.add_argument("--verify-each", type=int, default=10, help="seconds to watch after each earlier scenario")
    ap.add_argument("--transition-timeout", type=int, default=150)
    a = ap.parse_args()
    scs = [read_scenario(p) for p in a.scenario]
    pid = None
    t0 = time.time()
    while not pid and time.time() - t0 < 120:
        pid = find_pid(a.exe)
        time.sleep(0.5)
    if not pid:
        log("ERROR: no running", a.exe)
        return 2
    g = Game(pid)
    log("attached to", a.exe, "pid", pid)
    while True:
        if not g.alive():
            log("ERROR: the game exited before the match settings were filled")
            return 2
        s = g.u64(SETTINGS_PTR)
        b = g.rd(s, 0x100) if s else None
        if b and b[0xFF] == 1 and b[0x3F] == 27:
            break
        time.sleep(0.2)
    g.wr(s + 0x7A, bytes([1]))           # QuickCounts
    g.wr(s + 0xEC + 0x26, bytes([1]))    # presentation mode 1 = Fast Play
    first = scs[0]
    for key, copies in (("home", HOME_COPIES), ("away", AWAY_COPIES)):
        if key in first:
            for c in copies:
                g.wr(s + c, bytes([int(first[key])]))
            log("team", key, "=", first[key], "(stadium and uniforms only, not the players) written to", len(copies), "copies; read back", [g.rd(s + c, 1)[0] for c in copies])
    for sc in scs[1:]:
        for key in ("home", "away"):
            if key in sc and sc[key] != first.get(key):
                log("WARNING", sc.get("name", "?"), key, "differs from the first scenario: teams are set once, at the start; ignored")
    while not (g.counts_obj() and g.log_count() >= 1):
        if not g.alive():
            log("ERROR: the game exited before the match went live")
            return 2
        time.sleep(0.5)
    time.sleep(6)
    log("match is live; start state", state(g))
    results = []
    for i, sc in enumerate(scs):
        results.append(apply_one(g, sc, a, a.verify if i == len(scs) - 1 else a.verify_each))
        if not g.alive():
            break
    log("SUMMARY", "%d of %d scenarios passed" % (sum(results), len(scs)))
    return 0 if all(results) and len(results) == len(scs) else 1


if __name__ == "__main__":
    sys.exit(main())
