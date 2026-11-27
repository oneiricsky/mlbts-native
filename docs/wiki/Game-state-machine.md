The game's top-level flow is a set of 12 state classes that share one interface, and each topic below is one table. Their function bodies were read by four agents, and each report was then spot-checked against the generated C (20 claims per report), so this page keeps what held up. The detail pages are [Intro states](Intro-states), [Batter up state](Batter-up-state), [Play states](Play-states) and [End states](End-states). Tags: C means the body shows it, I means inferred, H means a guess.

## The 12 classes

| State | Vtable | Handlers |
|---|---|---|
| STADIUM_CREATOR | `0x70021d7400` | `0x7000eb72b4` |
| OPTIONS_ON_RAMP | `0x70021dbed0` | `0x7000ed20d0` |
| PRE_PLAY | `0x70021e1798` | `0x700106d054` to `0x700106f0d0`, `0x7001071a64` |
| PRE_GAME | `0x70021e22c8` | `0x700108ae04` |
| BATTER_UP | `0x70021e2708` | `0x700108b418` to `0x700108e610`, `0x700108ed0c` |
| GAME_INTRO | `0x70021e2998` | `0x700108f7a4` |
| GAME_OVER | `0x70021e2b00` | `0x700108f7c4` to `0x70010920f4`, `0x70010924e0` |
| INNING_OVER | `0x70021e2d38` | `0x7001092518`, `0x700109276c`, `0x70010936d4` |
| IN_PLAY | `0x70021e2ea0` | `0x70010936ec` to `0x7001094afc`, `0x70010961b8` |
| LINEUP_INTRO | `0x70021e2fb0` | `0x700109773c` |
| PLAY_OVER | `0x70021e3258` | `0x700109a680` to `0x700109d510`, `0x700109d8c4` |
| WARM_UP | `0x70021e3538` | `0x70010a2e78` to `0x70010a3908`, `0x70010a3b5c` |

## What each vtable slot does

| Slot | Role | Tag |
|---|---|---|
| 0, 1 | destructor thunks, 5 lines each | [C] |
| 2 | returns the state's name | [C] |
| 3 | resets the state's own fields to defaults (WARM_UP also logs) | [C] |
| 5 | enter: runs once when the state starts. Intro states log `ATT_SCREEN: ...` and store a start time; BATTER_UP resets its timer and fields and asks for the stadium lighting; PLAY_OVER starts the background lighting bake | [C] |
| 6 | exit: clears phase and step, resets the input context | [C] |
| 7 | update: runs every frame, adds the frame time into a float at `[this+0x8]`, then runs a phase machine | [C] |
| 9, 10 | subscribe and unsubscribe to events on a bus at `[0x7002298000+0x428]` | [C] |
| 32, 33 | skip hooks and sub-state tables, differ by state | [I] |
| 5 to 7 | nothing calls them directly: they are reached through the vtable by whatever owns the state, so "enter", "exit" and "update" are readings of what the bodies do | [I] |

Events subscribed through slots 9 and 10:

| State | Events subscribed |
|---|---|
| BATTER_UP | 17 events |
| PRE_PLAY | 7 events |
| IN_PLAY | 22 events |

## Where the sub-state lives

| State | Sub-state | Phase or step |
|---|---|---|
| BATTER_UP | `[this+0x18]` | `[this+0x1c]` |
| PRE_PLAY | `[this+0x18]` | |
| IN_PLAY | `[this+0xc]` | `[this+0x10]` |
| GAME_OVER | `[this+0x18]` | `[this+0x1c]` |
| PRE_GAME, GAME_INTRO and other intro states | `+0xc` or `+0x18`, by state | |

The one function every phase change passes through:

| Function | What it does | Open | Tag |
|---|---|---|---|
| `f_7000e23cec` | every phase change goes through it; it posts event 0x13d (56 callers). It stores the mode number, the new phase and a flag next to each other on its stack and passes the address of the first | whether the receiver reads the flag is not visible | [H] |

## BATTER_UP sub-states

| Value | Name | Set by |
|---|---|---|
| 0 | NONE | event 0x151 |
| 1 | WALK_UP | writer not found |
| 2 | WALK_UP_PRES | `0x700108c030`, `0x700108cc58` |
| 3 | PLAYERS_SETUP | `0x700108c904`, `0x700108cd24`, `0x700108d9d0` |
| 5 | SELECT_PITCH | `0x700108cf34` |
| 7 | LAUNCH_PITCH | `0x700108d4ec` (6 if the global at `0x70022b65b0` is 0x12) |
| 8 | CAREER_PREPITCH | writer not found |
| 9 | IN_PITCH | `0x700108e610`, which also posts event 0x133 |
| 10 | MANAGER_MODE | `0x700108d4ec` with flag 0, which posts 0x16b |

What the table adds up to:

| Point | Detail | Tag |
|---|---|---|
| Decoding | from the jump table in the setter `0x700108b500`, with each case's log string matched | [C] |
| Path | NONE, WALK_UP or WALK_UP_PRES, PLAYERS_SETUP, SELECT_PITCH, LAUNCH_PITCH, IN_PITCH, with MANAGER_MODE reachable from SELECT_PITCH | |
| Values 4, 6, 11 | used but never logged | |
| Handover | how BATTER_UP hands over to the next state is not found: slot 7 has no block for sub-states 8 or 9 | |

## IN_PLAY sub-states

| Value | Name | Note |
|---|---|---|
| 0 | NULL | slot 3 clears it and logs `state = NULL` |
| 1 | IN_PITCH | event 0x13f moves here unless already 1 |
| 2 | IN_PLAY | |
| 3 | POST_PITCH | |
| 4 | ANIM_SEQUENCE | entry posts (4, 0), waits 2.5 s if a flag is set |
| 5 | PLAY_OVER | in this sub-state `0x700109448c` (slot 7) posts request (7, 0, 0) every update to hand over |

Its event handler:

| Function | Role | Note |
|---|---|---|
| `0x70010939dc` | IN_PLAY's event handler: a function the state calls, not a vtable slot | event 0x13f moves it to IN_PITCH, and the 0x213 rules were checked |
| `0x70010939dc` | the same handler also reacts to 0x38, 0x61, 0x20a, 0x5b and 0x21a | those were read but not re-checked |

## PRE_PLAY and GAME_OVER names

| State | Names | Table | Note | Tag |
|---|---|---|---|---|
| PRE_PLAY | 22 sub-state names, 0 ONLINE_SYNC_META to 21 EXIT | pointer table at `0x70022d19a8` that slot 5 addresses literally | | [C] |
| GAME_OVER | sub-states 0 to 14 (NONE, MERCY_RULE, PRES_GROUP_A and so on) and five phases (ENTER, LOAD, UPDATE, UPDATE_PRES, EXIT) | sub-states at `0x70021e2c90`, phases at `0x70021e2d00` | slot 5 picks the first sub-state, and nearly every presentation ends in POST_GAME_MENU | [C] |

The mercy-rule message depends on a byte at `[[0x700227e6b8]+0x137]`:

| Condition | Message |
|---|---|
| byte is zero | "Game called due to mercy rule" |
| byte is nonzero | the "griefing rules" text |

## The end of a play

| Function | What it does | Tag |
|---|---|---|
| PLAY_OVER slot 5 | posts event 0x11c and starts the background lighting bake (`f_70012c54ec`, then `f_70012d20a0`) | |
| `f_700109aa1c` | then picks how the play is shown by trying presentation kinds in order: 0xb, 0xa, 6, and 6 again through `f_70010e672c`. The first accepted kind is stored at `[this+0x20]` and routes the exit | [C] |
| reading of 0xb | that 0xb means game over | [I] |
| INNING_OVER slot 5 | posts event 0x11 | |
| `f_7000ed562c` | called by INNING_OVER's CHECK_SUB step; it holds the "Do you still want ... to come in? You have 15 seconds" prompt | |

## Not found

| Question | State |
|---|---|
| What ends an inning or a game | not in these handlers: the outs and score tests live elsewhere |
| How BATTER_UP leaves | no block for its last sub-states |
| What most event ids mean | only the ones above have a seen effect |
| Names for BATTER_UP 4, 6, 11 and PLAY_OVER 1, 6, 7 | used, never logged |
| Who owns and calls the states | no direct caller of slots 5 to 7 |
