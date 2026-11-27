"""Press controller buttons in a running test game from outside, then say what the match data holds.

    python -I tools/pad_drive.py --slot ID STEP [STEP ...]

STEP: a button (A B X Y PLUS MINUS LEFT UP RIGHT DOWN), or wait:<seconds>. The game must run with MLB_HARNESS_PAD=1
(tools/game.py run ID --env MLB_HARNESS_PAD=1). Prints the count object (what the trainer's Match page reads) and the
newest screenshot in the slot's profile.
"""
import argparse
import glob
import os
import re
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import game  # noqa: E402
import scenario as sc  # noqa: E402

BTN = dict(A=0, B=1, X=2, Y=3, PLUS=10, MINUS=11, LEFT=12, UP=13, RIGHT=14, DOWN=15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True)
    ap.add_argument("steps", nargs="*")
    a = ap.parse_args()
    pid = sc.find_pid("mlb_" + a.slot)
    if not pid:
        raise SystemExit("no running game for slot " + a.slot)
    g = sc.Game(pid)
    run = game.run_dirs(a.slot)
    log = open(os.path.join(sorted(run)[-1][1], "mlb.log"), encoding="utf-8", errors="replace").read()
    m = re.search(r"external buttons word at ([0-9A-Fa-f]+)", log)
    if not m:
        raise SystemExit("the log names no buttons word: run with MLB_HARNESS_PAD=1")
    word = int(m[1], 16)
    for s in a.steps:
        if s.startswith("wait:"):
            time.sleep(float(s[5:]))
            continue
        g.wr(word, struct.pack("<Q", 1 << BTN[s]))
        time.sleep(0.15)
        g.wr(word, struct.pack("<Q", 0))
        time.sleep(0.6)
    try:
        o = g.counts_obj()
        print("count object %#x: %s  side %s" % (o, sc.state(g), sc.side_byte(g)))
    except RuntimeError as e:
        print("count object unreadable:", e)
    shots = sorted(glob.glob(os.path.join(game.slot_path(a.slot), "profile", "shot-*.png")), key=os.path.getmtime)
    print("newest shot:", shots[-1] if shots else None)
    screens = re.findall(r"Entering screen: \[[^\]]*->([^\]]*)\]", open(os.path.join(sorted(run)[-1][1], "mlb.log"),
                                                                    encoding="utf-8", errors="replace").read())
    print("last screens:", screens[-5:])


if __name__ == "__main__":
    main()
