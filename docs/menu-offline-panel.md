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

Slow machine, checked 2026-11-26: with `MLB_FPS_LIMIT=30` (mean 29.7 fps, the slowest the setting takes) the start is the same:
black x18 (frames 772 to 908), then the menu, and the only screen entered afterwards is the test press's own; no stray A
opened a mode. Below that the 0.3 s before the Ok is still wall time and was not tried.
connected game (no server here); with a connection slot 6 sets the bytes itself and the hook changes nothing.

## Open work (2026-11-26): the gap and the "NETWORK ERROR" box

### The gap under the header: closed by one Down press at start (part of `MLB_HIDE_OFFLINE_BANNER`)
The menu page is taller than the screen. The offline panel (y 228 to 864 of 1080) was its first row and the tile row
(Road to the Show, Diamond Dynasty, Franchise, Storylines; tiles about 304 wide, top at y 991) its second. The page
scrolls with the focus. With the panel hidden, the page still started unscrolled: an empty space under the header and
the tile row cut off at the bottom of the screen. A synthetic Down press 1.0 s after the menu's selection box
enters (`nne_log` in `runtime/mlb/hid.c`, only for the first online entry, `ol_OnlineEntry (0)`, and only when
`menu_offline.c` has installed its hook) scrolls the page to the tile row and puts the focus on the first tile, Road to
the Show (the mode that works offline), with its hero art behind; the same view the game shows after a tile is
pressed. Only at start: after a tile press the page is already scrolled.
At start the window also shows black (`gfx_present_hold` in `runtime/gfx/gfx_present.c`) from the first `GameModesMain`
(59) until 0.7 s after that Down, and the player's own input is ignored then, so the box, the gap and the scroll are never
seen; the black ends on a clock that counts only while the game polls its input (the game pauses without the focus, which
made an early version miss its presses in a real window), with a 12 s limit. Check: `python -I tools/menu_startup_check.py
<profile>` on a run with `MLB_SHOT` every 10 frames: fresh slot, 2026-11-26: 22 black samples (frames 3340 to 3550, about
3.5 s), then the scrolled menu; 0 box samples and 0 gap samples in 140 sampled frames. The same black covers a press on a tile that needs
the network, from `ol_OnlineEntry (1)` until 0.7 s after the Ok: with an external pad driver (Right, then A on Diamond Dynasty)
the samples were black x26 (start), menu x38, black x21 (the press), menu again, with 0 box and 0 gap samples.
Check: `python -I tools/menu_offline_check.py CONTROL.png FIXED.png SCROLLED.png`; a control frame with the panel
(`MLB_HIDE_OFFLINE_BANNER=0`) against a fixed frame before the scroll and one after it. Measured 2026-11-26: panel
region std 56.1 with the panel (1896 yellow pixels), 5.9 in the gap, 44.1 after the scroll (hero art, no yellow); the
tile strip under the region is identical between the control and the gap frame (0.00) and the view is stable for the 1800
frames sampled after. Up, Left and Right were not tried; the first Down worked. Why the game starts unscrolled, and
whether the starting focus could be set instead of pressing a button, is not known. The layout holds no tile-row
geometry (a scan of every object in `FRONTEND.NSW` for 1740 x 636, for tiles about 304 wide near y 991, and for y values
near the screen bottom found nothing that fits), so the row is placed at run time from the dynamic list [H].

### The "NETWORK ERROR" box: dismissed by the port (`MLB_NO_NETWORK_ERROR`, on by default)
The box shows up twice offline: about half a second after the menu loads at every start (after the game's first login
attempt, `ol_OnlineEntry (0)`), and after a tile that needs the network (`ol_OnlineEntry (1)`). It waits for Ok.
Fix (`runtime/mlb/hid.c`, `nne_log`): the game's log lines give the order "enter ol_OnlineEntry", "Setting Online to
ONLINE_NOT", "enter GameModesMain", "Selection Box 2 enters"; at the last one the port presses A (the box's Ok) 0.3 s
later, for 0.1 s. The box therefore flashes instead of waiting; what raises it in the game's code was not found (a code
patch would remove the flash). Pressing B instead looked safer and was not: B on the menu moves focus to the top bar
(`ProfileHub` opened on the next A). Check: `python -I tools/network_error_check.py <profile>` on a run with
`MLB_SHOT` every 10 frames from 2600 to 4590, a test press (`MLB_HARNESS_PRESS=30000,A`) every 30 s and the same
files: box in 89 of 200 shots with `MLB_NO_NETWORK_ERROR=0`, in 3 of 200 with it on (frames 3370 to 3390, a tile press);
the screens entered match the test presses one for one. Not checked: 1.0.15 (the log lines are the same, so it should
work), a slow machine (the 0.3 s is wall time; a box that comes later than that would get no Ok, and the next press
of the player's own would close it), a real connection (the steps need "Setting Online to ONLINE_NOT").

Earlier notes, from before this fix:
What the trace showed [C]: a press on an online mode's tile enters `ol_OnlineEntry (1)`; the game logs "Setting Online
to ONLINE_NOT" (`f_7000a49f9c`, called from `f_70009d56f8`), reads the stats files, and returns to `GameModesMain (7)`;
the box appears over that screen, blurred behind (`UITempBlurRT`). Ruled out, each with a run [C]:
- `CNetSessionManager` dialog functions (`f_70009bebac` ShowNetworkErrorDialog, `f_70009bd394`, `f_7001654864`
  NetDialogs, `f_70009be360`, `f_70009be918`) and the NetDialogs family at 0x7001650000 to 0x7001656000: never called.
- Swapping `bail_online` for `bail_screen` in `FRONTEND.NSW` (ol_OnlineEntry's failure mode): the box still appears.
- Renaming `OnlineEntry_ReconnectFail` in `FRONTEND.NSW`: the box still appears.
- `OnlineQueryView` (vtable 0x700219e988): `f_70009d7940` runs every frame (the update tick); slot 12 `f_70009d5824`
  is the 8000-line variable provider for the script's `[ONLINE.*]` values.
Not tried: a code patch (tools/data/patches, about 50 s to generate and 2.5 min to build) at the place that returns to
`GameModesMain` with code 7, or a hook that presses A for the player.
Wasted effort to avoid: a test run takes two to five minutes; `MLB_MENU_TEST` is the port's own menu test hook (do not
reuse the name); `MLB_HARNESS_PRESS` A presses are not harmless (the second one activates a tile).

### Layout file format (`FRONTEND.NSW`, `GAME.NSW`, ...)
[C] = measured, [H] = inferred. Corrected 2026-11-26: an earlier version of this section paired each layout block with the
string pool BEFORE it, which named every screen after its neighbour. `tools/nsw_edit.py` has the right pairing.
- `IFF0ASSH` header (16 bytes: tag, 0, total size), then a run of blocks. A block starts with `VOIDASS0` (then a hash, a
  size, a table of section offsets) and runs to the next one. Its tail holds the screen's string pool: the word
  0x8000005b, NUL-separated strings (the first is the screen's name), and a table of 8-byte ids. So the nodes of a screen
  are in the block that ENDS with its pool. [C]
- Nodes are 0x50 bytes or more: colour (u32), x, y, z, width, height (float32, a root node is 1920 x 1080), then flag words
  and a tail of (offset, 0x80xx | child count). A node's position is relative to its parent. [C for the first six fields]
- Textures are not named in the layout: `FRONTEND.TEX` has 320-byte records (name at +0x30, width and height as two u16
  at +0x84); no hash of a texture name I tried (CRC32, FNV, ELF, djb2, sdbm) matches the layout's ids. [C]
- Screen names are not unique (`GameModesMain` at 7773028 is the end of a 117 KB block that starts at 7662992). [C]

### The menu's real layout (2026-11-26): `GameModesMain`, found
- The whole of `FRONTEND.NSW` is resident in memory (a scan found 3620 blocks), so presence in memory does not say which
  screen is live. Searching for the menu script's strings (`DynamicListLoop`) finds the pool `GameModesMain` in a heap copy
  (1.0.20 run: pool at 0x1a199a5e4); the live node tree next to it is a copy of the 117 KB block with its pointers filled
  in (its `VOIDASS0` hash e67f3317 equals that block's, its name pointer points into that pool). [C]
- That block (file offset 7662992; `nsw_edit.py nodes GameModesMain`) holds the menu: a page container (0, 220, 1920 x 1080
  at +19432), a tile row container (92, 832, 1738 x 204 at +19512) with four 304 x 204 tiles at x 246, 560, 874 and 1188
  (+19616, +19896, +20176, +20456), and a node (92, 228, 1738 x 634) at +25064, the place of the offline panel; the 1740 wide
  node at +29860 is the 54 high bar. Measured on screen: tiles 304 wide, the first at x 338, the panel at y 228. [C]
- Why the page starts with the tile row below the screen: the page container sits at y 220 and the tile row at 832 inside
  it. When the focus lands on a tile the page scrolls up by about 220 (to y 0), which is the view with the hero art and the
  tile row near the bottom (y 832). That is what the one Down press does. [C for the numbers, H for the scroll amount]
- Edit test: moving the tile row's y from 832 to 69 (`nsw_edit.py set GameModesMain 19520 69 --expect 832 --out DIR`, run
  with `MLB_ROMFS_OVERRIDE=DIR`) puts the tiles near the top of the unscrolled page; after the game's own scroll on focus they
  end up at the very top, over the header. So the layout can be edited, and a position change needs the scroll amount
  changed with it (not found yet; likely the page container's y 220, +19440). [C for the effect]
- The earlier "poke a node, nothing moved" results were about other screens' nodes (the 6 KB block after `GameModesMain` is
  `ol_ChallengeList`'s, and `GameModesMain_ForBeta`'s block is 21 KB ending at 6502336), not about this one.
- Not found: where the offline panel's picture and the hero art are placed, and the event that shows the hero art (the page
  stays dark until a tile gets the focus).

### Leads for the open items (2026-11-26), from first-call traces of the whole game around the events
- The Down press: the functions first called after it include `f_7000847a90` (applies a signed row step from `+0x4b`/`+0x4d`,
  then refreshes the list), `f_700084ebb0` (the UI message handler, 8912 lines, table events), `f_700089a4d0` (rebuilds the
  list at `+0xa8`), `f_7000888fa8` (the selection box's constructor, `SelectionBoxTable`) and `f_7000889060` (`SelBoxComplete`).
  Calling the row step on the menu's list object, instead of pressing a button, is the way to drop the synthetic press; the
  list object was not identified. [I]
- The error box is drawn by the same table and message widgets as the rest of the menu (the first calls before it are
  `f_7000855470`, `f_7000860aa0` "rebuilds and draws table" and the blur pass `f_700080e888`), and no layout node of its size
  exists in any `.NSW` file, so the engine builds it in code. The functions that ran when it was raised and were checked
  not to be it: the session manager's dialog functions, the `NetDialogs` family, `OnlineQueryView` functions
  `f_70009d7940`, `f_70009d5824`, and the error-info parser `f_70009e2a1c` with its caller `f_70009e1910` (never called). [C]
- The failure path itself: `ol_OnlineEntry` runs script commands against the server (`mlb_login.post_update` and others) through
  `OnlineQueryView`, the game logs "Setting Online to ONLINE_NOT" from `f_7000a49f9c`, called by `f_70009d56f8` from the
  online-status handler `f_7000ad07e0` (vtable `0x70021a4770` slot 20), which also runs `f_7000a8d9a0` (screen marks). [C]
- What the error box is (memory dump while it was up, 2026-11-26) [C]: the game's one generic selection box. Its object (vtable
  `0x700218f080`: slots named `UI_SEL_BOX`, "Selection Box 2", `SelectionBox2`; at `0x1a6ca15c0` in that run) is built once, at
  the first menu entry, by `f_7000888fa8` (the `SelectionBoxTable` constructor, called from main+0x8a7224); `f_7000889060` is
  its `SelBoxComplete` handler and `f_7000889190` looks a `SelBoxComplete` item up by name. The text "Network Error" sits
  inline at offset `+0x20` of that object and the body "A network communications error has occurred. ..." at `+0x60`
  (a second record, at `0x1a6c99f08`, holds the same two strings and a pointer to the object plus `f_7000889190`). So the
  box is the selection box filled with the error text by whatever code raises it, which is why no layout node or dialog
  function of its own exists. Not found: the writer of those two text fields (a write watch on `+0x20` would name it).

## The box removed at its source: code patch set `no_net_box` (2026-11-26)

Dismissing the box with a synthetic A press works, but the box is still built and flashes for a few frames. The patch set
`no_net_box` (same setting, `MLB_NO_NETWORK_ERROR`, on by default) stops the game building it. Three places do: two in
the online-status handler `f_7000ad07e0` (sites at main+0xad0c2c and +0xad0c64) and `f_7000aa6ea8`, which runs every
frame and calls `f_7000889978` when an error is pending (site at main+0xaa6f0c, found with `tools/ctl.py`: a first-call
trace from the title screen to the menu). With the three sites in, `f_7000889978` and `f_7000889c18` are never called, no
box screen is entered, and the port's own A press is skipped. Measured on one live game, shots every 0.7 to 3 s after
the title: black x3 (the hold), then the scrolled menu x4, no box and no gap (`tools/menu_startup_check.py`).
Not checked: 1.0.15 (no exefs on this machine); a second, third and later error in one session.
