"""Start an Exhibition match between two chosen teams in a running game (1.0.20), through the game's own menus.

    python -I tools/exhibition.py --exe mlb_sonnet --log RUN.out --away 1 --home 0 [--from title|menu]

Why it works: the lineups, rotations, cards and scorebug are built from the match settings block
(u64 at main+0x4651350: home team +0x3f, away +0x40, copies at +0x47/+0x59 and +0x52/+0x54/+0x56, stadium +0x47 and
+0x3e+9) when the menus go on after team select. A write made once the match is already loaded, or in a run that skips
the menus, comes too late and changes only the stadium and uniforms. So the tool presses the real menu buttons, and
right after the home team is confirmed on the team-select screen (the game has just written its own pick there) it
overwrites the block with the chosen teams, then goes on through uniform, stadium, options, starters and lineup.
Seen 2026-11-24: written BOS (away 1) and BAL (home 0) over a pick of TOR and ARI, the starter screen, the pregame
lineup, the dugout intro and the scorebug all showed Boston and Baltimore players.

Team ids are the division order: 0 BAL 1 BOS 2 NYY 3 TB 4 TOR | 5 CWS 6 CLE 7 DET 8 KC 9 MIN | 10 HOU 11 LAA 12 OAK
13 SEA 14 TEX | 15 ATL 16 MIA 17 NYM 18 PHI 19 WSH | 20 CHC 21 CIN 22 MIL 23 PIT 24 STL | 25 ARI 26 COL 27 LAD
28 SD 29 SF (0 to 4, 25 and 27 are confirmed against the game's own picks; the rest follow the same order).
The game must expose the pad word: run it with MLB_HARNESS_PAD=1 (the log line says "external buttons word at ...").
Needs the game's own menu: it does not work in a run that boots straight into a match (AIvAI autostart).
"""
import argparse
import re
import struct
import sys
import time

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
import scenario as sc  # noqa: E402

BTN = dict(A=0, B=1, X=2, Y=3, PLUS=10, MINUS=11, LEFT=12, UP=13, RIGHT=14, DOWN=15)
HOME_COPIES, AWAY_COPIES = (0x3F, 0x47, 0x59), (0x40, 0x52, 0x54, 0x56)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True, help="process name without .exe")
    ap.add_argument("--log", required=True, help="the game's stdout log (has the pad word and the flow lines)")
    ap.add_argument("--away", type=int, required=True)
    ap.add_argument("--home", type=int, required=True)
    ap.add_argument("--from", dest="start", choices=("title", "menu"), default="menu",
                    help="title: at the title screen; menu: at the main menu (after a match exit)")
    ap.add_argument("--delay", type=float, default=15, help="seconds to wait after the pick before overwriting")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()

    pid = sc.find_pid(a.exe)
    if not pid:
        sc.log("ERROR: no running", a.exe)
        return 2
    g = sc.Game(pid)

    def text():
        return open(a.log, errors="replace").read()

    pad = None
    for m in re.finditer(r"external buttons word at (?:0x)?([0-9a-fA-F]+)", text()):
        pad = int(m.group(1), 16)
    if not pad:
        sc.log("ERROR: no pad word in the log (start the game with MLB_HARNESS_PAD=1)")
        return 2

    def press(name, hold=0.15, gap=0.6):
        g.wr(pad, struct.pack("<Q", 1 << BTN[name]))
        time.sleep(hold)
        g.wr(pad, struct.pack("<Q", 0))
        time.sleep(gap)

    def count(p):
        return len(re.findall(p, text()))

    def wait_for(p, n0, what, timeout=a.timeout):
        t0 = time.time()
        while count(p) <= n0:
            if not g.alive():
                raise SystemExit("ERROR: the game exited while waiting for " + what)
            if time.time() - t0 > timeout:
                raise SystemExit("ERROR: timed out waiting for " + what)
            time.sleep(0.5)
        sc.log("seen:", what)

    team_sel = r"Entering screen: \[TitleLoadingScreen->TeamSelect"
    n_ts = count(team_sel)
    n_ge = count(r"===GAME ENTERED===")
    if a.start == "title":
        time.sleep(2)
        press("PLUS", gap=6)
        press("A", gap=6)
    press("DOWN", gap=2)
    press("DOWN", gap=2)
    press("A", gap=1)
    wait_for(team_sel, n_ts, "team select")
    time.sleep(3)

    s = g.u64(sc.SETTINGS_PTR)
    before = g.rd(s, 0x80)
    press("RIGHT", gap=2)  # a changed selection makes the game rebuild the rosters; the untouched default keeps the preloaded TOR/LAD ones
    press("A", gap=2)  # confirms the active side (home) and moves on to the uniform screen
    t0 = time.time()
    while g.rd(s, 0x80) == before and time.time() - t0 < 20:
        time.sleep(0.2)
    pick = g.rd(s, 0x80)
    sc.log("the game's own pick: away", pick[0x40], "home", pick[0x3F])
    time.sleep(a.delay)
    for o in HOME_COPIES:
        g.wr(s + o, bytes([a.home]))
    for o in AWAY_COPIES:
        g.wr(s + o, bytes([a.away]))
    g.wr(s + 0x3E + 9, bytes([a.home]))
    back = g.rd(s, 0x80)
    sc.log("written: away", back[0x40], "home", back[0x3F], "stadium", back[0x3E + 9])
    if (back[0x40], back[0x3F]) != (a.away, a.home):
        raise SystemExit("ERROR: the write did not stick")

    for name in ("uniform", "stadium", "away uniform", "away stadium-or-options"):
        press("A", gap=3)
    press("A", gap=6)  # options -> starters
    press("A", gap=5)  # starters -> pregame lineup
    press("PLUS", gap=1)
    wait_for(r"===GAME ENTERED===", n_ge, "match entered")
    wait_for(r"FLOW STATE ENTER: GAME_STATE_BATTER_UP", count(r"FLOW STATE ENTER: GAME_STATE_BATTER_UP"), "first batter")
    end = g.rd(s, 0x80)
    sc.log("settings at the first batter: away", end[0x40], "home", end[0x3F])
    ok = (end[0x40], end[0x3F]) == (a.away, a.home)
    sc.log("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
