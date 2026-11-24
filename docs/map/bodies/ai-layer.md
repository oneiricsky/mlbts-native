# AI decision layer — 47×119 method-table family (main 1.0.20)

Read-only analysis of `work/gen` (generated C) and `work/build/game/exefs/main`. No repo file was modified.
Tag meaning: **[C]** a string, symbol or code read proves it; **[I]** a strong pattern in the code suggests it;
**[H]** a guess.

## Summary

1. The family is **one 119-method virtual interface with 47 implementations** ("method tables"), all in
   `0x7002164248`–`0x700216f3f0`; there are no other 119-slot tables in the binary.
2. Each table is 119 function pointers (952 bytes) followed by 16 zero bytes of padding, stride `0x3c8`;
   an array of 47 pointers to the tables starts immediately after them at `0x700216f3f0`.
3. Every method also has a **public trampoline** (119 of them, `0x70000b4ad4`–`0x70000b7cc4`): check the
   object, resolve its canonical table through `0x70000b4b4c` and the registry, tail-call the method.
4. The **base table** (`0x7002164248`) is a pure default: its 119 entries are tiny stubs at
   `0x70000b7d34`–`0x70000b8084` (`return;` or `return 0`); the other 45 tables override only what they need.
5. The overrides are **small accessors**: state predicates (`return x1 == 8`), float parameter writes
   (`0.2`, `0.35`, `0.56`, `90.0`), enum ids (`0x2d08`, `0x3600`, `0x36d2`) and "supported" flags returning 1.
   None reaches large logic (no callee over 150 generated lines), so this is the **actor/play-control API
   the AI calls**, not the scoring code itself.
6. The role strings are decision-site **labels passed to a gate function** `0x70001c2384`
   ("ONLINE AI BATTER" at `main_0007.c:14607-14611`), not class names — the game has no RTTI (the 16 bytes
   before each table are zeros).
7. Slot use clusters name the consumers: 20–25 fielding/catch, 56–60 baserunning/steal, 73–89 batting/pitching,
   0/1/5/13/33/73 locomotion parameters, 2/3/17/19/37/38/78/84–87/95/96/104/110/114 fixed flags.
8. Three table pairs are byte-identical (`0x7002164248`/`5cc0`, `7b00`/`9940`, `a860`/`dd50`), so 47 tables
   hold 44 distinct method sets.

## Where the data is

- Tables: `0x7002164248` + n×`0x3c8`, n = 0…46, last `0x700216f038`; last block ends `0x700216f3f0`.
- Registry array: `0x700216f3f0`–`0x700216f568` (47 pointers, module-relative addends). Raw read:
  `00700216f3f0: 0000000002164248` / `00700216f3f8: 0000000002164610` / `00700216f400: 00000000021649d8`.
- Padding proof: `00700216f5f8: 00000000000b8084` (slot 118 of table 0), `00700216f600: 0`,
  `00700216f608: 0`, `00700216f610: 00000000000b7d34` (slot 0 of table 1).
- Public trampolines: 119 functions, `0x70000b4ad4` … `0x70000b7cc4`, one per slot; each calls
  `f_70000b4b4c` (`map_find callers 0x70000b4b4c` reports "119 direct callers").

## Slot layout

| Slot group | Meaning | Tag | Evidence |
|---|---|---|---|
| 0, 1 | movement-parameter getter pair, per move type (27 tables override, base returns 0) | C | `f_70000b8f68`: `x2 == 2` → `0x3e4c0000` (0.2) stored to `*x1`; `f_70000b85c0`: `x2 == 4` → `2`, `x2 == 5` → `5` |
| 2, 3 | "interface supported" constant pair; 33 tables use the shared `0x70000b8170`/`0x70000b8178`, 14 use the base 0 | C | `f_70000b8170`: `x0 = (uint32_t)(0x1ull);`; base `f_70000b7d3c` zeroes x0 and stores it (see function map) |
| 4 | default 0; only one table (`0x700216c6a0`) overrides it | C | `f_70000b7d4c` zeroes x0 and is slot 4 in 46 tables |
| 5 | speed/rate query, optionally plus a class-id-specific bonus (90.0) | C | `f_70000b8090`: `fsub32(x2, 0x6)` then `0x42b40000` added when id `0x2cd8`; `f_70000b8590`: `0x3eb33333`/`0x3e4ccccc` |
| 6–19 | state/anim predicates and ids | C | `f_70000b8370` (`x1 == 8`), `f_70000b8388` (returns id `0x2d08`), `f_70000b8c44` (ids `0x11e9`,`0x11ea`,`0x3068`) |
| 20–25 | fielding / catch selection, checked by catch code | I | callers `0x700038b57c` ("Deflection catch"), `0x70003892d4` ("Replacing catch %d with low catch %d."), `0x700038a97c` ("Working catch ring") |
| 28, 29 | state query used by 11 AI-action wrappers (`0x70000b45c0` …) | I | caller list of trampoline `0x70000b6b84` (slot 28) has 11 entries incl. `0x70000b45c0`, `0x70000b4660` |
| 33–36 | float parameter writes (turn/accel style) | C | `f_70000b82b0` stores `0x40400000` (3.0); `f_70000b83bc` stores `0x3f0f5c29` (0.56) when `x2 == 8` |
| 37, 38 | predicate pair, overridden by 34 of 47 tables | C | 34 tables list a non-base function at slot 37/38, e.g. `0x70000b8650`/`0x70000b8658` |
| 43, 50, 56–60 | baserunning / steal decisions | I | slot 57 caller `0x700032fd94` has `RUNNER DECIDE %s foul = %s\n`; slot 59 caller `0x7000335b04` has `[STEAL-JUMPTIMING] …` |
| 61, 63 | shared predicates; slot 61 is the same 7-line function in 30 tables | C | 30 tables use `0x70000b848c` at slot 61 (body returns 1); 33 override the slot |
| 73–75 | bulk loco-parameter fill (7 floats + flag at +0x28) | C | `f_70000b8494`: writes `0x42dc0000` (110.0), `0xc23f6666` (-47.85), `ST32(x19+0x28, 1)`; `f_70000ba4d4`: `0x420e`, `0x40d6`, `0x4249` |
| 76–89 | batting / pitch inputs read by swing and pitch code | I | slot 80 caller `0x70000c6f20` ("ONLINE AI BATTER"); `0x7000358520` has `{Hitchance: %.2f, Hitroll: %.2f …}` |
| 90–96 | capability flags and byte clears | C | `f_70000b8540`/`f_70000b8548`: `ST8(x1, 0u)`; `f_70000b8efc`: returns 1 and `ST32(x2, 0u)` |
| 104–118 | flags plus id mapping | C | `f_70000b8578`: `x1 == 5` → `0x36d2` else `0x3600` |

## Table families

There are exactly **47** 119-slot tables, all in the one page group `0x7002160000`; 44 distinct contents.
Grouping by the set of slots a table overrides (base table excluded) gives these shapes:

| Family | Tables | Tag | Evidence |
|---|---|---|---|
| all-default | 2: `0x7002164248`, `0x7002165cc0` | C | zero overrides; every entry is a `0x70000b7d34`–`0x70000b8084` stub |
| one-method tweaks | 8: `0x70021658f8`,`6450`,`6818`,`6fa8`,`8290`,`8658`,`9578`,`aff0` | C | a single override each, e.g. slot 112→`0x70000b8e90` (returns 1), slot 90→`0x70000b8efc` |
| locomotion profiles | 6: `0x7002167370`,`7b00`,`8de8`,`9940`,`b3b8`,`c6a0` | C | extras `{0,1,4,5,6,8,9,33,43,50,113}`: speed/anim getters plus the slot-73 parameter block |
| steal / runner | 3: `0x700216a498`,`b780`,`f038` (and `ac28`) | I | extras `{10,15,21,28,56,59,63,66,79,116}`; slot 56/59 are the steal-timing inputs |
| hit / pitch | 1: `0x700216bb48` | I | extras `{10,21,28,74,75,80,81,89}`; slots 74/75/80/81/89 are swing and pitch-type inputs |
| hit + catch combo | 5: `0x700216bf10`,`c2d8`,`d988`,`e118`,`e4e0` | I | extras include 24/25 (catch) together with 74/75/80/81/89 (bat) |
| all-round | 2: `0x70021649d8` (45 overrides), `0x7002165530` (47) | C | these two override far more slots than any other class |
| role strings | — | C | `ONLINE FIELDER DECISION` + `ONLINE %s DECISION` + `SUPPORT`/`PUPPET`/`CUTOFF`/`COVER` (`0x70000acfe8`), `ONLINE RUNNER DECISION` (`0x70000b3154`), `ONLINE AI BATTER` + `GRIFFEY REANALYZE PITCH` (`0x70000c6f20`), `AI Chose #%d (%s)` (`0x70000cd760`) |

The remaining 20 tables own unique override sets: the two all-round classes plus one-off combinations
(e.g. `0x700216ce30`, `0x700216d1f8`, `0x700216d5c0`, `0x700216ec70`).

What the families are for, in plain words: the 47 implementations are the per-role control sets the
gameplay/AI code drives — a batter, a runner, a fielder (with SUPPORT/PUPPET/CUTOFF/COVER sub-roles), a
pitcher and supporting actors. Only the four role strings above and the slot-use clusters prove the
mapping; no table carries its own name.

## Function map

| Address | Role | Tag | Evidence |
|---|---|---|---|
| `0x700216f3f0` | registry: 47 table pointers, indexed by class | C | dump `00700216f3f0: 0000000002164248`, `…f3f8: 0000000002164610`; 47 entries to `0x700216f568` |
| `0x70000b4b4c` | resolve an object's canonical method table and its base sub-object | C | `x0 = (uint64_t)(0x700216f000ull); x0 = (uint64_t)(x0 + 0x3f0ull); … f_70000b4b4c` (`main_0006.c:45810-45812`); 119 direct callers |
| `0x70000b4ad4` | public trampoline, slot 5 (speed/rate) | C | after the registry call: `x8 = LD64(x0)` then `x8 + 0x28` (`main_0006.c:45819`) |
| `0x70000b5100` | public trampoline, slot 0 (movement parameter) | C | `x8 + 0x0` after `f_70000b4b4c`; single caller `0x7000265064` |
| `0x70000b52e4` | public trampoline, slot 57 (runner foul decision) | C | caller `0x700032fd94` contains `RUNNER DECIDE %s foul = %s\n` |
| `0x70000b53d4` | public trampoline, slot 59 (steal jump timing) | C | caller `0x7000335b04`: `[STEAL-JUMPTIMING] Steal attempt success/timing roll: …` |
| `0x70000b5678` | public trampoline, slot 35 (six sim callers) | C | callers include `0x70001cfb64` (3370 generated lines) |
| `0x70000b56d0` | public trampoline, slot 73 (loco parameter block) | C | callers `0x7000d1cdc0`, `0x700167bb7c` (has `PERFECT PCI late inside %f …`) |
| `0x70000b61e8` | public trampoline, slot 24 (catch type) | C | caller `0x70003892d4`: `Replacing catch %d with low catch %d.` |
| `0x70000b6264` | public trampoline, slot 25 (catch ring) | C | caller `0x700038a97c`: `Working catch ring`, `Canned catch` |
| `0x70000b6b84` | public trampoline, slot 28 (state query, 11 callers) | C | callers `0x70000b45c0`, `0x70000b4660`, `0x70000b4720`, `0x70000b47a0`, `0x70000db3fc` … |
| `0x70000b6fbc` | public trampoline, slot 84 (bat/contact parameter) | C | caller `0x700035abec`: `Broken Bat Chance: %.3f, Speed %.2f, Location %.2f, Timing %.2f` |
| `0x70000b706c` | public trampoline, slot 79 (batter decision input) | C | callers `0x70000c58d0`, `0x70000c6f20` (ONLINE AI BATTER), `0x70000ca4ec` |
| `0x70000b70c4` | public trampoline, slot 80 (most-used method, 9 callers) | C | caller `0x70000c6f20` ("ONLINE AI BATTER"); `0x7000358520` (`{Hitchance: …}`) |
| `0x70000b7764` | public trampoline, slot 89 (pitch selection input) | C | caller `0x70000cd760` (`AI Chose #%d (%s)`, pitch-percent warnings) |
| `0x70000b7c64` | public trampoline, slot 20 (deflection) | C | caller `0x700038b57c`: `Deflection catch` |
| `0x70000b7d34` | base slot 0, empty default | C | `void f_70000b7d34(Cpu *c) { FN_ENTER(0x70000b7d34ull); return; }` |
| `0x70000b7d3c` | base slot 2, returns 0 | C | zeroes x0 then `c->x[0] = x0; return;` (`main_0006.c:49800-49804`) |
| `0x70000b8170` | shared slot 2 in 33 tables, returns 1 | C | `x0 = (uint32_t)(0x1ull);`; `map_find fn 0x70000b8170` lists slot 2 of 33 tables |
| `0x70000b8178` | shared slot 3, returns 1 | C | identical 7-line body |
| `0x70000b8090` | slot 5 impl: +90.0 speed for class id `0x2cd8` at move type 6 | C | `fsub32(x2, 0x6)` … `x8 = (uint32_t)(0x42b40000ull)` … `compare x0, 0x2cd8` |
| `0x70000b814c` | slot 1 impl: 11 for move type 3, 3 for move type 5 | C | `x2 == 3` → `x8 = 0xbull`, else `x2 == 5` → `x8 = 0x3ull` |
| `0x70000b82b0` | slot 13 impl: writes float 3.0 | C | `x8 = (uint32_t)(0x40400000ull); ST32(x1, x8)` |
| `0x70000b8370` | slot 20 impl: `IsState(8)` | C | `fsub32(x1, 0x8); x0 = (CC_NE) ? 0 : 1` |
| `0x70000b8388` | slot 24 impl: maps `(x1==1, !x2)` to id `0x2d08`, else -1 | C | `x8 = (uint32_t)(0x2d08ull); x0 = (fc_logic32(CC_EQ)) ? x8 : ~0u` |
| `0x70000b8418` | slot 44 impl: `IsState(2)` | C | `fsub32(x1, 0x2); x0 = (CC_NE) ? 0 : 1` |
| `0x70000b8494` | slot 73 impl: fills the loco parameter block | C | `0x42dc0000` (110.0), `0xc23f6666` (-47.85), `ST32(x19 + 0x28, 1)` |
| `0x70000b8540` | slot 95 impl: clears a byte flag | C | `{ uint64_t ea = x1 + 0x0ull; ST8(ea, 0u); }` |
| `0x70000b8578` | slot 118 impl: `x1 == 5` → `0x36d2` else `0x3600` | C | `x9 = (uint32_t)(0x36d2ull); x0 = (CC_EQ) ? x9 : x8` |
| `0x70000b8c44` | slot 16 impl: action-id predicate (`0x11e9`, `0x11ea`, `0x3068`) | C | `x8 = (uint32_t)(0x11e9ull)` … `0x3068ull` |
| `0x70000b8efc` | slot 90 impl: returns 1 and zeroes `*x2` | C | `x0 = (uint32_t)(0x1ull); ST32(x2, 0u)` |
| `0x70000b8f68` | slot 0 impl (class `0x7002167370`): 0.2 for move type 2 | C | `fsub32(x2, 0x2); … 0x3e4c0000` stored to `*x1` |
| `0x70000b8f94` | slot 5 impl: +90.0 for class id `0xbfc` | C | `fsub32(x0, 0xbfc)` … `x8 = (uint32_t)(0x42b40000ull)` |
| `0x70000ba4d4` | slot 74 impl: second loco parameter block (35.5, 6.7, 50.25 …) | C | `0x420e0000` / `0x40d60000` / `0x42490000` stores at `x19+0x30..0x5c` |
| `0x70000bb414` | shared helper, always returns 0 (30 callers) | C | `c->x[0] = x0; return;` with x0 zeroed (`main_0006.c:56718-56722`) |
| `0x70000b3154` | ONLINE RUNNER DECISION site | C | string `ONLINE RUNNER DECISION` (rodata `0x7001cfb0a4`) |
| `0x70000c6f20` | ONLINE AI BATTER decision site | C | `c->x[1] = (uint64_t)(0x7001d4d000ull); c->x[1] = (c->x[1] + 0xb03ull);` → `ONLINE AI BATTER` at `0x7001d4db03` (`main_0007.c:14607-14608`) |
| `0x70000acfe8` | fielder decision dispatcher (role name → `ONLINE %s DECISION`) | C | strings `ONLINE FIELDER DECISION`, `ONLINE %s DECISION`, `SUPPORT`, `PUPPET`, `CUTOFF`, `COVER` |
| `0x70000cd760` | AI pitch-type selection | C | strings `AI Chose #%d (%s)` (rodata `0x7001c401ad`), `AI Pitch Type selection` |
| `0x70000ae8b0` | manager/substitution decision (`ACT_*` actions) | I | strings `ACT_Slot1Out`, `ACT_Slot2Out`, `ACT_OpponentsBullpen` |
| `0x70000a8fe0` | weighted-random decision helper (`Weight2Chance`) | C | `VIRTUAL ASSERT: Weight2Chance() was given weights that summed to 0 …` |
| `0x70000bff54` | loco-ring debug/label function | C | string `Loco Ring` |
| `0x70001c2384` | decision gate: takes the role label, stores the decision flag at object+0x35c8 | C | `x19` = object, `x1` = label; `{ uint64_t ea = x19 + x9; ST8(ea, (uint32_t)x8); }` with `x9 = 0x35c8` (`main_0013.c:36104-36105`) |
| `0x70001c877c` | play-candidate dispatcher, slot 5 of a 6-slot vtable | C | `map_find fn 0x70001c877c`: "in vtable 0x7002175c00 slot 5 of 6"; calls `0x70000c6f20` |
| `0x70001c1540` | "STEAL HIT BATTER SWING" play-candidate selector | I | string `STEAL HIT BATTER SWING` (rodata `0x7001cc92ef`) |
| `0x700032fd94` | runner foul/decision code that consumes slot 57 | C | strings `RUNNER DECIDE %s foul = %s\n`, `RUNNER COMMAND SET TO FOUL BALL!!!!` |
| `0x7000335b04` | steal jump-timing code that consumes slot 59 | C | string `[STEAL-JUMPTIMING] Steal attempt success/timing roll: …` |
| `0x700167bb7c` | swing/PCI code that consumes slots 73, 80, 83 | C | strings `PERFECT PCI late inside %f early outsice %f cutoff %f`, `AXIMUTH[%d] %f timing %f inout %f` |
| `0x7000358520` | hit-chance code that consumes slots 80, 83, 84 | C | string `        {Hitchance: %.2f, Hitroll: %.2f, Tipfoulchance: %.2f, Tipfoul %d, Miss: %d}` |
| `0x700038b57c` | fielding/catch code that consumes slots 20 and 23 | C | string `Deflection catch` |

## What is not mapped

- **No class names.** The build has no RTTI: the 16 bytes just before every table are zero (e.g.
  `0x7002164600`/`0x7002164608` ahead of `0x7002164610`), so the 47 implementations cannot be named from
  the binary; the family labels above come from the slots each class overrides and the role strings of the
  code that calls those slots.
- **No code writes a table address directly.** The four table addresses I scanned (`0x7002164248`,
  `0x7002167370`, `0x700216c2d8`, `0x700216f038`) each occur exactly once in `.rodata`/`.data` — in the
  47-slot registry — and the only code that reads the registry is `f_70000b4b4c`; how an object is bound
  to a table (constructor path) is still open.
- **Most slot semantics.** Slots 4, 6–19, 29–36, 39–55, 62–72 and 100–118 have callers but no read body
  that names them; their role labels above are cluster inferences, not confirmed names.
- **Class ids** `0x2cd8`, `0xbfc`, `0x1d2a`, `0x2611`, `0x2d08`, `0x3068`, `0x3600`, `0x36d2` are compared
  in code but not resolved to names (they look like action/animation ids shared with
  `0x70000b8c44`/`f_70000b8090`).
- **The 16-byte tails** after each table are all zero; their purpose (alignment vs. reserved header) is
  not proven.
- **Which of the 47 tables is which role** is inferred only for the clusters that touch steal, catch and
  bat/pitch slots; the 8 one-method classes and the 2 all-round classes remain unassigned.
- `0x70000c58d0`, `0x70000c5f88`, `0x70000c6124`, `0x70000ca4ec` (the batter-decision helpers called
  by `0x70000c6f20`) were listed but not read line by line.
