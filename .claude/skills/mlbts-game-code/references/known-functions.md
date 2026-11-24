# Known game addresses (1.0.20 unless marked)

Address = guest = host address; module offset = address - base (`main` base `0x7000000000`, `sdk` `0x7004c00000`), so `main+0x12c54ec` = `0x70012c54ec`.
Tags: [C] confirmed by a doc measurement, code, symbol or string; [I] inferred. "Source" says where it was established. Look any of them up with
`python -I tools/map_find.py fn <addr>`. 1.0.15 addresses are lower by 0x20..0x1500 for code (`tools/addrmap.py` maps them).

## Program entry, memory, logging

| Address | What | Tag | Source |
|---|---|---|---|
| `0x7000000880` | `nnMain` (112 bytes; the game's entry) | C | symbol |
| `0x70005b19e0` | `nninitStartup` (sets the heap; heap size set at `main+0x5b1a84`) | C | symbol, `runtime/mlb/heap.c` |
| `0x70005b30a0` / `0x70005b19d0` | `operator new` (4,060 callers) / `operator delete` (7,741 callers; the most-called function) | C | symbols |
| `0x7001c1f920`, `0x7001c1f990`, `0x7001c1f970`, `0x7001c1fa00`, `0x7001c1fa50` | `malloc`, `calloc`, `free`, `realloc`, `aligned_alloc` | C | symbols |
| `0x700055a820` | engine allocator, message "MemAlign - Unable to allocate %zu bytes from the %s pool"; reached from `operator new` | C | string |
| `0x700055d340` | `DyingAssert` reporter | C | string |
| `0x7000589b08` | crash/"dying" message writer (`MLB_DYING_MSG_START_V2`, "Built: %s %s") | C | string |
| `0x7001ad9090` (1.0.15 `0x7001ad7bd0`) | engine print/log function; trace it with `MLB_FNTRACE` to read the game's messages | C | AGENTS.md |

## Graphics functions

| Address | What | Tag | Source |
|---|---|---|---|
| `0x70005a1a90` | GPU wait: polls `nvnEventGetValue` until the frame's GPU signal; "hang in kick %u"; 47 direct callers in the index (the docs counted 63 call sites, some via indirect calls); ~53 waits per pitch before the walk-up patch; its start-kick marker `0x70005a1700` has 179 callers | C | docs/frame-rate.md, strings |
| `0x70005a1300` | GPU kick/submit (called with 2 in the lighting loop) | C | walkup-freeze.md |
| `0x70005a5388` (1.0.15 `0x70005a5368`) | returns entry min(level,4) of the five {w,h} render-size pairs; loads table pointer from `0x7002284df0`, table at `0x7001d82910` | C | resolution.c |
| 1.0.15 `0x70005a4634`, `0x70005a4b88` (1.0.20 addresses not recorded; find with `tools/addrmap.py` or by calling `0x70005a5388`'s callers) | resize the scene's render targets (colour, depth, third target, all 1440x810) | C | resolution.c |
| `0x7000095390` (1083 lines) | MSDF (distance-field) generator driver: logs "MSDF took %.4fms for %ux%u"; sits in the studio's external GraphicsUtils library | C | string, msdf-skip report |
| `0x7000030ec0`, `0x7000031e70`, `0x7000033530`, `0x70000339a0`, `0x70000336bc` | MSDF error-correction pass and its helpers; the pass divides `(a-0.5)/(a-b)` for every pixel and makes ~67 million NaNs at match start; `msdf_skip` patch at `main+0x311a0` skips pixels whose three channels are all infinite (683 to 189 ms) | C | msdf-skip report |
| `0x7000000f10` | helper called in the allocator failure report | I | call tree |

## Game flow

The game's top-level state machine is 12 state classes with the same interface [C, vtables]: each a 32-36 slot vtable overriding a shared base
(default stubs from `0x7000eb72c0`). Slots, read from the bodies and spot-checked (see Game-state-machine on the wiki and `docs/map/bodies/`): 0 and 1 destructor thunks; 2 returns the state name; 3 resets the state's fields; 5 enter (runs once: logs, stores a start time, requests lighting in BATTER_UP, starts the lighting bake in PLAY_OVER); 6 exit; 7 update every frame (adds the frame time into `[this+0x8]`, then a phase machine); 9 and 10 subscribe and unsubscribe to events on the bus at `[0x7002298000+0x428]`. Nothing calls slots 5 to 7 directly, so enter, exit and update are readings of the bodies [I]. Every phase change posts event 0x13d through `f_7000e23cec`.

| State | Vtable | Handlers |
|---|---|---|
| STADIUM_CREATOR | `0x70021d7400` | `0x7000eb72b4` |
| OPTIONS_ON_RAMP | `0x70021dbed0` | `0x7000ed20d0` |
| PRE_PLAY | `0x70021e1798` | `0x700106d054`-`0x700106f0d0`, `0x7001071a64` |
| PRE_GAME | `0x70021e22c8` | `0x700108ae04` |
| BATTER_UP | `0x70021e2708` | `0x700108b418`-`0x700108e610`, `0x700108ed0c` |
| GAME_INTRO | `0x70021e2998` | `0x700108f7a4` |
| GAME_OVER | `0x70021e2b00` | `0x700108f7c4`-`0x70010920f4`, `0x70010924e0` |
| INNING_OVER | `0x70021e2d38` | `0x7001092518`, `0x700109276c`, `0x70010936d4` |
| IN_PLAY | `0x70021e2ea0` | `0x70010936ec`-`0x7001094afc`, `0x70010961b8` |
| LINEUP_INTRO | `0x70021e2fb0` | `0x700109773c` |
| PLAY_OVER | `0x70021e3258` (+`0x70021e3378`) | `0x700109a680`-`0x700109d510`, `0x700109d8c4` |
| WARM_UP | `0x70021e3538` | `0x70010a2e78`-`0x70010a3908`, `0x70010a3b5c` |

Sub-states named in strings [C]: BATTER_UP: NONE, WALK_UP, WALK_UP_PRES, PLAYERS_SETUP, SELECT_PITCH, MANAGER_MODE, LAUNCH_PITCH, IN_PITCH.
IN_PLAY: NULL, IN_PLAY, IN_PITCH, POST_PITCH, ANIM_SEQUENCE, PLAY_OVER. PLAY_OVER: POST_PLAY, WAIT, EXIT, PRES_LOAD, PRES_GAMEOVER, CHALLENGE_PLAY.
INNING_OVER: NORMAL, PRESENTATION, START_INNING_PRES, CHECK_SUB. GAME_OVER: NONE, MERCY_RULE, POST_GAME_MENU, PRES_GROUP_A, PRES_GROUP_B, PRES_REEL,
PRES_COPYRIGHT, REPLAY_VAULT, WAIT_FOR_MESSAGE. Home Run Derby has its own `HRDERBY_STATE_IN_PLAY` near `0x7001300000`.

| Address | What | Tag | Source |
|---|---|---|---|
| `0x700108b628` (1.0.15: use `tools/addrmap.py`) | BATTER_UP slot-5 handler (587 lines). At `main+0x108bbb4` it requested stadium lighting with force=1: the walk-up freeze | C | walkup-freeze.md |
| `0x700109a6a8` | PLAY_OVER WAIT handler; starts the background lighting bake after each play (calls `0x70012d20a0`) | C | walkup-freeze.md |
| `0x7000d52680` | advances the in-game time-of-day clock (about 17.5 s of game time per pitch, more per batter/inning) | C | walkup-freeze.md |
| `main+0xd514e0` (inside a function, not its entry) | game event handler code; event `0x220` turns frame-time averaging off, `0x61`/`0x11c`/`0x213` on | C | framerate.c |
| `main+0xd4f6e0` | copies the averaging byte right before the frame timer runs | C | framerate.c |
| `0x700000b140` | per-frame call that runs the lighting bake step (`0x70012e0150`) | C | walkup-freeze.md |

### Verified by reading the body of `0x700108b628` (BATTER_UP slot 5) [C]

`x19` = the BATTER_UP state object. `[x19+0x18]` holds the sub-state number: the handler compares it with 3 (then sets 4 and runs a small call) and with 1 (then calls
`0x700108c030`, the WALK_UP_PRES handler); otherwise it calls `0x700108cd24` (PLAYERS_SETUP); an earlier path calls `0x700108b500` (WALK_UP). So slot 5 dispatches to the
sub-state handlers listed above. Fields seen: `[x19+0x20]` a 32-bit value re-read each frame (change detection), `[x19+0x24]` a flag byte, `[x19+0x26]`, `[x19+0x28]`, `[x19+0x31]`, `[x19+0x32]` bytes.
It asks `0x70012c54ec` for the lighting manager then calls `0x70012d0fcc`; the generated code carries both the original `x1 = 1` (force) and the patched path under `rt_patch_on[0]`,
and a second `rt_patch_on[0]` block clears bit 9 of `[manager+0xd3c]` (patch site 3), matching `docs/walkup-freeze.md`. It also makes virtual calls through
objects (`[obj]->[+0x80]`, `[+0x60]`, `[+0x90]`, `[+0x1b0]`) that were not resolved. Everything else in the function (what the 70+ callees do) is unread.

## Stadium lighting and props (the walk-up freeze)

| Address | What | Tag |
|---|---|---|
| `0x70012c54ec` | returns the lighting manager (object 0x101e40 bytes). Fields: on-screen buffer `+0xd38`, bake flag word `+0xd3c`, dirty byte `+0xc2d`, times at `+0x101400 + 4*buffer` | C |
| `0x70012d0fcc(manager, force)` | request lighting for the current time | C |
| `0x70012d1e04` | lighting switch/bake decision: quick-switch to a finished spare buffer, else start a bake | C |
| `0x70012d20a0` | start the background bake (flags `0xec01`, one step a frame, ~50 frames) | C |
| `0x70012e0150` | runs a bake step; flag bit 9 (0x200) makes one call loop all ~50 steps with a GPU wait each | C |
| `0x700128d2a0` | indirect-light probes; refresh when the lighting-version counter (`0x7002ca9338`) changes | C |
| `0x70019fb800`, `0x70019fb880`, `0x70019fbbb0` | turn stadium props off/on at 19.5 h (17.0 h in months 0 and 12); table at `0x70021edca0` | C |

Patch `walkup_light`: 6 sites (`main+0x108bbb4`, `0x12d1f74`, `0x12d1f7c`, `0x12d1f84`, `0x12d1f98`, `0x108bbc0`; see `tools/data/patches-1.0.20.txt`). Result: frames over
100 ms in 30 pitches 27 -> 0.

## Broadcast "moments" and league leaders

| Address | What | Tag |
|---|---|---|
| `0x7000e5640c` | full refresh from the batter-up event (inning change) | C |
| `0x7000e54c00` | builds top-10 lists for 23 stats in 4 groups = 92 lists, each a pass over up to 1,350 players plus `qsort_r` | C |
| `0x7000e53620` | game-start sequence | C |
| `0x7000e53654` | clears the object, builds lists (`main+0xe53808` calls `0x7000e54c00`); the patch `walkup_leaders` nops that first build | C |
| `0x7000e543a4`, `0x7000e54080`, `0x7000e545f0` | build lists again first thing / write other fields | C |

## Input, saves, tutorials, storage

| Address | What | Tag | Source |
|---|---|---|---|
| `0x7001341c20` (1.0.15 `0x7001340720`) | pad update; repeats a held d-pad/stick; pad records array at `main+0x45aef28` (up to 8, 7 seen) | C | hid.c |
| `main+0x1343380` | PlayStation-to-Switch face-button map applied after `GetNpadState` (Switch A is circle, B cross, X triangle, Y square) | C | hid.c |
| `main+0x4a36f4` | `BUTTON_MASK_UI_ACCEPT` = `0x2000` (menus confirm with circle) | C | hid.c |
| `0x7000de7c28` | Road to the Show career autosave after a played game (no arguments) | C | rtts_autosave.c |
| `0x700045c724` | returns the career record; trigger tokens stored as u16 at `+0x12c0` | C | rtts_autosave.c |
| `0x70004c77bc` (slot `0x700217e580`) | runs once each time a full screen is entered | C | rtts_autosave.c |
| `0x7000bd1a4c` ... `0x7000bd35e0`, `0x7000bc0970`, `0x7000bc1708`, `0x7000bc611c` | the 11 hub menu commands that buy or refund upgrades (perks, tools, pitch upgrades) | C | rtts_autosave.c |
| `0x7003abfa98` -> `+0x198` -> `+0x318` | universal profile pointer chain; finished-tutorials list | C | tutorials.c |
| `0x7000a3357c` (1.0.15 `0x7000a32a5c`) | add a finished tutorial name to the profile and send the timed list to the server | C | tutorials.c |
| `0x7000570280` (1.0.15) | mounts cache storage 0 as `FS_GameData` | C | cache_storage.c |
| `0x7000570c50` (1.0.15) | the game's file layer (location 3 = cache storage) | C | cache_storage.c |
| `0x7000d197fc`, `0x7000d199bc` (1.0.15) | find / write custom batting cameras `CUSTOMCAMS_<n>.CAM` | C | cache_storage.c |
| `main+0xf020` .. `main+0xfa0c` | inline software keyboard wrapper state machine (Appear, ChangedString, DecidedEnter, Cancel) | C | swkbd.c |
| `main+0x152e844` | game modes menu asks the eShop for consumables (refused offline) | C | services.c |
| `main+0xaa201c` | time-zone rule request site | C | time.c |

## Frame timing (module offsets; add `0x7000000000`)

`main+0x58a9f0` frame timer; `+0x22ad028` vsync count (1 = 60 fps); `+0x22c90c4` time step; `+0x22c9078` averaging flag; `+0x2cb6150` timer carry.
1.0.15 offsets are `0x1000`-`0x20` lower (`k_addrs[]` in `framerate.c` has both).

## Dev-harness hooks

Match-settings struct pointer at `0x7004651350` (`main+0x4651350`); team ids written at home `+0x3f`, `+0x47`, `+0x59`, away `+0x40`, `+0x52`, `+0x54`, `+0x56`
(all copies must be written; writing one gave the wrong uniforms). Team ids: 0 BAL, 1 BOS, 2 NYY, 3 TB, 4 TOR, 5 CWS, 6 CLE, 7 DET, 8 KC, 9 MIN, 10 HOU, 11 LAA,
12 ATH (unconfirmed), 13 SEA, 14 TEX, 15 ATL, 16 MIA, 17 NYM, 18 PHI, 19 WSH, 20 CHC, 21 CIN, 22 MIL, 23 PIT, 24 STL, 25 AZ, 26 COL, 27 LAD, 28 SD, 29 SF.
Boot options (`BOOT/CONFIG_MAIN_USER.TXT`): `AIvAI` + `GameOnly` = AI-vs-AI match with no input; option names are matched by a 32-bit hash (see game-binary.md).

## Fielding, catching and running (body reads, 2026-11-23)

Read from the generated C; the detail is on [Fielding](Fielding). The block is built on a named "ring" per
character: a state function names its state in strings, then calls the shared ring entry.

| Address | What | Tag | Source |
|---|---|---|---|
| `0x70002696a0` | shared "Working ring" state entry; all 22 callers are per-state ring functions | C | string "ARB Working ring" |
| `0x700010b5c0` | selects a fielder's fly-ball time intervals | C | "Selecting flyball intervals for %d" |
| `0x7000117700` | rejects an interval it cannot reach | C | "Rejecting interval: %d [%.2f-%.2f]" |
| `0x7000271448` | "Get ball in ring": ball to fielder target, avoidance, throw and catch rings | C strings, I role | "Get ball in ring" |
| `0x70003915c8` | catch-attempt dispatcher: canned, then predictive, then working catch ring | C | calls `0x7000379ea0` first |
| `0x7000379ea0` / `0x700038b57c` | canned catch / deflection catch | C | the strings |
| `0x7000384a60` | the throw itself; called only by `0x70003908f0` and `0x7000391000` | C | "Throw" |
| `0x700032fd94` | runner advance/return/pickoff decision (8,427 lines, 129 callees) | C strings, I role | "RUNNER DECIDE %s foul = %s" |
| `0x700031d438` | runner update hub, 77 callees, no strings | I | call edges |
| `0x7000344134` | runner leadoff ring, 12 named states | C | "Runner Leadoff Ring" |
| `0x70002d0a40` | umpire safe/out call ring | C | "SAFE TURN", "OUT CALL" |

## Front-end, Road To The Show and the database layer

Detail on [Frontend](Frontend). The front end is a data-driven UI: `uiEngine` keeps a screen deque and one
worker prints the entry log; screens are C++ objects with a 14-slot vtable; cells bind to named properties.

| Address | What | Tag | Source |
|---|---|---|---|
| `0x700089c9e0` | screen switch worker; prints `uiEngine: Entering screen: [%s->%s (%d)]` | C | the string |
| `0x700089c720` | screen request by id (156 callers); `0xff` is the leave path | C | body |
| `0x70008bb110` | pad bits to 16-bit UI action (452 callers) | C | `LD32(x0+38) & 0x3f` |
| `0x70008a71f0` | pumps the next UI event from five providers | I | virtual calls `+0x80..+0xe0` |
| `0x70004c77bc` | per-screen entry hook, slot 2 of 14 in vtable `0x700217e570` | C | vtable |
| `0x70007fcc40`, `0x70007f4940`, `0x700084d070` | register 42 table, 22 list and 23 grid UI property names | C | `CURRENT_ROW`, `CELL_INDEX`, ... |
| `0x700085cb60` | `uiElementDataTable` update with a dirty mask | C | the Mask string |
| `0x700041a290` | loads `frontend//rtts//Goals.xml` | C | the path |
| `0x7000bd559c` | applies one hub upgrade and records `calendar_date` | C | the fields |
| `0x700181d2f0` | loads `Frontend\Stats\stats.bin` and its `_INJ` variant | C | the path |
| `0x700181b070` | database index lookup by player id | C | "GetDatabaseIndex looping over %d players" |

## Audio and commentary

Detail on [Audio](Audio). One software mix (Sony SCREAM) goes to `audout` as 48 kHz 6-channel PCM16; music,
PA, umpire and commentary are streams through the game's own 7-state slot machine.

| Address | What | Tag | Source |
|---|---|---|---|
| `0x70018cfd10` | `DeviceOut` thread: lists and opens audout, then loops the pump | C | "DeviceOut" |
| `0x70018d00e0` | drains the PCM ring into `nn::audio::AppendAudioOutBuffer` | C | the PLT call |
| `0x70003dde10` | stream slot state machine: 7 states, state number at `+0` | C | "Moving to STATE BUFFERING" |
| `0x70003df4b8` | manual fade: `snd_AutoGain` or state 6 plus a stop-pending byte | C | 48 callers |
| `0x70003d263c` | music bank names `Jukebox_%02d` and `Audio\%s.bnk` | C | the strings |
| `0x70021e07d8` | 129-entry play-by-play handler vtable (several copies exist) | C | vtable |
| `0x7000e37630` | `DoPickoffResultPXP`, a 1,444-line commentary handler. At offset `+0x3f0` it copies the event name with `strncpy`, then calls vtable slot 9 (`+0x48`) | C | "BaseResultHandler", "PitchGetsAwayResult", "PickoffStealResult" |

## The 119-slot actor API (47 tables)

Detail on [AI actor API](AI-actor-API). This family is not the AI's scoring code: it is the actor/play-control
interface that AI decision code calls through, and the role strings sit in the client code around it.

| Address | What | Tag | Source |
|---|---|---|---|
| `0x7002164248`-`0x700216f038` | 47 tables of 119 slots, stride `0x3c8`, one interface | C | vtable index |
| `0x70000b4ad4`-`0x70000b7cc4` | 119 public trampolines, one per slot | C | each calls the resolver |
| `0x70000b4b4c` | resolver: object to canonical table, through the array at `0x700216f3f0` | C | 119 callers |
| `0x70000b7d34`-`0x70000b8084` | the base table's 119 default stubs (return, or return 0) | C | bodies |
| slots 20-25 / 56-60 / 73-89 | catch / runner-steal / bat-pitch input clusters | I | callers' strings |

## Game records, telemetry and league leaders

Detail on [Game modes](Game-modes). The largest function is not a mode-to-handler table: it builds the
end-of-game telemetry record and derives the mode description from settings.

| Address | What | Tag | Source |
|---|---|---|---|
| `0x7000e0fb10` | end-of-game telemetry builder: 334 map entries, mode-name ladder, single caller `0x7000df7fc0` | C | body |
| `0x7000df7d2c` | formats `<TELEMETRY_MAN_ENDED PLAY_MODE=... GAME_MODE=...>` | C | the format |
| `0x7000df7fc0` | vtable `0x7002295ae0` slot 2: 2 team + 80 batter + 80 pitcher builder calls | C | body |
| `0x7000e54c00` | builds 92 league-leader lists: 23 stats in 4 groups | C | body |
| `0x70006753d0` | collects up to 1,350 players and qsorts them | C | `mov w9,#0x546` |
| `0x7000e5640c` | refreshes the leaders; builds twice, and 0.2.0's `walkup_leaders` nops the first | C | patch line |
| `0x7000eb72c0` | bare `ret` virtual, slot 4 of 32 game-state vtables | C | body |

## Animation and locomotion

Detail on [Lighting](Lighting) (which covers the animation core it found next door).

| Address | What | Tag | Source |
|---|---|---|---|
| `0x700140e900`-`0x7001437e00` | LocoManager: motion transitions, throttle, idles, ring containers | C strings, I extent | the strings |
| `0x70013af7fc` / `0x70013a8250` / `0x7001383e80` | `KineCore::CoreAnimationState::SetupNewAnimation` / `AnimWrap::InitByMem` / `Kinematics::Update` | C | names |
| `0x7000d4e560` | `LoadAnimBin`: loads an animation clip | C | the name |
| `0x7001500000`-`0x7001547fff` | studio online services (olClient, socket, OpenSSL), not animation | C | string themes |

## Corrections to earlier pages (2026-11-23)

| Claim | Correction | Tag | Source |
|---|---|---|---|
| the 119-slot vtable family is "the AI decision layer" (Region A, [I]) | it is the actor/play-control API the AI drives; 47 tables, not about 40, and no AI scoring inside | C | [AI actor API](AI-actor-API) |
| `0x7000e0fb10` is "the game-mode table" (game-binary.md) | an end-of-game telemetry builder that also maps settings to a mode description; the mode choice is that ladder | C | [Game modes](Game-modes) |
| `0x70012d20a0` "one step a frame, ~50 frames" (walkup-freeze.md) | flag `0xec01` confirmed; the bit-9 path loops all stages with a GPU wait, which the 1.0.20 stage code does not reconcile with 50 frames | C flag, open count | [Lighting](Lighting) |

## Teams, batting side and the live count object (2026-11-24, found while building the scenario tool)

| Address | What | Tag | Evidence |
|---|---|---|---|
| global `main+0x3aeb728` | pointer to the two-team table T: team object A at `T+0x18`, team object B at `T+0x20` | C | disassembly of `0xd1cd78` / `0xd1cd98` |
| byte `[B+0x124]` (B = `[T+0x20]`) | the BATTING side, 0 or 1: index of the batting team object in T | C | `0xd1cd78` returns `T[0x18 + 8*side]`; read live: write after the transition trick unproven |
| `0x700d1cd78` | `GetBattingTeam()`: `[T + 0x18 + 8 * byte([[T+0x20]+0x124])]` | C | disassembly |
| `0x700d1cd98` | `GetFieldingTeam()`: the other one: `[T + 0x18 + 8 * (byte == 0)]` | C | disassembly |
| `[teamobj+0x120]` | the team's id (0..29) | I | `0x7000e32230` (half-inning start) loads it from both accessors |
| `0x7000e32230` | half-inning start (`[HALF INNING]`, "Half Inning Start: Cleared Event Buffer"): resets per-half fields, calls both team accessors | C | strings, body |
| `0x7000fe0cd0` / `0x7000f94700` | lineup setup / pitcher intro for the half-inning (`[DefensiveLineup: ...]`, `[Pitcher Intro: ...]`) | C strings, I role | map_find |
| `[[main+0x227e6b8]]` = count object O | `+0x8` away score, `+0xc` home score, `+0x10` balls, `+0x14` strikes, `+0x18` outs, `+0x20` half-inning index (even top, odd bottom): all write-proven; `+0x19c/+0x1ac/+0x1bc` base array is rebuilt from the real runners within about 3 s | C (live writes) | `tools/scenario.py`, five passing scenarios |
| `0x70001824b74` | `GetConfig(k)`: byte `settings+0x3e+k`; k=1 home team, k=2 away team. The rosters, cards and scorebug follow them only when they are written as the menus leave team select (`tools/exhibition.py`); `f_7001824c18` is the matching SetConfig | C | live runs and screenshots |

## Main-menu data object (2026-11-24, hides the offline panel)

- `f_7000c0da4c` (vtable 0x70021bd438 slot 6) sets obj+0x129 (online) and obj+0x128 (server allows panels). [C, read, logged 0/0 offline]
- `f_7000c0dc6c` (slot 8) hands field values to the menu script; SHOW_DYNAMIC_PANELS = obj+0x129 && obj+0x128. [C]
- Fields of the class "GameModesMain" (slot 4 `f_7000c0df84`): HAS_ANNOUNCEMENTS, ANNOUNCMENT_NUMBER, SHOW_DYNAMIC_PANELS, STUBS_CAP (`f_7000c0d970`). [C]
- See docs/menu-offline-panel.md and runtime/mlb/menu_offline.c.
