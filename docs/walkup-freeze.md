# The walk-up freeze

Before every pitch (when the batter-up state starts) the game froze for 250-380 ms, and at inning changes for longer.
The code patches in `tools/data/patches-1.0.20.txt` and `patches-1.0.15.txt` remove it: set `walkup_light` (6 sites)
and set `walkup_leaders` (1 site). Each has a settings row, `MLB_WALKUP_LIGHT` and `MLB_WALKUP_LEADERS` (both on by
default; `=0` runs the game's own code), and a toggle on the settings menu's Game tab. Addresses below are 1.0.20's;
1.0.15's are 0x1500 lower.

## Cause
The game lights each stadium for the time of day. Its clock moves during a game (about 17.5 s per pitch and more per
batter and inning, `f_7000d52680`), and the lighting is baked again for each new time. The lighting manager
(`f_70012c54ec`, an object of 0x101e40 bytes) keeps two lighting buffers, the one on screen (`+0xd38`) and a spare,
with the time each holds at `+0x101400 + 4 * buffer`. The flag word `+0xd3c` starts and steers a bake, which
`f_70012e0150` runs (once a frame, from `f_700000b140`).

1. **After every play** the game bakes the new time into the spare buffer in the background: `f_70012d20a0` (from
   `f_700109a6a8`) sets flags `0xec01`, and the bake runs one step per frame for about 50 frames (0.9 s). It ends with
   flags 2 and does not switch buffers.
2. **When the next pitch's batter-up state starts**, the handler `f_700108b628` asks for the lighting again,
   `f_70012d0fcc(manager, 1)` at `main+0x108bbb8`. The `1` means "force": `f_70012d1e04` then ignores the spare buffer
   the game has just finished and bakes the same time again (flags `0xef01`). Bit 9 of those flags makes that one call
   of `f_70012e0150` loop through all ~50 steps at once, each a full scene pass followed by a GPU kick and wait
   (`f_70005a1300(2)`, `f_70005a1a90()`). That is the freeze, the "about 50 submit-and-wait round trips in one frame"
   at each walk-up.

Logging the manager's fields whenever they change (`MLB_FNDUMP=70012e0150:d3c,d38,101400:f,101404:f`) shows it before
every pitch: the spare buffer holds, for example, 19.1882 h from the background bake, and the blocking bake makes
19.1882 h again and then switches to it.

## Set `walkup_light`
- **Site 1** (`main+0x108bbb4`, `mov w1, #1` -> `mov w8, #1 ; strb w8, [x0, #0xc2d] ; mov w1, wzr`): the batter-up
  handler asks without force, the way the game's other callers do (`main+0x4e17f0`, `0xe2c94c`, `0x1082084` and
  `0x1096454` mark the lighting dirty, `+0xc2d`, and pass 0). If the spare buffer holds the current time,
  `f_70012d1e04` switches to it at once; otherwise it starts a bake (site 3).
- **Site 2** (`main+0x12d1f74`, five words after `str w8, [x9]`): that quick switch bumps the counter at
  `*PTR_DAT_700229d620` but not the lighting-version counter at `0x7002ca9338`, which the end of a bake also bumps
  (`main+0x12e0db4..0x12e0e24`). The counter's only reader, the indirect-light probes (`f_700128d2a0`), refresh only
  when it changes; without this site they kept an older bake's lighting (screenshots 10-15 % off in brightness).
- **Sites 4-6** (`main+0x12d1f7c`, `0x12d1f84`, `0x12d1f98`): when `f_70012d1e04` starts a bake it ends by
  tail-calling `f_70019fb800` with the time (`main+0x12d2018..0x12d208c`), which turns a set of stadium props off or
  on at 19.5 h (17.0 h in months 0 and 12), at stadiums with an entry in the table at `0x70021edca0`. The quick switch
  returned before that call; its three exits now branch to the same stadium check and call.
- **Site 3** (`main+0x108bbc0`, right after the request): clears bit 9 of `+0xd3c`. When the clock moved since the
  background bake (the first batter after an inning change: the inning and the simulated half add time), the
  unforced request starts a new bake; without bit 9 it runs one step per frame (about 1.2 s) and bit 8 switches
  buffers when it ends. Until then the lighting of the earlier time stays on screen (about 10 game minutes earlier).
  A scene's first bake still runs at once: `f_70012e0150` sets bit 9 itself while `+0x288` is 0.

Registers: each replacement writes only registers the following code overwrites before reading (w8 before a `bl`,
x8/x9 on a path that ends in the function's return, w9 before `mov w9, #0x40400000`), and none sets flags.

## Set `walkup_leaders`
At an inning change about 90 ms of game work remained. Sampling the main thread in those frames put most of it in the
broadcast "moments" refresh: `f_7000e5640c` (from the batter-up event) -> `f_7000e54c00`, which builds top-10 lists
for 23 stats in 4 groups, 92 lists, each a pass over up to 1,350 players and a `qsort_r`. The refresh and the
game-start sequence `f_7000e53620` both call `f_7000e53654`, which clears the object and builds the lists
(`main+0xe53808`), and then `f_7000e543a4`, which builds them again first thing (`main+0xe543d0`). The site turns the
first build into a `nop`. Nothing between the two builds reads the lists (`+0x1b0b8..+0x25d38`), `f_7000e54c00` resets
every entry before it fills them, and `f_7000e53654` has no other callers.

## What else changes
- The background bake now decides the lighting a few seconds earlier than the forced one did (right after the play
  instead of at the next batter-up). Its inputs are the same.
- Where the game pins the time (some stadiums and modes), it no longer bakes the same time again before every pitch.
- Site 3 also clears a bit 9 that another caller set earlier in the same frame (a roof change at the same moment,
  say): that bake then runs in the background too.
- Site 2 also refreshes the probes when the game's other callers take the quick switch.

## How it was checked
Road to the Show as a Double-A starting pitcher (Hartford), pitching through the meter, 1280x720, 60 fps limit, driven
unattended; for each version the same exe with both switches off and on.

| game | switches | pitches | frames over 100 ms |
| --- | --- | --- | --- |
| 1.0.20 | off | 30 | 27: median 260 ms, max 334 ms |
| 1.0.20 | on | 30, 1 inning change | 0 (mean 60.0 fps) |
| 1.0.15 | off | 15 | 11: median 230 ms, max 297 ms |
| 1.0.15 | on | 15 | 0 at walk-ups; one 496 ms frame of first-time shader and pipeline work |

Earlier runs of the same sites (built from a tree with more diagnostics) traced the lighting manager:
- 40 pitches with 4 inning changes, `walkup_light` on: no frame over 100 ms; the slowest were three of 88-96 ms at
  inning changes, the league-leader work. With `walkup_leaders` on too (40 pitches, 2 inning changes): 71 ms at most.
- The inning-change bake runs with flags `0xed01` for about 1.2 s and switches buffers before the pitch screen; no
  blocking bake (`0xef01`) after the first pitch.
- The lighting matches the game's own: the same screen areas over four screenshots a run, in games started at 13:05
  and 21:30, read the same within 2 % with the switch off and on (10-15 % off before site 2 was added).
- League leaders: the lists differ from launch to launch, so the check is inside one launch: 32 list fields logged
  right after the first build (entry of `f_7000e54080`) and right after the second (entry of `f_7000e545f0`) at the
  full refresh are identical.
- Sites 4-6: neither an unpatched nor a patched game crossing 19.5 h at Hartford called `f_70019fb800` (Hartford has
  no entry in the props table), so the prop switch itself was not seen in game.

1.0.15's sites are 0x1500 lower (`tools/addrmap.py` matched 8 or more words around each; the original words are equal,
and `recomp/gen.py --patches` checks them); only site 2's load offset differs (the counter's slot is
`main+0x2283820`). The setup's Build step, run on an install folder holding 1.0.15's code, picks
`patches-1.0.15.txt` and builds an `mlb.exe` with both sets.

Every run, switch off or on, also has one frame of 50-134 ms soon after the first pitch, with 2-8 ms of new graphics
pipelines: the port meeting pipelines for the first time in the match, not this.
