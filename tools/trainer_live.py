"""Live check of the in-game trainer (stage 1) on a running AI-vs-AI match.

    python -I tools/game.py create trainer --exe <build>/mlb.exe
    python -I tools/trainer_live.py [--slot trainer]

Needs game/romfs/BOOT/CONFIG_MAIN_USER.TXT with AIvAI and GameOnly. The run is hidden with a fake audio device. The
trainer is driven by MLB_TRAINER_TEST (dev builds); the checks use the trainer's own read-back lines in mlb.log and,
from outside the game, tools/scenario.py's memory reader. Prints one line per check; exit code = failed checks.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import game  # noqa: E402
import scenario as sc  # noqa: E402

SAVED = dict(away=4, home=3, balls=3, strikes=2, outs=1)
# frames after the trainer first reads a match; play is under way well before SET_AT
SHOW_AT, SET_AT, SAVE_AT, REPLAY_AT, REPLAYS, JUMP_AT = 2800, 3000, 3150, 3300, 5, 4900
failed = 0


def check(ok, text):
    global failed
    failed += not ok
    print("PASS" if ok else "FAIL", text, flush=True)


def commands(jumps):
    c = ["%d:show" % SHOW_AT]
    c += ["%d:set %s %d" % (SET_AT, k, v) for k, v in SAVED.items()]
    c.append("%d:save 1" % SAVE_AT)
    for n in range(REPLAYS):
        at = REPLAY_AT + 300 * n
        c += ["%d:set %s 0" % (at, k) for k in SAVED]
        c.append("%d:load 1" % (at + 100))
    c += ["%d:jump %d" % j for j in jumps]
    return ";".join(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="trainer")
    # one jump a run: it waits for real outs, and a second request replaces the first. From the match's start (half 0,
    # side 1) an even target takes one extra change of sides first, an odd one goes straight: run both.
    ap.add_argument("--jump", type=int, default=2, help="the half-inning index to jump to")
    ap.add_argument("--timeout", type=int, default=800)
    a = ap.parse_args()
    jumps = ((JUMP_AT, a.jump),)
    env = ["MLB_TRAINER=1", "TOTK_HIDDEN_WINDOW=1", "TOTK_AUDIO=paced", "MLB_SHOT=" + ",".join(str(f) for f in range(4000, 12001, 800)),
           "MLB_TRAINER_TEST=" + commands(jumps)]
    argv = [sys.executable, "-I", os.path.join(HERE, "game.py"), "run", a.slot, "--timeout", str(a.timeout)]
    for e in env:
        argv += ["--env", e]
    saved_file = os.path.join(game.slot_path(a.slot), "profile", "trainer.txt")
    if os.path.isfile(saved_file):   # an earlier run's slot would pass the file check by itself
        os.remove(saved_file)
    before = set(game.run_dirs(a.slot))
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL)
    g, log, arrived = None, "", {}
    deadline = time.time() + a.timeout
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
        new = sorted(set(game.run_dirs(a.slot)) - before, key=str)
        if not new:
            continue
        path = os.path.join(new[-1][1], "mlb.log")
        if os.path.isfile(path):
            log = open(path, encoding="utf-8", errors="replace").read()
        if g is None:
            pid = sc.find_pid("mlb_" + a.slot)
            g = sc.Game(pid) if pid else None
        if g is None:
            continue
        for at, half in jumps:
            if half in arrived or "test +%d: jump %d" % (at, half) not in log:
                continue
            try:
                if sc.state(g)["half_index"] == half:
                    time.sleep(4)
                    arrived[half] = (sc.state(g)["half_index"], sc.side_byte(g))
                    print("outside reader at half index %d: %s" % (half, sc.state(g)), flush=True)
            except RuntimeError:
                pass
        if len(arrived) == len(jumps):
            time.sleep(60)   # the match plays on
            check(g.alive() is not None, "the game is still running 60 s after the last jump")
            break
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "game.py"), "stop", a.slot], stdout=subprocess.DEVNULL)
    proc.wait(60)

    check("audout: no output device" not in log, "the log has an audio output")
    check("FATAL" not in log, "no FATAL line in the log")
    back = [(m[1], int(m[2]), int(m[3]), m.start())
            for m in re.finditer(r"trainer: (\w+) = (\d+), read back (\d+)", log)]
    check(len(back) >= len(SAVED) * (1 + 2 * REPLAYS), "%d read-back lines" % len(back))
    wrong = [b[:3] for b in back if b[1] != b[2]]
    check(not wrong, "every read-back equals the value written (mismatches: %s)" % wrong[:6])
    check("trainer: slot 1 saved" in log, "slot 1 saved")
    slot = glob.glob(os.path.join(str(game.slot_path(a.slot)), "profile", "trainer.txt"))
    text = open(slot[0]).read().split() if slot else []
    got = [int(x) for x in text[2:7]]
    check(got == [SAVED[k] for k in ("away", "home", "balls", "strikes", "outs")], "trainer.txt holds %s" % got)
    good = 0
    for n in range(REPLAYS):
        mark = log.find("test +%d: load 1" % (REPLAY_AT + 300 * n + 100))
        seen = {}
        for name, want, read, pos in back:
            if mark >= 0 and pos > mark and name not in seen:
                seen[name] = read
        good += all(seen.get(k) == v for k, v in SAVED.items())
    check(good == REPLAYS, "replay restored the saved values %d of %d times" % (good, REPLAYS))
    for _, half in jumps:
        at = arrived.get(half)
        check(at is not None and at[0] == half and at[1] == sc.expected_side(half),
              "jump to half index %d: (index, batting side) = %s, expected side %d" % (half, at, sc.expected_side(half)))
    print("%d failed; log in the slot's newest run folder" % failed)
    return failed


if __name__ == "__main__":
    sys.exit(main())
