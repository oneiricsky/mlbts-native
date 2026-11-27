# BATTER_UP: what the function bodies show

Game 1.0.20, class vtable `0x70021e2708` (36 slots), read from the recompiler's generated C (`work/gen/main`); in that C `x19` is the state object ("this"). Citations are lines of `work/gen/main/<file>`, the recompiler's output, so they only help someone who has generated that folder. Tags: [C] the body I read shows it, [I] inferred, [H] guess. The tables below give what was read, the sub-state machine and its setter, the object's fields, its events, what each part calls, and what is still open.

## What was read

| Scope | Members | Note |
|---|---|---|
| Read in full | slots 3, 6, 7, 9, 10, 24, 26, 27, 28, 31, 32, 33, 34, 35; the setter `0x700108b500`; the handlers `0x700108b4ac`, `0x700108c030`, `0x700108c904`, `0x700108cd24`, `0x700108cf34`, `0x700108d4ec`, `0x700108d9d0`, `0x700108debc`, `0x700108e4ec`, `0x700108e610` | plus the small helpers they call |
| Cited, not redone | slot 5 (`0x700108b628`) | read earlier in the same session and is cited |
| Not read | `0x700108c9b8`, `cae0`, `cc58`, `ce48`, `d194`, `d340`, `d5d0`, `d720`, `d808`, `daa0`, `dba4`, `be8c` | only summarised by their callees |

## What was found

| Part | Function | What it does | Tag |
|---|---|---|---|
| Per-frame update | slot 7 | adds the frame time into a timer at `[this+0x8]`, then runs a two level state machine: the sub-state at `[this+0x18]` and a step counter at `[this+0x1c]`, calling a different function for each pair | none |
| Start-of-batter handler | slot 5 | asks for the stadium lighting, resets fields (including the timer at +0x8, which slot 7 would never grow if slot 5 ran every frame), then dispatches on the sub-state; it adds no frame time | [I] |
| Sub-states | 0 to 11 | nine have names in the game's own log strings; 4, 6 and 11 are used but never logged | none |
| Event ids | slots 9, 10 | the same object subscribes itself to 17 event ids and removes them again | [C] |
| Event handler | `0x700108debc` | turns those events into field changes | [C] |
| Hand-over | not in these bodies | the update has no block for sub-states 8 or 9, and nothing read writes another game state | none |

## Sub-state numbers

| Value | Name | Written by | Evidence |
|---|---|---|---|
| 0 | NONE | slot 3, slot 6 | main_0120.c:51975 to 52016, 54951 |
| 1 | WALK_UP | the setter only | jump table main_0120.c:52058; extra log "ATT_SCREEN: Batter walkup." |
| 2 | WALK_UP_PRES | `c030`, `cc58` | main_0120.c:52888, 53777 |
| 3 | PLAYERS_SETUP | `c904`, `cd24`, `d9d0` | main_0120.c:53521, 53805, 54764 |
| 4 | no log | `c030`, slot 7, `dba4` | main_0120.c:52904, 53073, 53174, 54886 |
| 5 | SELECT_PITCH | `cf34` | main_0120.c:53987, 54100 |
| 6 | no log | `d4ec` | main_0120.c:54381 |
| 7 | LAUNCH_PITCH | `d4ec` | main_0120.c:54408 |
| 8 | CAREER_PREPITCH | the setter only | jump table, string at main_0120.c:52058 |
| 9 | IN_PITCH | `e610` | main_0121.c:1602 |
| 10 | MANAGER_MODE | `d4ec`, `e4ec` | main_0120.c:54395, main_0121.c:1461 to 1546 |
| 11 | no log | not found | slot 7 tests it at main_0120.c:53456 |

## The setter

The names come from a jump table in the setter `0x700108b500`:

| Step | Function | What it does | Evidence | Tag |
|---|---|---|---|---|
| Store the value | `0x700108b500` | stores the new sub-state at `[this+0x18]` and its second argument at `[this+0x1c]` | — | [C] |
| Compare | `0x700108b500` | compares the value with 10, then indexes a byte table at `0x7001d9c8de` | main_0120.c:52043 to 52058 | [C] |
| Each case | `0x700108b500` | logs one string and prints a newline (the call `f_7001c1fc90(0xa)`, newline by its argument) | — | [I] for the newline |
| Values 4 and 6 | `0x700108b500` | map to the default case, which logs no string (it only prints the newline); values above 10 also go there | — | [C] |
| Enter functions | `cd24`, `cf34`, `d4ec`, `e610` | write the number directly and log the same strings, so they work as "enter this sub-state" functions | — | [C] |

## The pitch sequence

| From | To | How | Evidence | Tag |
|---|---|---|---|---|
| start | 0 | slot 3 zeroes fields, sets the sub-state to 0 and stores four floats to globals | main_0120.c:51975 to 52016 | [C] |
| 1 | 4, then 3 | step 3 writes 4 and calls `cd24` | main_0120.c:53010 to 53100 | [C] |
| 2 | 4, then 3 | `cae0` at step 4, `cc58` at step 2, step 3 writes 4 and calls `cd24` | main_0120.c:53101 to 53201 | [C] |
| 4 | 3 | step 3 calls `cd24` | main_0120.c:53202 to 53283 | [C] |
| 3 | 5 | step 0 calls `ce48`, step 2 calls `cf34` | main_0120.c:53284 to 53330 | [C] |
| 5 | 7 or 6 | step 3 calls `d4ec(this, 1)`; it writes 7, or 6 when the global at `0x70022b65b0` equals 0x12 | main_0120.c:53295 to 53398, 54378 to 54408 | [C] |
| 5 | 10 | `d4ec` with flag 0 posts event 0x16b and writes 10; `e4ec` does the same when its countdown ends | main_0120.c:54389 to 54395, main_0121.c:1528 | [C] |
| 7 | 9 | step 2 calls `e610` unless that global is 0x11 or 0x12; `d808` also calls it | main_0120.c:53418 to 53455, 54620 | [C] |
| 6 | 0 | step 3 posts event 0x151, which `debc` turns into sub-state 0 | main_0120.c:53399 to 53417, main_0121.c:1038 | [C] |
| 10 | 3 | step 0 posts, then `c904` can write 3 | main_0120.c:52979 to 53009, 53521 | [C] |
| 11 | 4, then 3 | `d9d0`, `daa0`, then `dba4` writes 4 and calls `cd24` | main_0120.c:53456 to 53490, 54886 | [C] |

Read as a path:

| Question | Answer | Tag |
|---|---|---|
| The path | NONE, then WALK_UP or WALK_UP_PRES, then PLAYERS_SETUP, then SELECT_PITCH, then LAUNCH_PITCH, then IN_PITCH, with MANAGER_MODE reachable from SELECT_PITCH | [C] for each row above |
| Order check | that order matches the strings | none |
| Who first writes 1 or 2 | not shown | none |
| Setter callers outside this class | `0x7000f27d4c`, `0x7000f281b0`, `0x7000f282b4`, `0x7000f29804` | [C] |
| The two read (`f281b0`, `f282b4`) | fetch this state object from a global manager and call the setter with 5, jumping straight to SELECT_PITCH | [C] |
| Inside `e4ec` | sub-state 10 is entered when a countdown ends (see Event handler) | none |

## Object fields

| Offset | Meaning | Tag | Evidence |
|---|---|---|---|
| +0x08 | seconds in the state | [C] | slot 7 adds its time argument (main_0120.c:52962 to 52963); zeroed by slot 31 and by events 0x8b, 0x11a, 0x135, 0x290 |
| +0x10 | start of a second base class | [I] | slot 32's copy `0x700108ea54` reads +0x8 where slot 32 reads +0x18 |
| +0x18 | sub-state | [C] | slot 7, the setter |
| +0x1c | step inside the sub-state | [C] | slot 7 writes it at main_0120.c:53005 to 53386 |
| +0x20 | integer, set to -1 at start and by event 0xdc | [C] | main_0120.c:52007, main_0121.c:1052 |
| +0x24 | byte flag, zero at start, read by slot 5 and `cf34` | [C] | main_0120.c:51997; meaning [H] |
| +0x27 | byte set to 1 by event 0x163 | [C] | main_0121.c:1038 jump table, case `e064` |
| +0x28 | byte flag; slot 5 stores a call result here, outside code sets it 1 or 0, `e4ec` returns it | [C] | `f_7000f282b4`, `f_7000f281b0`; meaning [H] |
| +0x29 | byte set to 1 by event 0x11b, cleared at start and in slot 6 | [C] | case `df18` |
| +0x2a to +0x2c | bytes set by event 0x22f; +0x2c is the low bit of a virtual call | [C] | main_0121.c:1065 and the `e114` block |
| +0x2f | byte set when event 0x167 has payload field 0x20 equal to 5 | [C] | case `e07c` |
| +0x31, +0x32 | bytes slot 5 fills from other calls | [C] | slot 5 |

## Timing globals

Four floats are written by slot 3 into globals; what they time is not stated by the code.

| Float | Where | Evidence | Tag |
|---|---|---|---|
| 30.0 | at the pointer in `0x7002298000+0x3e8` | main_0120.c:51989 to 52012 | [C] |
| 4.0 | at `+0x3f0` | main_0120.c:51989 to 52012 | [C] |
| 7.0 | at `+0x3f8` | main_0120.c:51989 to 52012 | [C] |
| 6.0 | at `+0x400` | main_0120.c:51989 to 52012 | [C] |

## Events

| Call | Shape | Note | Tag |
|---|---|---|---|
| Subscribe | slot 9 calls `f_70005e6830(id, bus, this, mode)` for 17 ids on the bus at `[0x7002298000+0x428]` | — | [C] |
| Unsubscribe | slot 10 calls `f_70005e69d0(id, bus, 0)` for the same ids | — | [C] |
| Post | `f_70005e6b40(id, payload)` is the matching post call, used here with ids 0x13d, 0x151, 0x16b, 0x133, 0x2a2, 0x8a and 0x72 | 964 callers | [C] for the shape, [I] for the names subscribe, unsubscribe and post |

## Event handler

Handler `0x700108debc` takes (id, payload, this):

| Id | Effect | Tag |
|---|---|---|
| 0x8b, 0x11a, 0x135 | timer `[this+0x8]` set to 0 | [C] |
| 0x290 | if a virtual call on this is true, calls `f_7000d6d22c` on a global, then resets the timer | [C] |
| 0x9a | if a virtual call on `[0x7002295000+0xb40]` is false, step `[this+0x1c]` set to 0 | [C] |
| 0xdc | if payload field 0xc is non-zero, `[this+0x20]` set to -1 | [C] |
| 0x11b | `[this+0x29]` set to 1 | [C] |
| 0x5b | subscribed by slot 9 (`main_0121.c:54994`); what its handler does was not read | [C] for the subscription |
| 0x150, 0x151 | a call on the object at `[0x700227e000+0x688]` with 5 or 6, then sub-state set to 0 and NONE logged (0x150 also sets a byte at +0xba of the object at `[0x700227e000+0x128]`) | [C] |
| 0x152 | calls `f_70004d2aac(7)` and `f_7000d9b008` with 4.0 | [C] |
| 0x163 | `[this+0x27]` set to 1 | [C] |
| 0x167 | if payload field 0x20 is 5, `[this+0x2f]` set to 1 | [C] |
| 0x1a6 | if payload field 0x20 is 5, the sub-state is 5 and the step is 5 to 7, step set to 5 | [C] |
| 0x22f | queries two virtual calls and sets +0x2a, +0x2b, +0x2c | [C] |
| 0x209, 0x2a3 | subscribed but no case in this handler | [C] |

Case targets for 0x11a to 0x167 come from the byte table at `0x7001d9c8e9` (main_0121.c:1038).

## What each part calls

| Callee | Role | Tag | Evidence |
|---|---|---|---|
| `f_7000574c40` | writes a log line; always followed by a newline call | [I] | 343 callers |
| `f_7000e23cec(this, sub, flag)` | posts event 0x13d with the sub-state | [C] | main_0100.c:1538 to 1550 |
| `f_70005e6b40` | posts an event | [I] | 964 callers |
| `f_70000a7360` | true when the pointer at `0x7003abfa98` is set and its field +0x18c is 1 | [C] | main_0006.c:29808; same pointer `tutorials.c` documents as the universal profile |
| `f_7000a49df8` | called with that profile pointer and a built record in `cf34` | [C] | main_0120.c:54070; meaning [H] |
| `f_7000f2598c(obj, id, flag)` | stores the id at `[obj+0x28]` when it is 1 to 0x12 and the byte at `+0xc0` is clear, and 0 otherwise (`main_0109.c:1326-1330`); called with 0x10, 4, 0x11, 0x12, 9 | [C] | main_0109.c:1312 |
| `f_7000daea5c` | logs "ACT_UPDATE"; called by `cd24`, `d340`, `d808` | [C] | strings |
| `f_70010a5544(out)` | writes the pointer at `0x7003b22000+0xad0` to `*out`, true if non-null | [C] | main_0121.c:29545 |
| `f_70012c54ec` then `f_70012d0fcc` | the lighting manager request, in slot 5, with the walk-up patch inline | [C] | main_0120.c:52513 to 52516 |
| `f_7000f2868c` | stores 7 at `[obj+0x30]` and logs "Exit" | [C] | main_0109.c:4691 |

## Slots

| Slot | Address | Role | Tag |
|---|---|---|---|
| 0, 1 | `ed04`, `ed08` | 5 line thunks, not read | none |
| 2 | `ed0c` | 8 lines, holds the string "GAME_STATE_BATTER_UP", not read | none |
| 3 | `b418` | enter: zero fields, sub-state 0, set four floats | [C] |
| 5 | `b628` | a query with 0xace9617f, field resets, lighting request, then dispatch to `c030` or `cd24` by sub-state | [C] |
| 6 | `dca4` | exit: clear flags, call `f_7000d82738` and `f_700134df20(0)`, sub-state 0 | [C] |
| 7 | `c1a0` | update with the time argument | [C] |
| 9, 10 | `dd48`, `e1bc` | subscribe and unsubscribe 17 events | [C] |
| 24 | `e73c` | query: false in sub-states 4 and 6, the inverse of `f_70000a7360` in 9, true otherwise | [I] |
| 26 | `e784` | query tied to sub-states 3, 5 and 7 | [I] |
| 27 | `e820` | query: a virtual call on this, `[this+0x28]`, several globals, a float against 1.5 | role [H] |
| 28 | `e900` | query: five global byte flags, tail call to this vtable +0x88 | role [H] |
| 31 | `eca0` | zero timer; store a float from a 3 entry table (2.0, 4.0, 6.0 at `0x7001d9c938`) chosen by a 1 to 3 setting | [C] |
| 32 | `e9d8` | in sub-state 2, if a queried byte is set, post event 0x72 | [C] |
| 33 | `ead0` | when two virtual queries pass and the sub-state is 0xb or 2, call `f_7000d1eef4(global, 1)`; always set step 3 | [C] |
| 34, 35 | `ebd8`, `ec30` | thunks calling `f_700133fcc0` with fixed arguments | [C] |
| 4, 8, 11 to 13, 19 to 22, 29, 30 | — | point at 5 to 7 line stubs shared with other states, not read | none |
| 14 to 18, 23, 25 | — | small thunks, not read | none |

## Not determined

| Question | What is known | Tag |
|---|---|---|
| How BATTER_UP leaves | no block for sub-states 8 or 9 in slot 7, and no write of another game state in the bodies read; event 0x133 is posted when IN_PITCH starts (main_0121.c:1606), so an outside listener is the likely route | [H] |
| What states 4, 6 and 11 mean | state 6 is a variant of the launch when `0x70022b65b0` equals 0x12; the meaning of that value is unknown | none |
| What the 7.0 second value times, and why a countdown ends in MANAGER_MODE | `e4ec` compares the timer with the float at the pointer `0x7002298000+0x3f8` (main_0121.c:1484 to 1491), stores the remaining time to `0x7003b18000+0x1a8`, and on expiry or a true `f_7000f29804` posts event 0x16b and writes 10; a pitch clock is a guess | [H] |
| The bodies of the twelve step functions listed at the top, and who first writes sub-states 1 and 2 | not read | none |
| Slot 5's first act | a call to `f_70005398c0` with the value 0xace9617f (main_0120.c:52150 to 52156); if it returns true the handler logs "We're trying to crash 1." and branches to `be80`, which logs and then tail-calls `be8c`. The shape fits the hash-matched dev options in `docs/dev-config.md`, and that hash is not among the 27 named there | [I] |
