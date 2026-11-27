# Codebase map

A function-level map of this repo and the game binary it runs. Built by scripts in `tools/`, so it can be regenerated and checked.

## Rebuild

```
python -I -m pip install libclang --target work/pylib      # once; libclang for the C/C++ parse
python -I tools/map_source.py --out work/map/index                # hand-written and vendored source
python -I tools/map_generated.py                                  # recompiled game code (needs work/gen)
python -I tools/map_binary.py                                     # names + check vs the original code
python -I tools/map_strings.py                                    # strings per game function + vtables
python -I tools/map_all.py                                        # all of the above in order, then docs + coverage
python -I tools/map_find.py fn 0x700108b628                       # look up a game function (see its docstring)
python -I tools/map_docs.py                                       # writes docs/map/
python -I tools/map_coverage.py                                   # exits 1 if anything is unmapped
```

See [coverage.md](coverage.md) for the last result.

## Repo contents

| Area | Functions | Page |
|---|---|---|
| `installer` | 168 | [source/installer.md](source/installer.md) |
| `recomp` | 263 | [source/recomp.md](source/recomp.md) |
| `runtime/core` | 1159 | [source/runtime-core.md](source/runtime-core.md) |
| `runtime/gfx` | 3054 | [source/runtime-gfx.md](source/runtime-gfx.md) |
| `runtime/mlb` | 378 | [source/runtime-mlb.md](source/runtime-mlb.md) |
| `runtime/shaders` | 18 | [source/runtime-shaders.md](source/runtime-shaders.md) |
| `runtime/third_party` | 1859 | [source/runtime-third_party.md](source/runtime-third_party.md) |
| `tools` | 655 | [source/tools.md](source/tools.md) |
| `tools/equipment` | 173 | [source/tools-equipment.md](source/tools-equipment.md) |
| `tools/linktest` | 7 | [source/tools-linktest.md](source/tools-linktest.md) |
| `tools/packages` | 195 | [source/tools-packages.md](source/tools-packages.md) |
| `tools/vendor` | 3421 | [source/tools-vendor.md](source/tools-vendor.md) |
| `tools/xlate` | 35 | [source/tools-xlate.md](source/tools-xlate.md) |

Total: 11385 source functions. C/C++ come from a libclang parse (a real compiler front end, same defines and include paths as the build), Python from `ast`, vendored C# and GLSL from a regex (lower fidelity).

## Game binary

See [binary.md](binary.md): 135,060 recompiled functions in the `main` and `sdk` modules, address ranges, SDK namespaces and the functions the repo already names.

[regions/](regions/) holds one note per address range of `main` (A to F, with the `sdk` module in F): subsystem per 256 KB window and key functions, every claim tagged confirmed, inferred or guess.

[bodies/](bodies/) holds notes from reading function bodies (the 12 game-state classes and six subsystem passes), each report spot-checked against the generated C. The `.claude/skills/mlbts-game-code` skill is the entry point for future sessions.

A complete function map is generated from the same index:

- [Function map](Function-map) has the method and the totals.
- [Function census](Function-census) counts every function in every 256 KB window.
- `Functions-A` to `Functions-F` plus `Functions-SDK` list every function that carries a symbol, an import or a string.

`tools/map_roles.py` names the import thunks from the relocation table and classifies every body; `tools/map_functions_doc.py` writes the pages. Both read `work/map/index/`, so those pages are rebuilt locally like the index and are not committed.

The functions with no string, symbol or simple shape are read from their own code:

1. `tools/map_read_prep.py` normalises each generated body to its meaningful operations and writes dossiers in batches.
2. Subagents read the batches and write `out-<n>.jsonl`.
3. `tools/map_read_merge.py` validates them into `work/map/index/roles_read.jsonl`.
4. `tools/map_roles.py` applies that overlay, so the census and the `Read roles` pages carry what the read found.

That pass covered 47,308 `main` functions; the completeness pass reads every remaining body, `sdk` included (see [read-pass.md](read-pass.md)).

The game's saves carry their own class and field names. `tools/save_schema.py` reads that schema out of the zlib-compressed Flux archive in a save and writes `work/map/saves/schema.json`; the wiki's `Save schema` page lists the classes and fields, and searching one of those names in the code finds the function that reads or writes it.

## Subsystems

| Area | What it is |
|---|---|
| `runtime/core` | Generic Switch-OS host: CPU state, memory, kernel services, audio, filesystem |
| `runtime/gfx` | NVN-to-Vulkan graphics layer, shader handling, textures, upscalers, UI |
| `runtime/mlb` | MLB-specific hooks: input, saves, resolution, dev harness |
| `runtime/shaders` | Shader sources |
| `runtime/third_party` | Vendored Dear ImGui and AMD FidelityFX headers |
| `recomp` | Recompiler: ARM64 lifter and C emitter (`gen.py`) |
| `installer` | Setup and updater |
| `tools` | Build, dev harness, test and analysis scripts |
| `tools/xlate`, `tools/vendor` | Shader translator built on vendored Ryujinx C# |
| `tools/packages`, `tools/equipment` | Offline package and equipment tooling |
