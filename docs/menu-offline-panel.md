# The offline panel on the main menu

Without a connection the game-modes menu (the first screen after the title) fills its top with a large panel: a
crossed-out Wi-Fi symbol, "YOU ARE CURRENTLY DISCONNECTED!", "RECONNECT AND GAIN ACCESS TO..." and the names of the
online features. This port has no online play, so the panel only takes space. `MLB_HIDE_OFFLINE_BANNER` (on by
default; `=0` runs the game's own code) and a toggle on the settings menu's Game tab remove it. Addresses are 1.0.20's;
1.0.15 is not covered yet (the setting logs that and the panel stays).

## Cause
The panel is one picture, `dynamictile_home_offline` (1740x636, entry 898 of `NSW/UI/FRONTEND/FRONTEND.TEX`), shown
inside a focus frame by the menu screen `GameModesMain` in `FRONTEND.NSW`. The screen's script draws it when the
variable `[GameModesMain.SHOW_DYNAMIC_PANELS]` is false, and otherwise lists the server's tiles
(`[ONLINE.DYNAMIC_PANELS.gmm.Tiles]`). The text is part of the picture; it is in no text table.

The variable comes from the screen's data object (vtable `0x70021bd438`, four fields: HAS_ANNOUNCEMENTS,
ANNOUNCMENT_NUMBER, SHOW_DYNAMIC_PANELS, STUBS_CAP). Slot 6 (`f_7000c0da4c`) sets two bytes in it from the online state,
`+0x129` (online) and `+0x128` (the server data allows panels); slot 8 (`f_7000c0dc6c`) hands the field values to the
script, and for SHOW_DYNAMIC_PANELS it gives `obj[+0x129] && obj[+0x128]` [C]. Offline both bytes are 0 (logged).

## The fix
`runtime/mlb/menu_offline.c` replaces the slot-8 function by a host function that sets both bytes to 1, runs the
game's function, and puts the bytes back. The script sees SHOW_DYNAMIC_PANELS true and the list of server tiles, which
is empty offline, so neither the picture nor its frame is drawn. The bytes stay 0 for every other reader.

## What else changes
- The empty space where the panel was stays (the mode buttons keep their places; the layout is the game's).
- The first selected item on the menu is the first mode button instead of the panel.
- Setting both bytes for good was tried first: the game then believed it was online and showed a "NETWORK ERROR" box.
- Making the picture transparent was tried too (a 4x4 transparent image in its place): the picture went, the frame stayed.

## How it was checked
`tools/menu_offline_check.py CONTROL.png FIXED.png` compares the menu at frame 6000 of two headless runs (hidden window,
fake audio, the same game files; the harness's boot file replaced for the run so the game starts at the menu): panel
region standard deviation 56.1 with the setting off against 5.9 on, yellow pixels 1896 against 0, teal frame-edge pixels
2151 against 0, and the strip with the mode buttons identical (mean difference 0.00). Not checked: 1.0.15, and a
connected game (no server here); with a connection slot 6 sets the bytes itself and the hook changes nothing.
