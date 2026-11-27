"""Live check of the trainer's hooks (batted-ball readout and the pitcher's energy) on a running AI-vs-AI match.

    python -I tools/game.py create trainer --exe <build with the trainer patch sets>/mlb.exe
    python -I tools/trainer_live_hooks.py [--slot trainer]

The build needs code generated with tools/data/patches-1.0.20.txt (sets trainer_contact, trainer_pitch). The run
watches a few pitches, holds the pitcher's energy, then releases it. If the game reads the held value, energy carries
on from it after the release; if only a copy was held, it falls straight back to where it would have been. Checks come
from the trainer's own log lines. One line per check; exit code = failed checks.
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import game  # noqa: E402

# frames after the trainer first reads a match
SHOW, HOLD, RELEASE, END = 2800, 5000, 12000, 15000
failed = 0


def check(ok, text):
    global failed
    failed += not ok
    print("PASS" if ok else "FAIL", text, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="trainer")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    cmds = ["%d:show" % SHOW, "%d:freeze 1" % HOLD, "%d:freeze 0" % RELEASE, "%d:hide" % END]
    env = ["MLB_TRAINER=1", "TOTK_HIDDEN_WINDOW=1", "TOTK_AUDIO=paced",
           "MLB_SHOT=" + ",".join(str(f) for f in range(8000, 30001, 1000)), "MLB_TRAINER_TEST=" + ";".join(cmds)]
    argv = [sys.executable, "-I", os.path.join(HERE, "game.py"), "run", a.slot, "--timeout", str(a.timeout)]
    for e in env:
        argv += ["--env", e]
    before = set(game.run_dirs(a.slot))
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL)
    log = ""
    deadline = time.time() + a.timeout
    while proc.poll() is None and time.time() < deadline:
        time.sleep(1)
        new = sorted(set(game.run_dirs(a.slot)) - before)
        if not new:
            continue
        path = os.path.join(new[-1][1], "mlb.log")
        if os.path.isfile(path):
            log = open(path, encoding="utf-8", errors="replace").read()
        if "test +%d: hide" % END in log:
            break
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "game.py"), "stop", a.slot], stdout=subprocess.DEVNULL)
    proc.wait(60)

    check("trainer_contact on, trainer_pitch on" in log, "both patch sets are on")
    check("FATAL" not in log, "no FATAL line in the log")
    hold = log.find("test +%d: freeze 1" % HOLD)
    release = log.find("test +%d: freeze 0" % RELEASE)
    pitch = [(m.start(), float(m[1]), float(m[2]), float(m[3])) for m in re.finditer(
        r"trainer: pitch stamina ([\d.]+) energy ([\d.]+) confidence ([\d.]+)", log)]
    pre = [p[2] for p in pitch if 0 <= p[0] < hold]
    held = [p[2] for p in pitch if 0 <= hold < p[0] < release]
    after = [p[2] for p in pitch if 0 <= release < p[0]]
    print("before:", pre[-6:])
    print("held:  ", held)
    print("after: ", after[:8])
    check(len(pre) >= 3 and pre[-1] < pre[0], "unheld, energy falls")
    check(len(held) >= 5 and max(held) - min(held) < 0.005, "held, the value at each pitch stays put (%d pitches)"
          % len(held))
    # without a hold energy falls about 0.008 a pitch: carrying on means within a few such steps of the held value
    check(bool(held and after) and held[-1] - after[0] < 0.03,
          "released, energy carries on from the held value: held %s, then %s" % (held[-1:], after[:1]))
    contacts = re.findall(r"trainer: contact direction (-?[\d.]+) launch (-?[\d.]+) speed ([\d.]+)", log)
    check(len(contacts) >= 1, "%d batted balls read, e.g. %s" % (len(contacts), contacts[:3]))
    print("%d failed; screenshots and log in the slot" % failed)
    return failed


if __name__ == "__main__":
    sys.exit(main())
