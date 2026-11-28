# Report: frame dips and hitches

Status: the dips caused by my own diagnostics are fixed (they were never in `main`). Upstream's 0.2.0 fixed the
per-pitch freeze after this report was written; see "Update after merging 0.2.0" below. The lineup-card stall and the
load stalls are still open.

## 1. Cutscene dips of 25 to 45 fps

Cause: four `getenv()` calls per `get_view` call in temporary diagnostics, reached on each descriptor-memo miss (about
1,000 per frame, about 10 microseconds each, about 12 ms per frame). With the values cached, `get_view` costs about
0.06 microseconds per call and the cutscene interval is 16.6 ms (60 fps) against 24.3 ms uncached.
`main` never had the calls. Rule kept: no env or config lookups in per-draw or per-call paths, even in diagnostics.

A 6.5 minute harness run on clean code: 59 fps mean, VRAM flat at 2.6 GB, RAM flat.

## 2. Per-pitch hitch (about 190 ms; fixed upstream in 0.2.0)

This section is the analysis as written before the 0.2.0 merge. Its conclusion that the waits were inherent was wrong.

About 21 per 6.5 minute run, 175 to 205 ms each, at WALK_UP_PRES, SELECT_PITCH and PLAYERS_SETUP. Pipeline builds,
translation, texture uploads and fences were all zero in those windows.

The game submits a command buffer, spins until the GPU is idle, then submits again. The spin is `f_70005a1a90`
(`work/gen/main/main_0043.c:40807`): it waits until an event counter reaches the last submitted count (63 call
sites). A pitch burst is about 53 to 55 of these waits of about 4.4 ms each.

Per wait: about 0.8 ms game packaging, about 1.5 ms port recording, about 1.7 ms GPU, about 0.4 ms for the done
signal to arrive. The relight dispatches are dependent (each reads the 24-layer probe array the previous one wrote),
so batching them or rewriting the loop is not an option.

## 3. Lineup card stall (about 555 ms)

`PresIntroStartingLineup`, about 5 minutes into a harness run. 25 to 26 lock-step waits, each submission 44,000 to
48,000 commands: about 13.6 ms recording plus about 8.5 ms GPU and latency, about 22 ms per wait.

A draw log shows each submission is a full frame: 1024x1024 (two) and 512x512 / 256x256 depth passes, 1440x810 scene
passes interleaved, a 1920x1080 post pass. The picture presented is the SHOW NETWORK intro graphic. A GPU-write check
found about 930 writes into guest memory per card submission (about 4.1 MB; 71 from shaders, 52 texture writes),
against about 350 for a normal 9,400-command submission. So the results are not shown to be unused, and signalling
early or skipping these submissions was not attempted.

## 4. Things that did not work

- Compute descriptor bind-skip: no effect (record 4.70 against 4.69 ms per wait, replay end 9.20 against 9.20 ms,
  mean frame 16.92 against 17.02 ms). Most compute layouts use push descriptors and the push skip is graphics-only, so
  the change did nothing. Dropped.
- An early-signal knob (`MLB_EVENT_GPU`) once crashed in the draft cutscene because of an unbounded apply loop; that
  was fixed by applying in order, and the knob stays off by default. Every waited submission carries one event signal
  and two counter reports, so any early signal must not skip counter reports.

## 5. Loading stalls

Stalls of 1.3 to 1.6 s (around frames 994 and 1016) are the game's main thread blocked in a kernel service call
during asset loading. They are on the game side.

## Update after merging 0.2.0

Upstream's 0.2.0 (commit 59e77de, 2026-11-21, "fix: no freeze before each pitch (walk-up lighting) or at inning changes") fixed the
per-pitch freeze. Before every pitch the game baked its time-of-day lighting again in one frame, about 50 scene passes
with a GPU kick and a wait each, although it had just baked the same time in the background after the last play.
Upstream patched the game's code so it asks for the lighting unforced (`tools/data/patches-1.0.20.txt`, settings
`WALKUP_LIGHT` and `WALKUP_LEADERS`, on by default; cause and measurements are in `docs/walkup-freeze.md`). The 53 to 55
waits measured in section 2 were that bake. We tried to make the waits cheaper and did not ask why the game was doing
the work.

Measured on the merged build (400 s harness runs, one run per setting, windows 2 to 6):

| | Textures off, before | Textures off, merged | Normal + colour, before | Normal + colour, merged |
| --- | --- | --- | --- | --- |
| Frames over 100 ms per minute | 3.2 | 0.2 | 4.4 | 0.6 |
| Frames over 50 ms per minute | 4.4 | 1.0 | 6.0 | 2.6 |

The worst-frame entries in the 150 to 260 ms band went from 17 and 24 (of 30) to 4 and 2. With colour maps on, the
merged build had more frames over 25 ms (30.6 per minute against 23.8) and a slightly lower 1% low (42.8 against 44.2
fps); with one run each that may be noise.

Still open: the lineup-card stall (the merged colour run had one 724 ms frame there; it may be the same kind of
redundant work, which has not been checked) and the 1.3 s load stall near frame 1000. With one run per setting the
numbers are not firm.

## Possible next steps, in order of risk (written before 0.2.0; steps 1 to 3 are superseded for the per-pitch hitch)

1. Logging-only check of which waited submissions write results the CPU later reads.
2. A default-off early-signal knob for submissions that pass step 1.
3. A lower relight step count (visual check needed).
4. A second GPU lane, or spreading steps over frames, only as a last resort.

## Not measured

Whether the lineup-card frames are read back, and what the per-pitch relight does when the step count is lowered.
Other machines and GPUs: all numbers are from one RX 6700 XT.
