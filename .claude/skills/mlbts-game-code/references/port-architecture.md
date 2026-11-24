# Port architecture (Fastball, `runtime/` + `recomp/`)

Sources: `docs/runtime-port.md`, `AGENTS.md`, `docs/graphics-plan.md`, `docs/frame-rate.md`, file headers. Tags: [C] confirmed, [I] inferred.
Per-function list of the port's own source: `docs/map/source/*.md` and `python -I tools/map_find.py src <name>`.

## Layers

| Path | Role |
|---|---|
| `recomp/` | ARM64 to C generator (lifter, NEON/FP lowering, jump tables, flags/register caching, module layout, code patches in `patches.py`). TotK Recomp `ae30a61`, unmodified |
| `runtime/core/` | Generic fake Switch OS: CPU/SIMD headers, `dispatch.c` (indirect branch table), NSO loader, guest memory, kernel + threads (3 virtual cores), SVCs, IPC/CMIF, `fs_host.c` (nn::fs overrides), audio renderer/mixer, Win32 platform layer. Nothing MLB-specific |
| `runtime/mlb/` | MLB-specific: `main.c`, `boot.c`, `cfg.c` (every setting; each is also a command-line flag), `services.c`+`am.c`/`aoc.c`/`time.c`/`account.c` (HLE services), `hid.c` input, `hdtex.c` PS5 textures, `framerate.c`, `resolution.c`, `tutorials.c`, `rtts_autosave.c`, `cache_storage.c`, `packages.c`, `swkbd.c`, `harness.c` |
| `runtime/gfx/` | NVN front end (`nvn_api_*.c`), Vulkan back end (`vk_exec*.c` replay, `vk_pipeline.c`, `vk_texture.c`, `vk_memory.c`, `vk_rec.c`, `vk_sync.c`), shader client (`gfx_shader.c` to the .NET translator), present/window, DLSS/FSR, in-game menu (`ui/menu.cpp`, Dear ImGui) |
| `tools/` | build, extraction, analysis, harness (`harness.py`, `game.py` run slots, `bench.py`), map tools (`map_*.py`) |
| `installer/` | player's setup/launcher: extracts their NSPs, builds `mlb.exe` on their PC |

Rule: `runtime/core` holds nothing MLB-specific; `runtime/mlb` holds nothing another title could not replace. Edits to vendored files carry a `fastball` comment saying which screen/texture/address made them necessary.

## Two ways the port meets the game [C]

1. Symbol override. `main` imports 765 symbols from `sdk` through its GOT; the port replaces chosen ones (nn::fs, hid, account, swkbd, vi, nv, nvn procs) with host functions. Only calls from `main` into `sdk` can be caught this way.
2. IPC level. Calls made inside `sdk` (oe/am/apm/lm init) reach services through IPC, implemented in `runtime/mlb/services.c` and siblings. A command not yet seen stops with a named fatal `ipc_unimplemented`.

The port also wraps game functions/globals at known per-version addresses (`rtts_autosave.c`, `tutorials.c`, `framerate.c`, `resolution.c`, `hid.c`) and rewrites game instructions at generation time through code patch sets.

## Boot [C]

| Step | What happens |
|---|---|
| 1 | The loader maps `main` at `0x7000000000` and `sdk` at `0x7004c00000`, applies 122,737 + 33,849 relocations and binds 765 imports |
| 2 | The main thread (priority 44, core 0, 1 MiB stack) runs `nn::init::Start` |
| 3 | SDK init opens `lm`, `apm`, `appletOE`, `aoc:u`, `ectx:aw`, `pctl` and `time:u` |
| 4 | Module constructors run (`main` 1,025 init_array entries, `sdk` 87) |
| 5 | `nnMain` mounts the RomFS as `FS_Rom`, temporary storage as `FS_Temp` and cache storage 0 as `FS_GameData` (only with `MLB_CACHE_STORAGE`), and reads `FS_Rom:/BOOT/CONFIG_MAIN_USER.TXT` or `CONFIG_MAIN.TXT` |
| 6 | Graphics bring-up |
| 7 | Bink intro movies (decoded by the game itself), then menus; the console is docked, 1920x1080 |

## Graphics [C unless marked]

| Topic | Detail |
|---|---|
| Pipeline | the game records NVN command buffers and calls `nvnQueueSubmitCommands`; the front end builds an op stream; an async replay thread (`MLB_REPLAY_ASYNC`, default on) walks it (`vk_exec.c`, draws in `vk_exec_draw.c`); a recorder thread (`vk_rec.c`) makes the Vulkan calls |
| Frame cost | a sum, not an overlap: after the submit the game polls an event word (`f_70005a1a90`) until the GPU signals, then runs its own code; a heavy frame is game code 5 to 7 ms + replay 7 to 10 ms + GPU tail about 2 ms (see Frame rate and GPU waits) |
| Textures | live in guest memory (Tegra block-linear); `vk_texture.c` keeps a VkImage cache keyed by the full descriptor plus a per-address list; several images at one address is aliasing (on console an image is its memory) and causes most "image from another menu" bugs: `alias_copy`, `alias_overwritten`, `slot_resolve`; GPU-compressed textures (BC7 via an R32G32B32A32_UINT render) are caught by `cpu_rewrite_refresh` |
| Shaders | precompiled Maxwell binaries in the RomFS (456 `.FXBNVN` banks, about 4,505 unique graphics stages) go through the Ryujinx translator (`tools/xlate`) to SPIR-V; caches in `work/build/` |
| Scene image | one HDR image 1440x810 (B10G11R11) stretched to 1080p in the game's last pass; `resolution.c` changes the table the game reads; DLAA and FSR work on that image |
| PS5 images | a compute dispatch binds them at the Switch-size mip (`get_view`, `hd_shift`); a new PS5 category needs its compute consumers checked first |
| Diagnostics | F12 own capture (`MLB_CAPTURE_KEY=1`), `MLB_DRAWLOG`, `MLB_SHOT`, `MLB_DRAWTEX`, `MLB_WATCH`; RenderDoc through `tools/renderdoc.cmd` (the own capture moves to F9) |

## Frame rate [C]

The game does not count frames. Its timer (1.0.20 `main+0x58a9f0`) sleeps to a vsync count it keeps (`main+0x22ad028`, 1 = 60 fps) and sets the time step `s_fDeltaTime` from measured frame times (`main+0x22c90c4`; averaging flag `main+0x22c9078`). With a limit other than 60, `framerate.c` writes 0 into the vsync count at each present, so the game runs at the rate frames come, at normal speed, and the present pacer holds the limit. Whole-vsync mode (event 0x220 handled at `main+0xd514e0`) makes the game hold its own 60. Carry guard `main+0x2cb6150`. Highest limit 240. No game code patched.

## Settings, versions, patches

| Topic | Detail |
|---|---|
| Settings | env `MLB_<KEY>` (or `TOTK_<KEY>`), then `work/build/mlb.cfg`, then the `cfg.c` default |
| Game version | SHA-256 of `main`; `tools/data/expected-<ver>.json`; `tools/addrmap.py` maps 1.0.15 addresses to 1.0.20 |
| Patch sets | `tools/data/patches-1.0.20.txt` and `-1.0.15.txt` (format in `recomp/patches.py`, passed to `recomp/gen.py --patches`): `walkup_light` (6 sites), `walkup_leaders` (1), `msdf_skip` (research branch); the generator lifts the original and the replacement and a runtime switch picks one |

## Saves, input, audio, misc [C]

Saves are the same files on every host (`CARR<n>/`, `PLYA<n>/`, `SETT<n>/`); `mlb.exe --import-save` copies from Ryujinx. RomFS is the extracted directory (`romfs.complete` marker required; 1.0.20: 37.9 GB, 86,235 files). Input is one merged full-key pad as Player 1; a second player is unsupported by design (issues 21, 26). Face buttons map by label in menus and by position in play, switched by the game's own `uiEngine: Entering screen: [...]` log lines. Audio: Sony Scream mixes in software to 5.1 PCM for `audout`; WASAPI output; a live audio device is needed (or `TOTK_AUDIO=paced`). Online play and Diamond Dynasty are out of scope; offline packages server is optional.

## Build and run

`python -I tools/build.py` (clang+lld+ninja, about 2.5 min clean). Incremental: `ninja -f work/build/build.ninja` from the repo root. After `build.py` changes or a source file is added, regenerate the ninja file (`python -I tools/build.py --exefs work/build/game/exefs --portable`). Close `mlb.exe` before linking. Compiler `C:/Program Files/LLVM/bin/clang.exe` (LLVM 23). Runtime must also compile with llvm-mingw (no `__try`, no MSVC-only APIs). Generation: `python -I recomp/gen.py --exefs work/build/game/exefs --out work/gen --modules main,sdk --patches tools/data/patches-1.0.20.txt`, about 50 s. The runtime (never game code) is compiled with a PGO profile `tools/data/runtime.profdata`.
