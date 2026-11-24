# History and open questions

Read before reopening something. Sources: `docs/reports/*.md`, `docs/walkup-freeze.md`, `docs/frame-rate.md`, `CLAUDE.md`. Numbers are from one PC (RX 6700 XT / RTX 3060 Ti dev machines).

## Solved

| Problem | Cause | Fix | Evidence |
|---|---|---|---|
| 250-380 ms freeze before every pitch, longer at inning changes | after each play the game bakes stadium lighting in the background, then the batter-up handler forces a second blocking bake (~50 scene passes with a GPU wait each) | patch `walkup_light` (6 sites) + `walkup_leaders` (1 site; a duplicate league-leader list build) | frames over 100 ms in 30 pitches: 27 -> 0; fixed upstream in 0.2.0 |
| 5-6 hour crash (issue 17) | loader bound symbols differently from Horizon's rtld: memory leak | copy rtld's rule | upstream 0.2.0 |
| Bright yellow face with PS5 colour maps | a compute pass measures skin tone with `texelFetch` over a rectangle in Switch texel coordinates; on a 1024x512 image that is the wrong quarter, lit face shaders divide by it | bind PS5 images from the Switch-size level in compute (`get_view`, `hd_shift`) | blown faces 50 -> 0 of 101 shots |
| 15 ms cold-disk stalls per PS5 head file, 200-670 ms frames | file read on the replay thread at first upload | prefetch thread on file open (`MLB_HD_PREFETCH`) | max stall on replay thread 28 ms -> 0.7 ms |
| Match-start freeze (MSDF step ~700 ms) | game proves empty space has no edges: ~67 M NaN results, 97% of pixels infinite | patch `msdf_skip` (research branch, not merged) | 687 -> 189 ms mean, 6 runs; 1,048,576-byte texture identical on 2 stadiums |
| Cutscene dips 25-45 fps | `getenv()` x4 per `get_view` in diagnostics (12 ms/frame) | cache once; rule: no lookups in per-draw paths | 59 fps mean, 6.5 min |
| Tutorials back every start; hub upgrades lost; custom cameras reset | online-only profile; autosave not triggered by hub purchases; cache storage never created | `tutorials.c`, `rtts_autosave.c`, `cache_storage.c` | per-file headers |
| Face buttons wrong in menus vs play | one icon cell serves both; Switch build maps by place | `MLB_PAD_MAP=auto` switched by the game's UI screen log lines | hid.c |

## Open

| Problem | State | Settles it |
|---|---|---|
| Match-start CPU work (1.4 to 1.6 s frame) | grass tiles about 172 ms plus MSDF about 700 ms; MSDF fixed on a research branch, grass untouched; other start frames: a 52-wait GPU burst at Pitch History and Meter init (245 ms), shader-loading frames, a UI node event wait | profile the grass step; trace the 52-wait burst |
| Lineup card stall (555 ms, now about 64 ms) | believed to be the same lighting bake, inferred from the shape, never traced with the manager's fields | log the manager's fields at the lineup card |
| `msdf_skip` equality | proven for two stadiums only | more stadiums, times of day and weather, a whole match, the 1.0.15 address (needs the 1.0.15 exefs); re-measure `research/float-fixup` |
| PS5 colour maps | opt-in; verified on about two heads | about two dozen heads from both teams with the known-bad control and one full match; compute consumers of other PS5 categories |
| Issue 10 | confirm flips to circle on `PresSkip` and the dynamic challenge popup | add those screens to the menu list in `hid_game_log`; needs the challenge screen's real name |
| Issue 18 | no ball in one batting-cage mode above 60 fps; cause unknown; the 0.2.0 step guard is unconfirmed | same mode at 60, 144 and 240; `frame rate:` log lines; an F12 capture |
| Issues 21 and 26 | local 2-player is a design limit (all pads merged into Player 1) | how the game asks for pad 2 |
| Frame timing | which screens use whole-vsync timing; MLB's lowest safe frame step | log the mode per screen |
| Game state machine | which of slots 5 and 7 is update and which is transition; who calls them; the base class | read the handlers' bodies |
| Harness | where time of day and weather are stored; whether scenario code (Situation, Moment, Storyline) is callable | `MLB_WATCH` and state diffs |
| Anonymous functions | about 95,000 `main` functions, about 12,800 with a string | the region notes list what is unexamined |

## Out of scope
Online play, Diamond Dynasty, DLC, other game versions.
