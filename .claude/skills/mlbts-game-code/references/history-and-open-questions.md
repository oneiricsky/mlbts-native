# History and open questions

Read before reopening something. Sources: `docs/reports/*.md`, `docs/walkup-freeze.md`, `docs/frame-rate.md`, `CLAUDE.md`. Numbers are from one PC (RX 6700 XT / RTX 3060 Ti dev machines).

## Solved

| Problem | Cause | Fix | Evidence |
|---|---|---|---|
| 250-380 ms freeze before every pitch, longer at inning changes | after each play the game bakes stadium lighting in the background, then the batter-up handler forces a second blocking bake (~50 scene passes with a GPU wait each) | patch `walkup_light` (7 sites) + `walkup_leaders` (1 site; a duplicate league-leader list build) | frames over 100 ms in 30 pitches: 27 -> 0; fixed upstream in 0.2.0 |
| 5-6 hour crash (issue 17) | loader bound symbols differently from Horizon's rtld: memory leak | copy rtld's rule | upstream 0.2.0 |
| Bright yellow face with PS5 colour maps | a compute pass measures skin tone with `texelFetch` over a rectangle in Switch texel coordinates; on a 1024x512 image that is the wrong quarter, lit face shaders divide by it | bind PS5 images from the Switch-size level in compute (`get_view`, `hd_shift`) | blown faces 50 -> 0 of 101 shots |
| 15 ms cold-disk stalls per PS5 head file, 200-670 ms frames | file read on the replay thread at first upload | prefetch thread on file open (`MLB_HD_PREFETCH`) | max stall on replay thread 28 ms -> 0.7 ms |
| Match-start freeze (MSDF step ~700 ms) | game proves empty space has no edges: ~67 M NaN results, 97% of pixels infinite | patch `msdf_skip` (research branch, not merged) | 687 -> 189 ms mean, 6 runs; 1,048,576-byte texture identical on 2 stadiums |
| Cutscene dips 25-45 fps | `getenv()` x4 per `get_view` in diagnostics (12 ms/frame) | cache once; rule: no lookups in per-draw paths | 59 fps mean, 6.5 min |
| Tutorials back every start; hub upgrades lost; custom cameras reset | online-only profile; autosave not triggered by hub purchases; cache storage never created | `tutorials.c`, `rtts_autosave.c`, `cache_storage.c` | per-file headers |
| Face buttons wrong in menus vs play | one icon cell serves both; Switch build maps by place | `MLB_PAD_MAP=auto` switched by the game's UI screen log lines | hid.c |

## Open

- **Match-start CPU work** (1.4-1.6 s frame): grass tiles ~172 ms + MSDF ~700 ms; MSDF fixed on the research branch, grass untouched. Other start frames: a 52-wait GPU burst at Pitch History/Meter init (245 ms), shader-loading frames, a UI node event wait.
- **Lineup card stall** (555 ms, now ~64 ms): believed to be the same lighting bake, inferred from shape, never traced with the manager's fields.
- **msdf_skip equality** proven for 2 stadiums only; other stadiums/times/weather, a whole match, and 1.0.15 address (needs the 1.0.15 exefs) are open. `research/float-fixup` needs re-measuring after the NaNs are gone.
- **PS5 colour maps** still opt-in: verified on ~2 heads; need ~two dozen from both teams with the known-bad control and one full match. Compute consumers of other PS5 categories unchecked.
- **Issue 10** (confirm button flips to circle on `PresSkip`, dynamic challenge popup): add those screens to the menu list in `hid_game_log`; needs the challenge screen's real name.
- **Issue 18** (no ball in one batting-cage mode above 60 fps): cause unknown; step guard from 0.2.0 unconfirmed.
- **Issues 21/26** (local 2-player): design limit (all pads merged into Player 1); needs how the game asks for Npad No2.
- **Which game screens use whole-vsync timing**; MLB's lowest safe frame step.
- **The game state machine**: which of slots 5 and 7 is update vs transition; who calls them; the base class.
- **Time of day / weather storage** for the harness; scenario code (Situation, Moment, Storyline) callability.
- **About 95,000 anonymous `main` functions**: see `docs/map/regions/` for the region notes; roughly 12,800 reference a string, the rest are named only by neighbours, vtables and callers.

## Out of scope
Online play, Diamond Dynasty, DLC, other game versions.
