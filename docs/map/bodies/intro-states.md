# Game states read from their bodies: setup and intro

Six of the twelve game-state classes, read from the generated C (`work/gen/main`, game 1.0.20): PRE_GAME, GAME_INTRO, LINEUP_INTRO, WARM_UP, STADIUM_CREATOR and OPTIONS_ON_RAMP. Tags: [C] the body I read shows it, [I] inferred from a pattern, [H] guess. File and line ranges point at the function in the generated C, and in every function `x19` is the state object (`this`).

## Method

| Scope | Read as | What is complete | What is missing |
|---|---|---|---|
| Small functions | read in full, register save and restore stripped | the whole body | nothing |
| Large functions: slot 7 of LINEUP_INTRO, WARM_UP and OPTIONS_ON_RAMP, slot 5 of OPTIONS_ON_RAMP | skeleton: every call, branch, compare and store, but not every load | the phase logic | arithmetic between the calls |
| Callee sizes, caller counts and strings | local index | sizes, counts and strings | |

## Slots

Checked against all six states.

| Slot | Role | Evidence | What it does | Tag |
|---|---|---|---|---|
| 3 | resets the state's own fields to defaults | `main_0104.c:49979-49986`, `main_0121.c:2781-2788`, `main_0105.c:27701-27719` | every slot 3 is a run of stores to the object: STADIUM_CREATOR sets `+0x14` to 2; GAME_INTRO zeroes `+0x18` and `+0x20`; OPTIONS_ON_RAMP sets `+0x20`=5, `+0x30`=4, `+0x38`=1 | [C] |
| 3 (sub-state log) | logs a sub-state | | only WARM_UP's slot 3 also logs "GAME_STATE_WARM_UP: state = %s" | |
| 5 | enter: starts the state | | LINEUP_INTRO, WARM_UP and OPTIONS_ON_RAMP log "ATT_SCREEN: ..." here; GAME_INTRO and LINEUP_INTRO store a start time; WARM_UP posts event 0x218; PRE_GAME sets phase 2 or 3 | [C] |
| 6 | exit: tears the state down | `main_0120.c:51265-51323`, `main_0121.c:11155-11200`, `main_0121.c:26371-26426` | PRE_GAME zeroes phase and step; LINEUP_INTRO zeroes `+0x20`, `+0x29` and starts a fade ("SPFX - Fade"); WARM_UP calls the function whose string is "Exit" | [C] |
| 7 | update: runs every frame while the state is active | `main_0120.c:51048-51170` | it is a phase machine that polls (PRE_GAME waits for a byte at `0x70045ad12b` to become 0xff), so it must be called repeatedly; the caller was not read | [I] |
| 9, 10 | subscribe and unsubscribe to events | | for PRE_GAME (events 0x7d, 0x7e) and LINEUP_INTRO (0x11e, 0x1a6) slot 9 calls `f_70005e6830(id, bus, state, 3)` per event and slot 10 calls `f_70005e69d0(id, bus, 0)` for the same ids; STADIUM_CREATOR and WARM_UP have five-line default stubs; OPTIONS_ON_RAMP slots 9 and 10 are 23 and 20 lines, same size as the others, and were not read | [C] |

## Phase fields

Each state keeps its position in a phase number on the object; the offset differs by state.

| State | Phase | Step | Other | Evidence | Notes |
|---|---|---|---|---|---|
| STADIUM_CREATOR | `+0xc` (0 idle, 1 leaving) | `+0x10` | `+0x14` requested phase, 2 means none | [C] `main_0104.c:50056-50139` | |
| PRE_GAME | `+0xc` (2, 3, 4 set; 1, 3, 4 tested) | `+0x10` (0, 1, 2) | | [C] `main_0120.c:51048-51170` | |
| GAME_INTRO | `+0x18` (0, 1, 2) | `+0x1c` (0, 1, 2) | `+0x8` start time in seconds, `+0x20` counter | [C] `main_0121.c:2820-2943` | the two-value store `st64[x19+0x18] = 0x100000001` sets phase 1 and step 1 in one write |
| LINEUP_INTRO | `+0x18` (1 to 7) | `+0x1c` (1 to 3) | `+0x8` start time, `+0x24` flag, `+0x28` byte, `+0x2a` byte | [C] `main_0121.c:11332-12042` | |
| WARM_UP | `+0x18` (1 to 8) | `+0x1c` | `+0x22`, `+0x23` bytes, `+0x28` default 8 | [C] `main_0121.c:26437-26848` | |
| OPTIONS_ON_RAMP | `+0x18` (1 to 10) | `+0x1c` (1, 2) | `+0x20` value 1 to 5, default 5 | [C] `main_0105.c:28344-28832` | |

## States

### PRE_GAME

| Slot | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 5 (enter) | `f_70000a7360`, `f_700054aab8`, `f_70008e40a4` | `main_0120.c:50925-51047`; global byte `[0x7002284000+0x9a8]` | clears a global byte, asks `f_70000a7360` (true when `[[0x7003abfa98]+0x18c]` is 1), builds strings with `f_700054aab8` ("PORTALROOM", "EnterGame" are the strings the index finds in it) and sets phase 2, or phase 3 when `f_70000a7360` is true and `f_70008e40a4` is false; ends by setting the global byte to 1 | [C] |
| 7 (phase 1) | `f_700108ab40` | | sets phase 2 and runs helper `f_700108ab40` | [C] |
| 7 (step 0 of 3) | `f_70012f3f38` | | in phase 4, calls `f_70012f3f38(0x78, ...)` and moves to step 1 | [C] |
| 7 (step 1 of 3) | byte `0x70045ad12b` | `main_0120.c:51048-51170` | waits for the byte at `0x70045ad12b` to equal 0xff, then moves to step 2 | [C] |
| 7 (step 2 of 3) | virtual +0x60 on `[0x700227e688]` | | makes a virtual call at offset 0x60 on the object behind `[0x700227e688]` with arguments (2, 0, 0) | [C] |
| Phase change | `f_700108adb0` | `main_0120.c:51324-51358` | event 0x7e arrives at `f_700108adb0`, which stores 4 into `[state+0xc]` when the event id is 0x7e | [C] |
| Phase change (listener) | `f_700108adb0` | slot 9 registers 0x7d and 0x7e on the state and the function sits next to it | that the function is the registered listener | [I] |
| Helper | `f_700108ab40`, `f_7000231000`, `f_7000d558b0` | `main_0120.c:51171-51259`; `[0x700227e128]`, `[0x700227e708]` | gets the singleton at `[0x700227e128]`, sets bit 0x800000 in a flag word at `[obj+0x34]` of `[0x700227e708]`, makes virtual calls at +0x20 and +0x88, calls `f_7000231000(.., 0x16)`, posts to `f_7000d558b0`, then sets step 1 | [C] |
| Next state | virtual +0x60 on `[0x700227e688]` | | only the +0x60 call at the end of phase 4 | [C] |
| Next state (argument) | | | what the 2 means | [H] |

### GAME_INTRO

| Slot | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 5 (enter) | `f_70005748ac` | `main_0121.c:2801-2802`; multiplier `0x358637bd`, about 1e-6 | zeroes phase and step, stores a start time at `+0x8` (seconds: `f_70005748ac` returns an integer tick count, the slot converts it to float and multiplies by 0x358637bd, about 1e-6), zeroes `+0x20`, then makes the +0x60 call with (3, 0, 0) | [C] |
| 7 (step 0 of 3) | `f_70010e6318`, `f_7000e23cec`, `[0x7002295b40]`, object `[0x7003b22ad0]` | | drives the presentation object at `[0x7003b22ad0]` through three steps; step 0 starts it: virtual call at +0x80 on the object at `[0x7002295b40]`, `f_70010e6318`, `f_7000e23cec` | [C] |
| 7 (step 1 of 3) | virtuals +0xa0, +0xd0, +0x98 | | calls its virtual +0xa0 every frame and +0xd0 to ask if a part finished, then +0x98 and step 2 | [C] |
| 7 (step 2 of 3) | virtual +0xe0 | | waits for virtual +0xe0 to return true | [C] |
| 7 (end) | virtual +0x60 | | phase becomes 2 and the +0x60 call with (3, 0, 0) is made again | [C] |
| 32 (skip) | virtual +0xb8 on `[0x7002295b40]` | `main_0121.c:2949-2971` | calls virtual +0xb8 on the object at `[0x7002295b40]` (the one step 0 of slot 7 calls at +0x80), adds 1 to `+0x20`, sets phase 2, so it is an external "skip" that finishes the state | [C] |
| 32 (caller) | | | who calls it | [H] |
| Next state | virtual +0x60 | | the +0x60 call, same as PRE_GAME | [C] |

### LINEUP_INTRO

| Slot | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 5 (enter) | `f_7001c1fb00` | `main_0121.c:10968-11154`; `[[0x700227e688]+0x28]` | logs "ATT_SCREEN: Lineup intro." (`f_7001c1fb00`, 23 callers), stores a start time at `+0x8`, sets byte `+0x28` to (`[[0x700227e688]+0x28]` != 0xa) | [C] |
| 5 (phase pick) | `f_7000f1ec9c`, `f_70000aa6c0`, virtual +0x158 | | picks the starting phase: 2 or 3 by byte `+0x28` (2 when set), 7 when `f_7000f1ec9c` is true, 6 when `f_70000aa6c0` is true, 1 when a virtual call at +0x158 is true and byte `+0x2a` is 0 | [C] |
| 5 (lighting, events) | `f_70012c54ec`, `f_70012d0fcc` | `main_0121.c:10968-11154` | asks the lighting manager for a lighting update with force 0 (`f_70012c54ec`, `f_70012d0fcc(mgr, 0)`) and posts events 0x127 and 0x2cf | [C] |
| 3 (reset) | `f_70005398c0` | hash `0xbbbdd089` | sets byte `+0x2a` to the answer of `f_70005398c0(0xbbbdd089)`, then clears `+0x18` to `+0x27` and sets `+0x34` to -1 | [C] |
| 3 (hash query) | `f_70005398c0` | 233 callers, takes a 32-bit hash; the dev-config notes say options are looked up by hash | it is probably one of the config-query functions | [I] |
| 7 (update) | `f_7000e23cec`, `f_7001097118`, `f_7001097210`, `f_70010973c0`, `f_7000f622dc` | | phase machine over phases 1 to 7 and steps 1 to 3; each phase calls `f_7000e23cec(state, phase)` when it changes, and big single-caller helpers `f_7001097118` (67 lines), `f_7001097210` (119 lines), `f_70010973c0` (79 lines), `f_7000f622dc` (147 lines) | [C] |
| 6 (exit) | `f_70012f3f8c` | `main_0121.c:11155-11200`; `[[0x700227e6b8]+0x20]` | clears `+0x20` and `+0x29`, and when `[[0x700227e6b8]+0x20]` is 0, a global byte is 0 and two values match, starts a fade through `f_70012f3f8c` (string "SPFX - Fade", argument 0.5) | [C] |
| Next state | | | not seen in the skeleton; this state does not make a visible +0x60 call | [H] |

### WARM_UP

| Slot | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 5 (enter) | `f_70010a301c`, `f_7000d1e7b8`, `f_700181c784`, `f_700183eafc` | `main_0121.c:26156-26263` | posts event 0x218, clears `+0x8`, `+0x22`, sets `+0x28` to 8, logs "ATT_SCREEN: Pitcher warmup.", then calls `f_70010a301c(state, 1)`, a 107-line function that logs "GAME_STATE_WARM_UP: state = %s", then calls `f_7000d1e7b8`, `f_700181c784` and `f_700183eafc` and tests a returned value for greater than zero (what they look up was not read) | [C] |
| 5 (phase 1) | `f_70010a301c` | | that it sets phase 1 | [I] |
| 3 (reset) | | `main_0121.c:26140-26155` | resets `+0x8`, `+0x22`, `+0x18`, sets `+0x28` to 8, and logs the same line | [C] |
| 7 (phase changes) | `f_7000574c40`, `f_7000e23cec` | 343 callers | eight phases at `+0x18`; every phase change is `st64[x19+0x18] = value` followed by `f_7000574c40` (the logger, 343 callers) and `f_7000e23cec` | [C] |
| 7 (phase helpers) | `f_70010a301c`, `f_70010a3814`, `f_70010a3908` | | phases 2/3 call `f_70010a301c`, phase 6/7 call `f_70010a3814` (73 lines), phase 8 calls `f_70010a3908` (159 lines); each of those is named by the same "state = %s" string | [C] |
| 6 (exit) | `f_7000f2598c` | `main_0121.c:26371-26426`; `[[0x7000d1cd98]+0x14c]` | calls the function whose string is "Exit" when its object exists, sets a flag at `[[0x7000d1cd98]+0x14c]` to 1, clears phase and step, logs, and resets the input context (`f_7000f2598c(obj, 0, 0)`) | [C] |
| Next state | | | not visible in the skeleton | [H] |

### STADIUM_CREATOR

| Slot | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 5 (enter) | `f_7000f2598c`, `f_7000d558b8` | `[0x7002294220]`; value `0xC47F3` | sets the input context to 0x11 (`f_7000f2598c`), clears a byte at `[0x7002294220]`, calls `f_7000d558b8` with the value 0xC47F3 (what that call does was not read), and zeroes `+0xc` to `+0x13` | [C] |
| 7 (every frame) | `[0x700227e128]` virtual +0x38 | | each frame calls virtual +0x38 on the singleton at `[0x700227e128]` | [C] |
| 7 (phase 0, step 0) | `f_7000eb6abc` | | when phase is 0 and step is 0, calls `f_7000eb6abc(obj, 7)` once and sets step 1 | [C] |
| 7 (step 1) | `f_7000f34134` | `[x19+0x14]` | when step is 1 and `f_7000f34134` returns true and `[x19+0x14]` is not 2, it copies the request into the phase | [C] |
| 7 (phase 1, exit) | `f_7001087120`, `f_700133fcc0`, `f_70013400e0`, virtual +0x58 | | runs the exit sequence: `f_7001087120`, `f_700133fcc0(0,0,1)`, `f_70013400e0` and a virtual call at +0x58 | [C] |
| 6 (exit) | | | the same exit sequence, for when the state is left from outside | [C] |
| Next state | | `[x19+0x14]` | set from outside by writing a value into `[x19+0x14]` | [C] |

### OPTIONS_ON_RAMP

| Slot | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 5 (enter) | `f_70000a82d0`, `f_7000a6d050`, `f_7000ed05b8` | `main_0105.c:27720-27885` | logs "ATT_SCREEN: OptionsOnRamp.", clears `+0x26`, `+0x8`, `+0x3a`, `+0x44`, sets `+0x30`, checks `f_70000a82d0` and `f_7000a6d050` (339 lines, 150 callers), and calls the screen builder `f_7000ed05b8` (299 lines) | [C] |
| 7 (phases) | `f_7000ecfe38`, `f_7000ecfe80` | | ten phases at `+0x18`; it calls two 15-line functions whose strings are "HideAutoPitching" and "HideAutoHitting" | [C] |
| 7 (helpers) | `f_7000ed12b8`, `f_7000ed13e8`, `f_7000ed15e8`, `f_7000ed1738`, `f_7000ed1800` | single caller each | one helper per phase: `f_7000ed12b8` (88 lines), `f_7000ed13e8` (144), `f_7000ed15e8` (102), `f_7000ed1738` (58), `f_7000ed1800` (299) | [C] |
| 6 (exit) | `[0x700227e798]` virtual +0x80 | | resets the object, clears phase and step, resets `+0x20` when it is 5, sets a global byte and finishes with virtual +0x80 calls on `[0x700227e798]` | [C] |
| Meaning | | | the name and the two strings say this screen offers the pre-game options, including whether pitching and hitting are automatic | [I] |
| Next state | | | not visible in the skeleton | [H] |

## Shared helpers

| Function | Evidence | What it does | Tag |
|---|---|---|---|
| `f_7000e23cec(state, phase, flag)` | `main_0100.c:1538-1563`; 56 callers | posts event 0x13d: stores the mode id from `[[0x700227e688]+0x20]`, the phase and the flag next to each other on its stack and passes the address of the first, so listeners hear every phase change | [C] |
| `f_7000e23cec(state, phase, flag)` | | whether the receiver reads the flag is not visible in the posting function | [H] |
| `f_70005e6b40(id, data)` | 964 callers; inferred by argument shape and by slots 9 and 10 using the same ids | posts an event (`f_70005e6830` subscribes and `f_70005e69d0` unsubscribes) | [I] |
| `f_7000f2598c(obj, id, flag)` | `main_0109.c:1312-1344` | stores `id` at `[obj+0x28]` and calls `f_7000d931e0` with it when the id is 1 to 0x12 (it stores 0 instead when the id is out of range or the byte at `+0xc0` is set); states set 0x11 on enter and 0 on exit | [C] |
| `f_7000f2598c(obj, id, flag)` | | meaning "input context" | [H] |
| `f_7000574c40(...)` | 343 callers, takes a format string | the logger: reads a global switch and walks a list of sinks; called with the state log format on every phase change | [I] |
| `f_70005748ac()` | `main_0042.c:41496-41513` | returns a tick count converted to a number with a multiply-by-reciprocal; two imported calls underneath | [C] |
| `f_70000a7360()` | `main_0006.c:29808-29826`; 403 callers | true when `[[0x7003abfa98]+0x18c] == 1` | [C] |
| `f_70000a7360()` | | meaning | [H] |
| `[0x700227e688]` object | | holds a mode id at +0x20 and +0x28 and answers a virtual call at +0x60 that PRE_GAME and GAME_INTRO use to end | [C] |
| `[0x700227e688]` object | | the object's identity | [H] |

## Open questions

| Item | Scope | Why open |
|---|---|---|
| Which function calls slot 5, 6 and 7, and when | all six states | this needs the code that owns the state objects, which was not read |
| What the argument to the +0x60 call means | PRE_GAME (2), GAME_INTRO (3) | not determined from the bodies read |
| How LINEUP_INTRO, WARM_UP and OPTIONS_ON_RAMP end | those three states | the skeletons show phase changes and events but no direct transition call |
| The event ids | 0x7d, 0x7e, 0x11e, 0x1a6, 0x13d, 0x218, 0x127, 0x2cf | only the posting and subscribing sites were read |
| Slots not read | slots 32 and 33 of LINEUP_INTRO, slot 27 and 32 of OPTIONS_ON_RAMP, slots 9 and 10 of OPTIONS_ON_RAMP | not read |
| The loads inside the large slot 7 bodies | LINEUP_INTRO, WARM_UP, OPTIONS_ON_RAMP | read as a skeleton, as explained above |
