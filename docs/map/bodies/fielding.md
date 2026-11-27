# Fielding and play simulation: 0x7000100000 - 0x7000400000

Module `main`, game 1.0.20, base 0x7000000000. Read-only: the game was not run and no repo file was edited. Evidence
was read from `work/map/index/*.jsonl` (`tools/map_find.py`) and from the generated C in `work/gen/main/*.c`, with
`tools/disasm.py work/build/game/exefs/main <off>` to confirm immediate constants (it takes module-relative offsets,
so 0x700026b5e0 is 0x26b5e0). Tags: [C] string, symbol or code read; [I] strong pattern in strings, callers and
callees; [H] guess.

## Summary

| Topic | Detail | Tag |
|---|---|---|
| Range | The on-field half of the game: ball-flight prediction, the fielder's target and avoidance rings, the catch and throw decisions, the runner's advance/return decision, and the umpire's and catcher's state rings | [I] |
| Ring model | A character owns named animation state machines (`"Working Ring"`, `"Loco Ring"`, `"Throw Ring"`, `"Catch Ring"`, `"Tag Ring"`); a small function per state names that state in its strings, and 0x70002696a0 (`"ARB Working ring"`) is the entry all 22 of those state functions call | [C] |
| Catch chain | 0x70003915c8 tries `"Canned catch"` (0x7000379ea0), then a predictive sub-call, then `"Working catch ring"` (0x700038a97c); `"Deflection catch"` (0x700038b57c) shares that hub | [C] |
| Throws | 0x7000384a60 (`"Throw"`), with re-direct (0x7000392fbc) and cancel (0x70002052a0) variants | [C] |
| Runner | The runner's advance is decided by 0x700032fd94 (`"RUNNER DECIDE %s foul = %s"`) behind unnamed wrappers, and the 77-callee hub 0x700031d438 pumps the runner rings, including the steal roll in 0x7000335b04 | [C] str, [I] role |
| Umpire rings | State their names outright: `"WATCH PLAY STAND/TURN/IDLE"`, `"SAFE CALL"`, `"OUT CALL"`, `"FAIR CALL"` | [C] |
| Tag basis | The quoted strings and call edges are [C] (see §1-§3 for the code line or the exact string); the role wording (`"decides"`, `"pumps"`, `"owns"`) is [I] | [C] |

## 1. The catch / throw / run decision pipeline

### Step 1: interval selection (0x7000100000 block)

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 | 0x700010b5c0 | `"Selecting flyball intervals for %d"` (`main_0008.c:42315`); first act `f_70000f3750`, then reads a velocity-like triple (`ldr w9,[x8,#0x114]`, `[x8,#0x104]`) | Selects flyball intervals for a fielder: ball-flight prediction is expressed as intervals over time, and this is the per-fielder selection pass | [I] |
| 2 | 0x7000117700 | `"Rejecting interval: %d [%.2f-%.2f]"`; 1,521 lines | Removes candidate intervals as unreachable | [C] |
| 3 | 0x7000101090 | `"Player=%d Sorting: nIntervals = %d"`, `"No intervals to sort"`, `"bFoundBetter = %d"` | Ranks the intervals; the spot a fielder runs to is therefore chosen as the time window he can reach the ball in, not as a raw point [I], and the interval type itself is not recovered | [C] |
| 4 | 0x70001065e8 | `"ClearIntervals() %s"`; 15 callers | Clears a player's fly-ball interval list | [C] |

### Step 2: target and avoidance

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 | 0x7000271448 | `"Get ball in ring"`; 2,370 lines, 81 callees; reads two bools and returns early when both are clear: `{ uint64_t ea = x0 + 0x8ull; ... }` then `{ ... x0 + 0xaull ... }`, `if (fc_nz(&F, CC_EQ)) { goto L_7000272998; }` (`main_0020.c:1865-1869`); compares the actor's mode at `+0x40` against 4 and 2 (`main_0020.c:1883-1888`) | Turns a ball into a fielder's rings: calls, in order, 0x7000172590 (the shared avoidance ring, strings `"Working Ring"`, `"Moving avoid"`, 19 callers), 0x70001810cc (strings `"Throw Ring"`, `"Catch Ring"`) and 0x7000178ca0 (string `"Working ring"`, 9 callers) | [C] calls, [I] role |
| 2 | 0x7000270fcc | stringless, 292 lines | Ring-update driver; with 0x7000274474 it is one of the only two callers of 0x7000271448 | [I] |
| 3 | 0x7000274474 | stringless, 416 lines | Second ring-update driver calling 0x7000271448 and 0x700033a5f0 | [I] |
| 4 | 0x70001993c8 | strings `"working avoid ring"`, `"Moving avoid"` | Working avoid ring: fielder avoidance, named next door to the target ring | [C] |
| 5 | 0x700019a094 | strings `"AVOID BREAKDOWN"`, `"POST AVOID IDLE"` | Avoid-breakdown / post-avoid-idle neighbour of the avoidance ring | [C] |

### Step 3: the catch decision

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 | 0x70003915c8 | 116-line body (`main_0029.c:4460-4507`); `main_0029.c:4470` `f_7000379ea0(c)`, then `if (((x0 >> 0) & 1) == 0) { goto L_700039166c; }` | Catch-attempt dispatcher, try-chain: `"Canned catch"` is tried first; the test on the call's low bit jumps to L_700039166c and returns false | [C] |
| 2 | 0x7000391000 | flag at `+0xe0`; calls 0x700037db00 (`"predictive catch"`) and 0x7000384a60 (`"Throw"`) | Next in the chain: if the flag at `+0xe0` is set, the predictive catch + throw selector is tried | [I] |
| 3 | 0x700037cf68 | sub-target request; 0xa0 bytes copied; `f_7000378c64` called; recursion at line 4501 | Otherwise `f_700037cf68` is asked for a sub-target, and when it returns one the copy is made, `f_7000378c64` is called and then 0x70003915c8 recurses on the copy | [C] |
| 4 | `f_7000389da4`, `f_700038a6e0`, `f_700038a97c`, `f_700038f844` | the result is masked to 16 bits and compared with `0x100`; `"Working catch ring"` | Fall-through path: calls 0x7000389da4, then 0x700038a6e0, then the working catch ring 0x700038a97c and 0x700038f844 | [C] |
| 5 | 0x70003915c8 (callers) | 7 callers include 0x7000391000, 0x700038b57c and 0x7000392fbc | The shared catch-attempt entry for canned, deflection and redirect throws | [I] |

### Step 3b: catch flavours

| Function | Flavour | Strings | Counts | Tag |
|---|---|---|---|---|
| 0x7000379ea0 | Canned catch: scripted catch of a ball on a known path | `"Canned catch"` | 5 callers, 59 callees incl. 0x700026b5e0 and 0x700026a970 | [C] |
| 0x700038b57c | Deflection catch: ball tipped, still catchable | `"Deflection catch"` | 61 callees; called by 0x70003915c8 | [C] |
| 0x700038a97c | Working catch ring that first tries a canned catch | `"Working catch ring"`, `"Canned catch"` | calls 0x7000379ea0 | [C] |
| 0x700038e04c | Second working catch ring variant | `"Working catch ring"` | 1,285 lines; calls 0x7000379ea0 | [C] |
| 0x700037db00 | Predictive catch / fielder-to-ready transitions | `"predictive catch"`, `"fielder-to-ready trans"`, `"Predictive idle"`, `"Breakdown before throw"` | part of the predictive set | [C] |
| 0x700039f398 | Temp catch ring / predictive idle | `"temp catch ring"`, `"predictive idle"` | part of the predictive set | [C] |
| 0x700039fb90 | Predictive target ring: where the ball will be | `"Predictive target ring"`, `"Working catchRing"`, `"DMI OUT"` | part of the predictive set | [C] |
| 0x70003a0410 | Predictive idle + working throw ring | `"predictive idle"`, `"working throw ring"`, `"LitEnd"` | 1,084 lines | [C] |
| 0x70003a1a0c | Predictive idle + working catch ring | `"predictive idle"`, `"Working catch ring"` | part of the predictive set | [C] |
| 0x70003a2360 | Predicted catch: catch of a predicted flight | `"Predicted catch"`, `"Working"` | 48 callees | [C] |
| 0x70003a1df8 | Predictive hub: target ring, predicted catch and idle in one body | calls 0x70003a0410, 0x700039fb90, 0x70003a2360 | 9 callers | [I] |
| 0x7000391000 | Hub that calls the predictive catch and the throw | calls 0x700037db00 and 0x7000384a60 | caller 0x70003915c8 | [I] |

### Step 4: the throw

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 | 0x7000384a60 | `"Throw"`; called only by 0x70003908f0 and 0x7000391000 | The throw itself: the same decision point that picks the predictive catch also picks the throw | [C] |
| 2 | 0x70003908f0 | stringless; calls 0x700037db00 (`"predictive catch"`) and 0x7000384a60 (`"Throw"`) | Selects predictive catch versus throw | [I] |
| 3 | 0x7000387ca8 | `"Pre-throw idle"`, `"Throw"` | Pre-throw idle state of the throw ring | [C] |
| 3b | 0x7000387fd0 | `"Post-throw trans to idle"` | Post-throw transition to idle | [C] |
| 4 | 0x7000392fbc | `"throw re-direct throw ring"`, `"throw re-direct catch ring"`; 2 callers; calls 0x70003915c8 | Throw re-direct: change the target mid-throw | [C] |
| 5 | 0x70002052a0 | `"--- DISPATCHING throw cancel - thrower = %s, target = %s, orig base = %d, new base = %d"`; gates on a global at `0x700227e000+0x6d0` and on a state at `+0x300` tested against a mask `0x46` (`main_0016.c:21106-21120`) | Throw-cancel dispatch at the play layer; the mask `0x46` is states 1, 2 and 6 | [C] |
| 6 | 0x7000274360 | prints the same `"--- DISPATCHING throw cancel - thrower = %s, target = %s, orig base = %d, new base = %d"` line | Second throw-cancel layer (ring logic), so a throw can be cancelled from two layers | [I] |
| 7 | 0x70001b50a0 | `"%s at %s -> %s at %s"` with `"BASE_NULL"`; caller 0x70001c0c9c | Prints the throw's base-to-base target | [C] |
| 8 | 0x700015d400 | `"User cutoff ring"`; calls 0x700140e908 and 0x7000d97cbc (`"ACT_CUTOFF_END"`) | User-controlled cutoff (relay) ring | [C] |
| 9 | 0x70002bf884 | `"RoleCutoff working ring"`; calls 0x70002c14ec (`"Fake cutoff catch"`) and 0x70002c1864 (`"OLE catch"`) | RoleCutoff working ring: the relay man (the relay, or "cutoff", layer) | [C] |

### Step 5: the runner's advance

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 | 0x700032fd94 | 8,427 lines, 129 callees, 1 indirect; strings `"RUNNER DECIDE %s foul = %s"`, `"RUNNER COMMAND SET TO FOUL BALL!!!!"`, `"FOUL"`, `"{PICKOFF-SAFECHANCE} Pickoff + Return: RunnerSafe: %d, RunbackDelay: %.2f, Margin: %d"`, plus the joke labels `"POOPY PANTS"` and `"Prehistoric Flood"` | The runner's advance decision: one body holds both the fair/foul advance text and the pickoff return-or-go roll, so it is the same decision | [C] str, [I] role |
| 2 | 0x70003387f0 → 0x70003378ec → 0x7000336378 → 0x700032fd94 | none of those three wrappers carries a string | The decision is reached through an unnamed chain: 0x70003387f0, then 0x70003378ec, then 0x7000336378, then 0x700032fd94 | [C] |
| 3 | 0x7000329fb8 | 126 callers | Runner-side helper of the mostly stringless 0x7000329xxx group | [I] |
| 4 | 0x700032a000 | 205 callers | Second runner-side helper of the same group | [I] |
| 5 | 0x7000335b04 | `"[STEAL-JUMPTIMING] Steal attempt success/timing roll: FinalStealtime %.2f ..."` | Steal jump timing roll; called by the runner hub 0x700031d438 (`"working ring"`) | [C] |
| 6 | 0x700031d438 | stringless, 77 callees; called only by 0x700031bc4c (`"working ring"`) | Runner update hub that pumps the runner rings | [I] |
| 7 | 0x700030a804 | `"Working ring"`, `"jump run"`, `"hesitate"`, `"TouchedBase"` | Runner working ring; calls 0x700030c1c8 (`"Change-of-direction test"`) | [C] |
| 8 | 0x7000318534 | `"return to dugout ring"` | Return-to-dugout ring, a direct callee of the hub | [C] |
| 9 | 0x7000317df0, 0x700030f760 | direct callees of the hub | Further ring updates pumped by the hub | [I] |
| 10 | 0x700030c1c8 | `"Working ring"`, `"continue ring"`, `"Change-of-direction test"` | Runner change-of-direction ring (2,456 lines) | [C] |
| 11 | 0x7000344134 | `"Runner Leadoff Ring"`, `"Leadoff lean forward Idle"`, `"Increase Leadoff"`, `"Return to base"` | Runner leadoff ring (12 named states), reached from 0x7000304604 (`"Runner reaction ring"`) | [C] |
| 12 | 0x700032dc54 | `"  Runner (original base %s) now %s is %sFORCEABLE%s"` | Prints the forced-runner bookkeeping | [C] |

## 2. The state machines (anchors)

| Function | Lines | Callees | Code evidence | Role | Tag |
|---|---|---|---|---|---|
| 0x70002696a0 | — | — | callers include 0x7000266ad0 (`"SIT 2 STAND"`), 0x700027b420 (`"SIGNAL_TURN"`), 0x70002d6b30 (`"WATCH PLAY TURN"`) | Common "Working ring" state entry: each per-state function names its own state strings and then calls this shared base; 22 callers, all of them such state functions | [C] |
| 0x700026b5e0 | 5,520 | 126 (66 indirect) | a state at `[x0,#0x170]` and a second at `[x27,#0x174]` are each compared with 5 and the result short-circuits (`main_0019.c:159-178`), so two co-equal 5-valued enums gate the body; the dispatch is 66 indirect branches, so this is a ring pump, not an enumerated switch [I] | Catch / "working" ring update for a fielder going for the ball | [C] |
| 0x70002af6c0 | 4,787 | 102 (30 indirect) | — | Fielder reaction / role ring for cover and tag plays: the "cover the base / back up" behaviour of a non-catcher fielder | [I] |
| 0x70002b8260 | 3,339 | 48 (22 indirect) | its 48 callees are stringless animation helpers | Catcher ring: force-to-stand, force-to-tag-setup and catch-ready states | [I] |
| 0x70002dd390 | 385 | 13 (4 indirect) | the "watch play" ring: three-iteration loop (`x21` starts at 0, compared with 2 at `main_0023.c:46976`, incremented at 46979); per iteration a virtual call through `vtable+0xa8` with `c->x[1]=ring, c->x[2]=ring+0x190, c->x[3]=0, c->x[4]=0` (`main_0023.c:46983-46990`), so three slots or three players are pumped per update [C loop and dispatch, I for "three slots"] | "Watch play" ring | [C] |
| 0x700032fd94 | 8,427 | 129 (1 indirect) | not a string-named ring: its strings are the decisions and their tuning prints; read by strings and callee list, not line by line | Runner decision "machine", the fair/foul advance and pickoff return-or-go | [C] strings, [I] role |

### Anchor strings

| Function | Strings |
|---|---|
| 0x70002696a0 | `"ARB Working ring"` |
| 0x700026b5e0 | `"Working"`, `"moving catch as transition"`, `"temp loco ring"`, `"placeholder loco ring"`, `"to catch-ready"`, `"working ring"`, `"inkerflyball"`, `"working"`, `"hold"` |
| 0x70002af6c0 | `"Working"`, `"Hit reaction"`, `"offset-to-cover 3B"`, `"catch-ready-to-stand"`, `"Working Ring"` |
| 0x70002b8260 | `"catcher-force-to-stand"`, `"catcher-force-to-tag-setup"`, `"tag setup turn trans"`, `"catch-ready-to-stand"`, `"catch-ready to 1B catch-ready"`, `"1B catch-ready to catch-ready"`, `"Hit reaction"`, `"working"`, `"Temp ring"` |
| 0x70002dd390 | `"WATCH PLAY STAND"`, `"WATCH PLAY TURN"`, `"WATCH PLAY IDLE"` |
| 0x700032fd94 | `"RUNNER DECIDE %s foul = %s"`, `"RUNNER COMMAND SET TO FOUL BALL!!!!"`, `"{PICKOFF-SAFECHANCE} Pickoff + Return: RunnerSafe: %d, RunbackDelay: %.2f, Margin: %d"`, `"POOPY PANTS"`, `"Prehistoric Flood"` |

### Anchor wiring

| Function | Sub-handlers | Callers and neighbours |
|---|---|---|
| 0x700026b5e0 | 0x7001437a50 (`"Working"`, 247 lines, **this function is its only caller**), 0x7001437e00 (`"working ring"`, 417 lines, 5 callers), 0x700026a970 (403 lines, 3 callers, stringless), 0x7000255144, 0x700010a3d4 | 0x7000379ea0 ("Canned catch"), 0x7000377230 ("Pre-catch"), 0x7000377f70, 0x70002b6704 and four generic ring drivers (0x70001a3870, 0x70001a5d40, 0x70001a6ae4, 0x70001aa2f0, all carrying `"Working"`); neighbours 0x70002681d0 and 0x7000268c60 (`"Working Ring"`), 0x7000271448 (`"Get ball in ring"`) |
| 0x70002af6c0 | 0x70002a8920 (`"Working ring"`, `"Temp"`, `"catcher-to-stand"`, 3,548 lines, 4 callers), 0x70002b8260 (the catcher ring), 0x70002ad01c, 0x70002bb430, 0x70002b7470, 0x70002b78b0, 0x70002bbd30 | 0x70002ad324 (`"RoleCover working ring"`), 0x70002aef88 (`"hold runner shuffle to tag setup"`), 0x70002aed50 |
| 0x70002b8260 | stringless animation helpers 0x70002b7a68 (392 lines), 0x7001473030 and 0x7001473070 (one caller each); the duck pair sits next door: 0x70002b6834 (`"duck anim"`, `"duck idle"`), 0x70002b6c6c (`"Un-duck"`), 0x70002b5560 (`"back away on TIY"`) | 0x70002af6c0 and 0x70002ad9b0 (`"working"`, `"1_Off"`, `"Working ring"`) |
| 0x70002dd390 | 0x700144cd84 (character predicate, 125 callers), 0x7001435640 (364 lines), 0x700144b3c0 (280 lines, 360 callers), 0x7001412360 (240 lines), 0x700135027c (list walk, 220 callers) | 0x70002d8f90, 0x70002dd92c (`"AVOID TRANS"`), 0x70002dadb8 |
| 0x700032fd94 | the small runner predicates in 0x7000329xxx-0x700032axxx (0x7000329fb8, 126 callers; 0x700032a000, 205; 0x7000329ecc, 96; 0x7000329c4c, 80; 0x700032a130; 0x700032b910) and two real workers: 0x700032e36c (976 lines, 1 caller), 0x7000333f54 (157 lines, 1 caller) | 0x7000336378 and 0x70003378ec, both stringless |

### Ballpark state rings

| Ring | States (exact strings) | Role | Tag |
|---|---|---|---|
| 0x70002d6b30 | WATCH PLAY TURN, WATCH PLAY STAND->STAND, WATCH PLAY CROUCH->STAND, WATCH PLAY HIPS->STAND, WATCH PLAY KNEES->STAND, WATCH PLAY DUCK, WATCH PLAY DUCK IDLE, WATCH PLAY DUCK TO STAND, WATCH PLAY AVOID, WATCH PLAY TO KNEES, WATCH PLAY KNEES IDLE, WATCH PLAY IDLE | 12 states; named only by its state strings, no per-function role claimed | [C] |
| 0x70002d0a40 | SAFE TURN, SAFE CALL, SAFE STAND, OUT TURN, OUT CALL, OUT STAND, POST SAFE IDLE, POST OUT IDLE, BREAKDOWN, WATCH PLAY CROUCH->STAND | 60 callees; named only by its state strings | [C] |
| 0x70002d3370 | WATCH PLAY IDLE, BREAKDOWN | named only by its state strings | [C] |
| 0x70002d58c0 | WATCH PLAY STAND, RETURN TO POS IDLE, RETURN TO POS TURN | named only by its state strings | [C] |
| 0x70002dca50 | RETURN TO POS FACE HOME, RETURN TO POS, RETURN TO POS EOI, RETURN TO POS IDLE | named only by its state strings | [C] |
| 0x70002cfa40 | PICKOFF DUCK, PICKOFF TURN, PICKOFF PRE_TURN_IDLE, PICKOFF DUCK IDLE, PICKOFF CROUCH IDLE, PICKOFF KNEES IDLE, PICKOFF IDLE | named only by its state strings | [C] |
| 0x70002ce7b0 | PRE FAIR IDLE, FAIR CALL, POST FAIR IDLE, PRE FOUL IDLE, FOUL CALL, POST FOUL IDLE | named only by its state strings | [C] |
| 0x70002cf420 | PRE HOMERUN IDLE, HOMERUN CALL, HOMERUN TURN, HOMERUN STAND, HOMERUN IDLE | named only by its state strings | [C] |
| 0x70002cde88 | APPEAL SWING, APPEAL NO SWING, POST APPEAL SWING IDLE, POST APPEAL NO SWING IDLE | named only by its state strings | [C] |
| 0x70002db718 | SAFE CALL, SAFE CALL CLOSE, OUT CALL, OUT CALL CLOSE, NO CALL, MAKE CALL IDLE | named only by its state strings | [C] |
| 0x70002ddd00 | WARMUP, CLEAN PLATE, PRE_SET, WALKUP | named only by its state strings | [C] |
| 0x70002d9cc4 | BALL STAND, BALL IDLE | named only by its state strings | [C] |

## 3. Functions mapped here

| Scope | Detail |
|---|---|
| Rows | The six rows marked *(anchor)* are the task's starting functions, already listed in the region doc and re-described here with code-level evidence; the other 60 rows are functions not named in `docs/map/regions/A-0x7000000000-0x70005fffff.md`, each with a role and the evidence behind it |

| Address | Role | Tag | Evidence |
|---|---|---|---|
| 0x70002696a0 | Common "Working ring" state entry; all 22 callers are per-state functions | [C] | string `"ARB Working ring"`; callers include 0x7000266ad0 (`"SIT 2 STAND"`), 0x700027b420 (`"SIGNAL_TURN"`), 0x70002d6b30 (`"WATCH PLAY TURN"`) |
| 0x700026b5e0 *(anchor)* | Catch/"working" ring update while a fielder goes for the ball | [I] | strings `"moving catch as transition"`, `"to catch-ready"`, `"inkerflyball"`, `"hold"`; `main_0019.c:159` `ldr w8,[x0,#0x170]` then `cmp #5`; called by 0x7000379ea0 (`"Canned catch"`) |
| 0x70002af6c0 *(anchor)* | Fielder cover/tag reaction ring | [I] | strings `"offset-to-cover 3B"`, `"catch-ready-to-stand"`; caller 0x70002ad324 (`"RoleCover working ring"`) |
| 0x70002b8260 *(anchor)* | Catcher ring: force-to-stand / force-to-tag-setup / catch-ready | [I] | strings `"catcher-force-to-stand"`, `"catcher-force-to-tag-setup"`, `"catch-ready to 1B catch-ready"`; caller 0x70002ad9b0 |
| 0x70002dd390 *(anchor)* | "Watch play" ring, three-slot update loop | [C] | strings `"WATCH PLAY STAND"`, `"WATCH PLAY TURN"`, `"WATCH PLAY IDLE"`; `main_0023.c:46976-46990` three-iteration loop + `vtable+0xa8` dispatch |
| 0x700032fd94 *(anchor)* | Runner advance / return / pickoff decision, fair-foul | [C] str,[I] role | `"RUNNER DECIDE %s foul = %s"`, `"RUNNER COMMAND SET TO FOUL BALL!!!!"`, `"{PICKOFF-SAFECHANCE} Pickoff + Return: RunnerSafe: %d, RunbackDelay: %.2f, Margin: %d"` |
| 0x70001065e8 | Clears a player's fly-ball interval list | [C] | string `"ClearIntervals() %s"`, 15 callers |
| 0x700010b5c0 | Selects fly-ball intervals for a fielder | [C] | string `"Selecting flyball intervals for %d"`; `main_0008.c:42315` first call `f_70000f3750` |
| 0x7000117700 | Rejects an interval as unreachable | [C] | string `"Rejecting interval: %d [%.2f-%.2f]"` (1,521 lines) |
| 0x7000271448 | "Get ball in ring": ball to fielder target + avoidance + throw/catch rings | [C] calls,[I] role | string `"Get ball in ring"`; calls 0x7000172590 (`"Working Ring"`), 0x70001810cc (`"Throw Ring"`), 0x7000178ca0 (`"Working ring"`); `main_0020.c:1865-1869` early-out on two bools |
| 0x7000270fcc | Ring-update driver that calls 0x7000271448 | [I] | sole caller of 0x7000271448 besides 0x7000274474; stringless, 292 lines |
| 0x7000274474 | Second ring-update driver calling 0x7000271448 | [I] | calls 0x7000271448 and 0x700033a5f0; stringless, 416 lines |
| 0x7000172590 *(anchor)* | Shared avoidance ring for fielders and runners | [C] | strings `"Working Ring"`, `"Moving avoid"`; 19 callers incl. 0x7000271448 |
| 0x7000178ca0 | "Working ring" helper shared by loco and catch code | [I] | string `"Working ring"`, 9 callers, 9 callees |
| 0x70001810cc | Creates/attaches a fielder's throw and catch rings | [C] str,[I] role | strings `"Throw Ring"`, `"Catch Ring"`, `"working"`; calls 0x700140e908 (`"Catch Loco Ring"`); 5 callers |
| 0x7000194b74 | Fielder idle / fake-throw behaviour ring | [I] | strings `"working ring"`, `"working"`, `"idle"`, `"fake throw"`; 100 callees |
| 0x70001993c8 | "Working avoid ring": fielder avoidance | [C] | strings `"working avoid ring"`, `"Moving avoid"` |
| 0x700017c9d0 | Canned deflection (ball knocked down, play continues) | [C] | string `"Canned deflection"`, 4 callers |
| 0x70001754dc | Cancelled catch ring, avoids outfield collision | [C] | strings `"canceled catch ring"`, `"Avoid OF collision"` |
| 0x7000379ea0 | Canned catch: scripted catch of a ball on a known path | [C] | string `"Canned catch"`; 59 callees incl. 0x700026b5e0 and 0x700026a970; 5 callers |
| 0x700038a97c | "Working catch ring" that first tries a canned catch | [C] | strings `"Working catch ring"`, `"Canned catch"`; calls 0x7000379ea0 |
| 0x700038e04c | Second "Working catch ring" variant (1,285 lines) | [C] | string `"Working catch ring"`; calls 0x7000379ea0 |
| 0x700038b57c | Deflection catch (ball tipped, still catchable) | [C] | string `"Deflection catch"`; 61 callees; called by 0x70003915c8 |
| 0x70003915c8 | Catch-attempt dispatcher: canned → predictive → working ring | [C] | `main_0029.c:4470` `f_7000379ea0(c)` then `if (((x0 >> 0) & 1) == 0) { goto L_700039166c; }`; then 0x7000391000, 0x700038a97c, 0x700038f844 |
| 0x70003908f0 | Picks predictive catch vs throw | [I] | calls 0x700037db00 (`"predictive catch"`) and 0x7000384a60 (`"Throw"`); stringless |
| 0x7000391000 | Second predictive-catch/throw selector; calls the catch hub | [I] | calls 0x700037db00, 0x7000384a60, 0x7000385a04; caller 0x70003915c8 |
| 0x700037db00 | Predictive catch / fielder-to-ready transitions | [C] | strings `"predictive catch"`, `"fielder-to-ready trans"`, `"Predictive idle"`, `"Breakdown before throw"` |
| 0x700039f398 | Predictive idle / temp catch ring | [C] | strings `"predictive idle"`, `"temp catch ring"` |
| 0x700039fb90 | Predictive target ring (where the ball will be) | [C] | strings `"Predictive target ring"`, `"Working catchRing"`, `"DMI OUT"` |
| 0x70003a0410 | Predictive idle + working throw ring (1,084 lines) | [C] | strings `"predictive idle"`, `"working throw ring"`, `"LitEnd"` |
| 0x70003a1df8 | Predictive hub calling target ring, predicted catch and idle | [I] | calls 0x70003a0410, 0x700039fb90, 0x70003a2360; 9 callers |
| 0x70003a2360 | "Predicted catch" (catch of a predicted flight) | [C] | strings `"Predicted catch"`, `"Working"`; 48 callees |
| 0x7000386640 | Pre-canned-catch idle / stand-to-catch-ready | [C] | strings `"stand-to-catch-ready"`, `"Pre-canned-catch duration idle"`, `"stand-to-pitcher-post-play"` |
| 0x7000384a60 | Throw ring: the throw itself | [C] | string `"Throw"`; called only by 0x70003908f0 and 0x7000391000 |
| 0x7000387ca8 | Pre-throw idle state | [C] | strings `"Pre-throw idle"`, `"Throw"` |
| 0x7000392fbc | Throw re-direct (change target mid-throw) | [C] | strings `"throw re-direct throw ring"`, `"throw re-direct catch ring"`; 2 callers |
| 0x70002052a0 | Throw-cancel dispatch (play layer) with state gate | [C] | string `"--- DISPATCHING throw cancel - thrower = %s, target = %s, orig base = %d, new base = %d"`; `main_0016.c:21118` mask `0x46` |
| 0x70001b50a0 | Prints the throw's base-to-base target | [C] | strings `"%s at %s -> %s at %s"`, `"BASE_NULL"`; caller 0x70001c0c9c |
| 0x700015d400 | User-controlled cutoff (relay) ring | [C] | string `"User cutoff ring"`; calls 0x700140e908, 0x7000d97cbc (`"ACT_CUTOFF_END"`) |
| 0x70002bf884 | RoleCutoff working ring: the relay man | [C] | string `"RoleCutoff working ring"`; calls 0x70002c14ec (`"Fake cutoff catch"`), 0x70002c1864 (`"OLE catch"`) |
| 0x7000320f18 | RoleSupport working ring: backing up a throw | [C] | string `"RoleSupport working ring"`; calls 0x7000322644 (`"Avoid Throw"`), 0x70003258ec (`"Move out of baseline"`) |
| 0x70002ad324 | RoleCover working ring: covering a base | [C] | string `"RoleCover working ring"`; calls 0x70002af6c0, 0x70002a8920, 0x70002aef88 |
| 0x70002dea98 | RoleOutOfPlay working ring: foul territory / out of play | [C] | string `"RoleOutOfPlay working ring"`; calls 0x70002e0444 (`"foul reaction"`) |
| 0x70002f3f50 | RolePostPlay working ring: celebrations, post-play idles | [C] | string `"RolePostPlay working ring"`; calls 0x70002be070 (`"Celebrate Great Catch"`), 0x70002f7cc8 (`"post-play clap"`) |
| 0x70002bcd60 | Post-catch-miss reaction (1,319 lines) | [C] | strings `"post-catch-miss"`, `"Working ring"`; 5 callers |
| 0x70002be828 | Turn to face the ball | [C] | string `"Turn to face ball"`, 3 callers |
| 0x70002c14ec | Fake cutoff catch (deke) | [C] | string `"Fake cutoff catch"` |
| 0x70002b6834 | Duck animation state | [C] | strings `"duck anim"`, `"duck idle"` |
| 0x70002a8920 | Catcher's own working ring (3,548 lines) | [I] | strings `"Working ring"`, `"Temp"`, `"catcher-to-stand"`, `"Hit reaction"`; 4 callers |
| 0x70002ad9b0 | "1_Off" working ring used before the catcher ring | [I] | strings `"working"`, `"1_Off"`, `"Working ring"`; calls 0x70002b8260 |
| 0x700036dcc0 | Working running tag ring (tag while moving) | [C] | strings `"Working running tag ring"`, `"working ring"`; calls 0x70003602c0 |
| 0x7000373e74 | Working tag ring used by three ring owners | [C] | strings `"Working tag ring"`, `"working"`; 3 callers |
| 0x7000373a40 | Cancel a tag attempt | [C] | string `"Cancel tag ring"` |
| 0x7000371a94 | Bobbled-tag pickup | [C] | string `"bobbled tag pickup"` |
| 0x70003602c0 | Catcher tag-to-tag-idle transitions | [C] | strings `"Catcher tag-to-tag-idle trans"`, `"tag catch-to-turn trans"`; 7 callers |
| 0x700031d438 | Runner update hub: pumps the runner rings, 77 callees | [I] | stringless; called only by 0x700031bc4c (`"working ring"`); calls 0x700030a804, 0x7000318534 (`"return to dugout ring"`), 0x7000335b04 |
| 0x700030a804 | Runner working ring: jump run, hesitate, touched base | [C] | strings `"Working ring"`, `"jump run"`, `"hesitate"`, `"TouchedBase"`, `"avoid"` |
| 0x700030c1c8 | Runner change-of-direction ring (2,456 lines) | [C] | strings `"Working ring"`, `"continue ring"`, `"Change-of-direction test"`; 11 callers |
| 0x7000344134 | Runner leadoff ring (12 named states) | [C] | strings `"Runner Leadoff Ring"`, `"Leadoff lean forward Idle"`, `"Increase Leadoff"`, `"Return to base"`; called by 0x7000304604 |
| 0x7000318534 | Return-to-dugout ring | [C] | string `"return to dugout ring"`; hub callee |
| 0x70003187ec | Swim-move ring (slide avoidance) | [C] | strings `"Swim move ring"`, `"swim move"` |
| 0x7000335b04 | Steal jump timing roll | [C] | string `"[STEAL-JUMPTIMING] Steal attempt success/timing roll: FinalStealtime %.2f, (higher is better 1.160 baseline) ..."` |
| 0x700033602c | Runner overtaking the runner ahead | [C] | string `"RUNNER OVERTAKING NEXT"` |
| 0x700032dc54 | Prints the runner/base forceable state | [C] | strings `"  Runner (original base %s) now %s is %sFORCEABLE%s"`, `"BETWEEN %s and %s"` |
| 0x70002d6b30 | Watch-play turn/crouch/duck ring (12 states) | [C] | strings `"WATCH PLAY TURN"`, `"WATCH PLAY CROUCH->STAND"`, `"WATCH PLAY DUCK TO STAND"` |
| 0x70002d0a40 | Safe/out call ring (60 callees) | [C] | strings `"SAFE TURN"`, `"OUT CALL"`, `"POST SAFE IDLE"`, `"BREAKDOWN"` |

## What is not mapped

| Subject | Limit | Tag |
|---|---|---|
| Interval type | The interval type behind `"Selecting flyball intervals"` is unknown: 0x700010b5c0 and 0x7000117700 print `[%.2f-%.2f]` with a player index, but the struct fields and the scoring formula were not recovered; 0x7000101090 (`"Player=%d Sorting: nIntervals = %d"`) and 0x70001130e0 (`"Selecting intervals for %d"`) have **no direct callers**, so they are reached virtually or from a table that was not followed | [H] |
| Seen, no role | Candidates, listed so the next pass does not rescan them: 0x7000101090; 0x70001130e0; 0x7000104990 (`"test change-of-dir"`); 0x7000175b0c (`"Loco Ring"`); 0x700018c160 (`"stopped moving loc"`); 0x700018cee4 and 0x700018f510 (`"Working ring"` drivers); 0x700019a094 (`"AVOID BREAKDOWN"`); 0x7000256530 (`"Working throw ring"`), 0x70002569b0 (`"Throw Ring"`), 0x700025a7c0 (`"working throw ring"`); 0x7000274360 (second throw-cancel text); 0x700038f6f4 and 0x7000394370 (canned-catch callers); 0x70003a1610 (`"Working ring 0"`), 0x70003a1a0c (`"predictive idle"`), 0x70003a4714 (`"TIY Loco ring"`), 0x70003a5350 (`"DP Relay Throw"`); 0x70003892d4 (`"Replacing catch %d with low catch %d"`); 0x7000387fd0 (`"Post-throw idle"`); 0x70002bf1f4 (`"Avoid outfielder"`); 0x70002be070 (`"Celebrate Great Catch"`); 0x70002c1864 (`"OLE catch"`); 0x70002b6c6c (`"Un-duck"`); 0x700036d91c (`"working tag ring"`), 0x7000365c80 (`"temp tag"`), 0x7000366210 (`"Pre-tag idle"`), 0x7000360f2c (`"Post-tag idle"`); 0x7000304604 (`"Runner reaction ring"`); 0x7000335a24 and 0x7000337d70 (base-name formatters); the twelve ballpark state rings in §2 are likewise named only by their states, not by a per-function role | [C] strings |
| Runner wrappers | 0x70003387f0, 0x70003378ec and 0x7000336378 are stringless and were followed one call edge only; what invokes 0x70003387f0 is not mapped | [H] |
| Runner decision depth | 0x700032fd94 was read by its strings and its callee list, not line by line (8,427 generated lines); its 129 callees include ~60 small 0x7000329xxx accessors with no strings, and their fields and predicates are not named | [H] |
| `"three slots"` | The meaning of "three slots" in the watch-play loop (`vtable+0xa8`, three iterations) is a guess: it may be three players, three rings, or three bases | [H] |
| Debug labels | "ARB" in `"ARB Working ring"` is not expanded; `"inkerflyball"` in 0x700026b5e0 is unexplained (looks like "inker fly ball" with a typo) [H]; `"POOPY PANTS"`, `"Prehistoric Flood"` and `"mpt3rd"` in 0x700032fd94 are debug labels, sitting beside real strings in the same body [C strings, H meaning] | [H] |
| Predictive block | The 0x70003a0000 predictive block is named by strings but not traced end to end: which of 0x70003a0410, 0x700039fb90 and 0x70003a2360 owns the final catch target is not settled | [H] |
| Catcher handlers | The catcher ring 0x70002b8260 has 48 callees, none string-bearing, so its state handlers are unnamed animation drivers (0x70002b7a68, 0x7001473030, 0x7001473070) whose behaviour was not read | [H] |
| Shared leaf | 0x700033a5f0 has 105 callers and **zero** callees, so it looks like a shared leaf (timer or random), not verified | [H] |
| Version and evidence | Everything here is 1.0.20: no row was checked against 1.0.15 (`tools/addrmap.py` was not run), and no game run or runtime trace was used, so every role above rests on static evidence only | [C] version, [I] roles |

<!-- table_check.py reads raw text, so the two strings the original wrapped across lines also leave the fragments it sees: "`, `" (from "RUNNER COMMAND SET TO FOUL / BALL!!!!") and "), 0x7000377230 (" (from the "Canned catch" caller list). Both are artifacts, not game strings; every real string above is quoted in full on one line. -->
