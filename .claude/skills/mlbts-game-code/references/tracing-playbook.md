# How to find out what game code does

The game has no symbols for its own code, so understanding comes from several independent clues. Combine at least two before calling something [C].

## 1. Static clues (no game run)

| Clue | How | Shows | Limit |
|---|---|---|---|
| Strings | `python -I tools/map_find.py str "<text>"` (built from the original `adrp`+`add` pairs by `tools/map_strings.py`) | which function uses a message, asset name, UI screen name or state name | about 12,800 of `main`'s 94,991 functions reference a string; pure compute code (like the MSDF pass) has none |
| Neighbours | `map_find.py near <addr>`, `region <addr>` | the linker lays one source file's functions together, so an anonymous function shares its neighbours' subsystem | inference [I], not proof |
| Vtables | `work/map/index/vtables.jsonl` (5,813 runs in `main`) | a run of function pointers is a class's virtual methods; its members' strings name the class's role; the same slot across sibling vtables shows the interface (the 12 game states) | no RTTI, so no class names; the studio's reflection system ("Flux", ClassBroker) holds names as strings |
| Calls | `map_find.py fn <addr>`, `callers <addr>` | direct callees (named when they have strings or SDK names) and callers | indirect branches (`rt_dispatch`, 31,920 functions) are not in the graph; PLT stubs near `0x7001c1fb50` fan out to libc and the SDK |
| SDK names | `map_find.py name <text>` (19,260 named `sdk` functions) | `main` calls them through the PLT, so a game function calling `nn::fs::ReadFile`, `nvnQueueSubmitCommands` or `nn::hid::GetNpadState` is that kind of code | only the SDK is named, not the game's own code |
| Disassembly | `python -I tools/disasm.py work/build/game/exefs/main <addr> <len>` | the original ARM64, PLT targets named | offsets are module-relative in some tools (`sdk+0x13e700`; for `main` subtract `0x7000000000`) |
| Option names | `BOOT/CONFIG_MAIN.TXT` options are matched by a 32-bit hash (ELF-style hash, then `h*0x9E3779B7 + ~h*0x61C88641`; `docs/dev-config.md`) | names of boot options | only 27 of 109 hashes are named |
| Generated C | the file:line `fn` prints (`work/gen/main/main_NNNN.c`) | the most detail | noisy; use the clues above first |

### Reading generated C

A cheap way to read a body: strip the register save/restore after each call and collapse loads and stores. Take the line numbers from `map_find.py fn`.

```
sed -n <line>,<line+N>p work/gen/main/<file> | sed -E 's/x30 = 0x[0-9a-f]+ull;.*(f_[0-9a-f]+)\(c\);.*/CALL \1/; s/\{ uint64_t ea = (\w+) \+ (0x[0-9a-f]+)ull; uint64_t v = LD([0-9]+)\(ea\); (\w+) = [^;]*; \}/\4 = ld\3[\1+\2]/'
```

| Pattern | Meaning |
|---|---|
| `x0` | first argument and result |
| `x19` to `x28` | survive calls; `x19` is usually `this` |
| `x = 0x700227e000; x = ld64[x+0x128]` | load global #0x128 of that pointer table (others: `0x700227d000`, `0x7002291000`, `0x7002294000` to `0x7002298000`) |
| `rt_dispatch` after `ld64[ld64[obj]+off]` | a virtual call; `off` is 8 times the vtable slot |
| `rt_patch_on[n]` | a code-patch switch; the original and the patched code both sit in the function |
| `fsub32`, `fc_sub32` | flag-setting compares |
| `LD64`, `ST64`, `FN_ENTER(addr)` | loads, stores, function entry |

## 2. Dynamic clues (run the game; only short runs unasked)

| Setting | Logs | Notes |
|---|---|---|
| `MLB_FNTRACE=<addr>,...` | each call of those game functions: caller, x0 (shown as text if it points at a string) | `<lo>-<hi>` logs the first call of every function in a range |
| `MLB_FNTRACE_PEEK=<off>,...` | a value behind x0 when it changes | |
| `MLB_FNDUMP` | fields of the object a traced function receives, whenever they change | dev builds; documented use `MLB_FNDUMP=70012e0150:d3c,d38,101400:f,101404:f` (function, offsets, `:f` reads a float); read the parser in `runtime/mlb/` before relying on another form |
| `MLB_TRACE=fs` | every file open, read and close | with `MLB_FS_STACK=<path text>` also the game's call stack; other channels `svc,host,ipc,gfx,perf,sched,audio,present,all` |
| game log | the game's own `[lm 0]` lines; `uiEngine: Entering screen: [<movie>-><screen>]` names every UI screen entered | |
| `MLB_SAMPLER=on` | slow frames to `prof.txt.f<frame>` | slows the game; read with `tools/prof_report.py <profile> [mlb.map] --top 40 --chains 30`; state costs as a share of the thread's busy time |
| `MLB_STATEDUMP=1` and F8 | main's data and bss, for diffing situations | |
| `MLB_WATCH=<addr>,<size>;...` | texture creations and GPU writes in a guest range | |
| harness `dump = ...` | `buffer:addr=...` or `texture:fmt=0x25,size=512x512` | |
| F12 capture, RenderDoc | draw log and render targets; `pixel_history`, `debug_pixel`; `MLB_DRAWTEX` | |
| scenarios | `tools/scenario.py` and `tools/scenarios/*.txt` drive the harness into a situation | `tools/game.py` runs it in a slot, `tools/harness.py compare` byte-compares dumps, `tools/bench.py` alternates configurations |

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
