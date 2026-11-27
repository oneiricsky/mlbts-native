# MLB The Show 26: native Windows port (fork)

This is a personal fork of [sam110411/fastball](https://github.com/sam110411/fastball) (formerly mlbts-native).
Fastball is a static recompilation of MLB The Show 26 for Nintendo Switch: the game's code is translated ahead of
time into a native Windows program. The upstream README is in the collapsed section at the end, unchanged. Its
download links and release instructions point to upstream, not to this fork.

## Mods

Optional changes to how the game plays. Each can be turned on or off, and none changes your installed game files.

<details>
<summary>Mods table</summary>

| Mod | What it changes | How to use | Depends On |
| --- | --- | --- | --- |
| [Starting tokens](mods/rtts-start-tokens/rtts_start_tokens.py) | A new Road to the Show player starts with the token count you choose, 0 to 60000, instead of 50 or 75. A career past player creation keeps its count. | Make the override with the command below, then run the game with `MLB_ROMFS_OVERRIDE=<full path of the override folder>` | Your own RomFS; tried on game 1.0.20 |
| [Offline main menu](docs/menu-offline-panel.md) (built into the port) | Removes the "You are currently disconnected" panel, scrolls the menu to the mode tiles at start, and removes the "Network Error" box. The game's other message boxes still appear. | On by default. F1 → Game → Hide the offline panel and Skip the network error box, or `MLB_HIDE_OFFLINE_BANNER=0` and `MLB_NO_NETWORK_ERROR=0` to turn them off | Game 1.0.20; removing the box needs code generated with the patch file |
| [In-game trainer](docs/trainer.md) (built into the port) | Sets the match situation, edits ratings and pitcher energy, runs slow motion and has guaranteed cheats. | `MLB_TRAINER=1` or F1 → Trainer; F2 in a match | Game 1.0.20 |

</details>

Make the starting-token override, here with 60000 tokens:

```
python -I mods/rtts-start-tokens/rtts_start_tokens.py 60000 --romfs work/build/game/romfs --out work/mods/rtts_tokens
```

The override is a changed copy of a game file, so keep it under `work/`, which git ignores. Only the mod's script
belongs in `mods/`. The game reads one override folder at a time.

## What this fork is for

The fork aims to make the game run and look better on an AMD Radeon RX 6700 XT. It also maps enough of the game to
work on it, which so far covers a function map, the save format and test runs that need nobody at the PC. The table
lists the changes.

<details>
<summary>Feature table</summary>

| Feature | Behavior | Usage | Depends On |
| --- | --- | --- | --- |
| Background pipeline builds | Shader pipelines (the compiled graphics programs) build on background workers and at boot, so drawing does not stop to wait for a compile. | Built-In | Nothing |
| Skip boot intro | Skips the two boot movies, so the loading screen goes straight to the title. | `MLB_SKIP_INTRO`, or F1 → Game → Skip intro logos | Nothing |
| Dev options | The game's hidden dev options work, so `AIvAI` with `GameOnly` boots straight into an AI-vs-AI game. | Option table and hashes: [docs/dev-config.md](docs/dev-config.md) | Nothing |
| PS5 face textures | Replaces each player's face colour map and normal map (the texture that carries surface detail for lighting) with the PS5 ones: 2,409 heads' colour maps and 2,411 heads' normal maps. | Build an index with `tools/make_hd_index.py --all-heads`; F1 → Graphics → PS5 face textures, or `MLB_HD_TEXTURES=0` to turn them off | A PS5 dump |
| Run summary | Turns one run's log into a JSON summary of frame rate, slow frames and PS5 texture loads. | `python -I tools/perf_summary.py <log>` | A run log |
| Shorter match-start freeze | Skips the empty-space pixels in the match-start field pass, cutting that step from about 0.7 s to about 0.2 s with the same finished picture on the two stadiums tested. | `MLB_MSDF_SKIP` (on by default); settings menu, Shorter freeze at match start; game 1.0.20 only so far; report: [docs/reports/2026-11-23-msdf-skip.md](docs/reports/2026-11-23-msdf-skip.md) | Nothing |
| Idle sound thread | Stops a sound file thread's 100 µs sleep loop from spinning a processor core, cutting that thread from 97-99 % of a core to about 7 % with no measurable change in frame rate. Sound has not been checked by ear. | Built-In; details: [docs/sound-thread-spin.md](docs/sound-thread-spin.md) | Nothing |
| Function map | Indexes every recompiled function and gives 47,308 of them a one-line role. Includes a per-class field index and a generated wiki. | `python -I tools/map_find.py fn 0xADDR` (also `str "text"`, `callers 0xADDR`, `role 0xADDR`); [wiki](https://github.com/oneiricsky/mlbts-native/wiki) | Nothing |
| Save files | Decodes the save container and class schema. Editing a field by name also recompresses the save and rewrites its hash. | `python -I tools/save_schema.py`; `python -I tools/save_edit.py info` (also `verify`, `rename`, `rehash`, `set-field`) | Your save files |
| In-game trainer | A panel over the match that sets the count, outs and score, jumps to a later inning, saves and replays situations, edits ratings and pitcher energy, runs slow motion and has guaranteed cheats (contact, home run, miss, perfect aim, called strikes, wild throws scored as errors). Off by default. | F1 → Trainer, or `MLB_TRAINER=1`; F2 in a match. Details: [docs/trainer.md](docs/trainer.md) | Game 1.0.20; the two readout pages need code generated with the patch file |
| Headless test runs | Runs the game with its window hidden, a fake audio device and scripted buttons. | `TOTK_HIDDEN_WINDOW=1`, `TOTK_AUDIO=paced`, `MLB_HARNESS_PAD=1`, `MLB_SHOT=<frame>`; details: [docs/dev-config.md](docs/dev-config.md#headless-test-runs) | A Vulkan-capable GPU |
| Exhibition on demand | Starts a match between two chosen teams by pressing the menus and rewriting the match-settings block before the lineups are built. | `python -I tools/exhibition.py --exe mlb_sonnet --log RUN.out --away 1 --home 0` | `MLB_HARNESS_PAD=1`, and a run that goes through the menus (not the AIvAI autostart) |
| Dev harness (in progress) | Each test run follows a scenario file, so it can be repeated with nobody at the PC. | `MLB_HARNESS=<scenario file>` in dev builds; plan and status: [docs/dev-config.md](docs/dev-config.md) | Nothing with `TOTK_AUDIO=paced` |

</details>

In short runs on an RX 6700 XT the game held about 59 fps with PS5 textures on and off. One played match with them
on ran at a median of about 44 fps, with no run to compare it with, and stadiums turned black now and then in it; the
cause of neither is known. The textures are read from your dump and are not part of any release. Details and numbers
are in [docs/ps5-textures.md](docs/ps5-textures.md) and the
[2026-11-27 report](docs/reports/2026-11-27-ps5-all-face-textures.md).

## Research and the wiki

The fork's wiki publishes the function map, the function roles, the per-class field index and the save schema:
<https://github.com/oneiricsky/mlbts-native/wiki>. `tools/map_roles.py` and `tools/wiki_build.py` generate those
pages from `work/map/`, so they can be rebuilt from the generated C at any time.
[docs/map/README.md](docs/map/README.md) explains the code map behind them.


<details>
<summary>Original README (upstream)</summary>

# Fastball: MLB The Show 26, native on Windows

Fastball is a native Windows port of MLB The Show 26 for Switch.

<a href="https://recomplauncher.com/game/mlbts-native"><picture><source media="(prefers-color-scheme: dark)" srcset="https://recomplauncher.com/assets/press/launcher/badge-light.svg"><img alt="Get it on RecompLauncher" src="https://recomplauncher.com/assets/press/launcher/badge-dark.svg" height="48"></picture></a>

A static recompilation of **MLB The Show 26** (Nintendo Switch, version **1.0.20**; 1.0.15 also works) into a native Windows x86-64
program. The game's ARM64 code is translated to C ahead of time, compiled with clang, and linked against a small
host runtime that stands in for the Switch's operating system, GPU API and audio.

![Pitching screen](docs/img/pitching-screen.jpg)

> **Fan project.** This project is not affiliated with, endorsed by, or connected to Sony Interactive Entertainment,
> San Diego Studio, MLB, or Nintendo. It contains no game code, game assets or keys. You must supply your own legally
> obtained copy of the game.

## Status

Playable offline. The game boots, the menus work, and Exhibition, Road to the Show and Franchise run at 100+ fps on the
development machine (Ryzen 5 5600X, RTX 3060 Ti, Windows 11).

**Scope:** offline play only (exhibition, Road to the Show, Franchise, menus, local saves). Online play and Diamond
Dynasty are out of scope.

**Known problems:** current work is graphics correctness (some wrong or missing images, lighting) and performance.
Game versions 1.0.20 (the latest) and 1.0.15 are supported; other versions are not.

## Playing it

1. Download `Fastball-<version>-windows.zip` from [Releases](https://github.com/sam110411/fastball/releases),
   unpack it where you want the game to live (it needs about 40 GB there) and start **`Fastball.exe`**.
2. The setup looks for your game files and keys by itself (Ryujinx's and yuzu's folders, Downloads, Desktop, ...).
   Check what it found, pick anything missing, and press **Install**.
3. After about 10 minutes, press **Play**. From then on, `Fastball.exe` starts the game straight away (hold Shift
   while starting it for its window: updates, repair, save import).

Everything stays in that folder: the game goes into `MLBTS\`, and deleting the folder removes the port. Flags work too:
`Fastball.exe --fullscreen --fps-limit 120` (`MLBTS\mlb.exe --help` lists every setting).

The download contains no part of the game. The setup builds the game on your PC from your own files: the base game and
the 1.0.20 update (or 1.0.15) as NSP files dumped from your Switch, and your `prod.keys`. It needs about 40 GB free. To update the
port, press **Download and update** when the setup offers it (it checks once a day), or start a newer setup and press
**Update**; your game files, saves and settings stay. How the setup works and how a
release is made: [docs/release.md](docs/release.md).

## Features

- Native Windows executable, Vulkan 1.3 renderer. Switch shaders are translated at run time.
- Switch saves are used as they are: a Ryujinx save can be imported (the setup offers it, or `mlb.exe --import-save`).
- Road to the Show equipment without a connection, as an option of the setup: every item, with its picture, owned
  from the start ([`tools/equipment`](tools/equipment/README.md)).
- Road to the Show's Packages without a connection, as another option of the setup: the game earns and opens its
  equipment packs against a small server on the player's own PC ([`tools/packages`](tools/packages/README.md)).
  Nothing is sent anywhere, and it is off unless turned on.
- Xbox and PlayStation controllers (through SDL3) with rumble. The game's button prompts follow the controller in use.
- Keyboard and mouse.
- Resolution options: output size, render scale, FSR 1, NVIDIA DLSS / DLAA and AMD FSR 3.1 / FSR 4 (the setup
  downloads the DLSS and FSR libraries for the graphics card from NVIDIA's and AMD's repositories; they are not
  shipped here).
- FXAA, anisotropic filtering, shadow quality options, colour presets, HDR output, field-of-view and aspect options.
- In-game settings menu, performance overlay, fullscreen toggle (F11).
- Frame rate limit from 30 to 240 fps or the monitor's rate, at the game's normal speed
  ([docs/frame-rate.md](docs/frame-rate.md)).
- Software-mixed 5.1 audio output through WASAPI.
- Built-in diagnostics for graphics bugs: frame capture (F12), draw logs, RenderDoc support.

Every setting is a `KEY=VALUE` line in `mlb.cfg` next to `mlb.exe` (or an environment variable named `MLB_<KEY>`). The
full list is the table in [`runtime/mlb/cfg.c`](runtime/mlb/cfg.c).

## System requirements

<details>
<summary>System requirements table</summary>

| | Minimum |
|---|---|
| OS | Windows 10/11, 64-bit |
| CPU | x86-64 with AVX2 |
| GPU | Vulkan 1.3 capable (an NVIDIA RTX card is needed for DLSS) |
| RAM | 16 GB recommended; the page file should be large (RenderDoc captures need much more) |
| Disk | About 40 GB for the extracted game data, plus the build |

</details>

## Game files

Nothing from the game is included. You need:

- the base game and the 1.0.20 update (or 1.0.15), dumped from your own Switch (`.nsp` files), and
- your own `prod.keys` and `title.keys`. By default the tools read them from `%APPDATA%/Ryujinx/system/`. They are
  passed by path and never printed or copied.

Dumps, extracted data and builds live in `gamefiles/` and `work/`, which are git-ignored. Never commit them.

## Building from source

This section is for development. To play, use the setup above.

Requirements: LLVM clang with lld, Ninja and Python (a `.venv` in the repository), .NET 10 with Visual Studio 2022's
linker (for the shader translator). Always run Python as `.venv/Scripts/python -I <script>`; `-I` keeps user
site-packages from loading.

First-time setup, once:

```bash
# 1. extract the ExeFS and the RomFS from your own dumps (about 37 GB)
.venv/Scripts/python -I tools/romfs_dump.py --keys "$APPDATA/Ryujinx/system/prod.keys" --titlekeys "$APPDATA/Ryujinx/system/title.keys" --extract-all "gamefiles/<base>.nsp" "gamefiles/<update>.nsp" work/romfs
# 2. generate C from the game's code, with its code patches (about 50 s)
.venv/Scripts/python -I recomp/gen.py --exefs work/update/exefs --out work/gen --modules main,sdk --patches tools/data/patches-1.0.20.txt
# 3. fetch Vulkan headers, VMA and SDL3; build the shader translator
.venv/Scripts/python -I tools/fetch_deps.py
.venv/Scripts/python -I tools/build_xlate.py
```

Build and run (incremental after the first build, which takes a few minutes):

```bash
.venv/Scripts/python -I tools/build.py
work/build/mlb.exe
```

Details, including how the boot sequence was brought up: [docs/runtime-port.md](docs/runtime-port.md).

## Where files live

<details>
<summary>Where files live table</summary>

| What | Where |
|---|---|
| Executable and settings | `work/build/mlb.exe`, `work/build/mlb.cfg` |
| Log (replaced at each start) | `work/build/logs/mlb.log` |
| Saves and captures | `work/profile/` |
| Extracted game data | `work/romfs/`, `work/update/exefs/` |

</details>

Attach `mlb.log` to bug reports. Lines starting with `[lm 0]` are the game's own log, `[host]` lines are ours. A crash
prints `FATAL:` with host frames that can be symbolized with `llvm-symbolizer`.

## Debugging graphics

- **F12** captures a frame (draw log, screenshot, every render target) at no cost until pressed.
- Under RenderDoc (`tools/renderdoc.cmd`) F12 is RenderDoc's capture and ours moves to F9. Images and draws are named
  with their Switch memory address, so a wrong picture can be traced to the draw that made it.
- More: [AGENTS.md](AGENTS.md), [docs/graphics-plan.md](docs/graphics-plan.md).

## Repository layout

<details>
<summary>Repository layout table</summary>

| Path | What |
|---|---|
| `recomp/` | ARM64 to C generator |
| `runtime/core/` | Generic host: CPU, memory, kernel and threads, SVCs, IPC, file system, audio, Win32 platform |
| `runtime/mlb/` | MLB layer: boot, settings, services, input, log and crash reporter |
| `runtime/gfx/` | NVN front end, Vulkan back end, presentation, window, in-game menu, RenderDoc support |
| `tools/` | Build, extraction and analysis scripts |
| `mods/` | Optional gameplay mods, one folder each ([Mods](#mods)) |
| `docs/` | Binary reconnaissance, runtime notes, graphics plan |

</details>

Changes to vendored upstream files are marked `fastball` in the source with a comment explaining the case that
needed them.

## Credits and reference projects

This port stands on the work of the Switch recompilation community. Its generator and runtime come from:

- **[TotK PC Recomp](https://github.com/valentderah/totk-pc-recomp)** (Valiantsin Dzerakh), commit `ae30a61`: the
  code generator, the host runtime core, the NVN and Vulkan graphics stack, audio renderer, DLSS/FSR and in-game menu.
  This is the primary base.
- **[Astral Chain PC Recomp](https://github.com/captainj-sparrow/astral-chain-pc-recomp)**: the `audout:u` service.
- **[Super Odyssey PC Recomp](https://github.com/Simon3Sarkis/super-odyssey-pc-recomp)** and
  **[Savage Wind Recomp](https://github.com/Revivedx/SavageWindRecomp)**: references for structure and the menu and
  performance overlay.
- **[LAS Recomp](https://github.com/peiikai/LASRecomp)** (Link's Awakening): the original lineage of the Vulkan
  back end and of this kind of project.
- **[Ryujinx](https://github.com/Ryujinx/Ryujinx)**: its shader translator, and a correctness oracle for the game's
  behaviour.
- **[Atmosphère](https://github.com/Atmosphere-NX/Atmosphere)**: read for how NCA storage is layered (no code copied).
- **[RenderDoc](https://github.com/baldurk/renderdoc)**: the main graphics debugging tool.

Libraries: SDL3, Vulkan-Headers, Vulkan Memory Allocator, Dear ImGui, AMD FidelityFX FSR 1, NVIDIA NGX (DLSS, not
redistributed), Roboto font. Exact versions, licences and the files they went into are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

Third-party code keeps its own licence and attribution header; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The code adapted from TotK Recomp is MIT-licensed
(`runtime/core/LICENSE.totk-recomp`). No game content is distributed with this repository.

</details>
