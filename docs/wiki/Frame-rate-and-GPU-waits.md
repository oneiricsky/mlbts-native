Two questions: how the port can run the game above 60 fps without making it run fast, and why heavy scenes are slower than lighter ones that look the same.

## Running at other frame rates

The game does not count frames. Its frame timer (1.0.20 `main+0x58a9f0`) runs once a frame. It is given the number of 60 Hz vsyncs a frame should last, an int the game keeps in its data (`main+0x22ad028`, where 1 means 60 fps). It sleeps until that many vsyncs have passed, then measures how long the frame really took and sets the game's time step (`main+0x22c90c4`, copied into a global that about 200 places read). Normally the step is the average of the last 15 measured frame times, never less than vsyncs / 60 s.

So the game already moves by real time. With the vsync count at 0 it does not sleep, and the step is the average real frame time. The port's `framerate.c` writes 0 into the count at every present when the limit is not 60, and its present pacer holds the limit. No game code is patched. Choices in the F1 menu run from 30 to 240 or the monitor's rate.

Two guards. In the game's whole-vsync mode (switched by event 0x220 at `main+0xd514e0`; 0x61, 0x11c and 0x213 switch it back) a frame shorter than 1/60 s would step the game by 0, so there the port hands the game its own count back and the game holds 60. The game switches to that mode right before its timer runs, so the port also fills the timer's carry (`main+0x2cb6150`) with 1/60 s at every unlocked present; otherwise one frame could step by exactly 0 and anything dividing by the step would get an invalid number. Loading loops pass 1 themselves, so loading screens stay at 60.

Check: `MLB_TRACE=perf` logs game time against wall time every 600 frames. 1.00 means normal speed. At a limit of 144, 123 to 141 fps and 0.99 to 1.02.

Which game screens use whole-vsync timing is not known, and neither is the lowest safe step. An unexplained report (no ball in one batting-cage mode above 60 fps) may involve this; see [Upstream bug research](Upstream-bug-research).

## Why heavy scenes are slow

Measured on 2026-11-22 with upstream's setup (Ryzen 5 5600X, RTX 3060 Ti, DLAA on). Scenes like the outfield fan cam run at about 78 fps while similar-looking ones run much faster.

The frame is a sum, not an overlap. The game submits a frame (`nvnQueueSubmitCommands`) and right away waits for that frame's GPU work: its main thread polls an event word (`f_70005a1a90`) until the GPU signal arrives, and only then starts the next frame. On a Switch that wait is just the GPU's time. Here it is everything the port does after the submit.

| Step | ms from the submit |
|---|---|
| the replay thread starts translating the frame | +0.2 |
| replay done, last part submitted | +7.2 to +10.1 |
| the GPU reaches the signal | +9.3 to +12.2 |
| the game sees it and goes on | +9.6 to +12.2 |

Then the game's own code for the next frame takes 5.3 to 6.8 ms. A heavy frame costs roughly game code (5 to 7 ms) plus replay (7 to 10 ms) plus the GPU's tail after the replay (about 2 ms), one after another. The GPU itself is busy about 3.7 ms a frame. In the fan cam (about 3,000 draws) the replay alone is 8.2 ms of a 12.7 ms frame. Choosing a pitch removes the pitch overlay's draws and raises the frame rate about 10 fps every time.

Where the replay's time goes, in the attract match: 48 percent `prepare_draw` (shaders, pipeline, resources), 20 percent of it `bind_resources`, 10 percent the uniform snapshot at the start of a submission, 8 percent the VRAM mirror check, 8 percent feedback checks, 7 percent shader lookups. DLAA costs 1.17 ms of GPU time a frame.

Done: the replay reads the clock less often (the timer call was 7.6 percent of its busy time); finished parts go to the recorder thread without waiting; the runtime is compiled with a profile of the attract match (replay 3.22 to 2.92 ms a frame, 149.6 to 155.8 fps, two runs each).

Not taken: translating one frame on several threads (each draw depends on what earlier draws did, and rebuilding about 15,000 lines into a serial decide pass and a parallel build pass is too much); letting the game start the next frame before the GPU finishes (frames would overlap, but adds about 2 ms of input delay and the game may read GPU results after its wait); starting the replay while the game is still recording (same ordering problem).

## Other dips found along the way

- Cutscene dips of 25 to 45 fps came from four `getenv()` calls per `get_view` call in temporary diagnostics, about 1,000 per frame and about 12 ms. With the values cached `get_view` costs 0.06 microseconds a call. The rule kept: no environment or config lookups in per-draw or per-call paths, even in diagnostics.
- A compute descriptor bind-skip had no effect (record 4.70 against 4.69 ms per wait) and was dropped.
- An early-signal knob (`MLB_EVENT_GPU`) once crashed in a draft cutscene because of an unbounded apply loop. That was fixed and the knob stays off by default.

## Not measured

Other GPUs and machines, per-frame percentiles above the 1 percent low, whether the lineup-card frames are read back by the CPU.
