# Game states read from their bodies: setup and intro

Six of the twelve game-state classes, read from the generated C (`work/gen/main`, game 1.0.20): PRE_GAME, GAME_INTRO, LINEUP_INTRO, WARM_UP, STADIUM_CREATOR and OPTIONS_ON_RAMP. Tags: [C] the body I read shows it, [I] inferred from a pattern, [H] guess. File and line ranges point at the function in the generated C. In every function `x19` is the state object (`this`).

## How it was read

Small functions were read in full with the register save and restore stripped. The large ones (slot 7 of LINEUP_INTRO, WARM_UP and OPTIONS_ON_RAMP, slot 5 of OPTIONS_ON_RAMP) were read as a skeleton: every call, branch, compare and store, but not every load. So the phase logic is complete for them, and arithmetic between the calls is not. Callee sizes, caller counts and strings come from the local index.

## What each slot does

Checked against all six states.

| Slot | Role | Evidence |
|---|---|---|
| 3 | resets the state's own fields to defaults | [C] every slot 3 is a run of stores to the object: STADIUM_CREATOR `main_0104.c:49979-49986` sets `+0x14` to 2; GAME_INTRO `main_0121.c:2781-2788` zeroes `+0x18` and `+0x20`; OPTIONS_ON_RAMP `main_0105.c:27701-27719` sets `+0x20`=5, `+0x30`=4, `+0x38`=1 |
| 5 | enter: starts the state | [C] LINEUP_INTRO, WARM_UP and OPTIONS_ON_RAMP log "ATT_SCREEN: ..." here; GAME_INTRO and LINEUP_INTRO store a start time; WARM_UP posts event 0x218; PRE_GAME sets phase 2 or 3 |
| 6 | exit: tears the state down | [C] PRE_GAME `main_0120.c:51265-51323` zeroes phase and step; LINEUP_INTRO `main_0121.c:11155-11200` zeroes `+0x20`, `+0x29` and starts a fade ("SPFX - Fade"); WARM_UP `main_0121.c:26371-26426` calls the function whose string is "Exit" |
| 7 | update: runs every frame while the state is active | [I] it is a phase machine that polls (PRE_GAME waits for a byte at `0x70045ad12b` to become 0xff, `main_0120.c:51048-51170`), so it must be called repeatedly; the caller was not read |
| 9, 10 | subscribe and unsubscribe to events | [C] for PRE_GAME (events 0x7d, 0x7e) and LINEUP_INTRO (0x11e, 0x1a6): slot 9 calls `f_70005e6830(id, bus, state, 3)` per event, slot 10 calls `f_70005e69d0(id, bus, 0)` for the same ids. STADIUM_CREATOR and WARM_UP have five-line default stubs. OPTIONS_ON_RAMP slots 9 and 10 are 23 and 20 lines, same size as the others; not read |

The earlier note that slot 3 logs a sub-state is true only for WARM_UP, whose slot 3 also logs "GAME_STATE_WARM_UP: state = %s".

## Phase fields

Each state keeps its position in a phase number on the object. The offset differs by state.

| State | Phase | Step | Other |
|---|---|---|---|
| STADIUM_CREATOR | `+0xc` (0 idle, 1 leaving) | `+0x10` | `+0x14` requested phase, 2 means none |
| PRE_GAME | `+0xc` (2, 3, 4 set; 1, 3, 4 tested) | `+0x10` (0, 1, 2) | |
| GAME_INTRO | `+0x18` (0, 1, 2) | `+0x1c` (0, 1, 2) | `+0x8` start time in seconds, `+0x20` counter |
| LINEUP_INTRO | `+0x18` (1 to 7) | `+0x1c` (1 to 3) | `+0x8` start time, `+0x24` flag, `+0x28` byte, `+0x2a` byte |
| WARM_UP | `+0x18` (1 to 8) | `+0x1c` | `+0x22`, `+0x23` bytes, `+0x28` default 8 |
| OPTIONS_ON_RAMP | `+0x18` (1 to 10) | `+0x1c` (1, 2) | `+0x20` value 1 to 5, default 5 |

[C] for the offsets and the values compared: STADIUM_CREATOR `main_0104.c:50056-50139`, PRE_GAME `main_0120.c:51048-51170`, GAME_INTRO `main_0121.c:2820-2943`, LINEUP_INTRO `main_0121.c:11332-12042`, WARM_UP `main_0121.c:26437-26848`, OPTIONS_ON_RAMP `main_0105.c:28344-28832`. The two-value store `st64[x19+0x18] = 0x100000001` in GAME_INTRO sets phase 1 and step 1 in one write.

## Per state

### PRE_GAME

| Question | Answer |
|---|---|
| Slot 5 | [C] clears a global byte (`[0x7002284000+0x9a8]`), asks `f_70000a7360` (true when `[[0x7003abfa98]+0x18c]` is 1), builds strings with `f_700054aab8` ("PORTALROOM", "EnterGame" are the strings the index finds in it) and sets phase 2, or phase 3 when `f_70000a7360` is true and `f_70008e40a4` is false. Ends by setting the global byte to 1 (`main_0120.c:50925-51047`) |
| Slot 7 | [C] phase 1 sets phase 2 and runs helper `f_700108ab40`. Phase 4 has three steps: step 0 calls `f_70012f3f38(0x78, ...)` and moves to step 1; step 1 waits for the byte at `0x70045ad12b` to equal 0xff, then moves to step 2; step 2 makes a virtual call at offset 0x60 on the object behind `[0x700227e688]` with arguments (2, 0, 0) |
| Phase change | [C] event 0x7e arrives at `f_700108adb0`, which stores 4 into `[state+0xc]` when the event id is 0x7e (`main_0120.c:51324-51358`). That the function is the registered listener is [I]: slot 9 registers 0x7d and 0x7e on the state and the function sits next to it |
| Helper `f_700108ab40` | [C] gets the singleton at `[0x700227e128]`, sets bit 0x800000 in a flag word at `[obj+0x34]` of `[0x700227e708]`, makes virtual calls at +0x20 and +0x88, calls `f_7000231000(.., 0x16)`, posts to `f_7000d558b0`, then sets step 1 (`main_0120.c:51171-51259`) |
| Next state | [C] only the +0x60 call at the end of phase 4. What the 2 means is [H] |

### GAME_INTRO

| Question | Answer |
|---|---|
| Slot 5 | [C] zeroes phase and step, stores a start time at `+0x8` (seconds: `f_70005748ac` returns an integer tick count; the slot converts it to float and multiplies by 0x358637bd, about 1e-6 (`main_0121.c:2801-2802`)), zeroes `+0x20`, then makes the +0x60 call with (3, 0, 0) |
| Slot 7 | [C] drives a presentation object at `[0x7003b22ad0]` through three steps. Step 0 starts it (virtual call at +0x80 on the object at `[0x7002295b40]`, `f_70010e6318`, `f_7000e23cec`). Step 1 calls its virtual +0xa0 every frame and +0xd0 to ask if a part finished, then +0x98 and step 2. Step 2 waits for virtual +0xe0 to return true. Then phase becomes 2 and the +0x60 call with (3, 0, 0) is made again |
| Slot 32 | [C] calls virtual +0xb8 on the object at `[0x7002295b40]` (the one step 0 of slot 7 calls at +0x80), adds 1 to `+0x20`, sets phase 2 (`main_0121.c:2949-2971`), so it is an external "skip" that finishes the state; who calls it is [H] |
| Next state | [C] the +0x60 call, same as PRE_GAME |

### LINEUP_INTRO

| Question | Answer |
|---|---|
| Slot 5 | [C] logs "ATT_SCREEN: Lineup intro." (`f_7001c1fb00`, 23 callers), stores a start time at `+0x8`, sets byte `+0x28` to (`[[0x700227e688]+0x28]` != 0xa), and picks the starting phase: 2 or 3 by that byte (2 when set), 7 when `f_7000f1ec9c` is true, 6 when `f_70000aa6c0` is true, 1 when a virtual call at +0x158 is true and byte `+0x2a` is 0. It asks the lighting manager for a lighting update with force 0 (`f_70012c54ec`, `f_70012d0fcc(mgr, 0)`) and posts events 0x127 and 0x2cf (`main_0121.c:10968-11154`) |
| Slot 3 | [C] sets byte `+0x2a` to the answer of `f_70005398c0(0xbbbdd089)`, then clears `+0x18` to `+0x27` and sets `+0x34` to -1. `f_70005398c0` has 233 callers and takes a 32-bit hash; the dev-config notes say options are looked up by hash, so it is probably one of the config-query functions [I] |
| Slot 7 | [C] phase machine over phases 1 to 7 and steps 1 to 3. Each phase calls `f_7000e23cec(state, phase)` when it changes, and big single-caller helpers `f_7001097118` (67 lines), `f_7001097210` (119 lines), `f_70010973c0` (79 lines), `f_7000f622dc` (147 lines) |
| Slot 6 | [C] clears `+0x20` and `+0x29`, and when `[[0x700227e6b8]+0x20]` is 0, a global byte is 0 and two values match, starts a fade through `f_70012f3f8c` (string "SPFX - Fade", argument 0.5) |
| Next state | [H] not seen in the skeleton; this state does not make a visible +0x60 call |

### WARM_UP

| Question | Answer |
|---|---|
| Slot 5 | [C] posts event 0x218, clears `+0x8`, `+0x22`, sets `+0x28` to 8, logs "ATT_SCREEN: Pitcher warmup." (`main_0121.c:26156-26263`), then calls `f_70010a301c(state, 1)`, a 107-line function that logs "GAME_STATE_WARM_UP: state = %s" (that it sets phase 1 is [I]), then calls `f_7000d1e7b8`, `f_700181c784` and `f_700183eafc` and tests a returned value for greater than zero (what they look up was not read) |
| Slot 3 | [C] resets `+0x8`, `+0x22`, `+0x18`, sets `+0x28` to 8, and logs the same line (`main_0121.c:26140-26155`) |
| Slot 7 | [C] eight phases at `+0x18`. Every phase change is `st64[x19+0x18] = value` followed by `f_7000574c40` (the logger, 343 callers) and `f_7000e23cec`. Phases 2/3 call `f_70010a301c`, phase 6/7 call `f_70010a3814` (73 lines), phase 8 calls `f_70010a3908` (159 lines); each of those is named by the same "state = %s" string |
| Slot 6 | [C] calls the function whose string is "Exit" when its object exists, sets a flag at `[[0x7000d1cd98]+0x14c]` to 1, clears phase and step, logs, and resets the input context (`f_7000f2598c(obj, 0, 0)`) |
| Next state | [H] not visible in the skeleton |

### STADIUM_CREATOR

| Question | Answer |
|---|---|
| Slot 5 | [C] sets the input context to 0x11 (`f_7000f2598c`), clears a byte at `[0x7002294220]`, calls `f_7000d558b8` with the value 0xC47F3 (what that call does was not read), and zeroes `+0xc` to `+0x13` |
| Slot 7 | [C] each frame calls virtual +0x38 on the singleton at `[0x700227e128]`. When phase is 0 and step is 0 it calls `f_7000eb6abc(obj, 7)` once and sets step 1; when step is 1 and `f_7000f34134` returns true and `[x19+0x14]` is not 2 it copies the request into the phase. Phase 1 runs the exit sequence: `f_7001087120`, `f_700133fcc0(0,0,1)`, `f_70013400e0` and a virtual call at +0x58 |
| Slot 6 | [C] the same exit sequence, for when the state is left from outside |
| Next state | [C] set from outside by writing a value into `[x19+0x14]` |

### OPTIONS_ON_RAMP

| Question | Answer |
|---|---|
| Slot 5 | [C] logs "ATT_SCREEN: OptionsOnRamp.", clears `+0x26`, `+0x8`, `+0x3a`, `+0x44`, sets `+0x30`, checks `f_70000a82d0` and `f_7000a6d050` (339 lines, 150 callers), and calls the screen builder `f_7000ed05b8` (299 lines) (`main_0105.c:27720-27885`) |
| Slot 7 | [C] ten phases at `+0x18`. It calls `f_7000ecfe38` and `f_7000ecfe80`, two 15-line functions whose strings are "HideAutoPitching" and "HideAutoHitting", and one helper per phase: `f_7000ed12b8` (88 lines), `f_7000ed13e8` (144), `f_7000ed15e8` (102), `f_7000ed1738` (58), `f_7000ed1800` (299), each with a single caller |
| Slot 6 | [C] resets the object, clears phase and step, resets `+0x20` when it is 5, sets a global byte and finishes with virtual +0x80 calls on `[0x700227e798]` |
| Meaning | [I] the name and the two strings say this screen offers the pre-game options, including whether pitching and hitting are automatic |
| Next state | [H] not visible in the skeleton |

## Shared helpers

| Function | What it does | Evidence |
|---|---|---|
| `f_7000e23cec(state, phase, flag)` | posts event 0x13d: it stores the mode id from `[[0x700227e688]+0x20]`, the phase and the flag next to each other on its stack and passes the address of the first, so listeners hear every phase change; whether the receiver reads the flag is not visible in the posting function [H] | [C] `main_0100.c:1538-1563`; 56 callers |
| `f_70005e6b40(id, data)` | posts an event; `f_70005e6830` subscribes and `f_70005e69d0` unsubscribes | [I] by argument shape and by slots 9 and 10 using the same ids; 964 callers |
| `f_7000f2598c(obj, id, flag)` | stores `id` at `[obj+0x28]` and calls `f_7000d931e0` with it when the id is 1 to 0x12 (it stores 0 instead when the id is out of range or the byte at `+0xc0` is set); states set 0x11 on enter and 0 on exit | [C] `main_0109.c:1312-1344`; meaning "input context" is [H] |
| `f_7000574c40(...)` | the logger: reads a global switch and walks a list of sinks; called with the state log format on every phase change | [I] 343 callers, takes a format string |
| `f_70005748ac()` | returns a tick count converted to a number with a multiply-by-reciprocal; two imported calls underneath | [C] `main_0042.c:41496-41513` |
| `f_70000a7360()` | true when `[[0x7003abfa98]+0x18c] == 1`; 403 callers | [C] `main_0006.c:29808-29826`; meaning [H] |
| `[0x700227e688]` object | holds a mode id at +0x20 and +0x28 and answers a virtual call at +0x60 that PRE_GAME and GAME_INTRO use to end | [C] for the field reads and the call; the object's identity is [H] |

## Not determined

- Which function calls slot 5, 6 and 7, and when. This needs the code that owns the state objects, which was not read.
- What the argument to the +0x60 call means (2 in PRE_GAME, 3 in GAME_INTRO).
- How LINEUP_INTRO, WARM_UP and OPTIONS_ON_RAMP end: the skeletons show phase changes and events but no direct transition call.
- The event ids: 0x7d, 0x7e, 0x11e, 0x1a6, 0x13d, 0x218, 0x127, 0x2cf. Only the posting and subscribing sites were read.
- Slots 32 and 33 of LINEUP_INTRO, slot 27 and 32 of OPTIONS_ON_RAMP, slots 9 and 10 of OPTIONS_ON_RAMP.
- The loads inside the large slot 7 bodies, as explained above.
