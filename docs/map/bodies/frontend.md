# Front-end / Road To The Show, and the stats-roster block (main 1.0.20)

## Summary

The front end is a data-driven UI: `uiEngine` keeps a deque of screens (+0x218..+0x230), and every swap goes
through one worker that prints `uiEngine: Entering screen: [%s->%s (%d)]` and delivers an enter event to the new
screen. Screens are C++ objects with vtables (0x70004c77bc is slot 2 of the 14-slot screen vtable 0x700217e570).
Menu input arrives as named `kUIEvent*` records: one helper (0x70008bb110, 452 callers) decodes pad bits into
16-bit actions and the active screen's handler consumes them. Cells get text from named properties: four element
classes (Table/List/HorizontalList/TextBox) update from a data source, and registrars publish 42/22/23 fields
(`CURRENT_ROW`, `CELL_INDEX`, `IS_CURRENT_CELL`, ...); each screen also declares its own rows (`NUM_ROWS`,
`TITLE_STR`, ...). RTTS content loads from `frontend//rtts/*.xml` into C++ record tables, is validated, and writes
`calendar_date` events; the hub up-grade screen is a 4-column grid with per-slot token costs and 11+ handlers.
0x7001800000-0x70018c0000 is the binary DB layer behind those screens (`stats.bin`, `rosters.bin`, `players.bin`).

## Functions

| Address | Role | Tag | Evidence |
|---|---|---|---|
| 0x700089c9e0 | uiEngine screen switch: prints the entry log, tears down old screen, delivers enter event | C | stores and prints `"uiEngine: Entering screen: [%s->%s (%d)]\n"` (0x7001d62d4e) via f_70005717f0/f_7000589d44; walks +0x230 deque, builds event with f_7000888a50, dispatches f_70008a71f0 |
| 0x700089c720 | uiEngine screen request by id (0xff is what the leave path passes), 156 callers | C | locks +0x218/+0x220 deque via f_70008b87c8, then calls f_700089c9e0 with a 16-bit id read at `x8 - 8` |
| 0x700089c840 | 4-argument screen request variant (12 callers) | C | same deque compares at +0x218/+0x220, same f_700089c9e0 call, extra flag args x2/x3 |
| 0x7000888ad0 | UI event id -> name (`kUIEventEnter%d`, fallback `<UNKNOWN>`) | C | 32-bit offset tables at 0x7001d8b7e0 / 0x7001d8b8f0, output buffer 0x7003ab48d0, `"<UNKNOWN>"` at 0x7001d8b8fc |
| 0x70008a71f0 | pumps next UI event: polls 5 providers, skips sentinel 0x80000000 | I | calls vtable +0x80, +0x98, +0xb0, +0xc8, +0xe0 in turn, each result compared to 0x80000000, success cached at +0x18 |
| 0x70008bb110 | pad button -> 16-bit UI action (452 callers) | C | `LD32(x0+38) & 0x3f`, switch over 7..30, stores 16-bit result through x1; per-case reads at +0xd2/+0xec/+0x1bc/+0xe4 |
| 0x70008b84b0 | UI-engine pool allocator, 725 callers | C | looks up pool 0x7002289f78, calls f_700055afd0(pool,id,1); on failure logs `"UI Engine Mem Pool"` via f_70008889d0 |
| 0x70008b87c8 | locks the screen deque mutex (92 callers) | C | 105 lines, pair of 0x70008b8918 (94 callers); called immediately before the +0x218/+0x220 comparisons |
| 0x70004c6f30 | front-end go-to-screen helper with screen special cases | C | compares the name with `"r_Progress"`, `"ProfileHub"`, `"ol_RankedPlayNow"`; tutorial checks at +0xa0/+0xa1; ends in `f_700089c720(engine, 0, 0xff)` |
| 0x70004c77bc | screen class vtable slot 2 (0x700217e570): per-screen entry hook, tutorial setup | C | in vtable slot 2 of 14; calls `f_70004c1e9c` (`"Frontend/Tutorial/%s.xml"`), virtual `+0x80`, then `f_70004c6f30(this,name,id,0)` |
| 0x70004c7918 | screen vtable slot 3: name match then leave hook | C | compares x1+0x60 with the std::string at this+0xc0 (SSO length byte at +0xc0, data pointer at +0xc8) via f_7001c1ff00, then tail-calls f_700089d4e0(..., `"Leave_Tutorial"`, 0xff) |
| 0x70004c0eac | screen base ctor: installs base vtables, releases sub-objects | C | object+0/+8 = *0x7002281bc0+0x10 and +0x90; +0x1f8 = 0x700217e6d8; frees 8 pointers at +0xa8..+0x1f0 through f_70015410b4 |
| 0x70004c1048 | deleting destructor (calls 0x70004c0eac, then `operator delete`) | C | `musttail return f_70005b19d0` after f_70004c0eac; 0x70005b19d0 has the symbol `operator delete(void*)`, 7741 callers |
| 0x70004c1e9c | builds the tutorial XML path for a screen | C | two format strings: `"Frontend/Tutorial/%s.xml"` and `"Frontend/Tutorial/InGame/%s.xml"` |
| 0x70007fcc40 | registers the 42 table-element property names | C | writes 42 x 0x20-byte records: `"CURRENT_ROW"`, `"NUM_ROWS"`, `"CURRENT_COL"`, `"CAN_SCROLL_UP"`, `"IS_CURRENT_CELL"`, `"PARENT_DYNAMIC_TABLE"` |
| 0x70007f4940 | registers the 22 list-element property names | C | 22 records starting `"CURRENT_INDEX_NZ"`, `"CURRENT_INDEX"`, `"CELL_INDEX"`, `"NUM_CELLS"`, `"PARENT_DYNAMIC_LIST"` |
| 0x700084d070 | registers the 23 grid property names | C | 23 records: `"VIS_ROW"`, `"VIS_COL"`, `"IS_CURRENT_ROW"`, `"IS_CURRENT_COL"`, `"PARENT_TABLE"` |
| 0x700085cb60 | uiElementDataTable: applies a dirty mask and pushes data to rows/cells | C | `"uiElementDataTable Mask 0x%lx"`; reads element flags at +38/+0x2a, calls f_700085d6c0 and per-cell f_70008187f0 |
| 0x70008344f0 | uiElementDataList update (546 lines) | C | `"uiElementDataList Mask 0x%lx"`; sibling of 0x700085cb60 |
| 0x7000822820 | uiElementDataHorizontalList update (534 lines) | C | `"uiElementDataHorizontalList Mask 0x%lx"`; sibling of 0x700085cb60 |
| 0x700086f8f0 | uiElementDataTextBox update (292 lines) | C | `"uiElementDataTextBox Mask 0x%lx"`; the text-box case of the same data-binding family |
| 0x7000b56da0 | descriptor table for one screen's rows (jukebox/soundtrack) | C | 12 records: `"NUM_ROWS"`, `"CURRENT_ROW"`, `"TITLE_STR"`, `"IS_SONG_LOCKED"`, `"AUDIO_VAL_STR"`, `"CATEGORY_HAS_NEW_SONG"` |
| 0x7000bd38a0 | descriptor table for the perks/progression screen | C | `"PERKS_LIST_ACTIVE_INDEX"`, `"LEVEL_ACTIVE_INDEX"`, `"AVAILABLE_TOKENS"`, `"IS_ADD_EFFECT_FOCUSED"`, `"ADD_EFFECT_LIST_ACTIVE_INDEX"` (298 lines) |
| 0x7000be6290 | descriptor table for the free-agent / draft screen | C | `"SELECTED_FA"`, `"SELECTED_AMATEUR"`, `"FA_RANK"`, `"DRAFT_SIGNINGS"`, `"ASKING_SALARY"`, `"MULTI_YEAR_ASK"`; vtable 0x700215c000 slot 426 |
| 0x70004998c0 | on-screen goal/progress row text | C | `"DESC"`, `"CUR_VAL"`, `"TARGET_VAL"`; 764 lines, one caller |
| 0x700048fb60 | number formatting for stat cells | C | `"1.000"`, `"%d.%d"`, `"%1.2f"`; 18 callers; sibling 0x700048fa10 uses `"%.3f"`, `"1.000"` |
| 0x700041a290 | loads `frontend//rtts//Goals.xml` into the goal table | C | stores `"frontend//rtts//Goals.xml"` and `"\nLoading RTTS Config Data: Goals\n"`, allocates count+1 entries via f_70005b30b0 |
| 0x700041ac20 | processes one goal by type (switch 0..0xb) | C | switch table 0x7001d7da93, records of 0xa4 bytes from 0x7002280de0, warning `"WARNING!!! Attempting to process inactive Goal Type: %d ID: %d.\n"` |
| 0x7000423680 | validates goal definitions | C | 11 warnings, e.g. `"WARNING!!! Invalid Goal ID of %d, expected ID %d.\n"`, `"WARNING!!! Invalid goal Duration for Goal ID %d.\n"`, 2193 lines |
| 0x700041c3a8 | completes a goal and emits a calendar event | C | builds `"%d-%d-%d"` with `"calendar_date"`, fields `"evaluation_duration"`, `"is_success"`, `"is_cancellation"`, event `"RTTSGoalCompletion"` |
| 0x700041eb7c | adds a selectable goal slot | C | `"WARNING!!! Goal ID: %d trying to be added with %d selectable Goa..."` |
| 0x70004254b0 | loads `frontend//rtts//GameQuests.xml` | C | `"frontend//rtts//GameQuests.xml"`, `"reward tier: %d, reward type: %s, attribute: %s..."` |
| 0x7000460070 | loads `frontend//rtts//TrainingFocus.xml` | C | `"frontend//rtts//TrainingFocus.xml"`; 2441 lines, one caller |
| 0x7000463250 | builds the offered training-focus list | C | `"num_focuses"`, `"calendar_date"`, `"years_played"`, event `"RTTSTrainingFocusesOffered"` |
| 0x7000464ed0 | applies the chosen training focus | C | `"choice_category"`, `"calendar_date"`, `"regular_season"`, `"part_season"`, `"pitcher_role"`, event `"RTTSTrainingFocusSelected"` |
| 0x7000462570 | detects a training attribute cap | C | `"attribute"`, `"years_played"`, event `"RTTSTrainingFocusAttrCAPMet"`; 3 callers |
| 0x700044ef90 | D_GOALS_DATA block: the goal save/load record set | C | 7056 lines keyed by `"D_GOALS_DATA"`; the save-side counterpart of the Goals.xml load |
| 0x7000bd1a4c | hub up-grade: move cursor inside the focused column and clamp | I | switch on this+0x108 (0..3) selects vector +0xa8/+0xc0/+0xd8/+0xf0; length compare with this+0x98; empty slot skips; f_7000414040 gives the slot cost |
| 0x7000bd1bfc | hub up-grade: move with level-up validity test | I | same 4-vector walk plus f_7000417144 (can this slot be raised) and f_7000413a6c; rejects when cost > this+0x9e |
| 0x7000bd1d98 | hub up-grade: apply the focused upgrade (selection-object path) | I | x2 must be non-zero, reads the selection via f_7001c207a0(...,10); cost from f_7000414040; stores this+0x12e; subtracts from this+0x9e (tokens) then calls f_7000bd559c |
| 0x7000bd1f64 | hub up-grade: cycle which column is focused | I | callee set only: f_7000413c98, f_7000413d0c, f_7000414360, f_7000417144 (column checks) then f_7000416e70 (cost) and f_7000bd559c |
| 0x7000bd20cc | hub up-grade: rebuild the option list from career data | I | only caller of 0x7000bd22e4; uses f_70004a87e0, f_700181a6fc, f_70006abc34, f_70006b9da4 and builds strings |
| 0x7000bd2340 | hub up-grade: recompute a per-slot flag byte array over 32 slots | I | loops x22 = 0..0x20 step 8 and x26 = 0x10a..0x12e, tests each slot with f_7000416eb0, writes a byte at this+0x10e+i |
| 0x7000bd3078 | hub up-grade: initialise the cursor/selection word | C | 9 lines, `ST16(this+0xa2, 0x100)`, returns 0 |
| 0x7000bd3088 | hub up-grade: push the focus onto the focused slot | I | 60 lines, reads this+0x108 column, picks the focused byte, calls f_7000414580(item, 0) |
| 0x7000bd3140 | hub up-grade: spend tokens to raise the focused slot | I | id from the 4 vectors, cost f_7000414040, compare with this+0x9e, `ST16(this+0x9e, tokens-cost)`, f_7000440904, f_7000bd559c(this,1,0,sel) |
| 0x7000bd33a4 | hub up-grade: second purchase path (different cost/commit args) | I | same grid walk, cost from f_7000416e70, then f_7000bd559c(this,0,0,sel) and f_70004160c0 |
| 0x7000bd35e0 | hub up-grade: refresh the list after a change | I | 105 lines, ends in f_7000415600(0,0) then f_7000bd3f80(this); no token or calendar write |
| 0x7000bd3f80 | hub up-grade: rebuild the visible rows after a change | I | reads this+0x109 and this+0xa2, scans the global map at 0x7002cb39e8, calls f_7000bd5398/0x7000bd5438; 4 callers |
| 0x7000bd559c | applies one upgrade and records it against the calendar | C | `"%d-%d-%d"`, `"calendar_date"`, `"is_reverted"`, `"is_trigger_or_effect_upgrade"`, `"is_increased_effect"`; 1347 lines, 8 callers |
| 0x700181d2f0 | loads `Frontend\Stats\stats.bin` (and the _INJ variant) | C | `"Frontend\\Stats\\stats.bin"`, `"Frontend\\Stats\\stats_INJ.bin"`, `"Reading %s\n"`, `"Failed to open %s\n"`, `"Done reading %s\n"`, mode `"rb"` |
| 0x700181dc30 | loads `Frontend\Stats\rosters.bin` (and _INJ) | C | `"Frontend\\Stats\\rosters.bin"`, `"Frontend\\Stats\\rosters_INJ.bin"`, `"Reading %s\n"`, `"Done reading %s\n"` |
| 0x700181dfe0 | loads `Frontend\Stats\players.bin` (and _INJ) | C | `"Frontend\\Stats\\players.bin"`, `"Frontend\\Stats\\players_INJ.bin"`, `"USING GLOBAL MEM"`, `"Done reading %s\n"` |
| 0x700181b070 | database index lookup by player id | C | logs `"GetDatabaseIndex looping over %d players\n"`, loops i < this+0x38, compares record+0x9a with the wanted id, returns -1 when absent |
| 0x700181bef0 | recalculates every player's rank | C | logs `"Running RecalcAllRanks logic over %d players\n"`, calls f_70018444f0(player,-1,-1,0) per player; for indices 0xcee..0xd06 it first calls f_70018450e8 and skips when byte +0x50 is 0 |
| 0x70018286f0 | user/franchise saved-settings block | C | stores `"D_CSTM_SETTINGS"`, `"D_USER_SETTINGS"`, `"D_FRANOPTIONS"`, `"D_ORTCOUNTERS"`, `"D_INBOX"` |
| 0x700183af10 | loads/copies a player profile (D_PLR_PROFILE) | C | passes `"D_PLR_PROFILE"` to f_7000df2818 after a fill loop that writes 0x80000000 at offsets +0x1f5c/+0x1f7c of each 0x40-byte stack record |
| 0x700186fe18 | decides/executes a pitcher substitution | C | `"ERROR: Invalid Pitcher..."`, `"A batter is on the mound.  Substituting."`, `"cSubstitutionLogic::CheckPitcherSituation() returned tr..."` |
| 0x7001870ca0 | dumps the player-evaluation inputs used for a substitution | C | `"P/C/1B/2B/3B/SS/LF/CF/RF: %d %d %d %d %d %d %d %d %d, %..."`, `"Canplay P: %d, %s %s (Pos/Role: %d/%d)\n"` |
| 0x700185b630 | roster/lineup substitution with an error log | C | `"Error: pos %d team %d player out %d (%s), player in %d ..."`; 5 callers |

## What is not mapped

- The action-name hash used by the per-screen command tables. The 16-byte records at 0x70021b9f10..0x70021ba078
  hold `{u32 id, u32 0, u32 handler_rva, u32 0}` and the 11 up-grade handlers are entries there (0x7000bd1a4c is
  0x70021b9f58), but the ids (e.g. 0x880e0619) are not FNV-1a, CRC32, DJB2 or FNV-1 of any string in the image, so
  the command names stay unknown. The screen registry pairs at 0x70021b9000 use the same scheme.
- The UI XML schema and parser. The element classes and property names are known, but the reader that turns a
  `*.xml` layout file into elements was not traced (it is above 0x700086f8f0 and was only sampled). The RomFS
  `frontend/` tree is not present in this checkout (`work/romfs` is gone), so no layout file could be read either.
- 0x700215c000 is a 1025-slot function table that screens index for per-property evaluation (0x7000be6290 is slot
  426). Only a few slots were tied to names; the table's name list was not decoded.
- Which concrete screen class owns vtable 0x700217e570. Slots 0/1 are ctor/dtor, 2 is 0x70004c77bc, 3 is
  0x70004c7918, 4..11 are trivial stubs, 12/13 are 0x70004c10a0/0x70004c12e0; the class name never appears as a
  string and no factory that installs the vtable was found (no 8-byte pointer to it exists; data holds 32-bit RVAs).
- The in-game command names of the 12 up-grade handlers (0x7000bd1a4c..0x7000bd35e0) and the meaning of
  this+0x108/+0x98/+0x9e/+0x12e were not proven; 0x7000bd1f64, 0x7000bd20cc and 0x7000bd3088 are inferred from
  their callees only. The four column vectors at +0xa8/+0xc0/+0xd8/+0xf0 are assumed to be the four up-grade
  categories (every handler walks them identically); no string states the category names.
- 0x7000ac0000-0x7000c00000 holds ~40 further screen data classes (RttsMessages, RttsMilestones, BpEquipment,
  PerksProgression, Relationships, StadiumAssign, ...). Only the ones named in the table were opened.
- The Halyard/HalyardClient telemetry strings and the presentation/training code above 0x7001880000
  (`SPresDataTrain.spf`, `TRAIN_STATE_*`, `ACT_EXIT`) are outside the stats/roster DB layer and were not read.
- The runtime side (how `MLB_*` / hid input reaches f_70008bb110) is host code, not game code, and was not traced.
