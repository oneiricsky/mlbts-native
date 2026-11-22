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

## What limits the frame rate in heavy scenes

Measured on 2026-11-22 (1.0.20, Ryzen 5 5600X, RTX 3060 Ti, DLAA on, `MLB_FPS_LIMIT=240`), from `MLB_TRACE=perf` logs,
F12 captures and sampler profiles of an exhibition match and the attract match. Scenes like the outfield fan cam run at
about 78 fps while lighter ones look the same and run much faster; this is why.

### The frame is a sum, not an overlap

The game hands a frame over (`nvnQueueSubmitCommands`) and right away waits for that same frame's GPU work: its main
thread polls an event word (`nvnEventGetValue`, 1.0.20 `f_70005a1a90`) until the GPU signal at the end of the frame
arrives. Only then does it start the next frame. On the Switch that wait is the GPU's own time. Here it is everything the
port does after the submit. The `nvn: game GPU wait burst` lines time one wait from its start:

| step | ms from the submit |
|---|---|
| the replay thread starts translating the frame | +0.2 |
| replay done, last part submitted | +7.2 to +10.1 |
| the GPU reaches the signal | +9.3 to +12.2 |
| the game sees it and goes on | +9.6 to +12.2 |

Then the game runs its own code for the next frame for 5.3 to 6.8 ms. So a heavy frame costs roughly
**game code (5-7 ms) + replay (7-10 ms) + the GPU's tail after the replay (about 2 ms)**, one after another. The GPU
itself is busy only about 3.7 ms per frame and idle the rest, waiting for the next submission. In the fan cam (about 3,000
draws) the replay alone is 8.2 ms of a 12.7 ms frame. A scene with fewer draws gets a shorter replay, hence the large
frame rate differences between scenes that look alike.

Selecting a pitch raises the frame rate by about 10 fps every time: the pitch overlay goes away with its draws, and the
replay and the GPU's tail get shorter by that much. It is not a port bug.

### Where the replay's time goes

In gameplay the replay handles about 25,000 commands per frame. Most of its time is draws: about 665 indexed draws at
about 6.4 us each (`perf: frame N: replay by command`). Per draw it resolves the shaders and pipeline, checks feedback
between the targets and the textures, finds every texture and uniform block in the caches and builds the descriptors.
In the sampler profile of the attract match (replay thread only):

| part | share of replay time |
|---|---|
| `prepare_draw` (shaders, pipeline, resources) | 48 % |
| `bind_resources` (descriptors; inside `prepare_draw`) | 20 % |
| the uniform snapshot at the start of a submission (`vk_usnap_begin`) | 10 % |
| the VRAM mirror check at the start (`vk_mem_mirror_begin`, mostly `GetWriteWatch`) | 8 % |
| feedback checks (`feedback_prepare`) | 8 % |
| shader lookups (`shader_for`) | 7 % |

The rest is spread thin. These functions were already heavily tuned; much of what is left is the CPU waiting for memory.

DLAA costs 1.17 ms of GPU time per frame (`MLB_DLSS_TIMES=1`), most of the GPU's tail after the replay.

### What was done (dev, November 2026)

| change | effect in the attract match |
|---|---|
| the replay reads the clock less often when it decides where to split a submission (`c9fdcd7`) | `QueryPerformanceCounter` was 7.6 % of the replay's busy time |
| finished parts go to the recorder thread without waiting; the compute shader dump is off unless `MLB_DISPATCH_DUMP` is set; the last program lookups are remembered (`d5cf456`) | replay 3.41/3.53 -> 3.31/3.25 ms per frame; time spent waiting for the recorder 624 -> 212 ms per log period; fps unchanged within noise |
| the runtime is compiled with a profile of the attract match (`573f132`, `docs/runtime-port.md`) | replay 3.22 -> 2.92 ms per frame, 149.6 -> 155.8 fps |

Tried and reverted: splitting submissions inside a pass as well as between passes (the GPU's tail stayed at about
2.7 ms).

### Options considered and not taken

- **Translating one frame on several threads at once.** Each draw depends on what earlier draws in the same frame did:
  whether a texture exists yet and whether another image just drew over its memory (which decides copying or clearing
  its content; the aliasing behind most "image from another menu" bugs), whether an earlier GPU write changed a uniform
  block (later draws then read the new values, not the snapshot), whether a barrier between compute jobs can be skipped,
  and a dozen small records that let a draw skip work when it matches the previous one. Splitting the replay would mean
  rebuilding about 15,000 lines into a serial "decide" pass and a parallel "build" pass; the work free of these
  dependencies is too small and scattered to hand to other threads on its own.
- **Letting the game prepare the next frame while the port replays this one** (the port would end the game's wait
  before the GPU is done, one frame ahead). Frames would overlap: about 7.5 ms apart instead of 15 ms in the
  heavy scenes. The input delay grows by about 2 ms (one frame, but a frame half as long), not by a frame of today's
  length. Not done: the user prefers no added delay, and the game may read GPU results after its wait that would not be
  ready yet; that would have to be checked first.
- **Starting the replay while the game is still recording the frame.** Same order problem as above, and the game writes
  uniform data up to the submit.

### Smaller options still open (no added delay)

- The uniform snapshot and the mirror check at the start of each submission (about 18 % of the replay in the attract
  match) on helper threads: roughly 0.5-1 ms per heavy frame.
- A profile for the game's own code (5-7 ms of a heavy frame; typically 10-20 % faster) would help only the dev build:
  its counts are data taken from the game's code, which a release must not carry. General lessons about the translator's
  own output (its rarely taken error paths) could go into `recomp/` instead.
- DLAA off or a cheaper AA (F1 menu) shortens the GPU's tail by up to 1.2 ms.

### Measuring

- Compare builds with the same settings and alternate the runs: the attract match differs from run to run, and the
  sampler (`MLB_SAMPLER=on`, the dev `mlb.cfg`) slows the game noticeably. Turn it off for frame rate comparisons.
- `perf: frame N: replay by command` covers 600 frames; a block with an F12 capture in it (draw logs, screenshots) shows
  per-draw costs twice as high. Skip those blocks.
- The sampler writes `work/profile/prof.txt` only when the game exits normally (close the window, or `taskkill` without
  `/F`), and a profile must be read with the `mlb.map` of the build that made it.

## Supporting another game version

`k_addrs[]` in `framerate.c` lists, per version, the GOT slots of the vsync count and the averaging flag, and the
addresses of the step and the carry. Find them with `tools/addrmap.py` from the 1.0.20 addresses above and check them in the
disassembly of the timer (`tools/disasm.py`). An unknown version keeps the game's own 60 fps and says so in the log.
