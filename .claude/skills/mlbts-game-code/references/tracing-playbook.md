# How to find out what game code does

The game has no symbols for its own code, so understanding comes from several independent clues. Combine at least two before calling something [C].

## 1. Static clues (no game run)

1. **Strings.** `python -I tools/map_find.py str "<text>"` finds functions that reference a message, asset name, UI screen name or state name.
   Built from the original ARM64 `adrp`+`add` pairs (`tools/map_strings.py`), so it sees what the machine code uses. About 12,800 of `main`'s
   94,991 functions reference at least one string; pure compute code (like the MSDF pass) has none.
2. **Neighbours.** The linker lays one source file's functions next to each other. `map_find.py near <addr>` shows the closest string-bearing
   functions; `region <addr>` gives the theme of a 256 KB window. An anonymous function inherits its neighbours' subsystem [I].
3. **Vtables.** `work/map/index/vtables.jsonl` (5,813 runs in `main`): a run of function pointers is a class's virtual methods. Strings of its
   members name the class's role; the same slot across sibling vtables shows the interface (the 12 game states). No RTTI exists, so class names
   do not; the studio's reflection system ("Flux", ClassBroker) holds names as strings.
4. **Call graph.** `fn` lists direct callees (named when they have strings or SDK names) and `callers N`. Indirect branches (`rt_dispatch`,
   31,920 functions) are not in the graph; PLT stubs near `0x7001c1fb50` fan out to libc/SDK.
5. **SDK names.** 19,260 named `sdk` functions (`map_find.py name <text>`); `main` calls them through the PLT, so a game function calling
   `nn::fs::ReadFile`, `nvnQueueSubmitCommands`, `nn::hid::GetNpadState` is that kind of code.
6. **Disassembly.** `python -I tools/disasm.py work/build/game/exefs/main <addr> <len>` (names PLT targets). Offsets are module-relative in some
   tools: `sdk+0x13e700`; for `main`, subtract `0x7000000000`.
7. **Generated C** at the file:line `fn` prints (`work/gen/main/main_NNNN.c`). Registers are locals, `LD64/ST64` are loads/stores, `rt_dispatch` is an
   indirect branch, `FN_ENTER(addr)` marks function entry. Noisy: prefer the clues above first.
8. **Dev-config option names.** `BOOT/CONFIG_MAIN.TXT` options are matched by a 32-bit hash: ELF-style hash then `h*0x9E3779B7 + ~h*0x61C88641`
   (`docs/dev-config.md`); only 27 of 109 hashes are named.

## 2. Dynamic clues (run the game; only short runs unasked)

- **`MLB_FNTRACE=<addr>,...`** logs each call of those game functions (caller, x0; x0 shown as text if it points at a string); `<lo>-<hi>` logs the
  first call of every function in a range. **`MLB_FNTRACE_PEEK=<off>,...`** logs a value behind x0 when it changes.
- **`MLB_FNDUMP`** (dev builds) logs fields of the object a traced function receives, whenever they change. The one documented use, which found the
  lighting manager's behaviour, was `MLB_FNDUMP=70012e0150:d3c,d38,101400:f,101404:f` (function, then offsets; `:f` reads a float). Read the
  parser in `runtime/mlb/` before relying on any other form; the format is not documented elsewhere.
- **`MLB_TRACE=fs`** logs every file open/read/close (with `MLB_FS_STACK=<path text>` also the game's call stack): ties assets to code.
  `svc,host,ipc,fs,gfx,perf,sched,audio,present,all` are the other channels.
- **Game log lines** `[lm 0] ...` are the game's own log; `uiEngine: Entering screen: [<movie>-><screen>]` names every UI screen entered.
- **Sampler** `MLB_SAMPLER=on` (slows the game): slow frames dump `prof.txt.f<frame>`; read with `tools/prof_report.py <profile> [mlb.map] --top 40 --chains 30`.
  Express costs as a share of the thread's busy time.
- **Memory/state.** `MLB_STATEDUMP=1` + F8 writes main's data+bss for diffing situations; `MLB_WATCH=<addr>,<size>;...` logs texture creations and GPU writes in a guest range;
  harness `dump = buffer:addr=...` or `texture:fmt=0x25,size=512x512`.
- **Graphics**: F12 capture (draw log, render targets), RenderDoc MCP (`pixel_history`, `debug_pixel`), `MLB_DRAWTEX`.
- **Scenarios**: `tools/scenario.py` and `tools/scenarios/*.txt` drive the harness into a situation (teams, stadium, stop condition); `tools/game.py` runs it in a slot;
  `tools/harness.py compare` byte-compares dumps; `tools/bench.py` alternates configurations.

## 3. From finding to fix

1. State the cause with evidence (a repro, a log, a measurement). If unconfirmed it is a hypothesis; test it.
2. Ask **why the game does this work**, not how to make it cheaper. Check upstream first (`git fetch` to a temp ref and search the log; 0.2.0 had already fixed the freeze that took days to chase).
3. Prefer a **code patch set** (`tools/data/patches-1.0.20.txt`): list sites as original words and replacement words; each replacement may write only registers the following code overwrites
   before reading, and must not set flags unless intended. The generator checks the original words. Add the 1.0.15 equivalent via `tools/addrmap.py`, or mark 1.0.20-only.
4. Ship as one unit: patch + settings row in `runtime/mlb/cfg.c` (default on) + toggle in `runtime/gfx/ui/menu.cpp` + a doc with Cause, the fix, what else changes, how it was checked.
5. Measure per-change: before/after with the run count, alternated, same settings, fixed from frame 0; uncapped (the 60 fps cap hides per-frame cost); first run of a fresh slot is slower (caches).
   Verify output equality by byte compare when the patch should not change output (the MSDF texture SHA-256), and say how many inputs it covers.
6. Commit rules: Conventional Commit type subjects (`fix(gfx): ...`), SSH-signed by 1Password, author Sky Miles, model Co-Authored-By trailer allowed in this repo, push only when asked.

## 4. Evidence discipline

Tag [C]/[I]/[H] in docs and comments. "Inherent" is not a finding. A screenshot is not a verification; put a number, assertion or log next to it. Name what a check could not measure before using the eye.
