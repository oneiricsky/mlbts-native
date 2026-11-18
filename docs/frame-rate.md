# Frame rate limit (unlocked frame rate)

MLB The Show 26 runs at 60 fps on the Switch. The port can run it at a higher (or lower) frame rate without speeding
the game up or slowing it down. The code is [`runtime/mlb/framerate.c`](../runtime/mlb/framerate.c).

## Using it

- In game: **F1 → Display → Frame rate limit**. Choices: 30, 40, 45, 60 (the game's own, the default), 90, 120, 144,
  165, 240, or the monitor's refresh rate. It applies at once; no restart.
- In `mlb.cfg`: `MLB_FPS_LIMIT=120` (any of the values above, or `display`). The RecompLauncher has the same row.
- A limit above the monitor's refresh rate shows only with Presentation set to Fast VSync (mailbox) or Off.
- Loading screens stay at 60 fps whatever the limit (see below).

## Why the game does not speed up

Many games count frames: each frame moves the game forward by a fixed 1/30 or 1/60 s, so more frames per second make
the game run faster. TotK Recomp and Astral Chain Recomp had to patch the game code for this (their `frame_rate.c`).

MLB does not count frames. Its frame timer (1.0.20 `main+0x58a9f0`, 1.0.15 `main+0x58a9d0`; the two are the same
instructions) runs once a frame. It is given the number of 60 Hz vsyncs a frame should last, an int the game keeps in
its data (1.0.20 `main+0x22ad028`, 1.0.15 `main+0x22ab028`; 1 means 60 fps). It then:

1. sleeps until that many vsyncs have passed since the previous frame (this is what holds the game at 60 fps);
2. measures how long the frame really took and sets the game's time step (1.0.20 `main+0x22c90c4`, copied into the
   global `s_fDeltaTime` that about 200 places in the game read):
   - normally (the averaging flag, 1.0.20 `main+0x22c9078`, is on), the step is the average of the last 15 measured
     frame times, never less than vsyncs / 60 s;
   - in the other mode, the step is the number of whole vsyncs measured, never less than the vsync count.

So the game already moves by real time. The vsync count only sets its sleep and the step's lower limit. With the
count at 0 the game does not sleep, and the step is the average real frame time: the game runs at the rate the frames
come, at its normal speed. The port's present pacer (`nvn_api_obj.c`, `present_period`) then holds frames to the
limit.

What the port does at a limit other than 60 (no game code is changed):

- At every present it writes 0 into the vsync count, while the game is in its averaging mode. The game writes its own
  value back on some screen changes; the next present sets 0 again (one frame at 60 fps in between).
- In the whole-vsync mode a frame shorter than 1/60 s would step the game by 0, so there the game's own count goes
  back and the game runs at its own 60 fps. The game switches that mode with an event (`main+0xd514e0` in 1.0.20:
  event 0x220 turns averaging off; 0x61, 0x11c and 0x213 turn it on). The log says `frame rate: the game's own 60
  fps` when this happens, and the menu row shows "the game holds 60 here". Which game screens use that mode is not
  known yet.
- The game switches to whole vsyncs right before its timer runs, so the port only sees the switch one frame later. In
  that one frame the count is still 0, and a frame shorter than 1/60 s would step the game by exactly 0 (nothing
  moves; anything that divides by the step gets an infinite or invalid number). So at every unlocked present the port
  also fills the timer's carry (the time left over from the whole vsyncs, 1.0.20 `main+0x2cb6150`) to 1/60 s: that
  frame then steps by at least 1/60 s. With averaging on the carry changes nothing.
- The other callers of the timer (loading loops) pass 1 themselves, so loading screens stay at 60 fps.
- At 60 (the default) nothing of this runs: the game and the pacer behave as before.

The highest limit is 240, as in TotK Recomp (their shortest safe step). MLB's own lowest safe step is not known.

## Checking it

`MLB_TRACE=perf` logs every 600 frames the game time the steps added up to against the real time:

```
perf: frame rate: game time 4.72 s in 4.72 s (1.000), 127.2 fps, unlocked
```

1.00 means normal speed; above it the game runs fast. Measured on 2026-11-16 in the menus (1.0.20, Ryzen 5 5600X,
RTX 3060 Ti): at a limit of 144, 123-141 fps and 0.99-1.02; at 60, 59-60 fps and 1.00-1.14 (the windows above 1 also
appear at 60: the averaged step catching up after long frames).

## Supporting another game version

`k_addrs[]` in `framerate.c` lists, per version, the GOT slots of the vsync count and the averaging flag, and the
addresses of the step and the carry. Find them with `tools/addrmap.py` from the 1.0.20 addresses above and check them in the
disassembly of the timer (`tools/disasm.py`). An unknown version keeps the game's own 60 fps and says so in the log.
