---
name: mlbts-game-code
description: Fluent map of the MLB The Show 26 (Switch 1.0.20) game code and its Windows port (Fastball, this repo). Use before reading, tracing, patching or profiling anything in mlbts-native - game functions (f_7000..., main+0x...), the port's runtime/core, runtime/gfx, runtime/mlb layers, the recompiler, the dev harness, code patch sets, hitches and stalls, PS5 textures, frame rate, saves, input, or "what does this game function / address / subsystem do". Gives the architecture, where each game subsystem lives in the binary, 100+ named game addresses, the tool that looks any function up, and the method that found them.
---

# MLB The Show 26 game code + the Fastball port

Read this first, then open the reference file for the part you are touching. Everything here was checked against the
repo, the binary and `docs/`; each claim is tagged [C] confirmed (read from binary/code/measurement),
[I] inferred, [H] hypothesis. Do not state an [I] or [H] as fact.

## Overview

- The game is MLB The Show 26 for Nintendo Switch, version 1.0.20 (also 1.0.15). ARM64 code in two modules:
  `main` (base `0x7000000000`, 94,991 functions, the game) and `sdk` (base `0x7004c00000`, 40,069 functions, Nintendo
  SDK 19.3.11 + NVN). `rtld` is not recompiled. [C]
- The port is a static recompilation. `recomp/gen.py` turns every ARM64 function into C
  (`void f_<address>(Cpu *c)`, in `work/gen/{main,sdk}/*.c`, ~10.5M lines, git-ignored, rebuilt from the player's own
  game files). `runtime/` is a fake Switch OS + NVN-to-Vulkan graphics under that code. [C]
- Guest addresses are host addresses. A function's name *is* its address: `f_70012c54ec` = guest `0x70012c54ec` =
  `main + 0x12c54ec`. [C]
- The game has no RTTI and no symbols except SDK exports: 39 named in `main`, 19,260 in `sdk`. The game's own
  ~95,000 functions are anonymous. Meaning is recovered from strings, vtables, address neighbourhood, SDK calls and
  tracing. [C]
- Game data never goes in git: `work/`, `gamefiles/`, `refs/` are ignored. Derived indexes of game code stay under
  `work/map/`. A release contains no game code. [C]
- The owner is not a graphics programmer: explain findings in plain words (see the repo `CLAUDE.md` rules).

## Reliability

Read this before trusting the map.

This is an index-level map, not a read-through of the code.

| Built from | Detail |
|---|---|
| Repo | the docs and the port's source (parsed) |
| Binary | strings and vtables recovered from the original machine code for all 135,060 recompiled functions |
| Region notes | six, written by Haiku agents from that index |

How far the reading goes:

- Every one of the 135,060 functions is classified: import name, SDK symbol, library, string evidence, or code shape (getter, forwarder, empty stub, ...).
- The 47,308 `main` functions that had no string, symbol or shape were then read from their own code in batches, normalised to the operations that matter.
- A completeness pass now reads every remaining body, the unnamed `sdk` functions included, so that the coverage chart's body-read bar reaches 100% everywhere. [Reading every function body](Reading-every-function-body) has the method, and the chart and the Read roles page show how far it has got.
- Bodies read in full: the handlers of all 12 game-state classes (about 60 functions, read by agents and spot-checked, 20 claims per report, with the wrong ones corrected; see `docs/map/bodies/`) and about 300 more from the subsystem passes.

How far to trust it:

- The read roles are leads, not verified facts. A 10-function audit found 6 right, 1 incomplete and 3 with a wrong specific detail, so open the body before relying on a detail (the wiki's Read roles page carries the same warning).
- Treat region-note roles tagged [I] or [H] as leads, and read the body (see the playbook) before building on one.
- Next step if more fluency is wanted: verify the read roles in a second pass, and add what you verify to known-functions.md.

## First steps

1. Rebuild/check the local index if `work/map/index/` is missing: `python -I tools/map_all.py` (needs
   `python -I -m pip install libclang --target work/pylib` once; ~2 min).
2. Look the thing up instead of grepping 10 million lines:

   | Command | Use |
   |---|---|
   | `python -I tools/map_find.py fn 0x700108b628` | size, callers, callees, strings, vtable slot, string-bearing neighbours |
   | `python -I tools/map_find.py str "MSDF took"` | which function uses a message, asset or UI string |
   | `python -I tools/map_find.py near 0x7000e54c00` | nearest functions that mention strings (linker order is source order) |
   | `python -I tools/map_find.py region 0x7001000000` | what the 256 KB around an address is about |
   | `python -I tools/map_find.py callers 0x70005a1a90` | direct callers |
   | `python -I tools/map_find.py name nvnQueue` | SDK and libc symbols |
   | `python -I tools/map_find.py src hd_apply` | a function of this repo's own source |
   | `python -I tools/map_find.py role 0x700108b628` | the complete map's row: kind, role, shape, evidence, window |
   | `python -I tools/fnxref.py 0x70003dde10` | every string a function references, in code order; use it instead of `str` when one string blob serves many functions |
   | `python -I tools/strdump.py 0x7001c7d37f` | the C string at a guest address |
   | `python -I tools/map_read_prep.py --limit 200` | normalise the next unread functions into a dossier for body reading |
   | `python -I tools/map_read_merge.py` | validate the read answers into `work/map/index/roles_read.jsonl` (applied by `tools/map_roles.py`) |
3. Read the generated C at the file:line `fn` prints, or `python -I tools/disasm.py work/build/game/exefs/main <addr> <len>`.
4. To see it run: `MLB_FNTRACE`, `MLB_FNDUMP`, the harness (reference: tracing-playbook.md).
5. Before changing anything: the repo rules in `CLAUDE.md` (diagnose first, numbers before and after, commit style,
   one game instance per run slot, no game data in commits).

## Reference files

Open only what the task needs.

| File | When |
|---|---|
| `references/port-architecture.md` | touching `runtime/`, `recomp/`, boot, services, graphics replay, settings, versions |
| `references/game-binary.md` | asking "where/what is this in the game": layout of `main`, game-state machine, engine, data, strings |
| `references/known-functions.md` | you have a game address or need the address of something already identified |
| `references/tracing-playbook.md` | you must find out what game code does: methods, tools, patch workflow, evidence rules |
| `references/history-and-open-questions.md` | before reopening a problem already investigated, or choosing what to research next |
| `docs/map/regions/*.md` (A to F) | you need the per-window subsystem table and ~40 key functions of one address range; written by Haiku agents from the index, all claims tagged, spot-checked (106 of ~120 quoted strings matched, the rest escaping/truncation) but no function body was read |
| the wiki's Function map (`Function-map`, `Function-census`, `Functions-A` to `Functions-SDK`) | you need every function of a region or window: the complete census and the per-region register of every function with a symbol, import or string |
| the wiki's subsystem pages (`Fielding`, `Frontend`, `Audio`, `AI-actor-API`, `Lighting`, `Game-modes`) | you need the on-field rings, the UI/screen layer, the audio path, the 119-slot actor API, the lighting bake or the end-of-game records, read from the bodies and checked against the index |
| `docs/map/README.md`, `source/*.md`, `binary.md`, `coverage.md` | a function of the port's own source (11,308 listed with callees and purpose), or binary totals and the coverage check |

## Working rules

| Rule | Why |
|---|---|
| Diagnose before fixing; numbers before and after, with run counts | The pitch hitch was first written off as "inherent GPU waits" and was one redundant lighting bake (fixed by a code patch: 6 sites for the lighting plus 1 for the league-leader lists). Never call a game behaviour inherent until you have asked why the game does that work |
| 1.0.15 and 1.0.20 differ | Code addresses moved by +0x20 to +0x1500, data by about +0x1000. Comments in `runtime/` are 1.0.15's unless they say otherwise. `tools/addrmap.py` maps an address between versions, and every patch and game-address hook picks its address per version. All addresses in this skill are 1.0.20 unless marked |
| The game steps by measured frame time | Frame-rate work does not need game patches (see port-architecture) |
| No env or config lookup in a per-draw or per-call path | Even in diagnostics: it cost 12 ms a frame once |
| The dev harness drifts | Compare fixed-from-frame-0 configurations or matched game events, never frame numbers |
| One game instance per slot | Start runs through `tools/game.py`, and never run long game runs unasked |
| A code patch is a unit | Patch lines in `tools/data/patches-<ver>.txt`, a settings row in `runtime/mlb/cfg.c` (default on), a menu toggle, and a doc with Cause, fix, what else changes and how it was checked |
| Do not trust an address in an older comment | Check it in the index for the right version |

## Wiki publishing

The same knowledge is published as the GitHub wiki of `oneiricsky/mlbts-native`.

| Source | Wiki pages |
|---|---|
| this page | Start-here |
| the references | How-the-port-works, The-game-binary, Known-game-functions, Tracing-playbook, History-and-open-questions |
| the region notes | Region-A to Region-F |
| `docs/wiki/`, written by hand | the findings pages: walk-up freeze, match-start freeze, load stalls, frame rate, PS5 textures, upstream bugs, dev harness |

Rebuild every page with `python -I tools/wiki_build.py` (writes `work/wiki/`, checks that all links resolve). Never edit a generated page in the wiki; edit its source here.

Publishing is a push to `git@github.com:oneiricsky/mlbts-native.wiki.git` (branch `master`), only when the owner asks. Steps that worked on 2026-11-23:

1. Run `wiki_build.py`.
2. With `GIT_TERMINAL_PROMPT=0` and `GIT_SSH_COMMAND="C:/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -o ConnectTimeout=15"`, clone the wiki to `work/wikirepo`. The clone and `ls-remote` print a harmless "IO is still pending on closed socket" line; if a clone fails, run it again.
3. `cp work/wiki/*.md work/wikirepo/`
4. Commit there with `git -c user.name="Sky Miles" -c user.email="14169181+oneiricsky@users.noreply.github.com" commit` (signing comes from the global config; do not change config).
5. `git push origin master`
6. Check the result by fetching each page (`/oneiricsky/mlbts-native/wiki/<Page>` should return 200).

GitHub creates the wiki repository only when someone saves a first page in the web UI, and the owner has to be signed in for that.

## Maintenance

If you learn a game function's meaning, add it to `references/known-functions.md` with its tag, the evidence and the
version. If the map tools change, update the commands above. If something here is contradicted by the code, fix this
skill in the same commit.
