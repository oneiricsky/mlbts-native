# PRE_PLAY and IN_PLAY: what the handler bodies do

This page covers the PRE_PLAY and IN_PLAY handler bodies in game 1.0.20, module `main`, from the vtable slots through the sub-state machines and the events that move them. All line numbers are in `work/gen/main/`. Tags say how sure each row is: [C] the body or data I read shows it, [I] inferred from what I read, [H] guess. Names of states and sub-states come from the game's own strings, and names of functions and fields are mine.

## Summary

| Topic | Finding | Tag |
|---|---|---|
| PRE_PLAY shape | Each game state is an object with a sub-state number and a vtable. PRE_PLAY keeps its sub-state at +0x18 and walks it through up to 22 named steps in one large update function (slot 7, 1,270 lines). | [C] |
| PRE_PLAY handlers | Every step has up to three handler functions, picked by a second counter at +0x1c. | [C] |
| IN_PLAY shape | Much smaller: its sub-state sits at +0xc, it has five steps, and incoming events (numbered messages on an event bus) move it from step to step. | [C] |
| PLAY_OVER hand-off | When IN_PLAY reaches its last sub-state, PLAY_OVER, it asks the state manager every frame for a state change; which game state that request names is not settled. | [C] for the request, [H] for the target |
| Correction | The earlier note that the 558-line `f_70010939dc` is an IN_PLAY vtable slot was wrong. That function is the event handler and sits outside the vtable, and IN_PLAY slot 7 is the 176-line `f_700109448c`. | [C] |

## What was read

| Part | Extent | Tag |
|---|---|---|
| PRE_PLAY vtable | slots 3, 5, 6, 9, 10 in full; the first 150 lines of slot 7 | [C] |
| PRE_PLAY handlers | `f_700106e610`, `f_700106e968`, and the decisions in `f_700106eb90`, `f_700106ecac`, `f_700106f0d0` | [C] |
| IN_PLAY vtable | slots 3, 5, 6, 7, 9 | [C] |
| IN_PLAY event handler | `f_70010939dc` up to its second switch | [C] |
| IN_PLAY sub-state functions | `f_70010946dc`, `f_70010947cc`, `f_70010948ec`, `f_7001094afc` | [C] |

## Vtable slots

| Slot | State | Function | What it does | Lines | Tag |
|---|---|---|---|---|---|
| 3 to 10 | both | | same roles in both states where I could check; the role word "Update" is [I] because I did not read the caller, the evidence being that slot 7 takes a float time step as its argument and subtracts or adds it to a timer | | [C] for the roles, [I] for "Update" |
| 3 | PRE_PLAY | `f_700106cfc4` | sets up the object: writes -1 to +0x18, fetches an object from `f_7000d81dd8` into +0x20, sets flags at +0x28 to +0x30, stores the address of `f_700106d054` at `[[0x700227e6f8]+0xa298]` | 15376 to 15417 | [C] |
| 3 | IN_PLAY | `f_70010936ec` | resets: clears +0x14, +0x16, +0x28 and +0x18, zeroes +0xc and logs "state = NULL" if it was nonzero | 7741 to 7763 | [C] |
| 5 | PRE_PLAY | `f_700106d0c8` | starts the state: sets sub-state 1, zeroes +0x8, logs the name of sub-state 1; if +0x28 is set it writes -1 and posts a request (5, 1, 1) through `[0x700227e688]` vtable +0x60 | 15453 to 15493 | [C] |
| 5 | IN_PLAY | `f_7001093730` | starts the state: clears fields, sets the global byte `[[0x7002298000+0x450]]` to 1, calls `f_700134df20(1)` | 7764 to 7799 | [C] for the writes, [I] for "starts" |
| 6 | PRE_PLAY | `f_700106d154` | ends the state: clears a byte in the `+0x20` object (+0x25), zeroes a global byte (0x7002ca4061), writes -1 at `[[0x7003aeb728]+0xc4]`, then calls three cleanup functions and clears +0x28 | 15494 to 15529 | [C] |
| 6 | IN_PLAY | `f_70010937a0` | ends the state: clears the same global byte `[[0x7002298000+0x450]]`, zeroes +0x14 and +0x18 | 7800 to 7831 | [C] for the writes, [I] for "ends" |
| 7 | PRE_PLAY | `f_700106d4c4` | update with the sub-state machine | 15745 to 17014 | [C] |
| 7 | IN_PLAY | `f_700109448c` | update with the sub-state machine | 8735 to 8910 | [C] |
| 9 | PRE_PLAY | `f_700106d1cc` | subscribes the object to 7 event ids | 15530 to 15577 | [C] |
| 9 | IN_PLAY | `f_7001093804` | subscribes to 22 event ids | 7832 to 7954 | [C] |
| 10 | PRE_PLAY | `f_700106d438` | the same 7 ids with `f_70005e69d0` (unsubscribe, [I]) | 15705 to 15744 | [C] |
| 10 | IN_PLAY | `f_700109419c` | not read | | |

## Event subscriptions (`f_70005e6830(id, bus, this, mode)`)

| State | Count | Ids | Bus | Tag |
|---|---|---|---|---|
| PRE_PLAY | 7 | 0x65, 0xdc, 0x11b, 0x121, 0x13e, 0x1a6, 0x2ac | `[0x7002296000+0xe0]` | [C] |
| IN_PLAY | 22 | 0x38, 0x41, 0x5b, 0x61, 0x83, 0xa7 (mode 1), 0xa6, 0xd9, 0xe1, 0xe2, 0x13f, 0x1a6, 0x200, 0x209, 0x20a, 0x208, 0x21a, 0x213, 0x21f, 0x20f, 0x2a3, 0x28b | `[0x7002298000+0x440]` | [C] |

## PRE_PLAY sub-state field

| Aspect | Detail | Tag |
|---|---|---|
| Field | a 32-bit number at +0x18 | [C] |
| Names | a table of string pointers at 0x70022d19a8, one every 8 bytes | [C] |
| Index proof | that the index is the sub-state number is shown by three writes: `f_700106e968` stores 2, 13 or 14 at +0x18 and loads the name at table offset 0x10, 0x68 or 0x70 (lines 17258 to 17328); `f_700106d054` stores 0x11 and loads offset 0x88 (lines 15418 to 15452); slot 5 stores 1 and loads offset 8 (lines 15467 to 15470) | [C] |
| Logger | each change calls the logger `f_7000574c40`, whose format string is "GAME_STATE_PRE_PLAY: state = %s" (0x7001d65514) | [C] |
| Counts | the slot 7 body has 16 stores to +0x18 and 20 logger calls (15745 to 17014) | [C] |
| Start values | slot 3 writes -1 and slot 5 writes 1 | [C] |
| Value 0 | slot 7 also handles the value 0: it moves to 1 once `f_7000a52ee4` returns true; how the field comes to read 0 is not shown in what I read | [C] for the move |

## PRE_PLAY sub-states

| No | Name | Handlers | Evidence | Tag |
|---|---|---|---|---|
| 0 | ONLINE_SYNC_META | | moves to 1 when `f_7000a52ee4` returns true (15771 to 15790) | [C] |
| 1 | ONLINE_SYNC_ENTER | `f_700106e610`, `f_700106e7e4`, `f_700106e968` | phases 0, 4 and 6: `f_700106e610` at line 15817, `f_700106e7e4` at 15810, `f_700106e968` at 15826 | [C] |
| 2 | RAIN_DELAY | `f_700106e968` | next step after 1 (default) | [C] |
| 3 | CRITICAL_SITUATION_PROMPT | | set by `f_700106ecac` | [C] |
| 4 | CRITICAL_SITUATION_SIM | | set by `f_700106ecac` | [C] |
| 5 | AUTO_FAST_FORWARD | `f_700106f670` | at 16394 | [I] |
| 6 | AUTO_SUB | `f_700106f7b0` | set by `f_700106eb90` and `f_700106f0d0`; `f_700106f7b0` at 16489 | [C] |
| 7 | SETUP_PLAY | | set inline at about 16475 | [I] |
| 8 | PROMPT_SUGGESTION | | set inline at about 16495 | [I] |
| 9 | PROMPT_PITCHER | | set inline at about 16525 | [I] |
| 10 | PROMPT_PINCH_HIT | | compared at about 16545 | [I] |
| 11 | PROMPT_PITCHER_HANDEDNESS | | compared at about 16616 | [I] |
| 12 | MANDATORY_SUB | | set inline at 16632 to 16643 | [I] |
| 13 | CAREER_INTRO | `f_700106ea54` | at 15890; chosen by `f_700106e968` when `f_70000aaae0` is true | [C] |
| 14 | CAREER_AUTO_SUB | `f_700106eb90` | chosen by `f_700106e968` otherwise; `f_700106eb90` at 16006 | [C] |
| 15 | CAREER_EVAL | `f_700106ecac` | set by `f_700106eb90`; `f_700106ecac` at 16029 | [C] |
| 16 | CAREER_FAST_FORWARD | `f_700106ecac` | set by `f_700106ecac` | [C] |
| 17 | CAREER_LAST_PLAY | `f_700106d054` | set by the callback `f_700106d054` (lines 15418 to 15452) | [C] |
| 18 | ONLINE_SYNC_EXIT | | set inline at about 16660 | [I] |
| 19 | ASYNC_PRES | | compared at about 16721 | [I] |
| 20 | ASYNC_CARD_SELCT (sic) | | set inline at about 16700 | [I] |
| 21 | EXIT | | set inline at 16710 to 16713 and by `f_700106f0d0` | [I] |

## PRE_PLAY table notes

| About | Note | Tag |
|---|---|---|
| Rows marked I | rest on the numeric store or compare in the slot 7 body matching the table; I did not read the bodies of those handlers | [I] |
| "set by" rows | taken from the stores I read in `f_700106e968`, `f_700106eb90`, `f_700106ecac` and `f_700106f0d0` (lines 17258, 17417, 17498, 17796) | [C] |
| Phase counter | +0x1c takes the values 0, 3, 4 and 6 in slot 7 (compare lines 15800 to 15830 for sub-state 1) | [C] |
| Phase reset | the write at +0x18 in `f_700106e968` also zeroes +0x1c in the same store (`ST32(ea) ST32(ea+4, 0)`, inside lines 17258 to 17328), so a sub-state change resets the phase to 0 | [C] |
| Phase meaning | reading the phase as begin, run and finish is [I] | [I] |

## PRE_PLAY transitions

| From | To | Condition | Lines | Tag |
|---|---|---|---|---|
| 1 | 2, 13 or 14 | 13 if `f_70000aaae0` is true and `[[0x700227e688]+0x28] == 0` and `f_700066cf68` is true; 14 if the last two differ; 2 otherwise | 17258 to 17328 | [C] |
| 14 | 6 or 15 | decided in `f_700106eb90` from values returned by `f_7001824b74` | 17417 to 17497 | [C] |
| 15 | 3, 4 or 16 | decided in `f_700106ecac` | 17498 to 17754 | [C] |
| next of `f_700106f0d0` | 6 or 21 | decided from `f_70003e53e0` and `f_70003e56bc` results | 17796 to 17901 | [C] |

## PRE_PLAY fields

| Offset | Seen | Meaning | Tag |
|---|---|---|---|
| all below | | all [C] as accesses and [H] as meanings | [C] access, [H] meaning |
| +0x8 | float, `[+0x8] = [+0x8] - dt` every update (15769 to 15772) | time counter | [C] access, [H] meaning |
| +0x18 | 32-bit sub-state, -1 at start | sub-state | [C] |
| +0x1c | 0, 3, 4, 6 | phase | [C] values, [I] meaning |
| +0x20 | pointer from `f_7000d81dd8` | game session object ([H]) | [C] access |
| +0x28 | byte, set 0 on exit | "needs reset" flag ([H]) | [C] access |
| +0x2a to +0x2e | bytes set to 1 or computed in slot 3 | flags ([H]) | [C] access |

## IN_PLAY sub-state values

| Value | Name | Where read | Tag |
|---|---|---|---|
| +0xc / +0x10 | sub-state / phase (0 or 1) | | [C] |
| mapping | the mapping is shown in the event handler: each case loads the value and a name string, then both go to the shared store at line 8109 (`ST64 [x19+12]`) and a call to the logger thunk `f_7001c1fb40` with the string | | [C] |
| 0 | NULL | 7752, 7824 | [C] |
| 1 | IN_PITCH | case at line 8083 | [C] |
| 2 | IN_PLAY | 8074 | [C] |
| 3 | POST_PITCH | 8101 | [C] |
| 4 | ANIM_SEQUENCE | 0x7001c78ba9, set at 9278 | [C] |
| 5 | PLAY_OVER | 0x7001d133c7, stored at 8885 and 9127 | [C] |

## IN_PLAY sub-states

| No | Name | Enter | Run | Tag |
|---|---|---|---|---|
| 0 | NULL | slot 3 and slot 6 reset to it | none | [C] |
| 1 | IN_PITCH | inline in slot 7: posts `f_7000e23cec(this, 1, 0)` and sets phase 1 (8764) | `f_70010946dc` (called at 8769; body 8911 to 8981) | [C] |
| 2 | IN_PLAY | `f_70010947cc` (8806; body 8982 to 9064) | `f_70010948ec` (8781; body 9065 to 9135) | [C] |
| 3 | POST_PITCH | `f_70010949d8` (8813; body 9136 to 9218, not read) | `f_7001094afc` (8793; body 9219 to 9334) | [C] for calls |
| 4 | ANIM_SEQUENCE | inline: posts `f_7000e23cec(this, 4, 0)`, sets phase 1, then zeroes +0x14 and +0x18, then sets +0x18 to 2.5 if a flag is set (8822 to 8852) | countdown (8860 to 8885) | [C] |
| 5 | PLAY_OVER | none | posts a state request every update (8894 to 8901) | [C] |

## IN_PLAY event handler

| Part | Detail | Tag |
|---|---|---|
| First block | `f_70010939dc` lines 7955 to 8112: a switch on the event id in x0, arguments id, data, state object | [C] |
| Second block | after line 8112; runs when `f_70000aa6c0` is true (it calls `f_7001824b74(0x48)` and tests the result above 0); switches again on ids 0xd9 to 0xe1 and 0x200 to 0x21f; I did not decode it | [C] for the gate |
| Event meanings | the event numbers are numbers only, and no string names them, so what each event means is [H] | [H] |

## IN_PLAY events

| Event | Goes to | Condition | Lines | Tag |
|---|---|---|---|---|
| 0x13f | IN_PITCH (1) | unless already 1 | 8083 to 8095 | [C] |
| 0x38, 0x61, 0x20a | IN_PLAY (2) | unless already 2 | 7981, 8027, 7995 table | [C] |
| 0x5b, 0x21a | POST_PITCH (3) | unless already 3 | 7983, 7995 table | [C] |
| 0x213 | IN_PLAY (2) or POST_PITCH (3) | reads flag bytes in the event data (x1): +0x29 set goes to POST_PITCH; +0x21, +0x2b, +0x2c or +0x2a set goes to IN_PLAY; otherwise two helper calls (`f_7000d438d4`, `f_70001c8500`) and a field test decide | 7997 to 8025 | [C] for the flags, [I] for the helpers |
| 0x21f | POST_PITCH (3) | only if `f_70016703f0 -> [+8] -> [+0x30c] == 4` | 8095 to 8100 | [C] |
| 0x83 | none in the first block | writes a float, no sub-state write seen | 8029 to 8073 | [C] |
| all other ids | no change | all other ids in the table at 0x7001d9c96a (events 0x20a to 0x21f) | | [C] |

## From pitch to end of play

| Step | What happens | Tag |
|---|---|---|
| 1 | the state starts (slot 5): global byte `[[0x7002298000+0x450]]` set to 1 and `f_700134df20(1)` called | [C] |
| 2 | event 0x13f arrives, so sub-state 1, IN_PITCH. Entering posts event 0x13d with the sub-state number (`f_7000e23cec`, main_0100.c 1538 to 1563, event id at 1548) | [C] |
| 3 | each update of IN_PITCH, IN_PLAY and POST_PITCH adds the time step to a float at +0x30. If it passes 30.0 and +0x2e is 0, the function collects data and calls `f_7000e02b98`, then sets +0x2e. That function and `f_7000e03780` contain the strings "game_mode" and "arena_submode". On leaving, if +0x2e is set, they call `f_7000df2bb0` and `f_7000e03780(timer)` and clear it. A long-play report to telemetry is [I]; the 30 s test and the calls are [C] | [C] and [I] |
| 4 | event 0x38, 0x61 or 0x20a arrives, so sub-state 2, IN_PLAY. The enter function reads the game mode value `[[0x700227e700]]`, calls vtable +0x58 of the object at `[0x700227ea08]` with argument 0xe, then calls `f_7000f2598c` with 0x11, 0xa or 0xb. Presentation changes are [H] | [C] for calls, [H] for meaning |
| 5 | while in IN_PLAY the update calls `f_7001094c88(dt)`, an 865-line function. When it returns true, the state goes to PLAY_OVER (5), after flushing the long-play report (`f_70010948ec`, lines 9065 to 9135; the store of 5 is at 9127). What it does inside was not read | [C] for the call, [H] for the contents |
| 6 | event 0x5b or 0x21a arrives, so sub-state 3, POST_PITCH. The run function `f_7001094afc` checks the options object from `f_70002803f0`: if byte +0x121 or +0x122 is set, go to ANIM_SEQUENCE (4). Otherwise, if `f_700029b5c8` is nonzero and `f_70002a15d4(1)` is true, go back to IN_PLAY (2). Otherwise poll the object at `0x7003b22ad0` through three vtable calls (+0xc0, +0xc8, +0xa0) and call `f_7001095b00(dt)`, a 459-line function; true means PLAY_OVER (5) | [C] |
| 7 | ANIM_SEQUENCE: a 2.5 second countdown at +0x18, set to 2.5 at entry when the options flag is on. If the global byte `[[0x7003b22ab0]+0x5b]` is nonzero the timer is zeroed. At 0 or below, go to PLAY_OVER (5) | [C] |
| 8 | PLAY_OVER (5): every update posts the request (7, 0, 0) through `[[0x700227e688]]` vtable +0x60 (8894 to 8901) | [C] |

## State-change requests

| Request | Where posted | Reading | Tag |
|---|---|---|---|
| (7, 0, 0) | every update of PLAY_OVER, through `[[0x700227e688]]` vtable +0x60 (8894 to 8901) | the hand-off in step 8 | [C] |
| (5, 1, 1) | PRE_PLAY slot 5, through the same object and slot | | [C] |
| first argument | both requests | I take it as the id of the state to go to | [I] |
| id 7 names PLAY_OVER? | | [H]: nothing I read maps ids to the 12 state classes | [H] |

## Event-free path to POST_PITCH

| Aspect | Detail | Tag |
|---|---|---|
| Function | `f_70010946dc`, the IN_PITCH run | [C] |
| Path | goes straight to POST_PITCH (3) without any event, separate from the events | [C] |
| Test | the game mode value read from `[[0x700227e700]]` against a bit mask 0x08b011b2 | [C] for the mask |
| Mask covers | modes 1, 4, 5, 7, 8, 12, 20, 21, 23, 27 when the value is 27 or lower | [H] for the mode names |
| Effect | sets sub-state 3 if the bit is set (lines 8960 to 8975) | [C] |
| Open | which modes those are is [H] | [H] |

## Callees

| Function | Shows | Tag |
|---|---|---|
| `f_7000574c40` | the PRE_PLAY logger: takes a format string and a name; 144 lines; 343 callers | [C] |
| `f_7001c1fb40` | a 9-line thunk called with the full log string in IN_PLAY (455 callers) | [C] |
| `f_7000e23cec` | posts event 0x13d with the sub-state number and a flag through `f_70005e6b40` | [C] |
| `f_70005e6830`, `f_70005e69d0` | called with an event id, the bus object, the state object and a mode; subscribe and unsubscribe by use | [I] |
| `f_70005e6b40` | posts an event (964 callers) | [I] |
| `f_7000e02b98`, `f_7000e03780` | 811 and 489 lines, strings "game_mode", "arena_submode" | [C] strings, [I] purpose |
| `f_70000a7360` | true when the field +0x18c of the object at global 0x7003abfa98 equals 1 (403 callers); that global is the one `runtime/mlb/tutorials.c` calls the universal profile | [C] |
| `f_70002803f0` | returns an options object; bytes +0x121 and +0x122 choose the ANIM_SEQUENCE path | [C] for use |
| `f_7000d81dd8` | returns an object stored at +0x20 of the PRE_PLAY state | [C] |

## Not determined

| Item | Why |
|---|---|
| Who calls slot 7 and how often | I did not read the state manager |
| Meaning of the event ids and the request ids | no names; only numbers |
| Which state a request id names | no id to class mapping read |
| Bodies of `f_7001094c88` (865 lines), `f_7001095b00` (459), `f_70010949d8`, `f_70010947cc` beyond the start | not read |
| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f598`, `f_700106f670`, `f_700106f7b0`, `f_700106faac`, `f_700106fd4c`, `f_700106fe40`, `f_700106ff28`, `f_70010700a8`, `f_7001070de0`, `f_7001071230` | not read; only their call sites in slot 7 |
| Rows 5 to 12 and 18 to 21 of the PRE_PLAY table | matched by number, not by reading the handler |
| The second block of the IN_PLAY event handler and event 0x83 | not decoded |
| IN_PLAY slot 10, slots 18 to 26 of both states | not read |
