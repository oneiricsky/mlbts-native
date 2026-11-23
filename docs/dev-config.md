# Dev harness

The retail game kept its engine's dev-config system. At boot it reads `BOOT/CONFIG_MAIN_USER.TXT`
from the RomFS if that file exists, and otherwise `BOOT/CONFIG_MAIN.TXT`. `#` lines are comments. A
bare line turns a boolean option on (case-insensitive). `KEY=VALUE` lines set values. Options are
matched by a 32-bit hash, so the names appear nowhere in the binary. The names were recovered by
reversing the hash (a custom ELF-style hash followed by `h*0x9E3779B7 + ~h*0x61C88641`), collecting
every hash constant the retail code passes to the three config-query functions (319 call sites, 109
unique hashes), and brute-forcing candidates until 27 matched. The rest are options not named yet,
or other lookups that share the hash function.

**The harness:** `game/romfs/BOOT/CONFIG_MAIN_USER.TXT` containing

```
AIvAI
GameOnly
```

boots the game straight into an AI-vs-AI exhibition without touching the menus, and needs no input.
AIvAI hands both teams to the AI once a game session starts; GameOnly tells the boot flow to start
a game.

## Live options

| Option | Hash | What it does | Named? | Sites |
|---|---|---|---|---|
| `GameOnly` | `0xC6F7ECA5` | Boots straight into a game, skipping menus and the title screen (confirmed). | | 12 |
| `AIvAI` | `0xAA21F9C5` | AI controls both teams in a game session (confirmed). | ✅ | 3 |
| `OpenBetaDemo` | `0x21108949` | Queried across boot and gameplay; the open-beta/demo switch. | | 53 |
| `StartupMovies` | `0x267A2101` | Gates the boot intro movies. | | 1 |
| `FastPlay` | `0x875D5965` | Faster gameplay pacing. | ✅ | 1 |
| `FastLoad` | `0x3DFD2037` | Sets a flag in a boot-globals struct. An A/B test showed no measurable change to boot-to-gameplay time; behavior otherwise unknown. | | 2 |
| `hrderbyOnly` | `0x07BDBC05` | Home Run Derby only. | | 7 |
| `ForceBootflow` | `0x96C88199` | Forces the boot flow. | | 1 |
| `ForcePlayGo` | `0x68452829` | Forces play-go (straight to gameplay). | | 4 |
| `NoCrowd` | `0x5B29C6D7` | No crowd rendering/audio. | | 1 |
| `NoIdle` | `0xA743410D` | No idle behavior. | | 1 |
| `NoWarmUp` | `0x1DB0461F` | Skips warm-up. | | 2 |
| `NoTTY` | `0x4F35A145` | No developer TTY output. | | 2 |
| `NoDOF` | `0x01161AA3` | Depth of field off. | ✅ | 1 |
| `NoTips` | `0x8333DD01` | No loading-screen tips. | ✅ | 2 |
| `CatcherView` | `0x4FFFBFD9` | Catcher view camera. | ✅ | 2 |
| `DisableUIElem` | `0xEAB3C09D` | Disables UI elements. | ✅ | 1 |
| `DisableJumboBink` | `0x6CFC5DB1` | No Bink movies on the jumbotron. | ✅ | 1 |
| `AlwaysDelayService` | `0x8D9D830D` | Always delays a service call. | | 2 |
| `DebugMatchupStats` | `0xE9154801` | Debug matchup-statistics overlay. | | 1 |
| `TestStorylines` | `0xA53B6861` | Storylines test path. | | 1 |
| `Savedata_Compression_Test` | `0x3EEB7277` | Save-data compression test. | | 2 |
| `getstadiumdata` | `0x0E1C0855` | Stadium-data action word. | ✅ | 6 |
| `Tutorial` | `0x35C16BC7` | Tutorial path. | | 1 |
| `Mobile` | `0x1020EF0D` | Mobile-platform paths. | | 14 |
| `pregame` | `0xF29AFC8D` | Pregame state. | | 1 |

"Sites" is how many places in the retail code pass the hash to one of the three config-query
functions. The hashes are the values the game compares config flags against. "Named?" means the
option appears (commented out) in CONFIG_MAIN.TXT itself. Except where a row says "(confirmed)",
the behavior descriptions are readings of the option names, not verified in-game behavior.

## Named in CONFIG_MAIN.TXT but compiled out

Their handlers are gone from the retail binary; uncommenting them in CONFIG_MAIN.TXT does nothing.

| Option | CONFIG_MAIN.TXT | Why it does nothing |
|---|---|---|
| `RunForever` | yes; in CScorer | No retail code queries its hash. |
| `DoPlayInit` | yes; in PlayInit | No retail code queries its hash. |
| `Inning`, `InnHalf`, `Outs`, `Strikes`, `Balls`, `HomeScore`, `AwayScore` | yes; in PlayInit | `KEY=VALUE` lines for DoPlayInit's scenario; the scenario itself is compiled out. |
| `UseAutoHit`, `HitAzimuth`, `HitIncline`, `HitSpeed` | yes; in Autohit | These feed DoPlayInit's scenario, which is compiled out. |
| `NoWad`, `NoHost` | yes; in FileSystems | No retail code queries their hashes. |
| `FileSys=ROM`, `SoundFileSys=ROM` | yes; in FileSystems | `KEY=VALUE` options; no retail code queries these hashes. |
| `world=ps3/stadiums/sf`, `rig=day` | yes; in world | `KEY=VALUE` options for the PS3-era sandbox; no retail code queries them. |
| `NoJumboMips` | yes; in Jumbotron | No retail code queries its hash. |
| `FlyCamToggle` | yes; in Graphics | No retail code queries its hash. |

Flag values, not options: the constants `1`, `5`, `100` and `255` in the query table are the values
the game compares config flags against, not option names.

Watch for fake matches when extending the table: short common words collide with the hash. One
candidate in this set looked plausible and was not.

## Running a comparison

This is upstream's method (docs/frame-rate.md, "Measuring"), with `tools/bench.py` doing the bookkeeping. The match
is the harness match above (`AIvAI` plus `GameOnly`), the one upstream calls the attract match.

1. Change one thing between the configurations: a setting such as `MLB_HD_TEXTURES`, or the build. Keep every
   other setting and `mlb.cfg` the same.
2. Alternate the runs (A, B, A, B), because the match differs from run to run and the machine drifts over a
   session. Add `--counterbalance` to flip the order every second round (A B B A).
3. Run each configuration at least twice, and three times if the difference is small. Record the run count with the
   result.
4. Play 400 s a run with the sampler off (`MLB_SAMPLER=off`: it slows the game) and `MLB_TRACE=perf`. One game at a
   time; `bench.py` refuses to start while `mlb.exe` is running.
5. Read the first minute separately. It holds loading and, now and then, a boot stall of 8 to 10 s. `compare`
   prints the first window's frame count and the figures from the second minute on.
6. Call a difference real only if the min-max ranges of the runs do not overlap, and say so when there are fewer
   than three runs. Otherwise write "within noise".

```
python -I tools/bench.py run --config off:MLB_HD_TEXTURES=off --config colour:MLB_HD_TEXTURES=hdtex_allc --runs 2
python -I tools/bench.py compare work/bench/<date>
python -I tools/bench.py compare off=run1.log off=run2.log colour=run3.log colour=run4.log
```

`run` starts `work/build/mlb.exe` (change it with `--exe` or `MLB_BENCH_EXE`) from its own folder, so the game finds
`game/romfs`, `profile/` and `mlb.cfg` beside it; put `MLB_EXEFS`, `MLB_ROMFS` or `MLB_PROFILE` in `--env` if a
build keeps them elsewhere. It writes `work/bench/<date>/<label>-<n>.log` and `.json` (the summary from
`tools/perf_summary.py` plus the run's settings). `--dry-run` prints the order and settings without starting
anything. `compare` also takes old logs with a `label=` prefix. The summary reads a log whether or not each line
starts with a timestamp (`MLB_LOG_TIME=1` puts `[ 12.345] ` in front of every line): its patterns are not anchored
to the start of the line.

## Dev harness plan

Status: design only, nothing here is built yet. It records what the owner settled. Anything not settled is marked
**open**.

In plain words: today a test run means starting the game by hand, with someone at the PC, and eyeballing the result.
The plan is a harness that runs a named scenario with one flag, needs nobody present, plays the same match every time,
records numbers and pictures, and says pass or fail in one plain line.

### Purpose

Three jobs, in this order of priority:

1. Speed and regression timing (frame times, stalls).
2. Output comparison (is the picture or data still correct after a change).
3. Exploring and reverse-engineering the game (start any match, mode or scene on demand).

Speed and output come first. Exploring grows out of the same controls.

### Ground rules

- **Unattended.** A run must work with nobody at the PC and no audio device. Today a run needs a live Windows audio
  output, or the game sits at the loading screen (`audout: no output device`). `TOTK_AUDIO=none` exists in
  `runtime/core/audout.c`; it must be checked as the fake device. Whether it gets the game past the loading screen is
  **open** until tested.
- **Repeatable.** A fixed random seed and a fixed clock, so the same match plays out the same way. (Until this
  exists, runs drift by hundreds of frames; see `CLAUDE.md`.)
- **Dev builds only.** The controls are `MLB_HARNESS_*` settings compiled only into dev builds, so players can never
  trigger them.
- **Owner starts it.** It runs only when the owner starts it. Nothing runs on its own.
- **Versions.** Game 1.0.20 first. Hooks are version-aware, so 1.0.15 needs only its address map
  (`tools/addrmap.py`) and a test, once the 1.0.15 exefs is available (it is not on this machine).

### Scenario file

One scenario file per run, kept in the repo, run with one flag. Fields:

| Field | Meaning | State |
|---|---|---|
| stadium | Which ballpark. | Set together with the teams (see below). |
| home team, away team | Team ids 0..29 (table below). | Working in a throwaway override (see below). |
| time of day, weather | Light and sky. | **Open**: not found in the game yet. |
| seed | Fixed random seed. | Decided; not built. |
| record | What to capture (see Recording). | Decided; not built. |
| stop | When the run ends. | **Open**: the exact choices (time, inning, event). |

Team ids:

| Id | Team | Id | Team | Id | Team |
|---|---|---|---|---|---|
| 0 | BAL | 10 | HOU | 20 | CHC |
| 1 | BOS | 11 | LAA | 21 | CIN |
| 2 | NYY | 12 | ATH (not confirmed) | 22 | MIL |
| 3 | TB | 13 | SEA | 23 | PIT |
| 4 | TOR | 14 | TEX | 24 | STL |
| 5 | CWS | 15 | ATL | 25 | AZ |
| 6 | CLE | 16 | MIA | 26 | COL |
| 7 | DET | 17 | NYM | 27 | LAD |
| 8 | KC | 18 | PHI | 28 | SD |
| 9 | MIN | 19 | WSH | 29 | SF |

**Team and stadium are set together.** The game keeps the home and away team in several copies inside one
match-settings struct, filled in about 3.5 s after boot. Writing only one copy gave Dodger Stadium with the wrong
uniforms. The working override (uncommitted, in `runtime/mlb/main.c` of the msdf-skip worktree, env vars
`MLB_HARNESS_HOME` and `MLB_HARNESS_AWAY`) writes every copy:

| Side | Offsets written |
|---|---|
| home | `+0x3f`, `+0x47`, `+0x59` |
| away | `+0x40`, `+0x52`, `+0x54`, `+0x56` |

Default is home 27 (LAD), away 4 (TOR). Home 0 and away 1 loads the Baltimore (BAL) files and a different field
texture checksum (127082744), which is a handy proof that the override takes effect.

### Modes in scope

AI-vs-AI exhibition, menus, Road to the Show, franchise, replays and cutscenes.

How to get into a mode: direct loading first, scripted button input only as the fallback.

1. Boot options from the existing option table above (`GameOnly`, `ForcePlayGo`, `hrderbyOnly`, and so on).
2. Calling the game's own entry functions.
3. Scripted button presses, only where 1 and 2 cannot reach.

Dropping players into a scenario should use the game's own scenario code where it exists (Situation, Moment,
Storyline). A search of the game code is in progress. **Open:** which of these exist and how to call them. The
`DoPlayInit` scenario options (`Inning`, `Outs`, `Balls` and the scores) are compiled out of retail (see the table
above), so they are no help.

### Recording

| What | How | Notes |
|---|---|---|
| Frame times | A frame-time log with named markers (for example "match start", "first pitch"). | Compare by marker, never by frame number. |
| Texture and buffer dumps | At the graphics call that writes them, for example the 512x512 `fmt 0x25` field texture at `nvnTextureWriteTexels`. | Byte compare. This is the check the msdf skip still needs for other stadiums. |
| Screenshot pixel diff | Against a reference picture. | Per machine, never committed. |
| State snapshot | A dump of chosen game state. | **Open:** which state. |
| GPU capture | A frame capture of the graphics commands. | |

### Baselines

The repo ships no game data, and the user compiles the game from their own copy, so baselines are made on each
machine at build time.

- The usual reference is the same build with one fix switched off against the fix on (for example `MLB_MSDF_SKIP=0`
  against the default).
- A known-good older build is the safeguard against a bug that is already in the reference.
- Screenshots are per machine and never committed.
- No hashes of game data are needed in the repo.

### Failure and smoke test

On failure the harness saves the log, the differing dump and a diff image in a local folder, prints one plain summary
and exits with a failure code.

It has one scenario to start with, the smoke test: boot, a short AI match, no crash, no stall, a sane frame rate.
"Sane" needs a number: **open**.

### In-game panel

- A tab in the settings menu turns dev mode on.
- Dev mode opens its own panel: match setup, dropping players into any scenario, recorder controls, and live
  readouts (frame-time graph, markers, last result).
- Keyboard and mouse only.
- Setup changes apply live mid-game where the game allows it. That needs a safe reload point per mode, which is
  **open**. (Mid-run changes have misled us before: head-show results are baked once, so fixed-from-frame-0 stays the
  rule for measurements.)

### Build order

The panel grows with each step.

| Step | What | Why this order |
|---|---|---|
| 1 | Match setup (stadium, teams, uniforms) and repeatability. | Everything else needs the same match each time. |
| 2 | Unattended mode and the frame-marker log. | Lets runs go without the owner and gives timing. |
| 3 | Texture dumps. | First output check. |
| 4 | Smoke test. | A cheap guard once 1 to 3 exist. |
| 5 | Screenshot compares. | |
| 6 | Direct loading per mode. | Needs the scenario-code search. |
| 7 | State snapshots and GPU capture. | |

### Open items

- Time of day and weather: where the game stores them.
- Whether `TOTK_AUDIO=none` gets the game past the loading screen.
- Which scenario code (Situation, Moment, Storyline) exists and how to call it.
- A safe reload point per mode for live setup changes.
- Stop conditions, state-snapshot contents, and the "sane frame rate" number.
- Whether team id 12 is the Athletics.
- 1.0.15: needs its exefs, then `tools/addrmap.py` and a test.
