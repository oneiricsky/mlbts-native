# Codebase map

A function-level map of this repo and the game binary it runs. Built by scripts in `tools/`, so it can be regenerated and checked.

## Rebuild and check

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

## What is in the repo

| Area | Functions | Page |
|---|---|---|
| `installer` | 168 | [source/installer.md](source/installer.md) |
| `recomp` | 263 | [source/recomp.md](source/recomp.md) |
| `runtime/core` | 1159 | [source/runtime-core.md](source/runtime-core.md) |
| `runtime/gfx` | 3054 | [source/runtime-gfx.md](source/runtime-gfx.md) |
| `runtime/mlb` | 378 | [source/runtime-mlb.md](source/runtime-mlb.md) |
| `runtime/shaders` | 18 | [source/runtime-shaders.md](source/runtime-shaders.md) |
| `runtime/third_party` | 1859 | [source/runtime-third_party.md](source/runtime-third_party.md) |
| `tools` | 595 | [source/tools.md](source/tools.md) |
| `tools/equipment` | 173 | [source/tools-equipment.md](source/tools-equipment.md) |
| `tools/linktest` | 7 | [source/tools-linktest.md](source/tools-linktest.md) |
| `tools/packages` | 195 | [source/tools-packages.md](source/tools-packages.md) |
| `tools/vendor` | 3421 | [source/tools-vendor.md](source/tools-vendor.md) |
| `tools/xlate` | 35 | [source/tools-xlate.md](source/tools-xlate.md) |

Total: 11325 source functions. C/C++ come from a libclang parse (a real compiler front end, same defines and include paths as the build), Python from `ast`, vendored C# and GLSL from a regex (lower fidelity).

## The game binary

See [binary.md](binary.md): 135,060 recompiled functions in the `main` and `sdk` modules, address ranges, SDK namespaces and the functions the repo already names.

[regions/](regions/) holds one note per address range of `main` (A to F, with the `sdk` module in F): subsystem per 256 KB window and key functions, every claim tagged confirmed, inferred or guess. The `.claude/skills/mlbts-game-code` skill is the entry point for future sessions.

## Subsystem guide

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
