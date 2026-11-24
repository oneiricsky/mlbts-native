# The game binary: what it is and where things are (1.0.20)

Per-region detail with evidence and tags: `docs/map/regions/*.md` (A to F, one file per address region). This file is the overview. Tags: [C] confirmed from a
string/symbol/measurement, [I] inferred, [H] guess. Addresses are `main` virtual addresses (`main` base `0x7000000000`).

## Facts about the program [C]

| Topic | Fact |
|---|---|
| Title | `0100AA7024094000`; 1.0.15 is update v983040, 1.0.20 is v1310720 |
| Modules | `main` (28.1 MiB text, 94,991 functions) and `sdk` (6.3 MiB text, 40,069); no `subsdk` |
| Engine | Sony San Diego's in-house engine descended from the PS3 era (build paths `c:/Jenkins/workspace/MLB26PATCH/BRANCHES/MLB26_PATCH/MLBPS3/SRC/...`), native NVN renderer; not Nintendo's sead |
| Libraries in `main` | libc++ (nnmusl libc), OpenSSL, libcurl, libwebp, nlohmann JSON, mini-XML, Opus, zlib, stb_image, EXR, Dear ImGui (debug), Lua 5.3, RAD Bink/Bink 2 (decoded by the game, no host decoder), Sony SCREAM audio with a `wws_gattaca` DSP graph, libfvad |
| SDK | 19.3.11 (NVN 19.3.11); `main` makes no SVCs, every OS call goes through `sdk` (58 `svc` sites); 765 imports from `sdk`; 124 exported symbols in `main`, 39 of them code (nnMain, new/delete, malloc family, a few libc++ methods) |
| CPU | ARMv8.0-A only (no LSE atomics, no SVE); heavy `thread_local` (2,543 TPIDR_EL0 reads); 499,842 scalar FP instructions and about 30k FMA (fused rounding must be exact); `blr` 38,320 and `br` 8,104 in `main` |
| Generated code | `main`: 3,659 jump tables, 4,345 `br` through `rt_dispatch`, 1,370 materialised targets; about 540 MB of C in 198 chunks |
| RomFS (1.0.20) | 86,235 files, 37.9 GB: `NSW/` (Switch assets: textures `.TEX`, models `.MOD`, shaders `NSW/SHADERS/*.FXBNVN`, audio `.SKX`), `PS4/` (shared animation `.xbn`), `PS5/`, `CROSS/` (movies, stadium audio), `FRONTEND/`, `BOOT/CONFIG_MAIN.TXT` |
| Formats | textures are `TX12NSW` containers (LZ4 blocks of block-linear data), PS5 files `TX12PS5` (raw); UI screens are movies (`.webp` art), logged as `uiEngine: Entering screen: [...]` |

## Address map of `main` (windows of 256 KB = 0x40000)

Where the linker placed things. Boundaries are approximate (to the window) unless a specific address is given. Functions per region and detail are in the region notes.

| Range | Contents | Tag | Note |
|---|---|---|---|
| `0x7000000000`-`0x70000fffff` | `_init`/`_fini`, `nnMain` (`0x7000000880`), then third-party/utility code: ASTC codec (~`0x700001e2e0`), nlohmann JSON, stb_image, tinyexr (`0x70001ecb90`), scene/mesh loading with mesh repair (`0x7000096960`, "smesh is not manifold") and the MSDF generator (`0x7000095390`, correction pass `0x7000030ec0`) | C | A |
| `0x7000100000`-`0x70003fffff` | core match simulation and AI: fielding, throwing, catching, baserunning, batting reaction (strings STANDING, WATCH, Catcher, Swing reaction, Leadoff, BounceAnalyzer); a family of 47 AI class vtables of 119 slots each with role strings such as "ONLINE AI BATTER" (`0x70000c6f20`) and "ONLINE RUNNER DECISION" | I (names C) | A |
| `0x7000380000`-`0x7000400000` | audio playlists/streams | I | A |
| `0x7000400000`-`0x7000500000` | UI/frontend, player cards, stats, calendar/rewards | I | A |
| `0x7000500000`-`0x70005fffff` | engine core: memory (`0x700055a820` allocator, `operator new/delete` `0x70005b30a0`/`0x70005b19d0`, `nninitStartup` `0x70005b19e0`), assertions, file layer (`0x7000570c50` in 1.0.15), NVN wrappers/GPU wait (`0x70005a1a90`), render sizes (`0x70005a5388`), ImGui | C | A |
| `0x7000600000`-`0x70006fffff` | Flux archive + nlohmann JSON serialization, parsers, create-player front end, presentation engine (cutscenes: PresEngineBase, SceneBase) | C/I | B |
| `0x7000700000`-`0x70008fffff` | roster moves, franchise setup, trades/strategy/uniforms, player data tables (`D_PLR_PROFILE`, `D_PLYR_CONTRACT`), UI widgets and rendering (glow/blur/tables) | I | B |
| `0x7000900000`-`0x7000bbffff` | online and Diamond Dynasty (out of scope): CPartyManager, CNetSessionManager, CPluginAuth, CRosterCache, CContentDownloader, CVaultView, leaderboards, mini-season; the offline universal profile is here too | C | B |
| `0x7000bc0000`-`0x7000bfffff` | Road to the Show attributes/tokens/perks/college hub (the 11 upgrade commands around `0x7000bd1a4c`-`0x7000bd35e0`) | C | B |
| `0x7000c00000`-`0x7000d3ffff` | league/team/player database screens, challenges, storylines, trades and free agency, inventory, crowd audio data | I | C |
| `0x7000d40000`-`0x7000e00000` | replay vault and camera editor, in-game HUD action groups, game session/telemetry, ambience; the time-of-day clock (`0x7000d52680`) and game event handler (`main+0xd514e0`) | I/C | C |
| `0x7000e00000`-`0x7000efffff` | game-mode table (`0x7000e0fb10`, 21,030 generated lines, the largest function), end-of-game and end-of-plate-appearance summaries, records/awards text, broadcast leaders (`0x7000e54c00`), base game-state stubs (`0x7000eb72c0`) | C/I | C |
| `0x7000f00000`-`0x7000ffffff` | pitching/bullpen/substitution UI, play-by-play commentary events (PXP_RF, pxp_milb: PitcherHit, RunnerScores, CatchFly) | C | C |
| `0x7001000000`-`0x70010fffff` | game flow: the 12 game-state classes and their handlers (`0x700106d054`-`0x70010a3b5c`), crowd audio, quick-sim results | C | D |
| `0x7001100000`-`0x70012fffff` | libwebp (~`0x70011468b0`), mini-XML, Flux class registry, stadium lighting manager (`0x70012c54ec`, `0x70012d....`, `0x70012e0150`), indirect-light probes (`0x700128d2a0`) | C | D |
| `0x7001300000`-`0x70013fffff` | Home Run Derby state machine (`0x700133da9c`), pad update (`0x7001341c20`), batter streaming, saves, animation core | C | D |
| `0x7001400000`-`0x7001547fff` | animation/locomotion (LocoManager), engine base objects (streams, event sources, ClassManager), game objects (ball, bat, stadium), studio online-services client (olClient, olPlatform, nifm) | C/I | E |
| `0x7001548000`-`0x7001648000` | OpenSSL (crypto, EVP, X.509, TLS) | C | E |
| `0x7001650000`-`0x70017bffff` | network error dialogs, character creation (face scan), character/equipment/uniform asset names, textures/materials, presentation playback and commentary text | C/I | E |
| `0x70017c0000`-`0x70017fffff` | 4,710 functions, 93% under 18 lines: C++ class boilerplate (getters, factories, destructors; 88% in vtables) + player-appearance/season-record serializers | I | E |
| `0x7001800000`-`0x70018bffff` | frontend/stats/rosters (3,200 functions), in-game substitution/inning logic (`SubstitutionLogic`), "Halyard" dev-service client | C/I | F |
| `0x70018c0000`-`0x7001a3ffff` | voice chat + libfvad, nlohmann JSON, stadium grass/field/college stadium table, Flux class registry, world/camera/lighting objects | C/I | F |
| `0x7001a40000`-`0x7001a7ffff` | libcurl | I | E/F |
| `0x7001a80000`-`0x7001bfffff` | Sony SCREAM audio and `wws_gattaca` DSP graph | C | F |
| `0x7001c00000`-`0x7001c227e0` | Bink async decode threads; libc/allocator (`malloc` `0x7001c1f920`...); 733 import thunks (9 lines each, jump through the table at `0x70022ab000`; hottest `0x7001c1fb70` 2,215 callers) | C | F |

Data: vtables of the game-state classes at `0x70021d7400`-`0x70021e3538`; class-broker/boilerplate vtables near `0x700223a550`; a 1025-slot vtable at `0x700215c000` unidentified (region C);
stadium props table `0x70021edca0`; import table `0x70022ab000`; globals pointer to universal profile `0x7003abfa98`; match settings pointer `0x7004651350`; pad records `0x70045aef28`.

## `sdk` module groups (named functions, from region F) [C]

nn::audio 1,427; nn::fs / file system 1,300; input (nn::hid and related) 1,351; accounts/network/crypto 3,238; SDK core 2,448; C++ runtime 1,465; NVIDIA GPU driver layer 790. NVN is only a handful of
named entry points around `0x70050b0000`-`0x70050f0bb0`; the rest are unnamed, so which game code calls which NVN function is not mapped. `main` looks procs up by name through
`nvnBootstrapLoader` (the table of 536 proc names is in `main`; 534 match TotK's list), so the port's `nvn_procs.c` hands out host functions by name. `0x700059a690` holds NVN entry-point names [I].

## How the game is organised

What the strings and vtables prove:

| Part | Evidence |
|---|---|
| Game flow | a state machine of 12 classes sharing one interface (see Known game functions); sub-states logged as `GAME_STATE_<X>: state = <Y>` |
| UI | a movie and scene engine; front-end screens run on data tables and string-keyed fields (`CURRENT_ROW`, `CELL_INDEX`, `uiElementDataTable`) |
| Reflection | "Flux": the `FluxClassBroker_T<X>` registry, `DEFINE_CLASSLABEL`, `Method_Broadcaster` (204 uses), the studio's tool-facing class system and the reason there is no RTTI; `YourClassName` is placeholder text from a code-comment template, not a class |
| Data | player, team and league data in named tables (`D_PLR_PROFILE`, `D_PLYR_CONTRACT`, `LG_STATS_DATA`, `D_SINGLE_G_DATA`), serialized through Flux archives and JSON |
| Commentary | play-by-play `PXP` events pick phrases per play; audio banks `PXP.SKX` (3.9 GB) on disk; text generators for records and awards; Sony SCREAM mixes in software and sends one 5.1 stream |
| Online | `ol*`, `CNet*` and `CPlugin*` classes over libcurl, OpenSSL and nifm; offline play follows the "no network" paths; a few online-profile behaviours leak into offline play (tutorials list, hub upgrade autosave, cache storage) |
| Config | `BOOT/CONFIG_MAIN(_USER).TXT` bare lines turn options on, matched by 32-bit hash (`AIvAI` 0xAA21F9C5 with `GameOnly` 0xC6F7ECA5 starts an AI match with no input; 27 of 109 queried hashes are named); three config-query functions, 319 call sites |
| Time of day | advances per pitch; stadium lighting is re-baked per new time into one of two buffers; stadium props flip at 19.5 h |
| Coverage | about 12,800 of 94,991 `main` functions reference a string; the rest are known by neighbours, vtable slots, callers and size |

## What is not mapped
Contents of the import table `0x70022ab000` (which libc/SDK function each thunk reaches); NVN call sites; the 1,025-slot vtable at `0x700215c000`; meaning of `s9Amp`; the gameplay physics/AI internals (no strings);
class names (no RTTI). Region notes list their own "Unknown / not examined" sections.
