"""Fastball, the MLB The Show 26 PC port: the setup and launcher; builds a playable folder from the player's own game files (docs/release.md).

    python -m installer --dest DIR --base NSP --update NSP --keys prod.keys [--no-dlss] [--no-fsr] [--shortcut] [--import-save]
    python -m installer.gui            the window (Fastball.exe starts it)

Modules: layout (where the bundled tools are: release folder or repository), detect (finding the keys, game files, a
Ryujinx save, the GPU), events (JSON progress on stdout and the log), steps (the steps, fastball-install.json, resume and
update), cli (the command line), gui (the window, a front end over the command line).

The release holds no game code or data: the steps extract the player's files and build mlb.exe on their PC. Standard
library only, apart from what the extraction tools import (numpy, lz4). After TotK Recomp's installer @ v0.4.0 (MIT).
"""
