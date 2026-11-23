How a test run is set up, and the rules for comparing two builds. Most of this exists because early runs misled us.

## The boot options that make a repeatable match

The retail game kept its engine's dev-config system. At boot it reads `BOOT/CONFIG_MAIN_USER.TXT` from the RomFS if that file exists, and otherwise `BOOT/CONFIG_MAIN.TXT`. Lines starting with `#` are comments, a bare line turns a boolean option on, and `KEY=VALUE` sets a value. Options are matched by a 32-bit hash, so the names appear nowhere in the binary. They were recovered by reversing the hash (an ELF-style hash followed by `h*0x9E3779B7 + ~h*0x61C88641`), collecting every hash the retail code passes to the three config-query functions (319 call sites, 109 unique hashes) and brute-forcing candidates until 27 matched.

A user file containing these two lines boots straight into an AI-against-AI match with no input:

```
AIvAI
GameOnly
```

Other options seen: `FastPlay`, `NoCrowd`, `NoWarmUp`, `NoDOF`, `NoTips`, `CatcherView`, `hrderbyOnly` (Home Run Derby only), `StartupMovies`, `ForcePlayGo`. Several options named in `CONFIG_MAIN.TXT` (the `DoPlayInit` scenario with inning, outs, balls and scores) are compiled out of the retail game and do nothing. Descriptions other than for `GameOnly` and `AIvAI` are readings of the names, not verified behaviour. Short common words collide with the hash, so a plausible name is not proof.

## Team ids

Team and stadium are set together: the game keeps the home and away team in several copies inside one match-settings struct (pointer at `main+0x4651350` in 1.0.20), filled about 3.5 s after boot. Writing only one copy gave Dodger Stadium with the wrong uniforms. The working override writes home at +0x3f, +0x47 and +0x59 and away at +0x40, +0x52, +0x54 and +0x56. Ids: 0 BAL, 1 BOS, 2 NYY, 3 TB, 4 TOR, 5 CWS, 6 CLE, 7 DET, 8 KC, 9 MIN, 10 HOU, 11 LAA, 12 ATH (not confirmed), 13 SEA, 14 TEX, 15 ATL, 16 MIA, 17 NYM, 18 PHI, 19 WSH, 20 CHC, 21 CIN, 22 MIL, 23 PIT, 24 STL, 25 AZ, 26 COL, 27 LAD, 28 SD, 29 SF. Home 0 and away 1 loads Baltimore and a different field texture (byte sum 127082744), which proves the override took effect.

## Run slots

Every run goes through `tools/game.py` in a slot of its own, so several games can run at once without stepping on each other. The game runs from `work/runs/<id>/`, a copy of the exe and the files it needs, with a folder per run holding `mlb.log`, `game.out`, `env.json` and `result.json`. A marker file `work/game.state/<id>.lock` is the slot's permit. `MLB_RUN_LABEL` puts a label in the window title. Real saves are copied, never written. `shared` runs start when fewer than three games are live and no exclusive run is live; `exclusive` (a timing run) starts only when no game is live.

A slot's first run fills its caches, so never take timing from it: the first game after a fresh copy of the exe folder took 37.1 s to reach the field picture and the next three took 22.5 s.

A game run needs an audio output. With none, the log says `audout: no output device` and the game sits at the loading screen. `TOTK_AUDIO=paced` is a silent fake device for unattended runs.

## Comparing two builds

1. Change one thing between configurations: a setting, or the build.
2. Alternate the runs (A, B, A, B), because the match differs between runs and the machine drifts. `--counterbalance` flips the order every second round.
3. At least two runs each, three if the difference is small. Record the run count with the result.
4. 400 s a run with the sampler off (`MLB_SAMPLER=off`, it slows the game) and `MLB_TRACE=perf`.
5. Read the first minute separately: it holds loading and sometimes an 8 to 10 s boot stall.
6. Call a difference real only if the min-max ranges of the runs do not overlap; with fewer than three runs say so. Otherwise write "within noise".
7. The 60 fps cap hides per-frame cost. Measure uncapped for performance claims.

`tools/bench.py run --config off:MLB_X=off --config on:MLB_X=1 --runs 2` does the bookkeeping, `compare` prints the table, and `tools/perf_summary.py` turns one log into JSON.

## Other rules learned the hard way

- Run a deliberately broken control before trusting a new metric (the known-yellow face proved the blown-pixel count could see the bug).
- Run each configuration fixed from frame 0. Switching a setting mid-run misled us, because head-show results are baked once.
- Never compare frame numbers between runs. They drift by hundreds of frames. Compare matched game events or fixed configurations.
- Diagnostics cost nothing in normal play: off by default, and never a `getenv` or config lookup in a per-draw or per-call path.
- Copy `mlb.log` before launching anything if it holds evidence; it is replaced at each start.

## Harness scenarios

`tools/scenario.py` and `tools/scenarios/*.txt` drive the game into a chosen match (teams, stadium, a stop condition, dumps). A dump such as `texture:fmt=0x25,size=512x512` writes the 512x512 field texture at the graphics call that creates it, and `tools/harness.py compare` byte-compares two dump folders. That is how the [Match-start freeze](Match-start-freeze) patch was shown to leave the picture unchanged. Open: where the game stores time of day and weather, and how to call its own scenario code (Situation, Moment, Storyline).
