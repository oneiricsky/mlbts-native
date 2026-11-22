**Fastball 0.2.0: the port has a name, Road to the Show equipment and packs work offline, AMD FSR, and many fixes.**

> [!IMPORTANT]
> **No game files are included.** You need your own copy of MLB The Show 26 with the **1.0.20** update (the 1.0.15
> update still works), dumped as NSP files from **your own** Nintendo Switch, and your Switch's `prod.keys`. This
> download contains no game code, data or keys, and no tools to obtain them. The setup builds the game on your PC,
> from your files, for your own use: don't share the installed folder. This is a fan project, not affiliated with or
> endorsed by Sony Interactive Entertainment, San Diego Studio, MLB or Nintendo.

## What's new

- **Fastball.** The port is now called Fastball, and **`Fastball.exe`** is the one program you start: after the
  install it opens the game straight away. Hold **Shift** while starting it (or start it with `--menu`) for its
  window: Play, Update, Repair, Import Ryujinx save and the Road to the Show options. The window has a new dark look.
- **Everything in one folder.** A new install goes into `MLBTS\` inside the folder you unpacked, with the setup's own
  settings and logs. Delete the folder and the port is gone. Shortcuts are now optional (off by default).
  Updates replace the setup's files in place.
- **Road to the Show equipment offline** (setup option, or **Add** in the launcher window): every equipment item
  (491 in 1.0.20), each with a picture made on your PC from your own game files, owned from the start.
- **Road to the Show packs offline** (another option): earn and open equipment packs as in the online game. A small
  server on your own PC answers the game; it only listens on your PC and sends nothing anywhere. With this option
  the equipment starts locked until you earn it from packs. Removing it unlocks every item again.
- **AMD FSR 3.1 and FSR 4.** **F1 → Graphics → AMD FSR** for any graphics card (FSR 4 on the Radeon cards that run
  it). The setup now downloads NVIDIA DLSS and AMD FSR for your graphics card by itself.
- **Settings menu:** rows that do nothing with your current settings or your PC are greyed out, with the reason in red.
- **A flag for every setting:** `Fastball.exe --fullscreen --fps-limit 120`; `MLBTS\mlb.exe --help` lists them all.
- **Faster:** the port's own graphics work per frame is about 30% lighter. In the attract match on the dev PC
  (uncapped), about 134 → 156 fps.

## Fixes

- **No freeze before each pitch** or at inning changes (the game rebuilt its stadium lighting every time).
  Thanks to 987G (#25).
- **No crash after 5 to 6 hours of play.** The game leaked memory at every match start (#17).
- **Custom batting cameras are kept** between starts (#19), and so are the other files the game keeps in its cache
  (the Settings menu's audio unlockables, among others).
- **Road to the Show hub upgrades are saved** (perks and attributes) without having to play a game first.
- **Finished tutorials stay finished** instead of coming back at every start.
- **The setup no longer stops** during the game data extraction when a security program blocks a file rename (#24).
- A frame could step the game by zero when the frame rate limit is above 60 (#18).
- Crash reports after a graphics driver error now say much more about the cause.

## Updating

**From 0.1.1 to 0.1.5:** start `MLBTS-Setup.exe` (hold Shift if it starts the game) and press **Download and
update**. The new version is unpacked into a `MLBTS-Setup-0.2.0` folder next to your old setup and rebuilds the game
in a few minutes. Your game folder, saves, settings and shortcuts stay where they are. From then on start
**`Fastball.exe`** in that new folder (your old desktop shortcut keeps working). You can delete the old setup
folder.

**From 0.1.0:** download `Fastball-0.2.0-windows.zip`, unpack it, start **`Fastball.exe`** and press **Update**.

## Download

| File | For |
|---|---|
| `Fastball-0.2.0-windows.zip` | Windows 10 or 11, 64-bit: **download this one** |
| `MLBTS-Setup-0.2.0-windows.zip` | The same, for the updater of setups 0.1.1 to 0.1.5 (no need to download it yourself) |

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
