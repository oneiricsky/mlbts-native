#!/usr/bin/env python3
"""The real check of tools/game.py, with the real game. About 1 minute of game time.

  python -I tools/test_game_real.py [--exe PATH] [--keep]

1. One run of 20 s in a fresh slot (a scenario stops the game): exit code 0, the log has the boot marker, audio is
   on, and the window title read from the operating system ends with [<id>].
2. Two such runs at once, in two slots: both stop by themselves, with two logs and two profiles, each window titled
   with its own label.
3. While those two run: a third slot asking for an exclusive turn without waiting exits with status 2, and a third
   shared run without waiting either starts or is refused, depending on whether another session's game is live
   (it counts as one of the three places). Which one happened is printed.
4. A game stopped by `stop` while it runs: it is asked to close and ends by that.
Then the real profile is compared with what it held before: a slot run never writes it.

Every run's result.json, game.log, game.out and env.json are copied to --evidence (default work/scratch/gamepy-real)
and the slots are released and deleted (--keep leaves them). Exit status: 0 every check passed, 1 one failed, 2 the
check could not run."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("game", os.path.join(HERE, "game.py"))   # -I: load by path
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
IDS = ("real-1", "real-2", "real-3", "real-4")
PROBE = "real-probe"


class BG(threading.Thread):
    def __init__(self, fn, *a, **k):
        super().__init__(daemon=True)
        self.fn, self.a, self.k = fn, a, k
        self.result = self.error = None

    def run(self):
        try:
            self.result = self.fn(*self.a, **self.k)
        except BaseException as e:
            self.error = e


def profile_hashes():
    """The real profile's saves, as they are now."""
    out = {}
    real = g.real_profile_dir()
    for it in g.PROFILE_ITEMS:
        p = os.path.join(real, it)
        if os.path.isdir(p):
            for base, _d, names in os.walk(p):
                for n in names:
                    f = os.path.join(base, n)
                    out[os.path.relpath(f, real)] = hashlib.sha256(open(f, "rb").read()).hexdigest()
        elif os.path.isfile(p):
            out[it] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def scenario(id, seconds):
    path = os.path.join(g.slot_path(id), "check.scn")
    with open(path, "w") as f:
        f.write("name = %s\nstop_after_s = %d\n" % (id, seconds))
    return path


def wait_until(fn, timeout, what):
    """Runs fn() every half second until it gives something other than None (max `timeout` s); prints what it got."""
    t0, got = time.time(), None
    while time.time() - t0 < timeout and (got := fn()) is None:
        time.sleep(0.5)
    print("   %s after %.1f s: %s" % (what, time.time() - t0, got), flush=True)
    return got


def started(id):
    m = g.read_marker(id) or {}
    return int(m["pid"]) if m.get("pid", "").isdigit() and g.slot_is_live(id) else None


def both_live():
    p2, p3 = started("real-2"), started("real-3")
    return [p2, p3] if p2 and p3 else None


def cli(*args):
    p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "game.py"), *args], capture_output=True, text=True,
                       timeout=120, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


def copy_evidence(res, where):
    dst = os.path.join(where, "%s-run-%d" % (res["id"], res["run"]))
    os.makedirs(dst, exist_ok=True)
    for name in ("result.json", "game.out", "env.json", "game.log"):
        src = os.path.join(res["run_dir"], name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--exe", help="the game (default work/build/mlb.exe, or MLB_GAME_EXE)")
    ap.add_argument("--evidence", default=os.path.join(g.root(), "work", "scratch", "gamepy-real"))
    ap.add_argument("--keep", action="store_true", help="leave the slots (about 170 MB each) instead of deleting them")
    a = ap.parse_args(argv)
    exe = os.path.abspath(a.exe or g.default_exe())
    ids = list(IDS) + [PROBE]
    taken = [id for id in ids if os.path.exists(g.slot_path(id)) or os.path.exists(g.marker_path(id))]
    if not os.path.isfile(exe) or taken:
        print("cannot run: %s" % ("no game exe at %s" % exe if not os.path.isfile(exe) else "slot(s) taken: " + ", ".join(taken)))
        return 2
    checks, results = [], []
    t_start = time.time()

    def check(ok, text):
        checks.append(bool(ok))
        print("%s %s" % ("PASS" if ok else "FAIL", text), flush=True)

    before = profile_hashes()
    for id in ids:
        g.create(id, exe=exe)                                      # fresh slots, so each first run pays for the caches
    threads = []
    try:
        # 1. one run
        print("1. one run of 20 s in slot real-1", flush=True)
        r1 = g.run("real-1", scenario=scenario("real-1", 20), wait=120)
        results.append(r1)
        check(r1["exit_code"] == 0 and r1["ended"] == "by itself", "1. exit code %s, ended %s, %.1f s" % (r1["exit_code"], r1["ended"], r1["seconds"]))
        log = open(r1["log"], encoding="utf-8", errors="replace").read() if r1["log"] else ""
        check("[host] harness: marker boot" in log, "1. the log has '[host] harness: marker boot'")
        check(r1["audio"] == "ok", "1. audio %s" % r1["audio"])
        check((r1["window_title"] or "").endswith("[real-1]"), "1. window title %r (visible: %s)" % (r1["window_title"], r1["window_visible"]))
        # 2. two runs at once
        print("2. two runs of 20 s at once, in real-2 and real-3", flush=True)
        for id in ("real-2", "real-3"):
            threads.append(BG(g.run, id, scenario=scenario(id, 20), wait=120))
        for t in threads:
            t.start()
        t_two = time.time()
        pids = wait_until(both_live, 130, "both games live (pids)")       # they wait first when 3 games are already live
        live = g.live_games()
        others = [e for e in live if e[2] not in ("real-2", "real-3")]
        print("   live on the machine now: %d (%s)" % (len(live), ", ".join("%s pid %d" % (e[2] or os.path.basename(e[1]), e[0]) for e in live)), flush=True)
        check(pids is not None, "2. two games live at once (pids %s), %.1f s after they were asked for" % (pids, time.time() - t_two))
        if pids is None:
            raise RuntimeError("the two games did not both start: step 3 needs them running")
        mine = [(int(g.read_marker("real-2")["pid"]), "", "real-2"), (int(g.read_marker("real-3")["pid"]), "", "real-3")]
        check(all(any(e[0] == m[0] for e in live) for m in mine), "2. both of them are in the process list, with their slots: %s" % [e[2] for e in live if e[2] in ("real-2", "real-3")])
        # 3. a third turn while two run
        code, out = cli("run", PROBE, "--mode", "exclusive", "--no-wait")
        check(code == 2 and "cannot start now" in out, "3. a third slot, exclusive, without waiting: exit status %s (%s)" % (
            code, out.strip().splitlines()[-1] if out.strip() else ""))
        code, out = cli("run", PROBE, "--no-wait", "--detach", "--scenario", scenario(PROBE, 6), "--timeout", "60")
        if code == 0:
            folder = [ln for ln in out.splitlines() if "folder" in ln][-1].split("folder", 1)[1].strip()
            path = os.path.join(folder, "result.json")
            wait_until(lambda: path if os.path.isfile(path) else None, 90, "the third run's result")
            r = json.load(open(path, encoding="utf-8"))
            results.append(r)
            check(True, "3. a third shared run without waiting, while real-2 and real-3 run: STARTED (%d other game(s) live besides them: %s); it ended %s with exit code %s after %.1f s" % (
                len(others), "none" if not others else ", ".join(e[2] or "?" for e in others), r["ended"], r["exit_code"], r["seconds"]))
        else:
            check(code == 2, "3. a third shared run without waiting, while real-2 and real-3 run: REFUSED, exit status %s (%s); %d other game(s) live besides them: %s" % (
                code, out.strip().splitlines()[-1] if out.strip() else "", len(others), "none" if not others else ", ".join(e[2] or "?" for e in others)))
        for t in threads:
            t.join(150)
        r2, r3 = threads[0].result, threads[1].result
        results += [r for r in (r2, r3) if r]
        ok = all(t.error is None for t in threads) and r2 is not None and r3 is not None
        check(ok, "2. both stopped by themselves: %s" % "; ".join("%s exit code %s, %s, %.1f s, audio %s" % (r["id"], r["exit_code"], r["ended"], r["seconds"], r["audio"]) for r in (r2, r3) if r) if ok else threads[0].error or threads[1].error)
        if ok:
            logs = [hashlib.sha256(open(r["log"], "rb").read()).hexdigest() for r in (r2, r3)]
            check(logs[0] != logs[1], "2. two different logs (%s and %s bytes)" % tuple(os.path.getsize(r["log"]) for r in (r2, r3)))
            check(all(r["window_title"] and r["window_title"].endswith("[%s]" % r["id"]) for r in (r2, r3)),
                  "2. window titles %r" % [r["window_title"] for r in (r2, r3)])
            check(r2["shared_with"] and r3["shared_with"], "2. each run saw the other as live on the machine (contended: %s, %s)" % (r2["contended"], r3["contended"]))
        profs = [os.path.join(g.slot_path(id), "profile") for id in ("real-2", "real-3")]
        check(profs[0] != profs[1] and all(os.path.isdir(os.path.join(p, "save")) for p in profs), "2. two profiles: %s" % " and ".join(profs))
        # 4. a game stopped by `stop`
        print("4. a longer run in real-4, stopped with stop once its window is there", flush=True)
        t4 = BG(g.run, "real-4", scenario=scenario("real-4", 120), wait=120, timeout=90)
        threads.append(t4)
        t4.start()
        t_live = time.time()
        pid = wait_until(lambda: started("real-4"), 60, "the game is live (pid)")
        check(pid is not None, "4. a longer run is live")
        asked_at = time.time() - t_live
        ended = g.stop("real-4", grace=30)                 # asked at once: before the game's own window exists
        t4.join(60)
        r4 = t4.result
        check(r4 is not None and ended == "after a close request" and r4["ended"] == "after a close request",
              "4. stop asked %.1f s after launch (the game's own window is not there yet): the game %s, %.1f s after launch, exit code %s, window %r" % (
                  asked_at, ended, time.time() - t_live, r4 and r4["exit_code"], r4 and r4["window_title"]))
        if r4:
            results.append(r4)
        after = profile_hashes()
        check(before == after, "the real profile is as it was: %d file(s), %s" % (len(after), "same hashes" if before == after else "CHANGED"))
    finally:
        for id in ids:
            try:
                if g.read_slot(id) is not None:
                    g.stop(id, grace=5, quiet=True)
                    g.release(id, quiet=True)
            except Exception as e:      # the report must still come out
                print("cleanup of %s: %s" % (id, e))
        for t in threads:
            t.join(20)
        os.makedirs(a.evidence, exist_ok=True)
        for r in results:
            copy_evidence(r, a.evidence)
        if not a.keep:
            for id in ids:
                try:
                    for p in g.clean_targets([id])[0]:
                        shutil.rmtree(p)
                except Exception as e:
                    print("clean of %s: %s" % (id, e))
    print("%s: %d of %d checks passed in %.0f s. Evidence: %s" % ("PASS" if checks and all(checks) else "FAIL",
          sum(checks), len(checks), time.time() - t_start, a.evidence), flush=True)
    return 0 if checks and all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
