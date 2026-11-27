Offline, the game's main menu opens with a big "You are currently disconnected" panel, a "Network Error" box that waits for Ok, and a gap under the header with the mode tiles cut off at the bottom of the screen. The fork hides all three in the port (`MLB_HIDE_OFFLINE_BANNER`, `MLB_NO_NETWORK_ERROR`, both on by default). This page is what the game does, how each part was found and checked, and what is still open. The code is in `runtime/mlb/menu_offline.c` and `runtime/mlb/hid.c`; the repo's `docs/menu-offline-panel.md` carries the same facts with the exact commands.

## In plain words

The menu is one tall page. The first row is a panel that the game fills with server news. With no server it fills it with a picture (a crossed-out Wi-Fi symbol, "YOU ARE CURRENTLY DISCONNECTED!", the names of the online features). The second row is the four mode tiles. The page only scrolls when the focus moves, so at start the tiles sit below the bottom of the screen. Taking the picture away alone leaves an empty space where it was.

Separately, the game tries to log in when it starts and again when a tile needs the network. Both fail offline, and a "Network Error" box with an Ok button appears and waits.

What the port does now: it makes the menu think the server panels are on (so the picture is never chosen), presses Ok on the box, presses Down once so the page scrolls to the tiles, and keeps the window black while that happens so none of it is seen. Pressing Down is the game's own scroll to the focused row, so the result is the view the game shows after a tile is picked: Road to the Show focused, its art behind, all four tiles visible.

## The offline panel

The picture is one texture, `dynamictile_home_offline` (1740 x 636, entry 898 of `FRONTEND.TEX`). The text is in the picture, not in any text table, which is why searching for it found nothing. The menu script shows it when the variable `[GameModesMain.SHOW_DYNAMIC_PANELS]` is false.

The menu's data object (vtable `0x70021bd438`, 1.0.20) has four fields: HAS_ANNOUNCEMENTS, ANNOUNCMENT_NUMBER, SHOW_DYNAMIC_PANELS, STUBS_CAP. Slot 8 (`f_7000c0dc6c`) hands their values to the script; for SHOW_DYNAMIC_PANELS it gives `obj[+0x129] && obj[+0x128]`. Slot 6 (`f_7000c0da4c`) sets both bytes from the online state, so offline both are 0. The fix wraps slot 8: it sets both bytes to 1 while that function runs and puts them back after. Setting them for good made the game believe it was online and raised the error box; making the picture transparent (a 4x4 transparent image in its place) hid the picture but left its focus frame.

## The error box

Offline the game logs in at start (`ol_OnlineEntry (0)`) and after an online tile (`ol_OnlineEntry (1)`). Each attempt logs "Setting Online to ONLINE_NOT", returns to `GameModesMain`, and about half a second after the menu's selection box enters the box fades in. The port reads those log lines in order and presses A (the box's Ok) 0.3 s after the selection box.

What was ruled out as the source, each with a run: the session manager's dialog functions (`f_70009bebac` and its neighbours, the `NetDialogs` family at `0x7001650000`) are never called; swapping `bail_online` for `bail_screen` in the layout file left the box; renaming `OnlineEntry_ReconnectFail` left it. The code that raises the box was not found. Pressing B instead of A looked safer and was not: B on the menu moves focus to the top bar.

## The gap, and the layout

The main menu is the 117 KB `GameModesMain` block of `FRONTEND.NSW`. It holds a page container (0, 220, 1920 x 1080), a tile row container (92, 832, 1738 x 204) with four 304 x 204 tiles at x 246, 560, 874 and 1188, and a node (92, 228, 1738 x 634) where the panel sits. The live copy is in the game's heap, found by scanning memory for the menu script's strings.

Findings from editing a copy of the file (`tools/nsw_edit.py`, run with `MLB_ROMFS_OVERRIDE`):
- Moving the tile row's y from 832 to 69 puts the tiles near the top of the unscrolled page. After the game's own scroll on focus they land at the very top, over the header: the scroll moves things by about as much as before.
- Setting the page container's y from 220 to 0 changes nothing at start: the menu still opens in the gap, because the hero art waits for the focus event, not for the page position. With the Down press the view is the same as without the edit.

So the one Down press stays. It is the game's own focus scroll and it also triggers the art.

## The startup sequence

At start the window shows black from the first `GameModesMain` until 0.7 s after the Down, and the player's buttons are ignored then. After a press on a tile that needs the network the same black runs from the online entry until 0.7 s after the Ok. The presses and the end of the black run on a clock that counts only while the game polls its input: the game pauses without the window focus, and a first version on wall time missed its presses when the window lost the focus.

## Numbers

Control (both settings off) against fixed, headless, same game files:

| Check | Control | Fixed |
|---|---|---|
| Brightness spread of the old panel area | 56.1 | 5.9 in the gap, 44.1 after the scroll |
| Yellow "DISCONNECTED" pixels | 1896 | 0 |
| Teal frame-edge pixels | 2151 | 0 |
| Screenshots showing the error box (every 10 frames, 2600 to 4590) | 89 of 200 | 3 of 200 |
| Startup, every 10 frames | gap and box visible for seconds | 22 black samples, then the menu; 0 gap, 0 box |
| Press on Diamond Dynasty, every 8 frames | the box for about 0.5 s | 21 black samples, then the menu; 0 box |

The checks are `tools/menu_offline_check.py`, `tools/network_error_check.py` and `tools/menu_startup_check.py`; each takes screenshots from a run with `MLB_SHOT`.

## What is not proven

- 1.0.15: not run. The log lines are the same, but the hook's addresses for the panel are 1.0.20 only, so there the panel stays.
- A real connection: the steps need "Setting Online to ONLINE_NOT"; with a server the port does nothing.
- A slow machine: the 0.3 s before the Ok is wall time. If the box comes later than that, the press lands early and, on the menu, would open the focused mode.
- The tile row's place is set in the layout, but the engine computes the scroll from the focused row; changing the layout position alone is not enough to move the menu's look.

## Related

[Frontend](Frontend), [Known game functions](Known-game-functions), [Dev harness and measuring](Dev-harness-and-measuring).
