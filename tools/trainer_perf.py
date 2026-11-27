#!/usr/bin/env python3
"""Frame rate and audio dropouts with the trainer off and on: AI-vs-AI matches, one at a time, with a window and sound.

    python -I tools/game.py create ID --exe <build>/mlb.exe
    python -I tools/trainer_perf.py --slot ID [--seconds 420]

Needs game/romfs/BOOT/CONFIG_MAIN_USER.TXT with AIvAI and GameOnly. Each run has the machine to itself. Prints the
game's per-minute frame-time lines and the audio mixer's last running totals; match against match, so compare minute by
minute and not single frames.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import game  # noqa: E402

CHEATS = ";".join("%d:cheat %s 3" % (k + 1, c) for k, c in enumerate(["contact", "aim", "strike", "wild"]))
RUNS = [("off", ["MLB_TRAINER=0"]), ("on", ["MLB_TRAINER=1"]),
        ("cheats", ["MLB_TRAINER=1", "MLB_TRAINER_TEST=" + CHEATS])]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slot", required=True)
    ap.add_argument("--seconds", type=int, default=420)
    ap.add_argument("--only", choices=[name for name, _ in RUNS])
    a = ap.parse_args()
    for name, env in RUNS:
        if a.only and name != a.only:
            continue
        argv = [sys.executable, "-I", os.path.join(HERE, "game.py"), "run", a.slot, "--timeout", str(a.seconds),
                "--mode", "exclusive"]
        for e in env + ["TOTK_TRACE=audio"]:
            argv += ["--env", e]
        before = set(game.run_dirs(a.slot))
        subprocess.run(argv, stdout=subprocess.DEVNULL)
        new = sorted(set(game.run_dirs(a.slot)) - before)
        if not new:
            print(name, ": no run was started", flush=True)
            continue
        log = open(os.path.join(new[-1][1], "mlb.log"), encoding="utf-8", errors="replace").read()
        print("== %s (%s)" % (name, new[-1][1]))
        for m in re.finditer(r"frametime: 60 s: .*?mean (\S+) fps, 1% low (\S+) fps, over 25 ms (\d+), 50 ms (\d+), "
                             r"100 ms (\d+)", log):
            print("   mean %s fps, 1%% low %s, frames over 25/50/100 ms: %s/%s/%s" % m.groups())
        audio = re.findall(r"audio: level .*?underruns (\d+), overruns (\d+), missing frames (\d+)", log)
        print("   audio at the end: underruns %s, overruns %s, missing frames %s" % audio[-1] if audio
              else "   no audio totals in the log")
        print("   trainer log lines %d; audio output: %s" %
              (log.count("trainer: "), "none" if "no output device" in log else "ok"), flush=True)


if __name__ == "__main__":
    main()
