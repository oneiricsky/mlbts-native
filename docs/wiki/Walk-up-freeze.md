Before every pitch the game froze for 250 to 380 ms, and for longer at inning changes. Upstream fixed it in Fastball 0.2.0 with code patches; this page is the cause and the measurements, from the fork's notes.

## In plain words

The game lights each stadium for the time of day, and the clock moves during a match (about 17.5 s of game time per pitch, more per batter and inning). Each new time needs the lighting worked out again, which the game calls a bake.

After every play the game quietly bakes the next time into a spare lighting buffer, one step per frame for about 50 frames. That is fine. Then, when the next pitch starts, one function asks for the lighting again with a "force" flag set. The force flag makes the game ignore the finished spare buffer and bake the same time again, all in one frame: about 50 full scene passes, each followed by a GPU kick and a wait. That is the freeze.

## The code involved (1.0.20 addresses)

| Function | Role |
|---|---|
| `f_7000d52680` | moves the game clock |
| `f_70012c54ec` | returns the lighting manager, an object of 0x101e40 bytes holding two lighting buffers and, at +0xd3c, a flag word that steers a bake |
| `f_70012d20a0` | starts the background bake after a play (flags 0xec01) |
| `f_700108b628` | the batter-up handler; at main+0x108bbb4 it calls `f_70012d0fcc` with force = 1 |
| `f_70012e0150` | runs bake steps once a frame; bit 9 of the flag word makes one call loop through all ~50 steps |

Logging the manager's fields while they change showed it before every pitch: the spare buffer already held 19.1882 h from the background bake, and the blocking bake made 19.1882 h again.

## The patches

Set `walkup_light` has six sites:

| Site | Change | Why |
|---|---|---|
| `main+0x108bbb4` | the batter-up handler asks without force, the way the game's other callers do | removes the second bake |
| `main+0x12d1f74` | the quick switch also bumps the lighting-version counter | without it the indirect-light probes keep an older bake's lighting (screenshots 10 to 15 percent off in brightness) |
| `main+0x12d1f7c`, `0x12d1f84`, `0x12d1f98` | the quick switch's three exits go through the same stadium check as a fresh bake | stadium props keep switching at 19.5 h (17.0 h in months 0 and 12) |
| `main+0x108bbc0` | clears bit 9 of the flag word right after the request | a bake needed after an inning change runs one step a frame in the background instead of in one frame |

Set `walkup_leaders` has one site. At an inning change the game builds its broadcast league-leader lists twice in a row (92 lists, each a pass over up to 1,350 players and a sort), about 90 ms of work. The patch drops the first build; nothing reads the lists in between.

Both are on by default with a settings row each (`MLB_WALKUP_LIGHT`, `MLB_WALKUP_LEADERS`); `=0` runs the game's own code.

## Numbers

Road to the Show, Double-A starting pitcher, 1280x720, 60 fps limit, driven unattended, same exe with the switches off and on.

Slow counts frames over 100 ms.

| Game | Switches | Pitches | Slow |
|---|---|---|---|
| 1.0.20 | off | 30 | 27 (median 260 ms, max 334 ms) |
| 1.0.20 | on | 30, one inning change | 0 |
| 1.0.15 | off | 15 | 11 (median 230 ms, max 297 ms) |
| 1.0.15 | on | 15 | 0 at walk-ups |

A longer run, 40 pitches with four inning changes, had no frame over 100 ms with the lighting patch on; the slowest were three of 88 to 96 ms at inning changes, which was the league-leader work. With the leaders patch on too, the worst was 71 ms.

## What the fork's earlier work got wrong

An earlier report here, written before 0.2.0 was merged, called these waits inherent: about 53 to 55 GPU waits per pitch, each about 4.4 ms. We tried to make each wait cheaper and never asked why the game was doing 50 of them. Upstream asked, and found the redundant bake. That is why the fork's working rules now say to ask why the game does the work first.

## Not seen

Neither an unpatched nor a patched game crossed 19.5 h at Hartford, which has no entry in the props table, so the prop switch itself was not seen in game.
