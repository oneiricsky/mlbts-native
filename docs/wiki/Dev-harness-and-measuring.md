How a test run is set up, and the rules for comparing two builds. Most of this exists because early runs misled us.

## Boot options

The retail game kept its engine's dev-config system. At boot it reads `BOOT/CONFIG_MAIN_USER.TXT` from the RomFS if that file exists, and otherwise `BOOT/CONFIG_MAIN.TXT`.

| Line | Meaning |
|---|---|
| starts with `#` | comment |
| a bare name | turns a boolean option on |
| `KEY=VALUE` | sets a value |

Options are matched by a 32-bit hash (an ELF-style hash followed by `h*0x9E3779B7 + ~h*0x61C88641`), so most names appear nowhere in the game. The code reads 132 distinct hashes and 33 are named; `python -I tools/config_options.py --names` lists them all.

A user file containing these two lines boots straight into an AI-against-AI match with no input:

```
AIvAI
GameOnly
```

Options seen:

| Option | Effect | Status |
|---|---|---|
| `GameOnly` | boots straight into a game | confirmed |
| `AIvAI` | AI controls both teams | confirmed |
| `FastPlay` | faster pacing | name only |
| `NoCrowd` | no crowd rendering or audio | name only |
| `NoWarmUp` | skips warm-up | name only |
| `NoDOF` | depth of field off | name only |
| `NoTips` | no loading-screen tips | name only |
| `CatcherView` | catcher camera | name only |
| `hrderbyOnly` | Home Run Derby only | name only |
| `StartupMovies` | gates the boot intro movies | name only |
| `ForcePlayGo` | straight to gameplay | name only |
| `FastLoad` | sets a boot flag; no measurable change in boot-to-gameplay time | tested |

Several options named in `CONFIG_MAIN.TXT` (the `DoPlayInit` scenario with inning, outs, balls and scores) are compiled out of the retail game and do nothing. "Name only" means the effect is a reading of the option's name, not verified behaviour. Short common words collide with the hash, so a plausible name is not proof.

## Team ids

Team and stadium are set together: the game keeps the home and away team in several copies inside one match-settings struct (pointer at `main+0x4651350` in 1.0.20), filled about 3.5 s after boot. Writing only one copy gave Dodger Stadium with the wrong uniforms. The working override writes every copy:

| Side | Offsets |
|---|---|
| Home | +0x3f, +0x47, +0x59 |
| Away | +0x40, +0x52, +0x54, +0x56 |

| ID | Team | ID | Team | ID | Team |
|---|---|---|---|---|---|
| 0 | BAL | 10 | HOU | 20 | CHC |
| 1 | BOS | 11 | LAA | 21 | CIN |
| 2 | NYY | 12 | ATH (unconfirmed) | 22 | MIL |
| 3 | TB | 13 | SEA | 23 | PIT |
| 4 | TOR | 14 | TEX | 24 | STL |
| 5 | CWS | 15 | ATL | 25 | AZ |
| 6 | CLE | 16 | MIA | 26 | COL |
| 7 | DET | 17 | NYM | 27 | LAD |
| 8 | KC | 18 | PHI | 28 | SD |
| 9 | MIN | 19 | WSH | 29 | SF |

Home 0 and away 1 loads Baltimore and a different field texture (byte sum 127082744), which proves the override took effect.

## Run slots

Every run goes through `tools/game.py` in a slot of its own, so several games can run at once without stepping on each other.

| Item | Detail |
|---|---|
| Game copy | runs from `work/runs/<id>/`, a copy of the exe and the files it needs |
| Run folder | one per run, holding `mlb.log`, `game.out`, `env.json` and `result.json` |
| Permit | the marker file `work/game.state/<id>.lock` |
| Window title | `MLB_RUN_LABEL` puts a label in it |
| Saves | real saves are copied, never written |
| `shared` run | starts when fewer than three games are live and no exclusive run is live |
| `exclusive` run | a timing run; starts only when no game is live |

A slot's first run fills its caches, so never take timing from it: the first game after a fresh copy of the exe folder took 37.1 s to reach the field picture and the next three took 22.5 s.

A game run needs an audio output. With none, the log says `audout: no output device` and the game sits at the loading screen. `TOTK_AUDIO=paced` is a silent fake device for unattended runs.

## Build comparisons

1. Change one thing between configurations: a setting, or the build.
2. Alternate the runs (A, B, A, B), because the match differs between runs and the machine drifts. `--counterbalance` flips the order every second round.
3. At least two runs each, three if the difference is small. Record the run count with the result.
4. 400 s a run with the sampler off (`MLB_SAMPLER=off`, it slows the game) and `MLB_TRACE=perf`.
5. Read the first minute separately: it holds loading and sometimes an 8 to 10 s boot stall.
6. Call a difference real only if the min-max ranges of the runs do not overlap; with fewer than three runs say so. Otherwise write "within noise".
7. The 60 fps cap hides per-frame cost. Measure uncapped for performance claims.

`tools/bench.py run --config off:MLB_X=off --config on:MLB_X=1 --runs 2` does the bookkeeping, `compare` prints the table, and `tools/perf_summary.py` turns one log into JSON.

## Measurement rules

| Rule | Why |
|---|---|
| Run a deliberately broken control before trusting a new metric | the known-yellow face proved the blown-pixel count could see the bug |
| Run each configuration fixed from frame 0 | switching a setting mid-run misled us, because head-show results are baked once |
| Never compare frame numbers between runs | they drift by hundreds of frames; compare matched game events or fixed configurations |
| Diagnostics cost nothing in normal play | off by default, and never a `getenv` or config lookup in a per-draw or per-call path |
| Copy `mlb.log` before launching anything if it holds evidence | it is replaced at each start |

## Scenarios

`tools/scenario.py` and `tools/scenarios/*.txt` drive the game into a chosen match (teams, stadium, a stop condition, dumps).

A dump such as `texture:fmt=0x25,size=512x512` writes the 512x512 field texture at the graphics call that creates it, and `tools/harness.py compare` byte-compares two dump folders. That is how the [Match-start freeze](Match-start-freeze) patch was shown to leave the picture unchanged.

Open: where the game stores time of day and weather, and how to call its own scenario code (Situation, Moment, Storyline).

## Team selection

Found 2026-11-24.

Problem: the players, cards and scorebug stayed Blue Jays against Dodgers in every run, whatever team numbers were written into the match settings block, the saved default record or the team objects.

What is established (all measured):

- The settings block (pointer at `main+0x4651350`) is a keyed option table. `f_7001824c18(key, value)` is the game's setter and `f_7001824fa0(block, key, value)` the block-level writer.
- For keys 1 to 0x53 both put the byte at block+0x3e+key, and `f_7001824b74(key)` reads it. Key 1 is the home team (`+0x3f`) and key 2 the away team (`+0x40`).
- Team ids follow division order: 0 BAL, 1 BOS, 2 NYY, 3 TB, 4 TOR, 5 to 9 AL Central, 10 to 14 AL West, 15 to 19 NL East, 20 to 24 NL Central, 25 ARI, 26 COL, 27 LAD, 28 SD, 29 SF (0 to 4, 25 and 27 confirmed against the game's own picks).
- The game reads those bytes once, as the menus leave team select, and builds the rosters, cards and scorebug then. The same bytes written after the match is built change only the stadium and uniforms (control: Ohtani in a Red Sox uniform at Fenway, scorebug TOR/LAD).
- An untouched default pick (TOR at LAD) keeps rosters loaded earlier, so the cursor has to be moved once before confirming.
- `tools/exhibition.py` presses the real menu buttons, overwrites the block right after the team-select confirm and checks it at the first batter. Four cold launches, four pairings, all matching on screen and in the block: BAL at BOS (Taylor Ward, Garrett Crochet), LAD at TOR (Ohtani, Gausman), BOS at BAL (Roman Anthony, Trevor Rogers), BOS at BAL again under a full function trace.

Plain words: the game decides the two teams at one moment in the menu. Fill the table then and the right players play; fill it later and nothing but the stadium and shirts change.

Where the bytes go (found 2026-11-24):

1. The read is in `f_7000bab324`, the screen handler the menus run as they leave team select. It is a vtable method, so the generated C shows no direct caller.
2. It reads option 2 (away) and then option 1 (home) with `f_7001824b74` and passes both numbers to `f_700066f324`.
3. That helper resolves each number through the league's team table (`f_700181ad34`: base at +0x8, count at +0x3c, stride 0x550, team id at record +0xc).
4. It then calls the game-entry builder `f_700066f390` with the two team records.

The builder creates the match's two team slots, which use the same 0x550-byte record and sit 0xaa0 apart, and copies one picked record into each slot with `f_700185d058`. That function copies the whole record:

| Part | Detail |
|---|---|
| +0x50 | a 0x368-byte block: a 0x2f8-byte memcpy plus the fields through +0x364, in `f_70018492c4` |
| +0x3b8 | a 0x148-byte block |
| +0x500 | 0x39 bytes |
| +0x540, +0x548 | pointers |

The per-player work is in `f_700066f770`, the builder's callee. It walks the player list in the copied block and builds the side's entries one at a time, 0x138 bytes each into a 40-slot array (0x30c0 bytes). It also carries the "ERROR: Entering MLB game when minor leagues are not active but player is not on an MLB team" check.

So the team numbers never go into roster rows: a number picks a team record, the record carries the player list, and the match builds its own copy of both.

Evidence comes from the BOS-at-BAL cold run with the full first-call trace (`work/runs/sonnet/logs/mlb.log`):

| Time | Event |
|---|---|
| 45.759 s | team select |
| 61.426 s | first call of `f_7000bab324`, from `main+0x89b9c8` |
| 61.426 s | first call of `f_700066f324` (x0 = 1, the away pick) |
| 61.426 s | first call of `f_700066f390` (x0 = 0x1c93ac100, the away team record) |
| 61.426 s | first call of `f_700185d058` (x0 = 0x1c72060b8, the match slot) |
| 88.886 s | GAME ENTERED |

The generated C is in `work/gen/main`: main_0081.c for the read, main_0050.c for the builder and the player loop, main_0170.c for the record copy.
