# PLAY_OVER, INNING_OVER and GAME_OVER: what the handler bodies do

Game 1.0.20. All three classes sit in `work/gen/main/main_0121.c`, so every "main_0121.c:N" below is a line in that file unless another file is named. I read the generated C of the handlers (with the register save and restore stripped) and the data tables they use. I did not run the game. A claim is tagged [C] when the body I read shows it, [I] when it is a reading of what I saw, [H] when it is a guess.

The generated C was read with the shell filter in the Tracing playbook. Two helper roles are my reading [I]: `f_7001c1fb40` takes the log string in x0 and looks like a print call, and `f_7001c1fc90(0xa)` follows a print each time, so it looks like a newline.

Notation: `[global 0xADDR + off]` is a field of the game object that the pointer at 0xADDR names. The game reaches these through its table of globals, loading the slot and then loading again through it; a few (such as 0x7003aeb818) are plain variables loaded once. The object's real type is not known.

## The three classes share one design

| Part | Evidence | Tag |
|---|---|---|
| Object | each state is an object (x0, held in x19) with a small-integer sub-state and a small-integer phase | C |
| Slot 5 | one-time setup work: clears timers, posts game events, picks the first sub-state; takes no time step | C |
| Slot 7 | per-frame update: its first lines keep the time step (s0) and add it to a float at `[state+8]`; then it switches on the sub-state and phase | C |
| Slot 3 | resets fields and prints the state name; PLAY_OVER sets sub-state 2, GAME_OVER sets sub-state 0 | C |
| Calling pattern | nobody calls slots 5 and 7 directly (the index shows 0 callers), so "once on entry" and "once per frame" are the natural reading and not something I saw called | I |
| Name print | every sub-state change prints `GAME_STATE_<CLASS>: state = <NAME>` | C |

Per-frame time: PLAY_OVER slot 7 adds the time step into `[state+8]` at main_0121.c:16719. INNING_OVER slot 7 keeps it in s8 and adds it in the first part of the function (6604-6720). GAME_OVER slot 7 passes it to `f_70003aaf00` at 3609.

The phase is a second counter inside each sub-state. Each sub-state has a begin handler (phase 0), an update handler (phase 2) and a finish check (phase 3). A sub-state change stores the new number, resets the phase to 0, prints the name and calls `f_7000e23cec`.

`f_7000e23cec(state, sub-state, flag)` (main_0100.c:1538, 56 callers) only posts game event 0x13d. It stores three 32-bit values next to each other on its stack (the number at `[global 0x700227e688 + 0x20]`, the sub-state and the flag) and passes the address of the first [C]. How many of them the receiver reads is not visible in the posting function [H]. The event posting function is `f_70005e6b40(event id, data pointer)` (main_0047.c:816, 964 callers).

## Slot 5 and slot 7 by state

| State | Slot 5 | Slot 7 | Slot 3 |
|---|---|---|---|
| PLAY_OVER | `f_700109a6a8`, 197 lines: enter | `f_700109af70`, 1,255 lines: per-frame switch | `f_700109a680`: set sub-state 2 and print POST_PLAY |
| INNING_OVER | `f_7001092518`, 163 lines: enter | `f_700109276c`, 789 lines: per-frame switch | no handler of its own among those read |
| GAME_OVER | `f_700108f904`, 414 lines: enter, picks the first sub-state | `f_700108ff50`, 549 lines: per-frame jump table | `f_700108f7c4`: set sub-state 0, allocate a helper object |

GAME_OVER has two more per-frame pieces. Slot 33 (`f_70010920f4`, main_0121.c:6080) is a second jump table for sub-states 4 to 13 (table at 0x7001d9c960 in the data, 10 entries, main_0121.c:6090-6100) [C]. A helper `f_700108f87c` (main_0121.c:3085-3133, four direct callers in the index) sets the sub-state: it stores its second argument at `[state+0x18]` and its third at `[state+0x1c]` and prints the name from a table [C].

## GAME_OVER sub-states, read from the game's own tables

GAME_OVER prints names from two arrays in the data. I read them straight from the image [C].

| Value | Name | Seen set at |
|---|---|---|
| 0 | NONE | slot 3 (3040) |
| 1 | MERCY_RULE | slot 5 (3281) |
| 2 | WAIT_FOR_MESSAGE | `f_70010907f8` (4288) |
| 3 | PERFORMANCE_EVAL | name only; printed in slot 33 (6294) |
| 4 | PRES_GROUP_A | slot 5 (3468), slot 7 (4033), `f_70010907f8` (4267) |
| 5 | PLAYER_OF_GAME | name only; printed in slot 33 (6306) |
| 6 | PRES_GROUP_B | `f_7001090fec` (4946) |
| 7 | PRES_COPYRIGHT | `f_70010911d8` (5022) |
| 8 | PRES_REEL | `f_7001091fb4` (5992) |
| 9 | PRES_REEL_SAVE | name only |
| 10 | POST_GAME_MENU | slot 5 (3342), slot 7 (3864) and eleven other places |
| 11 | REPLAY_VAULT | `f_7001091e78` (5903) |
| 12 | PRES_RTTS_OUTRO | name only |
| 13 | PRES_MOMENTS_OUTRO | slot 5 (3435) |
| 14 | FADE_COMPLETE_EXIT_GAME | name only |

The value table is at 0x70021e2c90 (entry n is value n+1). The phase table is at 0x70021e2d00 and holds five names: 0 ENTER, 1 LOAD, 2 UPDATE, 3 UPDATE_PRES, 4 EXIT, stored at `[state+0x1c]` [C].

"Name only" means the name is in the table and I found no handler that stores that value or prints it by itself. Values 3 and 5 are printed as names by slot 33, so they exist as sub-states even though I did not see where they are set.

## GAME_OVER: how it starts and what picks the first sub-state

Slot 5 (main_0121.c:3134-3587) does these things in order [C]:

1. Calls `f_70000a7360` and `f_70000a7430` and updates two settings objects through `f_7000df2bb0` and `f_7000df7b28` (3140-3225).
2. Posts event 0x11 to the event object at `0x7002291000+0x5d8` (3231) and clears `[global 0x7003b14aa8 + 0x398]` (3239).
3. Stores `f_70005748ac()` times 1.0e-6 (the constant 0x358637bd) in `[state+8]` at 3268-3274: a clock reading in seconds.
4. Chooses the first sub-state:

| Test | Result | Line |
|---|---|---|
| byte `[global 0x7003aeb818 + 0x136]` is nonzero (read at 3276) | sub-state 1 MERCY_RULE | 3281 |
| else `f_70000aa6c0()` is true | sub-state 10 POST_GAME_MENU | 3342 |
| else `f_70000a8220()` or `f_70000a82e0()` is true | sub-state 13 PRES_MOMENTS_OUTRO | 3435 |
| else (after `f_70008898c4` and two bytes) | sub-state 4 PRES_GROUP_A | 3468 |

The byte at `[global 0x7003aeb818 + 0x136]` is the mercy-rule flag, [I]: its only visible use is to start MERCY_RULE. What the three predicates mean is not shown by their bodies in this note [H]; they are short functions with 403, 146 and few callers.

MERCY_RULE (value 1) is entered by `f_70010906bc` (main_0121.c:4137-4227). It calls `f_7000e23cec` with the current sub-state, sets byte `[state+0x31]` to 1, builds a message and hands it to `f_70008a846c`. The message text depends on byte `[global 0x700227e6b8 + 0x137]`: zero gives "Game called due to mercy rule." (string at 0x7001ca5f49) and nonzero gives "Game called due to griefing rules." (0x7001d2d0be) [C: both strings read from the data, the byte is read at 4167]. It sets the phase to 2 (4192) and prints the name.

Other fields in GAME_OVER:

| Field | Meaning | Tag |
|---|---|---|
| `[state+0x08]` | float: start time in seconds, written in slot 5 and in `f_70010906bc` | C |
| `[state+0x18]` | sub-state number | C |
| `[state+0x1c]` | phase number | C |
| `[state+0x20]` | 16-bit value read at offset 0x130 of the result of `f_700181a6bc` (3245-3249) | C |
| `[state+0x24]` | result of `f_7000ed5528` (3227-3229) | C |
| `[state+0x28]` | set to 4 in slot 3 (3060); cleared in slot 5 | C |
| `[state+0x30]` | byte set to 1 at the top of slot 7 (3611) | C |
| `[state+0x38]` | pointer to a 0x28-byte helper object created by `operator new` in slot 3 (3061-3085) | C |

Almost every presentation sub-state in GAME_OVER ends by setting sub-state 10, POST_GAME_MENU: `f_700108ff50` (3864), `f_7001090a58` (4504), `f_7001090d88` (4786), `f_7001090fec` (4850, 4903), `f_70010911d8` (5041), `f_7001091330` (5214), `f_70010915a0` (5278), `f_70010918e8` (5503), `f_70010920f4` (6139, 6220) [C]. PRES_GROUP_A goes to WAIT_FOR_MESSAGE (4288). PRES_COPYRIGHT is set by `f_70010911d8` (5022).

The data above shows that GAME_OVER runs a chain of presentation sub-states and ends in POST_GAME_MENU. It does not show what ends the whole game, because value 14 (FADE_COMPLETE_EXIT_GAME) is only a name in the table [C] and no store of 14 is in the handlers I read.

## PLAY_OVER sub-states

The numbers are my mapping from each store to the string printed beside it. No table gives these names.

| Value | Name | Evidence |
|---|---|---|
| 0 | WAIT | printed at 16228 and 18025, set at 16229 and 18021 |
| 1 | no name | stored by slot 5 at 16220; its update handler `f_700109c0b8` hands over to 0 |
| 2 | POST_PLAY | slot 3 (16047); 16896 and 18088 |
| 3 | PRES_LOAD | 17670, 18041, 18450, 18476 |
| 4 | PRES_ENDOFPLAY | 16898 |
| 5 | PRES_GAMEOVER | 16882 |
| 6 | no name | handled at 16990-17030; no string |
| 7 | no name | stored at 17564 and 19674; no string |
| 8 | CHALLENGE_PLAY_PROMPT | 17853 |
| 9 | CHALLENGE_PLAY | 19027-19028, 19425-19426 |
| 10 | EXIT | 16853, 16932, 16977, 17020, 17061, 17584, 19314-19315 |

The state keeps its sub-state at `[state+0x24]` and the phase at `[state+0x28]`; phase values seen are 0 (begin), 2 (running) and 3 (finished) [C].

## PLAY_OVER: how a play ends

Slot 5 `f_700109a6a8` (main_0121.c:16052-16276) [C]:

1. Clears `[state+8]` and byte `[state+0x1c]`, and calls `f_700134df20(0)`.
2. Posts event 0x11c (16104).
3. Calls `f_70012c54ec` (the lighting manager) and then `f_70012d20a0` (16110): this starts the background lighting bake after each play, the one the walk-up freeze notes describe.
4. Calls `f_700109aa1c` (below) and then loops over a few checks on `f_70002e2348` (play data) that end in `f_700109ab58` when a base-running or ball-state condition holds.
5. Sets `[state+0x24]` to 1 (16220) when `f_70000a7360` or `f_7000a8325c` is true; otherwise sets it to 0 and prints WAIT (16228-16229).

`f_700109aa1c` (16299-16388) decides how this play will be presented. It starts `[state+0x20]` at 6 (16308), then asks the presentation controller, which it gets from the object at `0x7002295000+0xb40`, whether it can show a presentation of a kind. The tests run in this order: kind 0xb (gated by the byte `[global 0x700227e798 + 0x58]`), then kind 0xa (`f_70010e62c4(0xa)` must be true, and a virtual call at slot 0x170 answers), then kind 6 (`f_70010e62c4(6)`), then kind 6 once more through `f_70010e672c`. The first one accepted is stored in `[state+0x20]` with byte `[state+0x19]` set to 1 (16368-16369) [C]. That the kinds are presentation ids, and that 0xb means "game over" and 6 "normal end of play", is my reading of how the next step uses them [I].

Slot 7 `f_700109af70` then runs these sub-states [C], with the lines where each finishes:

| Sub-state | Begin | Update | Next |
|---|---|---|---|
| 1 | `f_7000e23cec`, then waits for `f_7000a8325c` (16820-16845) | `f_700109c0b8` | 0 WAIT (18021) |
| 0 WAIT | enter code at 16755-16830: posts event 0x11b once, sets a wait time at `[state+0x2c]` | loop at 17312-17493 | 3, 7 or 8 (17564, 17670, 17853) |
| 3 PRES_LOAD | `f_700109c1b4` (18030) | `f_700109c414` (18200) | by `[state+0x20]`: 0xb gives 5, 0xa gives 10, else 4 or 2 (16853-16898) |
| 4 PRES_ENDOFPLAY | `f_700109c534` (18283) | `f_700109c608` (18345) | 10 EXIT (16932); `f_700109c608` can also set 3 (18450, 18476) |
| 5 PRES_GAMEOVER | `f_700109c800` (18488) | virtual calls on the presentation controller | 10 EXIT (16977) |
| 6 | `f_7000e23cec(this,6)` | virtual calls on the presentation controller | 10 EXIT (17020) |
| 2 POST_PLAY | `f_7000e23cec(this,2)`, event 0x11b once | `f_700109c8bc` (18542) | 10 EXIT (17061) |
| 7 | `f_700109cbe8` (18773) | virtual calls | 10 EXIT (17584) |
| 8 CHALLENGE_PLAY_PROMPT | `f_700109cd28` (18864) | `f_700109ce30` (18937) | 9 (19028) |
| 9 CHALLENGE_PLAY | inline at 17626-17700 | `f_700109d498` (19394) | not read |

The WAIT sub-state decides how long to hold. Phase 0 computes `[state+0x2c]`, a number of seconds, from the play-result values `[game+0x30c]` and `[game+0x310]` (where game is `*(f_70016703f0()+8)`) and from several flags: the constants stored are 0, 1.0, 1.5, 2.0, 2.5, 3.0 and 3.5 (17215-17305) [C]. The update loop at 17312-17493 waits until `[state+8]` (elapsed) reaches that value, with early-out tests on `f_7001824b74(0x13)` and a flag at `[global 0x700227e6b8 + 0x128]`, then sets phase 3 (17493). The phase 3 handling at 17519-17575 calls `f_700109ade4` (16585, post-play work), reads `[game+0x308]` and `[game+0x310]` (compared with 2, 6 and 8), asks the presentation controller, and then picks 7 (if the byte `[global 0x700227e6b8 + 0x3d]` is set), 3 or 8. The three exits are at 17564, 17670 and 17853.

The EXIT handler `f_700109cf7c` (19034-19330, 292 lines) sets sub-state 10 and prints EXIT (19314-19315). It calls `f_700107e208` (main_0120.c:36295, 447 lines), which holds the strings "The batter", "The pitcher" and "A runner" and calls `f_70001e8834` (main_0014.c:28526, 2,158 lines), a play-result text builder with strings such as " stole home. " and " stole 3rd. " [C]. So EXIT builds the written description of the play [I].

PLAY_OVER state fields:

| Field | Meaning | Tag |
|---|---|---|
| `[state+0x08]` | float: seconds spent in the current sub-state | C |
| `[state+0x18]` | byte: set to 1 after event 0x11b has been posted once (16768-16778) | C |
| `[state+0x19]` | byte: a presentation kind was chosen (16347) | C |
| `[state+0x1a]` | byte: set to 1 after two events 0x14d are posted in `f_700109c1b4` (18134-18145) | C |
| `[state+0x1e]` | byte: set to 1 in `f_700109c1b4` when a presentation starts (18082) | C |
| `[state+0x20]` | the chosen presentation kind: 6, 0xa or 0xb | C |
| `[state+0x24]` | sub-state | C |
| `[state+0x28]` | phase: 0, 2, 3 | C |
| `[state+0x2c]` | float: how many seconds WAIT holds | C |

## INNING_OVER

The sub-state is at `[state+0x18]` and the phase at `[state+0x1c]` (both read as 32 bits, stored as 64). Names come from the strings printed beside each store.

| Value | Name | Set at |
|---|---|---|
| 0 | NORMAL | slot 5 (6565-6566) |
| 1 | PRESENTATION | slot 5 (6480-6481) |
| 2 | START_INNING_PRES | 6984-6985, 7158-7159 |
| 3 | CHECK_SUB | 7048-7049 |
| 4 | no name | 6875 |
| 5 | DONE | 7125-7126, 7300-7301 |

Slot 5 `f_7001092518` (6441-6603) [C]:

1. Posts event 0x11 (6455).
2. If the object from `0x7002295000+0xb40` (virtual slot 0x80) has `[+0x450] == 10` (6475), sets sub-state 1 and prints PRESENTATION.
3. Otherwise reads the half-inning counter `[global 0x700227e6b8 + 0x20]`. It rotates it right by 1 to get a count, takes bit 0 as a flag, adds 1, looks up two 16-bit values through `f_700184abb4`, and posts events 0x121 and 0x13b with them (6485, 6559). Then sets sub-state 0 and prints NORMAL.
4. Calls `f_7000574c40` and the newline helper, and if the counter equals 7 calls `f_70014aea4c(1)` and `f_70014af940` (6570-6579). I did not read those two.
5. Clears byte `[state+0x20]`.

Slot 7 `f_700109276c` (6604-7560, 789 lines) [C unless marked]:

| Sub-state | Action | Next |
|---|---|---|
| 0 NORMAL | per-frame call through the object at `0x700227e128` (virtual slot 0x38, with the time step), then phases 0 to 5: waits `[state+8]` against 2.0 s or 10.0 s (picked by `f_7000d7412c`; constants 0x40000000 and 0x41200000 at 6657-6658), posts event 0 to the object at `0x7002291000+0x5d8`, then a short hold and event 0x29a (6755) | 4 (6875) |
| 1 PRESENTATION | same phase ladder as 0, through `f_70003aaf00` for the time step | 4 (6875) |
| 4 | begin posts event 0x121 again and calls `f_7001093390` (7469) and `f_7001093278` (7393); update waits on the presentation controller | 2 START_INNING_PRES (7158) or 5 DONE (7125) |
| 2 START_INNING_PRES | posts event 0xcc, runs the presentation controller | 3 CHECK_SUB (7048) |
| 3 CHECK_SUB | reads bytes `[ctx+0x784]`, `[ctx+0x125]` and the value `[ctx+0x12c]` (7173-7180), clears bit 22 of `[global 0x700227e708 + 0x34]` (7199), calls `f_70013400e0`, `f_700133fcc0(1,0xff,1)`, `f_7000ed2780` and `f_7000ed562c` (7208; the function is main_0105.c:33822) | 5 DONE (7300) |
| 5 DONE | posts an event and tests the phase; the rest of the block was not read | not read |

`f_7000ed562c` (148 lines, one caller, `f_700109276c`) holds the prompts "Do you still want %s %s to come in? You have 15 seconds ..." and "Do you still want to change pitchers?" [C]. So CHECK_SUB is where a pending pitching change or substitution is confirmed with a 15 second limit [I]. No function with the SubstitutionLogic strings is reachable within two calls of any INNING_OVER handler [C: call-tree search]. Where the substitution is decided is therefore not in these handlers.

Slot 6 `f_70010934d8` (7560-7602) clears byte `[state+0x20]` and, through the object at `0x7002296000+0x848`, calls `f_7000eb466c`. Slot 32 `f_7001093558` was not read.

INNING_OVER state fields:

| Field | Meaning | Tag |
|---|---|---|
| `[state+0x08]` | float: seconds in the current phase | C |
| `[state+0x10]` | buffer handed to virtual calls on the presentation controller | C |
| `[state+0x18]` | sub-state | C |
| `[state+0x1c]` | phase: 0 to 5 | C |
| `[state+0x20]` | byte flag, cleared in slots 5 and 6 | C |

## The loop, as far as the bodies show

| Step | Evidence | Tag |
|---|---|---|
| BATTER_UP to IN_PLAY to PLAY_OVER | the earlier handler read (`f_700108b628`); PLAY_OVER slot 5 is entered after a play and starts the lighting bake | I |
| PLAY_OVER decides how the play is shown | `f_700109aa1c` picks kind 0xb (game over), 0xa or 6 | C |
| PLAY_OVER after the wait | sub-state 5 PRES_GAMEOVER if the kind is 0xb, EXIT if 0xa, otherwise PRES_ENDOFPLAY or POST_PLAY | C |
| PLAY_OVER finishes | sub-state 10 EXIT in every path; the number 10 is printed as the name | C |
| INNING_OVER runs | NORMAL or PRESENTATION, then START_INNING_PRES, CHECK_SUB (pitching change prompt), DONE | C |
| GAME_OVER runs | MERCY_RULE, POST_GAME_MENU, PRES_MOMENTS_OUTRO or PRES_GROUP_A first, then presentations, ending at POST_GAME_MENU | C |

What leaves each state is not in these bodies. Nothing I read stores a different game-state class: EXIT, DONE and POST_GAME_MENU are the final sub-states, and the code that sees them lives in whatever calls slots 5 and 7. Outs, score and inning tests, and the choice between INNING_OVER and GAME_OVER, are not in these handlers [H that they are in the caller or in the play data].

## Named callees seen

| Function | Role | Where seen |
|---|---|---|
| `f_70005e6b40` | post a game event (id in x0, data pointer in x1) | all three states |
| `f_7000f2598c` | post an event to the object at `0x7002291000+0x5d8` | INNING_OVER, GAME_OVER |
| `f_7000e23cec` | announce a sub-state change (event 0x13d) | all three states |
| `f_70012d20a0` | start the background lighting bake | PLAY_OVER slot 5 |
| `f_70016703f0` | return the game context; `+8` points at the play data | PLAY_OVER |
| `f_7000574c40`, `f_7001c1fb40`, `f_7001c1fc90` | print a string, print a string through a thunk, print a newline | all three states |
| `f_7000ed562c` | confirm a pitching change or substitution | INNING_OVER CHECK_SUB |
| `f_700107e208`, `f_70001e8834` | build the play description text | PLAY_OVER EXIT |
| `f_70010906bc` | enter MERCY_RULE and build its message | GAME_OVER |
| `f_70003aaf00` | per-frame call that takes the time step | INNING_OVER, GAME_OVER |

## Not determined

| Question | Why open |
|---|---|
| who calls slots 5 and 7 and what reads sub-state 10, 5 or POST_GAME_MENU | the callers are indirect; no direct call exists in the index |
| what ends an inning or a game (outs, score, extra innings) | no such test is in the handlers read |
| PLAY_OVER sub-states 1, 6, 7 | handled but never printed |
| the meaning of presentation kinds 0xa and 6 and the predicates `f_70000aa6c0`, `f_70000a8220`, `f_70000a82e0` | their bodies were not read |
| PLAY_OVER slots 6, 9, 10, 22, 32 and the 8-slot table at 0x70021e3378 | only slot 33 and table slot 3 were seen, both set CHALLENGE_PLAY |
| what follows CHALLENGE_PLAY and what handles phase 3 of EXIT | not read |
| GAME_OVER values 3, 5, 9, 12, 14 | names exist, no store found |
| INNING_OVER sub-state 4 and the DONE tail | partly read |
| the helper object GAME_OVER slot 3 builds at `[state+0x38]` and the callback address it holds | not read |
