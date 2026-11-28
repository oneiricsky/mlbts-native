# Report: performance of PS5 textures (normal maps and colour maps)

Status: measured on one machine; no slowdown found in steady play. Recommendation at the end.

These numbers are from the build before the 0.2.0 merge (2026-11-22). Upstream's 0.2.0 removed the per-pitch freeze, so
the per-pitch figures below describe the old build; the merged build's numbers are in
[2026-11-22-gpu-wait-hitches.md](2026-11-22-gpu-wait-hitches.md) ("Update after merging 0.2.0").

## What was compared

Three configurations on the dev harness (AIvAI, GameOnly, TOR at LAD), each run twice, 400 seconds a run (6 one-minute windows,
about 21,000 frames), one game at a time, same build (the one with the compute fix of 2026-11-22, no diagnostics):

| | Setting | Index entries |
| --- | --- | --- |
| A | `MLB_HD_TEXTURES=off` (Switch textures only) | 0 |
| B | the shipped all-heads normal-map index | 2,370 |
| C | all heads, normal and colour maps (`make_hd_index.py --all-heads --color`) | 7,116 |

## Method

- Frame times come from the game's own once-a-minute summary (`frametime: 60 s: ...` in the log): frames, mean fps, 1 % low fps and
  the counts of frames over 25, 50 and 100 ms. There is no per-frame log in a clean build, so percentiles above the 1 % low (p99.9 and so
  on) are not available. The "worst frame" lines give the longest frame of each window.
- RAM (working set and private bytes) and GPU memory (the Windows "GPU Process Memory, Dedicated Usage" counter for the game process)
  were sampled every 10 seconds from outside the game (`work/scratch/memsample.ps1`).
- HD load cost comes from the `hdtex: texture ... ms` log lines (the game logs the first 64 only).
- No screenshots were taken during the timed runs. A separate run of C took 101 screenshots for a yellow-face check
  (`work/scratch/ycount.py`, which counts the blown yellow-orange pixels).

## Results

| | A (off) | B (normal maps) | C (normal + colour) |
| --- | --- | --- | --- |
| mean fps, run 1 / run 2 | 59.2 / 59.1 | 57.5 / 59.0 | 58.9 / 57.4 |
| mean fps without the boot stall (see below) | same | 58.9 / 59.0 | 58.9 / 59.0 |
| 1 % low fps (median of the six windows), run 1 / 2 | 45.5 / 44.0 | 45.5 / 43.7 | 44.2 / 42.4 |
| frames over 50 ms, run 1 / 2 | 29 / 27 | 40 / 33 | 39 / 33 |
| frames over 100 ms, run 1 / 2 | 21 / 23 | 30 / 26 | 29 / 24 |
| longest per-pitch hitch | about 205 ms | about 210 ms | about 205 ms |
| RAM working set, steady / peak | 3.77-3.78 / 3.78 GB | 3.77 / 3.77 GB | 3.77-3.78 / 3.78 GB |
| GPU dedicated memory, steady / peak | 2,651-2,652 MB | 2,651-2,652 MB | 2,651 MB |
| swaps logged (first 64 only) | 0 | 58 | 64 (32 of them colour) |
| load time of the swaps, cold file cache / warm | n/a | 813 ms / 30 ms | 487 ms / 33 ms |
| slowest single load | n/a | 33 ms | 33 ms |
| hdtex errors, cannot open, not handled | 0 | 0 | 0 |
| blown-yellow shots, of 101 | n/a | n/a | 0 (peak 101 pixels, against 4,565 unfixed) |

Reading the table:

- **Frame rate:** about 59 fps in every configuration once the boot stalls are set aside. The run-to-run spread in A (0.1 fps) is
  smaller than the spread in B and C, but those are the two runs that contain a boot stall.
- **1 % low:** about 1 to 2 fps lower with HD textures (A about 44.8, B about 44.6, C about 43.3), roughly the size of the repeat spread
  within one configuration.
- **Hitches:** the HD runs have a few more frames over 100 ms than the baseline: A 21 and 23, B 30 and 26, C 29 and 24, so about 4 to
  6 more in six minutes (about one a minute). The ranges nearly touch, so this may be noise, but it is the one place a difference might be real.
  The long hitches are not longer: the per-pitch bursts (about 175 to 205 ms) and the lineup-card stall (frames near 6,000 to 6,400,
  180 to 215 ms) look the same in A, B and C. The GPU wait-burst diagnostic is not in a clean build, so the 25 to 26 waits of the card
  were not counted separately.
- **Memory:** no growth in RAM or in GPU memory. The extra HD images are small (about 0.7 MiB each, about 45 MB for 64 of them) and fit in
  the device memory blocks the renderer allocates ahead (256 MiB at a time), so the OS counter does not move.
- **Load cost:** the PS5 files are read once per head when it is first used. With a cold file cache that was 0.5 to 0.8 s in total over the
  first 58 to 64 heads, at most 33 ms for one file; with the files cached it was about 30 ms in total. No load stall was seen from the
  slow E: drive.

## Boot stalls

Two of the four HD runs (B1 and C2) had one 8.4 s and one 10.1 s frame at frame 14, right at start-up. None of the translation, pipeline,
upload, replay or wait timers had any of it, so it happened before any rendering work, and the baseline runs did not have it.
Six more start-up-only runs (three A, three C, 75 s each) showed no such stall, only the game's usual loading stall of about 1.3 to 1.4 s
near frame 1,000. The cause was not found, and with this few runs it cannot be called an HD effect or ruled out.

## Yellow-face check on C

With the all-heads colour index and the compute fix (`docs/reports/2026-11-22-yellow-face-ps5-colour-maps.md`), 0 of 101 shots were flagged; Ohtani and the catcher looked natural in the
contact sheet. Only a handful of faces were looked at; the 2,300 other heads were not.

## Not measured

- Other GPUs (all numbers are from one RX 6700 XT), other stadiums, matches longer than six and a half minutes, other modes.
- Per-frame percentiles above the 1 % low.
- GPU wait bursts and the lineup-card stall as counted waits (diagnostic not in the clean build).
- Whether the boot stall is related to the HD textures.
- Colour maps on heads other than the few looked at, and 2048-pixel colour maps.
