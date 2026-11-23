---
name: mlbts-game-code
description: Fluent map of the MLB The Show 26 (Switch 1.0.20) game code and its Windows port (Fastball, this repo). Use before reading, tracing, patching or profiling anything in mlbts-native - game functions (f_7000..., main+0x...), the port's runtime/core, runtime/gfx, runtime/mlb layers, the recompiler, the dev harness, code patch sets, hitches and stalls, PS5 textures, frame rate, saves, input, or "what does this game function / address / subsystem do". Gives the architecture, where each game subsystem lives in the binary, 100+ named game addresses, the tool that looks any function up, and the method that found them.
---

# MLB The Show 26 game code + the Fastball port

Read this first, then open the reference file for the part you are touching. Everything here was checked against the
repo, the binary and `docs/`; each claim is tagged **[C]** confirmed (read from binary/code/measurement),
**[I]** inferred, **[H]** hypothesis. Do not state an [I] or [H] as fact.

## What this is, in six lines

- The game is **MLB The Show 26 for Nintendo Switch, version 1.0.20** (also 1.0.15). ARM64 code in two modules:
  `main` (base `0x7000000000`, 94,991 functions, the game) and `sdk` (base `0x7004c00000`, 40,069 functions, Nintendo
  SDK 19.3.11 + NVN). `rtld` is not recompiled. [C]
- **The port is a static recompilation.** `recomp/gen.py` turns every ARM64 function into C
  (`void f_<address>(Cpu *c)`, in `work/gen/{main,sdk}/*.c`, ~10.5M lines, git-ignored, rebuilt from the player's own
  game files). `runtime/` is a fake Switch OS + NVN-to-Vulkan graphics under that code. [C]
- Guest addresses are host addresses. A function's name *is* its address: `f_70012c54ec` = guest `0x70012c54ec` =
  `main + 0x12c54ec`. [C]
- The game has **no RTTI and no symbols** except SDK exports: 39 named in `main`, 19,260 in `sdk`. The game's own
  ~95,000 functions are anonymous. Meaning is recovered from strings, vtables, address neighbourhood, SDK calls and
  tracing. [C]
- Game data never goes in git: `work/`, `gamefiles/`, `refs/` are ignored. Derived indexes of game code stay under
  `work/map/`. A release contains no game code. [C]
- The owner is not a graphics programmer: explain findings in plain words (see the repo `CLAUDE.md` rules).

## Honest status of this skill (read before trusting it)

This is an **index-level** map, not a read-through of the code. Built from: the repo docs, the port's source (parsed), strings and vtables recovered from the original
machine code for all 135,060 recompiled functions, and six region notes written by Haiku agents from that index. Function **bodies** read in full so far: one
(`0x700108b628`, see known-functions.md). About 12,800 of `main`'s 94,991 functions reference a string; the rest are known only by neighbours, vtable slots, callers and size.
Treat region-note roles tagged [I] or [H] as leads, not facts, and read the body (see the playbook) before building on one. Next step if more fluency is wanted: read the bodies
of the state handlers (`docs/map/regions/D-*.md`), the game-mode table (`0x7000e0fb10`) and the 47 AI class vtables of 119 slots, and add what you verify to known-functions.md.

## First 60 seconds on any task

1. Rebuild/check the local index if `work/map/index/` is missing: `python -I tools/map_all.py` (needs
   `python -I -m pip install libclang --target work/pylib` once; ~2 min).
2. Look the thing up instead of grepping 10 million lines:

   ```
   python -I tools/map_find.py fn 0x700108b628     # size, callers, callees, strings, vtable slot, string-bearing neighbours
   python -I tools/map_find.py str "MSDF took"     # which function uses a message/asset/UI string
   python -I tools/map_find.py near 0x7000e54c00   # nearest functions that mention strings (linker order = source order)
   python -I tools/map_find.py region 0x7001000000 # what the 256 KB around an address is about
   python -I tools/map_find.py callers 0x70005a1a90
   python -I tools/map_find.py name nvnQueue       # SDK/libc symbols
   python -I tools/map_find.py src hd_apply        # a function of this repo's own source
   ```
3. Read the generated C at the file:line `fn` prints, or `python -I tools/disasm.py work/build/game/exefs/main <addr> <len>`.
4. To see it run: `MLB_FNTRACE`, `MLB_FNDUMP`, the harness (reference: tracing-playbook.md).
5. Before changing anything: the repo rules in `CLAUDE.md` (diagnose first, numbers before and after, commit style,
   one game instance per run slot, no game data in commits).

## Reference files (open only what the task needs)

| File | Open it when |
|---|---|
| `references/port-architecture.md` | touching `runtime/`, `recomp/`, boot, services, graphics replay, settings, versions |
| `references/game-binary.md` | asking "where/what is this in the game": layout of `main`, game-state machine, engine, data, strings |
| `references/known-functions.md` | you have a game address or need the address of something already identified |
| `references/tracing-playbook.md` | you must find out what game code does: methods, tools, patch workflow, evidence rules |
| `references/history-and-open-questions.md` | before reopening a problem already investigated, or choosing what to research next |
| `docs/map/regions/*.md` (A to F) | you need the per-window subsystem table and ~40 key functions of one address range; written by Haiku agents from the index, all claims tagged, spot-checked (106 of ~120 quoted strings matched, the rest escaping/truncation) but no function body was read |
| `docs/map/README.md`, `source/*.md`, `binary.md`, `coverage.md` | a function of the port's own source (11,308 listed with callees and purpose), or binary totals and the coverage check |

## Rules that bit people before

- **Diagnose before fixing; numbers before and after with run counts.** The pitch hitch was first written off as
  "inherent GPU waits" and was in fact one redundant lighting bake (fixed by a 7-site code patch). Never call a game
  behaviour inherent until you have asked *why the game does that work*.
- **1.0.15 and 1.0.20 differ.** Code addresses moved by +0x20..+0x1500, data by about +0x1000. Comments in `runtime/`
  are 1.0.15's unless they say otherwise. `tools/addrmap.py` maps an address between versions; every patch and every
  game-address hook picks its address per version. All addresses in this skill are **1.0.20** unless marked.
- **The game steps by measured frame time**, so frame-rate work does not need game patches (see port-architecture).
- **No env/config lookup in a per-draw or per-call path**, even in diagnostics: it cost 12 ms a frame once.
- **Dev harness drifts**: compare fixed-from-frame-0 configurations or matched game events, never frame numbers.
- **One game instance per slot**; start runs through `tools/game.py`, and never run long game runs unasked.
- **A code patch is a unit**: patch lines in `tools/data/patches-<ver>.txt`, a settings row in `runtime/mlb/cfg.c`
  (default on), a menu toggle, a doc with Cause / fix / what else changes / how it was checked.
- **Do not trust an address in an older comment** without checking it in the index for the right version.

## The wiki

The same knowledge is published as the GitHub wiki of `oneiricsky/mlbts-native`. The skill is the source for the game-code pages (this page is Start-here, the
references become How-the-port-works, The-game-binary, Known-game-functions, Tracing-playbook and History-and-open-questions, and the region notes become Region-A to
Region-F). The findings pages (walk-up freeze, match-start freeze, load stalls, frame rate, PS5 textures, upstream bugs, dev harness) are written by hand in `docs/wiki/`.
Rebuild every page with `python -I tools/wiki_build.py` (writes `work/wiki/`, checks that all links resolve); never edit a generated page in the wiki, edit its source
here. Publishing is a push to `git@github.com:oneiricsky/mlbts-native.wiki.git` (branch `master`), only when the owner asks. Steps that worked on 2026-11-23: run
`wiki_build.py`; with `GIT_TERMINAL_PROMPT=0` and `GIT_SSH_COMMAND="C:/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -o ConnectTimeout=15"` clone the wiki to `work/wikirepo`
(the clone and `ls-remote` print a harmless "IO is still pending on closed socket" line; if a clone fails, run it again); `cp work/wiki/*.md work/wikirepo/`; commit there with
`git -c user.name="Sky Miles" -c user.email="14169181+oneiricsky@users.noreply.github.com" commit` (signing comes from the global config; do not change config); `git push origin master`.
GitHub creates the wiki repository only when someone saves a first page in the web UI, and the owner has to be signed in for that. Check the result by fetching each page
(`/oneiricsky/mlbts-native/wiki/<Page>` should return 200).

## Keeping this skill true

If you learn a game function's meaning, add it to `references/known-functions.md` with its tag, the evidence and the
version. If the map tools change, update the commands above. If something here is contradicted by the code, fix this
skill in the same commit.
