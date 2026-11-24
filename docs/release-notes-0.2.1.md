**Fastball 0.2.1: local multiplayer, an FSR 4 fix, smoother controllers and a Road to the Show creation fix.**

> [!IMPORTANT]
> **No game files are included.** You need your own copy of MLB The Show 26 with the **1.0.20** update (the 1.0.15
> update still works), dumped as NSP files from **your own** Nintendo Switch, and your Switch's `prod.keys`. This
> download contains no game code, data or keys, and no tools to obtain them. The setup builds the game on your PC,
> from your files, for your own use: don't share the installed folder. This is a fan project, not affiliated with or
> endorsed by Sony Interactive Entertainment, San Diego Studio, MLB or Nintendo.

## Changes

- **Local multiplayer works:** each controller is now its own player (#26).
- **FSR 4** no longer makes the close-ups between pitches dark with a grid pattern (#27).
- **No more hitches when a controller disconnects or reconnects** (Bluetooth pads especially): controllers are now
  read on their own thread instead of the game's.
- **Creating a Road to the Show player** no longer leaves a half-made career named "Joe Random" when the game closes
  during creation. Thanks to 987G (#29).

## Updating

**From 0.2.0:** start `Fastball.exe` while holding **Shift** and press **Update**.

**From 0.1.1 to 0.1.5:** start `MLBTS-Setup.exe` (hold Shift if it starts the game) and press **Download and
update**. The new version is unpacked into a `MLBTS-Setup-0.2.1` folder next to your old setup and rebuilds the game
in a few minutes. Your game folder, saves, settings and shortcuts stay where they are. From then on start
**`Fastball.exe`** in that new folder. You can delete the old setup folder.

**From 0.1.0:** download `Fastball-0.2.1-windows.zip`, unpack it, start **`Fastball.exe`** and press **Update**.

## Download

| File | For |
|---|---|
| `Fastball-0.2.1-windows.zip` | Windows 10 or 11, 64-bit: **download this one** |
| `MLBTS-Setup-0.2.1-windows.zip` | The same, for the updater of setups 0.1.1 to 0.1.5 (no need to download it yourself) |

## New install

1. Unpack the zip where you want the game to live (it needs about 40 GB there) and start **`Fastball.exe`**. Windows
   may warn that the app is unrecognised (it is not signed): choose **More info**, then **Run anyway**.
2. The setup looks for your keys and game files by itself: Ryujinx's and yuzu's folders, their game folders,
   Downloads, Desktop. Check what it found, pick what is missing, choose the Road to the Show options you want, and
   press **Install**.
3. It extracts the game's data (about 38 GB), translates the game's code and compiles it for your PC. That takes about
   10 minutes (a few more with the equipment option); you can cancel and continue later.
4. Press **Play**. From then on, `Fastball.exe` starts the game.

## What you need

- Windows 10 or 11, 64-bit; a CPU with AVX2 (Intel 4th generation / AMD Ryzen or newer)
- A graphics card with Vulkan 1.3 and a current driver; DLSS needs an NVIDIA RTX card
- 16 GB of RAM; about 40 GB of free disk space, plus 2 GB next to the setup while it builds

## Known issues

- **Busy scenes can still drop below 60 fps on slower processors**, batting views and the fan camera especially.
- **The first matches stutter** while the game prepares its shaders; they are kept, so it gets smoother as you play.
- The setup takes NSP files only (no XCI or NSZ yet), and only game versions 1.0.20 and 1.0.15.

## Reporting a problem

Open an issue and attach `MLBTS\logs\mlb.log` (it is replaced each time the game starts, so copy it right after the
problem). For a setup problem, attach the newest `logs\setup-*.log` from the setup folder.
