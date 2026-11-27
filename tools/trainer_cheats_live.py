"""Live check of the trainer's guaranteed cheats on a running AI-vs-AI match, one cheat a run.

    python -I tools/game.py create ID --exe <build>/mlb.exe
    python -I tools/trainer_cheats_live.py --slot ID --cheat contact|homer|miss|aim|strike|wild|control
                                           [--sides 1 away|2 home|3 both] [--also CHEAT] [--seconds N]

Needs game/romfs/BOOT/CONFIG_MAIN_USER.TXT with AIvAI and GameOnly. The cheat (and the one named by --also) is set
for those sides when the trainer first reads a match; an AI match has no side of its own, so mine is the away team
and theirs the home team. With one side only, the tool also checks that nothing was forced while the other team
batted (needs a run long enough to reach the bottom of the 1st). From outside the game the tool follows the count object (tools/scenario.py) and records every
change of it; from the log it takes what the trainer's hooks did. It prints the totals and checks what the cheat
promises:

    contact  every swing the model computed ended with a batted ball
    homer    every batted ball left at 110 mph or more between 27 and 31 degrees, and the score went up
    miss     swings were forced to miss, no ball was hit by a side the cheat covers
    aim      pitches were placed on the aim point
    strike   pitches out of the zone were called strikes, and a covered pitcher never had a ball counted
    wild     throws on a live ball were made wild; prints the game's errors and at-bat results
    control  nothing is set: the same totals for comparison

Screenshots (MLB_SHOT) land in the slot's profile. Exit code = failed checks.
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
import scenario as sc  # noqa: E402

failed = 0


def check(ok, text):
    global failed
    failed += not ok
    print("PASS" if ok else "FAIL", text, flush=True)


# One entry per batted ball the model computed, with what the game's own log says up to the next batter-up or ball:
# (the play is over, the batter checked the swing so the ball never happened, the at-bat results recorded).
def plays(after):
    lines = after.splitlines()
    marks = [i for i, line in enumerate(lines) if "trainer: contact" in line]
    out = []
    for n, i in enumerate(marks):
        end = marks[n + 1] if n + 1 < len(marks) else len(lines)
        part = lines[i:end]
        stop = next((k for k, line in enumerate(part) if "FLOW STATE ENTER: GAME_STATE_BATTER_UP" in line), None)
        done = stop is not None
        part = part[:stop]
        checked = any("AI Checked Swing" in line for line in part)
        recorded = [line.split(": ", 1)[-1].strip() for line in part if "recorded an at bat" in line]
        out.append((done, checked, recorded))
    return out


# The log's lines after the cheat began, each with the half-inning it came in (even: the away team bats).
def by_half(after):
    half = 0
    for line in after.splitlines():
        m = re.search(r"trainer: half-inning: .* half (\d+)", line)
        if m:
            half = int(m[1])
        yield half, line


# What the log says when each cheat changes something (--also adds another cheat's lines, which are not counted).
MESSAGES = {"contact": "swing given azimuth", "homer": "swing given azimuth", "miss": "swing forced to miss",
            "aim": "placed on the aim", "strike": "called a strike", "wild": "throw made wild", "control": "(?!)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True)
    ap.add_argument("--cheat", required=True, choices=["contact", "homer", "miss", "aim", "strike", "wild", "control"])
    ap.add_argument("--sides", type=int, default=3, choices=[1, 2, 3])
    ap.add_argument("--also", choices=["contact", "homer"])
    ap.add_argument("--seconds", type=int, default=420)
    ap.add_argument("--extra", default="", help="more trainer commands, <frames>:<command>;...")
    a = ap.parse_args()
    commands = "1:cheat %s %d" % (a.cheat, a.sides) if a.cheat != "control" else "1:hide"
    if a.also:
        commands += ";2:cheat %s %d" % (a.also, a.sides)
    if a.extra:
        commands += ";" + a.extra
    env = ["MLB_TRAINER=1", "TOTK_HIDDEN_WINDOW=1", "TOTK_AUDIO=paced", "MLB_TRAINER_TEST=" + commands,
           "MLB_SHOT=" + ",".join(str(f) for f in range(3000, 40001, 600))]
    argv = [sys.executable, "-I", os.path.join(HERE, "game.py"), "run", a.slot, "--timeout", str(a.seconds)]
    for e in env:
        argv += ["--env", e]
    before = set(game.run_dirs(a.slot))
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL)
    g, last, changes, path = None, None, [], None
    while proc.poll() is None:
        time.sleep(0.1)
        if path is None:
            new = sorted(set(game.run_dirs(a.slot)) - before)
            if new:
                path = os.path.join(new[-1][1], "mlb.log")
            continue
        if g is None:
            pid = sc.find_pid("mlb_" + a.slot)
            g = sc.Game(pid) if pid else None
            continue
        o = g.counts_obj()
        raw = g.rd(o, 0x24) if o else None
        if not raw:
            continue
        v = [int.from_bytes(raw[k:k + 4], "little") for k in (0x8, 0xC, 0x10, 0x14, 0x18, 0x20)]
        # the clock starts when the trainer reads the match: count only what follows
        if v != last and v[2] <= 4 and v[3] <= 3 and v[4] <= 3 and v[5] < 200:
            started = os.path.isfile(path) and "test +1:" in open(path, encoding="utf-8", errors="replace").read()
            changes.append((started, v))
            last = v
    log = open(path, encoding="utf-8", errors="replace").read() if path and os.path.isfile(path) else ""
    mark = log.find("test +1:")
    after = log[mark:] if mark >= 0 else ""
    seen = [v for s, v in changes if s]
    balls_up = sum(1 for p, q in zip(seen, seen[1:]) if q[2] > p[2])
    strikes_up = sum(1 for p, q in zip(seen, seen[1:]) if q[3] > p[3])
    contacts = [tuple(float(x) for x in m) for m in
                re.findall(r"trainer: contact direction (\S+) launch (\S+) speed (\S+)", after)]
    forced = re.findall(r"trainer: (missed|hit) swing given azimuth (\S+) launch (\S+) speed (\S+)", after)
    whiffs = len(re.findall(r"trainer: swing forced to miss", after))
    placed = len(re.findall(r"trainer: pitch placed on the aim point", after))
    called = len(re.findall(r"trainer: pitch out of the zone called a strike", after))
    runs = (seen[-1][0] + seen[-1][1]) - (seen[0][0] + seen[0][1]) if seen else 0
    results = plays(after)
    print("count changes %d: balls went up %d times, strikes %d; runs scored %d; last count %s"
          % (len(seen), balls_up, strikes_up, runs, seen[-1] if seen else None))
    print("batted balls %d (forced: %d after a miss, %d after a hit), forced misses %d, pitches centred %d, "
          "strikes called %d" % (len(contacts), sum(f[0] == "missed" for f in forced),
                                 sum(f[0] == "hit" for f in forced), whiffs, placed, called))
    for c, (done, checked, recorded) in zip(contacts, results):
        what = "check swing" if checked else ", ".join(recorded) or ("no at-bat result" if done else "still in play")
        print("  ball: direction %6.1f launch %6.1f speed %5.1f  %s" % (c + (what,)))
    check("audout: no output device" not in log, "the log has an audio output")
    check("FATAL" not in log, "no FATAL line in the log")
    check(bool(after), "the cheat command ran in a match")
    check(len(seen) > 5, "the match played on")
    if a.cheat == "contact":
        missed = sum(f[0] == "missed" for f in forced)
        check(missed > 0, "%d missed swings were given contact" % missed)
        check(len(contacts) >= missed, "each of them was read back as a batted ball")
    if a.cheat == "homer":
        check(len(contacts) > 0, "%d balls were hit" % len(contacts))
        good = sum(27 <= c[1] <= 31 and c[2] >= 110 for c in contacts)
        check(good == len(contacts), "%d of %d left at 110 mph or more, 27 to 31 degrees" % (good, len(contacts)))
        swung = [r for done, checked, r in results if done and not checked]
        homers = sum(any("Home Run" in x for x in r) for r in swung)
        check(homers == len(swung) > 0, "the game recorded a home run for %d of %d completed swings" % (homers, len(swung)))
        check(runs >= homers, "runs scored %d" % runs)
    if a.cheat == "miss":
        check(whiffs > 0, "%d swings were forced to miss" % whiffs)
        covered = [bool(a.sides & (1 << (half & 1))) for half, line in by_half(after) if "trainer: contact" in line]
        check(not any(covered), "no batted ball by a side the cheat covers (%d by the other)" % len(covered))
    if a.cheat == "aim":
        check(placed > 0, "%d pitches placed on the aim point" % placed)
        wild = [float(x) ** 2 + float(y) ** 2 for x, y in
                re.findall(r"pitch placed on the aim point \(the miss was (\S+) (\S+)", after)]
        print("  the misses removed were up to %.2f ft" % (max(wild, default=0) ** 0.5))
    if a.cheat == "strike":
        check(called > 0, "%d pitches out of the zone were called strikes" % called)
        # the pitching team is the one not batting; only its pitches are covered
        theirs = sum(1 for p, q in zip(seen, seen[1:]) if q[2] > p[2] and a.sides & (1 << (1 - (q[5] & 1))))
        check(theirs == 0, "the ball count never went up for a covered pitcher (%d; %d in all)" % (theirs, balls_up))
    if a.cheat == "wild":
        wild = len(re.findall(r"trainer: throw made wild", after))
        results = [x.split(": ", 1)[-1].strip() for x in after.splitlines() if "recorded an at bat" in x]
        print("  at-bats: %s" % ", ".join(results))
        check(wild > 0, "%d throws were made wild" % wild)
        errors = len(re.findall(r"Batter safe on throwing error", after))
        reached = sum("Reached On Error" in x for x in results)
        print("  batter safe on a throwing error %d; at-bats recorded as reached on error %d; ground outs %d; "
              "foul calls %d" % (errors, reached,
                                 sum(x.startswith(("Groundout", "Unassisted")) or x == "Double Play" for x in results),
                                 len(re.findall(r"RUNNER COMMAND SET TO FOUL BALL", after))))
    if a.sides != 3:
        touched = [half & 1 for half, line in by_half(after)
                   if re.search(MESSAGES[a.cheat], line)]
        want = a.sides - 1   # which half's pitches the cheat covers, for a batting cheat
        if a.cheat in ("aim", "strike", "wild"):
            want ^= 1
        halves = sorted({half for half, _ in by_half(after)})
        check(len(halves) > 1, "both teams batted (half-innings %s)" % halves)
        check(touched and all(t == want for t in touched),
              "all %d changes came while team %d batted" % (len(touched), want))
    print("%d failed; log %s" % (failed, path))
    return failed


if __name__ == "__main__":
    sys.exit(main())
