# In-game trainer: design

2026-11-24. For game version 1.0.20. Status: approved and built the same day. Stage 1 works; stages 2 and 3 ship as
readouts; stage 4 and the writes of stages 2 and 3 are not built. What happened to each is in `docs/trainer.md`.

Tags: **[C]** read from the code or seen live, **[I]** inferred, **[H]** guess. "My call" marks a choice the owner has
not made and can overrule.

## Intent

The owner asked for an in-game trainer that is not part of the F1 menu (its settings may be), then asked for it to
reach more of the game than match state, and chose the full version: memory edits plus function hooks, built in
stages. The owner has not said what it is mainly for (practice, play, or testing the port). My call: treat it as an
offline practice and sandbox tool.

## Goals

- Change a running match from inside the game, with a panel and hotkeys of its own.
- Reach match state, match settings, pitcher state, the batted ball and wind, then ratings, game speed and runners.
- Say honestly on screen what is not available (wrong version, no match, target not found yet).
- Cost nothing when off.

## Non-goals

- Online play and Diamond Dynasty.
- Version 1.0.15 in the first stages (its ExeFS is not on this machine). The trainer is unavailable there.
- Editing save files (`tools/save_edit.py` is the place for that).

## What would make it a failure

- It crashes a match or damages a save.
- With the trainer off, the game behaves or performs differently.
- A control that looks like it works and does nothing.

## Constraints

- Repo rules: a settings row in `runtime/mlb/cfg.c` for every setting (also a command-line flag), no config or
  environment lookup in a per-draw or per-call path, `recomp/` unchanged, MLB code in `runtime/mlb/`, vendored edits
  marked `fastball`.
- No game code or data in git.
- One game instance at a time for test runs (the lock folder); another session may be using the game.

## Approaches

| | What | For | Against |
|---|---|---|---|
| A | Outside program (like `tools/scenario.py`) | no build change | no in-game panel |
| B | In the runtime, memory edits only | small; low risk | cannot read or change anything decided in an instant, such as a batted ball |
| **C (chosen)** | In the runtime, memory edits plus hooks | reaches the batted ball and finds live objects | needs a build with new patch sets; more to verify |

## How it fits together

```text
keys / pad ──> trainer_ui (panel, ImGui)  ──requests──>  trainer (state, rules)
F1 tab ─────> cfg.c rows ─────────────────────────────>        │
                                                    ┌──────────┴──────────┐
                                           trainer_game (memory)   trainer_hooks (patch sets)
                                                    └────────── the running game ──────────┘
```

| Unit | File | Does | Depends on |
|---|---|---|---|
| Game access | `runtime/mlb/trainer_game.c` | Per-version address table; typed read and write of each target; answers "available, and why not" | `host.h` memory checks |
| Rules | `runtime/mlb/trainer.c` | Freezes, saved situations, applying queued requests once per presented frame | game access, cfg |
| Hooks | `runtime/mlb/trainer_hooks.c` | Host functions the patched call sites reach; records and optionally overrides | patch sets, game access |
| Panel | `runtime/gfx/ui/trainer_ui.cpp` | Draws the panel and readouts; turns keys and pad into requests | rules |
| Settings | `cfg.c`, a "Trainer" tab in `menu.cpp` | On/off, keys, panel corner and opacity, what stays on | cfg |

The panel never touches game memory. Only game access knows addresses. The logic in `trainer.c` and `trainer_game.c`
must be testable against a fake memory block, without the game.

### Memory edits

Every read and write checks the pointer chain with `mem_guest_readable` and a range check on the value found (outs
0..2, and so on). A check that fails marks that control unavailable and logs once. Writes happen once per presented
frame; `tools/scenario.py` has shown asynchronous writes to the count object to work [C]. Whether the other targets
tolerate it is part of each stage's live check.

### Hooks

The patch table already allows a guest `bl` to be replaced at generation time, switchable at run time
(`recomp/patches.py`). My plan [I, not yet built]: replace a caller's `bl <game function>` with a `bl` to an unused
address in the patch page, and register a host function there (`rt_register_host`, before `rt_dispatch_init`). The
host function calls the original with `rt_call`, then reads or changes the result. Switched off, the generated code
is one byte test and the original call. `rt_patch_switch` turns it on and off while the game runs. No recompiler
change is needed. What the code already shows [C]: the patch page (`0x7004b34000`) lies just past main's image, so
dispatch looks an address there up among host functions (`runtime/core/dispatch.c` refuses only addresses inside a
module), and it is within a `bl`'s 128 MB reach of main's code. Hook addresses must avoid the page words the patch
sets already use. The first hook of stage 3 proves this before anything else is built on it; if it does not work,
stop and bring the alternatives to the owner.

## Panel and controls (my calls)

```text
 TRAINER                              F2 hide
 [Match]  Pitcher  Hitting  Settings
 Balls   < 3 >     Strikes < 2 >    Outs < 2 >
 Away    < 4 >     Home    < 3 >
 Jump to inning  < 7 top >                 [go]
 Slot 1: 3-2, 2 out, 4-3        [save] [load]
```

- A compact window in a screen corner. The game stays visible and keeps running.
- F2 shows and hides it. F3 saves the situation, F4 replays it. Slow motion toggles on F6. All rebindable.
- While the panel has focus the game gets no input, as with F1. Hotkeys work with the panel hidden.
- Controller: hold both stick clicks to show and hide; inside, the D-pad and A/B work as in F1.
- Off by default (`MLB_TRAINER=0`), switched on in the F1 Trainer tab. A small "TRAINER" mark stays on screen while
  any freeze or override is active.
- Overrides and freezes reset when the match ends. Saved situations persist in `<profile>/trainer.txt`.
- In Season, Franchise and Road to the Show the first change of a match asks for confirmation, because the result
  goes into the save.

## Stages

Each stage is usable on its own and ends with its live check. A target that cannot be confirmed live ships as
unavailable, with the finding written down.

| Stage | Contents | Targets and confidence | Done when |
|---|---|---|---|
| 1 | Panel, F1 tab, hotkeys; balls, strikes, outs, scores, inning jump, saved situations | count object `[[main+0x227e6b8]]` [C]; inning jump lets the game play out one out and cannot go back [C] | a saved situation replays with matching read-back, 5 of 5 |
| 2 | Match settings by name; pitcher energy, confidence, stamina: show, set, freeze | settings `[main+0x4651350]` keys [I, teams C]; pitcher state offsets [C code, not live]; the live object found by a hook or a traced pointer chain | each setting listed as live, pre-match only or no effect, from a test; frozen energy holds over 20 pitches |
| 3 | Batted-ball readout (launch, direction, speed scale, spin); forced values with presets | contact result struct from `f_7001679cdc`'s first argument, callers `f_700028b4a4` and `f_700028d254` [I] | the readout matches the game's own exit-velocity screen; a forced launch angle shows on that screen |
| 4 | Wind; ratings; slow motion; runners | wind override [H]; ratings in live memory not yet traced; time step `main+0x22c90c4` [C address, scaling untested]; runners get rebuilt within about 3 s [C] | each is either working with a live check, or recorded as not reachable with the reason |

Open risks: the contact model may also run for the CPU's own predictions, so stage 3 has to tell a real swing from a
simulated one. Slow motion may upset the game's timing or audio. Some settings are probably read only at game entry.

## Checking

- A host test program (like `tools/harness_parse_test.c`) for the rules and the access layer against fake memory:
  range checks, freezes, situation save and load.
- Live runs in a `tools/game.py` slot with the audio check and the lock; read-back by log lines and
  `tools/scenario.py`.
- Trainer off: the generated code's only change is the byte test at patched sites; compare replay frame times before
  and after, with run counts.
- The panel is not a web page, so instead of WCAG tooling: assert text contrast of the panel colours (7:1 aim, 4.5:1
  minimum) and a minimum row height in the host test.

## Left to the builder

Names inside the files, the layout of `trainer.txt`, the exact patch site addresses, and the order of work inside a
stage.
