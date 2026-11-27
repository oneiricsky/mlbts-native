# Modes, summaries and records: main 0x7000e00000-0x7000f00000

Read-only pass over game 1.0.20 (`main` base 0x7000000000) using `tools/map_find.py`, `tools/disasm.py`, a
string-reference scan (`tools/fnxref.py` gives the per-function, code-order version) and the generated C in
`work/gen/`. Nothing in the repo was
changed and the game was not run. Every claim is tagged [C] (string, symbol or code read), [I] (strong pattern) or
[H] (guess); generated-C line numbers are 1.0.20's.

## Summary

| Item | Detail |
|---|---|
| Block role | This block is the game's **telemetry / game-record block**, not a menu of mode handlers. |
| Record builder | 0x7000e0fb10, the biggest function in `main` (21,030 generated lines), builds one named telemetry event per record: it fills a local `std::map<std::string,std::string>` with 334 inlined `map[key] = value` pairs (388 distinct strings: 164 `stat_*`, 46 `pinpoint_*`, 12 `option_*`, mode/team/player fields), then hands the map to f_7000df63a0, which emits it under a section name. |
| Payload | Its caller f_7000df7fc0 is reached from f_7000df7d2c, which formats `<TELEMETRY_MAN_ENDED PLAY_MODE="%d" GAME_MODE="%d" GAME_UUID="%s" >`: the map is a telemetry payload. The "mode" part is a ladder of 19 display-name strings ("HR Derby" … "Other") chosen from two global settings, not handlers. |
| Sibling builders | 0x7000e03ea0 (end of game) and 0x7000e07820 (end of plate appearance) fill the same kind of map and emit "EndOfGameSummary" / "EndPlateAppearanceSummary". |
| Leaders | The leader object at 0x7000e54c00 is 92 top-10 lists (4 groups × 23 stats, 10 × 0x30 bytes each) filled by f_70006753d0 from up to 1350 players and a `qsort`; 0.2.0's `walkup_leaders` patch removes the first of two identical builds in f_7000e5640c. |

## The big function (0x7000e0fb10)

### What it is

| Item | Finding | Tag |
|---|---|---|
| Shape | One function, not a table of mode ids to handlers: 21,030 generated lines, one direct caller (0x7000df7fc0), 57 direct callees, 2 indirect branches (`"rt_dispatch"`). | [C] |
| Callees | The 57 callees are shared machinery, not per-mode functions: record resolution (0x70001db950, 0x70001f9560), `std::map` lookup/insert (0x70000e8a00), `std::string` assign (0x70000e3b50), `std::to_string` (0x7001c20270), string construction/destruction, the global-setting getter (0x7001824b74), and a handful of 14-line predicates. | [C] |
| Dispatch | There is no call through a mode id and no array of function pointers. | [C] |
| Switch 1 | The two indirect branches are enum-to-label switches: `switch (c->x[10]) { case 0x7000e13234ull … }` (main_0099.c:3810) on a value at `sp+0x2d0` with four cases, "Directional" (3814), "Timing" (3864), "Zone" (3868), "CPU" (3872) and default "None" (3818), for the `batter_interface` key. | [C] |
| Switch 2 | main_0099.c:3923 for `pitcher_interface` (six cases "Classic"/"None"/"Meter"/"Pinpoint"/"Pulse"/"Analog", default "CPU"). These are setting labels, not modes. | [C] |
| Naming | The strings that suggested "game-mode table" are the 19 mode display names in the opening ladder. They are values written into one map key, `game_mode_description`. | [C] |

### Structure

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| Signature | f_7000e0fb10 | main_0099.c:78 | The function takes (x0 = context object, x1 = record kind, x2 = index) and allocates `sp_ - 0x740`. | [C] |
| Local map | f_7000e0fb10 | main_0099.c:83 zeroes its header | Builds a local `std::map` at `x29-0x68`. | [C] |
| Destroy | f_70000e895c | main_0099.c:21077 | Destroys the map with the recursive tree destructor f_70000e895c at the end. | [C] |
| Node format | f_70000e8a00 | disasm 0xe8af4 `mov w1, #0x50` | Read from f_70000e8a00: nodes are 0x50 bytes, the key is a 24-byte libc++ `std::string` at node+0x20 and the value is another at node+0x38. | [C] |
| Pair step 1 | f_70000e8a00 | main_0099.c:619 | `f_70000e8a00(c);`: map[key] node (returns node in x0). The function's pattern is always this pair of steps. | [C] |
| Pair step 2 | | main_0099.c:620 | `x0 = x0 + 0x38;` | [C] |
| Pair step 3 | f_70000e3b50 | main_0099.c:622 | `f_70000e3b50(c);`: assign node+0x38 (the value string). | [C] |
| Inlining | f_70000e8a00 | 334 sequences | 334 such lookup+assign sequences are inlined. | [C] |
| String table | | 388 distinct strings | The string table behind them has 388 distinct strings (164 `stat_*`, 46 `pinpoint_*`, 12 `option_*`, plus `batter_*`, `pitcher_*`, `game_mode`, `play_mode`, `home_score`, …). | [C] |
| Key building | | main_0099.c:603-617 | Keys are built in place as libc++ short strings: e.g. `x9 = 0x1c` (28 = 14<<1) then the bytes of "pitches_played". | [C] |

### One entry, end to end

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| Read counter | `pitches_played` | main_0099.c:581-622; `LD32(sp_ + 0x3ec)` at line 581 | Read a 32-bit counter from the incoming record. | [C] |
| Convert | f_7001c20270 | lines 582-597 | `std::to_string`, sret buffer in x8. | [C] |
| Build key | 0x7001c4ca29 | lines 603-617 | Build the key "pitches_played". | [C] |
| Lookup | f_70000e8a00 | line 619 | `map[key]` node. | [C] |
| Assign | f_70000e3b50 | line 622 | Assign the temporary. | [C] |
| Free | | line 622 | Free the temporary. | [C] |
| Next key | `pitches_simmed` | `LD32(sp_ + 0x2a8)`, line 641, key at 0x7001d063f3 | The next key is the same block reading another stack slot. | [C] |
| Bookkeeping | 0x70005b19d0 | 310 sites in this function | After each assign the code tests the temporary string's SSO flag and, if it owns heap memory, calls `operator delete`; that is why the function is so large: each field costs ~60 generated lines. | [C] |

### How a mode is chosen

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| Resolve record | f_70001db950, f_70001f9560 | main_0099.c:87-122 | With x1 (record kind) 0, 1 or 2 it calls f_70001db950 and f_70001f9560, and leaves through 0x7000e23264 if the resolved index is not positive or the flag at `sp+0x370` is clear. | [C] |
| Kind mapping | tail dispatch | main_0099.c:21029-21068; non-Mbl twin at 20795-20804 | Kind 0 = team, 1 = batter, 2 = pitcher: `if ((uint32_t)x28 == 0) goto L_7000e23200;` for "MblEndGameTeams", x28 == 1 for "MblEndGameBatters", x28 == 2 for "MblEndGamePitchers". | [C] |
| Settings getter | f_7001824b74 | jump table for n = 0x54..0x63 | All predicates in the ladder below read `f_7001824b74`, the global settings getter; `f_7001824b74(n)` returns a u16 field of the settings object. | [C] |

Then the mode display name is selected by this ladder:

| Setting test | Name written | Line | Tag |
|---|---|---|---|
| `GetSetting(0) == 3` | "HR Derby" | 130 | [C] |
| `GetSetting(0x48) > 0` | "Retro Mode" | 135 | [C] |
| `GetSetting(0) == 6` | "Demo Mode" | 142 | [C] |
| `GetSetting(0) == 4` | "Spring Training" | 199 | [C] |
| moments object exists | "Moments" | 205 | [C] |
| `GetSetting(0x13) == 5` | "Playoffs" | 214 | [C] |
| `GetSetting(0x13) == 1` | "Season" | 223 | [C] |
| `GetSetting(0x13) == 3` | "Franchise" | 232 | [C] |
| `GetSetting(0x13) == 4` | "RTTS" | 241 | [C] |
| predicate 0x7000e077e0 | "Challenge of the Week" | 247 | [C] |
| `GetSetting(0x13) != 6` and coop object | "Non-DD Co-op" | 263 | [C] |
| `GetSetting(0) == 5` | "Exhibition" | 276 | [C] |
| `GetSetting(0x13) == 7` | "League" | 285 | [C] |
| `GetSetting(0x13) == 8` | "Live" | 294 | [C] |
| `GetSetting(0) == 8` | "Training Modes" | 303 | [C] |
| DD and `GetSetting(4) == 3` | "Diamond Dynasty 3-innings" | 313 | [C] |
| DD (`GetSetting(0x13) == 6`) | "Diamond Dynasty" | 319 | [C] |
| 0x70018881c0 (RTTS + training + option) | "Custom Practice" | 325 | [C] |
| otherwise | "Other" | 329 | [C] |

After the ladder, the chosen name and the numeric mode ids go into their keys:

| Item | Detail | Evidence | Tag |
|---|---|---|---|
| Chosen name | The chosen name is written as `map["game_mode_description"]` (key at 0x7001d1a92d). | main_0099.c:334-349 | [C] |
| Other keys | Then `game_id` (0x7000e0ff78, 7 chars), `game_mode` (0x7000e100f8) and `play_mode` (0x7000e101e8) as numeric strings. | | [C] |
| Duplicate | The same ladder, with the same 19 names, is duplicated inside the end-of-game summary. | main_0096.c:8436-8620 | [C] |

### Emission

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| Pass map | f_7000df63a0 | main_0099.c:21069-21072 | At the end the map is passed with a `{ptr,len}` section name: `x1 = x29-0x68; x0 = {ptr,len}; f_7000df63a0(c)`. | [C] |
| Iterate | f_7000df63a0 | main_0094.c:43285-43306 | Iterates the map (node key at +0x20, value at +0x38, children +0/+8/+0x10). | [C] |
| Append | f_7000a3bcac | begin/end calls f_7000a3c6e8 / f_7000a3b7e0 / f_7000a3c190 | Appends each pair, wrapped by the begin/end calls. | [C] |
| Section name | "EndGameTeams" (12), "EndGameBatters" (14) or "EndGamePitchers" (15) | live path | These names are used on the live path. | [C] |
| Mbl names | "MblEndGame*" names (17/15/18) | disasm 0xa7fa0: `mov w0, wzr; ret` | Sit on a branch guarded by f_70000a7fa0, which is a stub returning 0. | [C] |
| Caller chain | f_7000e0fb10 ← f_7000df7fc0 only | vtable 0x7002295ae0 (5 slots), slot 2; main_0094.c:45205 | f_7000df7fc0 is slot 2 and is called by f_7000df7d2c, which builds telemetry XML including `<TELEMETRY_MAN_ENDED PLAY_MODE="%d" GAME_MODE="%d" GAME_UUID="%s" >`, `AudioInGameInfoExit`, `PresentationInfoExit`, `FrameRateSummary` and then calls f_7000df7fc0. So the map is a telemetry payload. | [I] |

## End-of-game summary (0x7000e03ea0)

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| Shape | f_7000e03ea0 | | Same shape: local map, ~40 fields, emit, destroy. | [C] |
| Event name | f_70000a7fa0 | main_0096.c:4737-4745 | The event name is chosen at the top: `f_70000a7fa0()` false → "EndOfGameSummary" (0x7001c801cd), true → "MblEndOfGameSummary" (0x7001cad3ef). | [C] |
| Key | f_70000a7fa0 | 0x7001c9a768, line 4749; main_0096.c:8416-8424 | Written as key "event_type" and reused as the section name at the end. | [C] |
| Shipped name | f_70000a7fa0 | | Since f_70000a7fa0 is a stub returning 0, the shipped build says "EndOfGameSummary". | [C] |

### Values

Each value is `std::to_string(...)` into the map; the row tag covers the whole entry.

| Key | Source | Line | Tag |
|---|---|---|---|
| `arena_submode` / "Not Arena" | arena object or the literal "Not Arena" | 4810 | [C] |
| `average_ping` | 32-bit value | 4946 | [C] |
| `away_control` / `home_control` | control flags | 5274 / 5338 | [C] |
| `local_player_count` / `online_players` / `player_count` | counters | 5400 / 5464 / 5535 | [C] |
| `home_team` / `away_team` | team ids | 5608 / 5671 | [C] |
| `league_id` | league id | 6077 | [C] |
| `home_overall` / `away_overall` | team overalls | 6173 / 6237 | [C] |
| `home_score` | `LD32([game_state->[0] + 0xc])` (source 6278, key 6299) | 6278-6317 | [C] |
| `away_score` | `LD32([game_state->[0] + 0x8])` (source 6341, key 6362) | 6341-6379 | [C] |
| `opponent_id` | opponent id | 6481 | [C] |
| `game_time_sec` | elapsed seconds | 6695 | [C] |
| `game_over` | byte `[game_state->[0] + 0x128]` (source 7005, key 7025) | 7005-7042 | [C] |
| `play_mode` | `GetSetting(0)` | 7160 | [C] |
| `local_player_win` | see below (key 7240) | 7198-7257 | [C] |
| `game_mode` | `GetSetting(0x13)` | 7323 | [C] |
| `game_mode_description` | the 19-name ladder | 8436-8620 | [C] |
| `moment_id` / `moment_name` | Moments fields | 7464 / 7511 | [C] |
| `current_year` / `year_offset` / `season_date` | franchise calendar | 7609 / 7677 / 7746 | [C] |
| `stadium_id` / `training_data` / `training_mode` / `user_overall` / `matchuuid` / `minigame_type` | assorted | 7811 / 7869 / 7932 / 8008 / 8061 / 8134 | [C] |
| `OnlineQueryView` / `GLOBAL_TC_RANK` / `player` / `rank` | online rank block | 8369-8390 | [C] |

### local_player_win

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| Only computation | `local_player_win` | key 7240; main_0096.c:7210-7213 | If `game_over` is 0 the answer is 0; otherwise it compares away score with home score to pick the winning team index (`CC_LE` → 0 else 1), walks to that team's record through the global at 0x700227e128, reads the team id at +0x128, and returns 0 only when that id is 4 or 5: the code computes `(id - 6) + 2` and maps the carry to 0. | [C] |
| 4/5 exclusion | | not known | The meaning of the 4/5 exclusion is not known; it is not a plain "id ≥ 6" test. | [H] |

### Text produced

| Item | Detail | Tag |
|---|---|---|
| Values | All values are decimal strings or ids except the event name and the mode name. | [C] |
| Prose | There is no sentence building here; the prose lives in the records/awards functions (0x7000e8xxxx). | [C] |

## End-of-plate-appearance summary (0x7000e07820)

### Event name

| Field | Value | Evidence | Tag |
|---|---|---|---|
| Shape | Same shape as the other two builders | | [C] |
| Event name | "EndPlateAppearanceSummary" (0x7001d5a250) or "MblEndPlateAppearanceSummary" (0x7001d06387) | main_0097.c:0x7000e079b8/0x7000e079c4 | [C] |
| Shipped name | The Mbl choice is again behind the f_70000a7fa0 stub, so the shipped build uses the non-Mbl name. | | [C] |

### Fields

| Field | Note | Tag |
|---|---|---|
| `play_mode`, `half_inning`, `event_type` | | [C] |
| `batter_interface` | enum→label switch; the scan finds "Directional", "Timing", "Zone", "Fixed Zone", "Big Zone", "CPU" and "None" in this function, more cases than in 0x7000e0fb10 | [C] |
| `checksum_plateappearance_also_pitch` / `_swing` / `_intentionalwalk`, `checksum_plateappearance_inning` | | [C] |
| `at_bat_scored`, `runs_awarded`, `plate_appearance_id`, `bases_occupied_pre`/`_post`, `bear_down_pitching` | | [C] |
| `used_guess_type_pitch` / `used_guess_zone_pitch`, `guess_type_pitch_result` / `guess_zone_pitch_result`, `pci_*`, `ambush_hitting_*`, `swing_*`, `pitch_*`, `launch_angle`, `hit_distance`, `first_bounce_x/z` | | [C] |
| `local_control`/`remote_control`, `active_card_effects`, `leverage_index`, `win_expectancy`/`_post`, `count_*`, `total_swings` | | [C] |
| `batter_attribute_*`, `pitcher_attribute_*`, DD item/series ids, `is_online`, `hitting_difficulty`, `pitching_difficulty`, and the shared stat keys | | [C] |

### Text produced

| Field | Key | Source | Tag |
|---|---|---|---|
| `ballpip_type` | 0x7001c431e1 (main_0097.c:5002) | A real enum→text conversion, chosen from bits 6/7/8/10/12/18 of the play flags (main_0097.c:4975-4983). | [C] |
| `ballhitscored_type` | 0x7001c6f5e3 (main_0097.c:5068) | The matching hit variant. | [C] |

| Field | Values | Addresses | Tag |
|---|---|---|---|
| `ballpip_type` | "Popup", "Flyball", "Linedrive", "Groundball", "Drag Bunt", "Sacrifice", "Other" | 0x7001c49894, 0x7001d0de37, 0x7001cfb12d, 0x7001cd2fcb, 0x7001c7d1c7, 0x7001d0dfe8 | [C] |
| `ballhitscored_type` | "Popup Hit", "Flyball Hit", "Linedrive Hit", "Groundball Hit", "Drag Bunt Hit", "Sacrifice Attempt Hit", "Other" | | [C] |

## League leaders (0x7000e54c00 / 0x7000e53654)

| Item | Finding | Evidence | Tag |
|---|---|---|---|
| Lists | `f_7000e54c00` initialises **92 top-10 lists**: four consecutive loops with `x19 = 0x17` (23) and entries 0x1e0 bytes apart (main_0101.c:5358-5442), at bases this+0x1b0b8, +0x1dd88, +0x208a8 and +0x233c8. | main_0101.c:5358-5442 | [C] |
| List layout | 4 × 23 = 92; each list is 0x1e0 = 10 × 0x30 bytes. Three gaps are 0x2b20 = 23 × 0x1e0; the first is 0x2cd0. | | [C] |
| Group stride | The collector's group stride is 0x2b20. | disasm 0xe5509c `mov w10, #0x2b20` | [C] |
| Stat type | For each of the 23 stats it picks a stat type from a 23-byte table at 0x7001d96784 (`switch` at main_0101.c:5526; bytes 0x69,0x00,0x04,…,0x64 are jump-table offsets). | main_0101.c:5526 | [C] |
| Collector call | Then calls f_70006753d0 with count 10 (`c->x[5] = 0xa`, main_0101.c:5660; call at 5666) and copies at most 10 entries back into the list (`cmp w21, #9`, main_0101.c:5673; stride 0x30 at 5808/5918). | main_0101.c:5660/5666/5673 | [C] |
| Collector | `f_70006753d0` (main_0050.c:8687) is the collector: it accepts up to **1350 players** (`mov w9, #0x546` in main_0050.c:8713, compared with 0x546 at 8776/8842/8906/9039/9086), and sorts them with libc `qsort` (`bl #0x1c20160 ; plt qsort` at 0x67574c; generated main_0050.c:8940). | main_0050.c:8687/8713/8940; 0x67574c | [C] |
| Groups | The 4 groups are the four leader boards the broadcast layer shows (the game keeps a "moments" top-10 list per stat per group). | | [I] |
| Clear and build | `f_7000e53654` clears the object and builds the lists: the call to f_7000e54c00 is at main+0xe53808 and is **already patched in the generated code**: `if (rt_patch_on[1]) { /* hint */ } else { … f_7000e54c00(c); … }` (main_0101.c:4013). | main_0101.c:4013 | [C] |
| Second build | `f_7000e543a4` (main_0101.c:4781) also calls f_7000e54c00. | main_0101.c:4781 | [C] |
| Inning-change refresh | `f_7000e5640c` (the inning-change refresh, called only by the PXP driver 0x7000e59c50) calls f_7000e53654 at main_0101.c:7091 and f_7000e543a4 at 7095, i.e. it builds the lists twice. | main_0101.c:7091/7095 | [C] |
| Patch | That double build is why 0.2.0 patches one call out. `tools/data/patches-1.0.20.txt`, set `walkup_leaders`: "The broadcast 'moments' system keeps top-10 lists for 23 stats in 4 groups (f_7000e54c00: 92 lists, each a pass over up to 1350 players and a qsort_r). Its full refresh f_7000e5640c … and its game-start sequence f_7000e53620 both call f_7000e53654, which clears the whole object and builds the lists (main+0xe53808), and then f_7000e543a4, which builds them again first thing (main+0xe543d0) … The site drops the first build." | `tools/data/patches-1.0.20.txt` | [C] |
| Site | The site is `site walkup_leaders main e53808 940004fe d503201f` (bl → nop), setting `MLB_WALKUP_LEADERS`, default 1 (`runtime/mlb/cfg.c:37`). | `runtime/mlb/cfg.c:37` | [C] |
| Unverified | I did not verify the claim that nothing reads the lists in between; the patch text says so, and the generated code shows the dropped call, but the read-range argument is the doc's, not re-derived here. | | [C] |

## Functions

Rows are function entries (verified in `work/map/index/generated_functions.jsonl`). "Evidence" quotes the exact
string, disassembly or generated-C line that supports the role; the tag applies to the role.

| Address | Role | Tag | Evidence |
|---|---|---|---|
| 0x7000e0fb10 | Builds one game-record telemetry event: local map of 334 key→text fields, 19-name mode ladder, section name at end | [C] | 21,030L; `334` × `f_70000e8a00`+`f_70000e3b50`; main_0099.c:21069-21072; "game_mode_description" |
| 0x7000df7fc0 | Drives the record builder: 2 team calls, the end-of-game summary, then 80 batter + 80 pitcher calls; vtable 0x7002295ae0 slot 2 | [C] | main_0094.c:45245-45335; callers=1; `f_7000e0fb10` ×162, `f_7000e03ea0` ×1 |
| 0x7000df7d2c | Telemetry emitter: formats audio/presentation/frame-rate XML and `<TELEMETRY_MAN_ENDED …>` | [C] | `'<TELEMETRY_MAN_ENDED PLAY_MODE="%d" GAME_MODE="%d" GAME_UUID="%s" >'`; `'FrameRateSummary'`; calls f_7000df7fc0 at main_0094.c:45205 |
| 0x7000df63a0 | Emits a named telemetry event from a `std::map` (iterates key+0x20 / value+0x38) | [C] | main_0094.c:43285-43306; callees `'data'`, `'event_type'`; 112 callers |
| 0x70000e8a00 | `std::map<std::string,std::string>` node lookup/insert (0x50-byte node, key +0x20, value +0x38) | [C] | disasm 0xe8af4 `mov w1,#0x50`; `memcmp` at 0xe8a90; main_0099.c:619 |
| 0x70000e3b50 | Assigns a `std::string` value into map node +0x38 | [C] | main_0099.c:622; callees 0x70000e3c74/0x7001c1fc40/0x70000e3894 |
| 0x70000e895c | Recursive `std::map` destructor (frees left/right, key, value, node) | [C] | disasm 0xe895c recursion; main_0099.c:21077 |
| 0x70000e0e58 | Constructs a `std::string` from a C string (used for every key and label) | [C] | 105 callers; main_0099.c:333; disasm builds SSO |
| 0x70000e38a8 | Builds a temporary `std::string` from (data,length) for the value side | [C] | main_0099.c:597; 342 callers |
| 0x7001c20270 | `std::to_string(int)` (sret buffer in x8) | [C] | 117 callers; main_0099.c:465/586; disasm writes SSO in x8 |
| 0x7001c1fc30 | `std::string` size accessor (length from SSO/pointer) | [C] | 2035 callers; main_0099.c:472 |
| 0x7001824b74 | Global settings getter: returns a u16 field, jump table for indices 0x54..0x63 | [C] | disasm 0x1824b74 `ldrh w0,[x9,#0x2e]` etc.; 2265 callers |
| 0x7000e03ea0 | Builds the end-of-game summary: ~40 fields, `game_over`, `local_player_win`, scores, teams, mode | [C] | `'EndOfGameSummary'`, `'average_ping'`, `'home_score'`; main_0096.c:6278-7257 |
| 0x7000e07820 | Builds the end-of-plate-appearance summary: ~100 fields and the `ballpip_type`/`ballhitscored_type` text | [C] | `'EndPlateAppearanceSummary'`; main_0097.c:4975-5162 |
| 0x7000e02b98 | Writes the `game_mode` / `arena_submode` / ball-state event (ball_state, ball_location_x/y/z) | [C] | `'ball_state'`, `'ball_location_x'`; 811L, 4 callers |
| 0x7000e03780 | Writes the `game_mode` / `play_time` / OnlineHangRecover event | [C] | `'play_time'`, `'OnlineHangRecover'`; 489L |
| 0x7000e003a0 | Writes the plate-appearance control event (`plate_appearance_id`, `local_control`, `remote_control`) | [C] | 1196L; strings as listed |
| 0x7000e02264 | Classifies a pitch/play outcome: "Unknown", "No Pitch Play", "Hit By Pitch" | [C] | 211L; strings as listed |
| 0x7000e54c00 | Initialises and fills 92 top-10 leader lists (4 × 23 stats) | [C] | main_0101.c:5358-5442; 4 × `0x17`; stride 0x1e0 |
| 0x7000e53654 | Clears the leaders object and builds it (patched call at main+0xe53808) | [C] | main_0101.c:4013 `rt_patch_on[1]`; `patches-1.0.20.txt` site e53808 |
| 0x7000e543a4 | Second leader build; calls f_7000e54c00 | [C] | main_0101.c:4781; callee list |
| 0x7000e5640c | Inning-change leaders refresh: calls f_7000e53654 then f_7000e543a4 (double build) | [C] | main_0101.c:7091/7095; caller f_7000e59c50 only |
| 0x7000e53620 | Game-start sequence: calls f_7000e53654, f_7000e54080, f_7000e543a4, f_7000e545f0 | [C] | 18L; callers=1; callee list |
| 0x70006753d0 | Collects up to 1350 players, sorts with `qsort`, returns up to 10 entries | [C] | `mov w9,#0x546` main_0050.c:8713; `plt qsort` 0x67574c |
| 0x70000a7ec0 | Predicate: `GetSetting(0) == 4` (Spring Training) | [C] | disasm `mov w0,wzr; bl 0x1824b74; cmp w0,#4` |
| 0x70000a7f40 | Predicate: `GetSetting(0) == 3` (HR Derby) | [C] | disasm `cmp w0,#3` |
| 0x70000a7f80 | Predicate: `GetSetting(0) == 6` (Demo Mode) | [C] | disasm `cmp w0,#6` |
| 0x70000a7fb0 | Predicate: `GetSetting(0x13) == 6` (Diamond Dynasty) | [C] | disasm `mov w0,#0x13; cmp w0,#6` |
| 0x70000a7fa0 | Hard-coded false: `return 0` (the "Mbl" predicate, so the Mbl branches are dead) | [C] | disasm `mov w0,wzr; ret`; 288 callers |
| 0x70000a8220 | Moments-active check; tail-calls 0xa7007c, which tests a global moments object | [I] | disasm `b #0xa7007c`; 0xa7007c loads 0x7003abffd0 and calls 0xa6d050 |
| 0x70018881c0 | Custom Practice check: `GetSetting(0x13)==4`, `GetSetting(0)==8`, `GetSetting(0x18)==1` | [C] | disasm `cmp w8,#4` / `#8` / `#1` |
| 0x70000aa6c0 | Predicate: `GetSetting(0x48) > 0` (Retro Mode) | [C] | disasm `mov w0,#0x48; cmp w0,#0; cset gt` |
| 0x7000e23460 | Trophy/achievement descriptions ("Achieve all trophies in MLB The Show 26", "Complete 4 Negro League Storylines.") | [C] | 533L; strings as listed |
| 0x7000e2c3a0 | Logs a pitcher put into the game during fast-forward and bullpen removal | [C] | `'Pitcher %s was put into the game during FF or immediately after.\n'` |
| 0x7000e3127c | Writes the mode banner log (`[MODE: SEASON]`, `[MODE: EXHIBITION]`, `[MODE: RTTS]`) | [C] | 910L; strings as listed |
| 0x7000e37630 | Base-result play-by-play handler | [C] | `'BaseResultHandler'`, `'PitchGetsAwayResult'`; 1444L |
| 0x7000e3c0d4 | Fielder-missed-catch event handler: clears the event buffer and stops the event | [C] | `'[FielderMissedCatchHandler: Stop]'`, `'[FielderMissedCatchHandler: Cleared Event Buffer]'` |
| 0x7000e3d830 | Home-run event handler | [C] | `'HomerunHandler'`; 290L |
| 0x7000e3e5a4 | Post-pitch event handler | [C] | `'PostPitchHandler'`; 811L |
| 0x7000e50820 | Division-rivalry text ("Division Rival", "Division Playoff Rivalry") | [C] | 862L; strings as listed |
| 0x7000e641c0 | Extra-innings comeback headline text | [C] | `'%s rally from %d down, win in extra innings against %s'` |
| 0x7000e652c0 | Prospect promotion text ("promote … to Triple-A") | [C] | `'%s promote %s %s (#%d MLB Prospect) to Triple-A %s'` |
| 0x7000e66d80 | Trade text ("acquire … in exchange for") | [C] | `'%s acquire %s %s from the %s in exchange for %s %s'` |
| 0x7000e673c0 | Release / designate-for-assignment / waiver-claim text | [C] | `'%s release %s %s %s'`, `'%s claim %s %s %s off Waivers'` |
| 0x7000e680d0 | Team streak text ("offense scorching", "rotation on a roll", "bullpen lights out") | [C] | 270L; strings as listed |
| 0x7000e882f0 | Player/Pitcher of the Month award text | [C] | `'Won the Player of the Month Award for %s'` |
| 0x7000e8a540 | All-Star representation text | [C] | `'Represented the %s in the %d %s All-Star Game'` |
| 0x7000e8a974 | Single-season/season HR and hits record-holder text | [C] | `'Single-Season HR Record Holder'`, `'Season Hits Record Holder (%d - %d)'` |
| 0x7000eb72c0 | Base game-state no-op virtual (`ret`); slot 4 of 29 game-state vtables | [C] | disasm `ret`; 5L; 29 vtables in `vtables.jsonl` list it at slot 4; neighbour 0x7000eb72b4 returns "GAME_STATE_STADIUM_CREATOR" |

## What is not mapped

| Topic | Not mapped |
|---|---|
| Field semantics | The exact field semantics of most of the 334 keys in 0x7000e0fb10. I identified the source for a handful (`pitches_played` from a stack counter, `home_score`/`away_score`/`game_over` from the game-state object, the mode ladder) and the destination for all of them, but each `LD32/LD64` offset into the incoming record is not named. |
| Record layout | The incoming record layout for the three builders (what `x0` points at, and the meaning of the +0x3e flags used for `ballpip_type`). Only the bit positions used for the labels are known. |
| Leader groups | I confirmed 4 × 23 and the collector's group stride 0x2b20, but not which group is which board (league/division/team/player) or the 23 stat ids behind the jump table at 0x7001d96784. |
| qsort vs qsort_r | The call I found in f_70006753d0 is the PLT entry for `qsort` (0x1c20160). The 0.2.0 patch text says `qsort_r`; that text is the doc's, not re-derived here. |
| Unexplained function | f_7000e4c0d4 (148L, 67 callers, only string "9AGQ_") is still unexplained. |
| Stubs | The 4-byte alignment/padding and the many 7-line `mov w0,wzr; ret` stubs between 0x7000eb72c4 and 0x7000eb7368 are counted but not individually identified; only the first (0x7000eb72c0) is placed in the vtable. |
| Vtable | The vtable at 0x7002295ae0 (the class that owns 0x7000df7fc0) has 5 slots; I read slot 2 only. |
| Versions | All addresses are 1.0.20. Nothing was checked against 1.0.15. |
| Coverage | This pass read generated C for the functions named above and no others; the other ~1,700 functions in the window are only counted, and their strings are not interpreted. |
