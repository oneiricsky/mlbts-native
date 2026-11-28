# Load stalls in the merged build

Where the time goes when the game loads something, measured on the 0.2.0 merge ("chore: use the fastball marker in the comments our edits added", 2026-11-22) with the harness match
(AI vs AI, TOR at LAD), on one PC (RX 6700 XT, PS5 dump on an 8 TB hard disk, repo and game files on an SSD).

## Summary

There are four separate stalls, not one. Only one of them is caused by this fork.

| # | Stall | Size | Cause | State |
| --- | --- | --- | --- | --- |
| 1 | Lineup card (the old 555 ms one) | now about 64 ms | the game's forced lighting bake, removed by upstream's walk-up patch (inferred, see below) | gone in 0.2.0 |
| 2 | Head textures with PS5 textures on | 200 to 670 ms frames, only on a cold file cache | the PS5 file is read from the hard disk on the replay thread at upload | fixed on this branch |
| 3 | Match start, once | 1.4 to 1.6 s frame | the game's own CPU work: grass geometry plus a 512x512 distance-field render | not fixed |
| 4 | Match start, a few frames | 140 to 250 ms | a burst of 52 GPU waits, shader loading, a UI event wait | not investigated further |

## Cause

### 1. The lineup card

Before the merge the lineup card ran 25 to 26 full-scene frames back to back, each waited on, about 555 ms in all
(`docs/reports/2026-11-22-gpu-wait-hitches.md`). After the merge, with PS5 textures off, the frame that enters
`PresIntroStartingLineup` is 64 ms (run `ls1`, frame 7034) and 60 ms in the merge agent's run (`N1`, frame 7025).

Upstream's walk-up patch stops the game from forcing a second bake of the stadium lighting; the old card did about 50
full-scene passes with a GPU kick and wait each, which is the shape of that bake. That the card was the same bake is
an inference from the two matching shapes and the before and after sizes. It was not traced with the lighting
manager's fields as upstream did for the walk-up.

### 2. PS5 textures: cold reads on the replay thread

The PS5 dump is on a hard disk. Reading 58 colour-map files (the part of each file the loader keeps, 0.67 MiB):

| | median per file | total for 58 |
| --- | --- | --- |
| cold (never read this boot) | 15.2 ms (p90 29.1, max 33.2) | 998 ms |
| warm (in the system cache) | 0.25 ms | 15 ms |

`hd_apply` reads the file on the replay thread at the texture's first upload, so a batch of new heads costs their cold
reads in one frame. The merge agent's colour run (`N2`) had a 724 ms frame at the lineup card with 687 ms of texture
upload, and 311, 121 and 108 ms frames elsewhere; the same match with PS5 textures off (`N1`) had none of these
(60 ms at the card). In a run on a warm cache (`ls2`) the lineup frame is 70 ms and no frame has more than 14 ms of
texture upload. The stall exists only when the files are cold: the first match after a boot, or after the cache has
been used for other things.

The game opens each head's Switch files long before the texture is first uploaded. In the file-open trace of a harness
match (`ls3`, the 38 swaps among the first 64 that the log keeps):

| open to first swap | seconds |
| --- | --- |
| minimum | 1.7 |
| median | 23 |
| maximum | 122 |

That is 100 times longer than a cold read, so a read started at the open is finished long before it is needed.

### 3. Match start: the game's own CPU work

One frame of 1.4 to 1.6 s at match start (frames 1016, 1052, 1743 in three runs; the frame number moves with pacing).
The game logs the cause itself in the lines just before it:

- `grass tiles generated in 172 to 177 ms`
- `MSDF took 775 to 968 ms for 512x512`, with `msdfgen (MSDF) = 775 to 900 ms` of it

In that frame the replay thread is busy 100 to 154 ms, texture upload is 5 to 11 ms, and fence and pacing waits are
under 15 ms. So it is CPU work in the lifted game code on the game's main thread, not file reads, uploads or the GPU.
The sampler on the main thread over frames 850 to 1500 shows no single hot function: the guest code is spread flat,
with the float-to-integer helpers `sfix_s` and `sfix_d` at about 5 % of samples. Nothing here was changed.

### 4. The other match-start frames (PS5 textures off)

From the 230 s run `ls1`, the frames of 100 ms or more besides the one above: 245 ms at frame 1127, where the log
shows a "game GPU wait burst: 52 waits over 867.5 ms" at the Pitch History and Pitch Meter initialisation; 186 ms at
frame 432 during "Loading shader ..." lines (pipeline and translation counters are zero, so it is the game's own
work); 171 ms at frame 3 (a 169 ms fence wait at the first frame); and 138 ms at frame 1474, a 113 ms event wait while
the game allocates UI nodes. These were counted but not traced further.

## Sites

- `runtime/mlb/hdtex.c`: `mlb_hd_load` (the file read), `hd_apply` in `runtime/gfx/vk_texture.c` (the caller, on the
  replay thread).
- `runtime/core/fs_host.c` `open_file`: where the game's RomFS opens pass through.
- The log lines used: `perf: slow frame`, `frametime: worst frame`, `hdtex: texture ... ms`, `fs read FS_Rom:/NSW/...`.

## The change (branch `research/load-stall`)

When the game opens `NSW/CHARACTERS/HEADS/<NAME>/<NAME>-COLOR.TEX` or `-NORMAL.TEX` for reading, the file layer calls a
hook (`rt_host_opened`, a weak function like the existing `rt_host_wrote`). `hdtex.c` looks up the PS5 file of the same
name in the index and hands it to one background thread (below-normal priority), which runs the normal loader and
throws the result away. That pulls the file into the system cache, so the upload's own read takes about 0.5 ms.
Each file is queued once. The setting is `MLB_HD_PREFETCH` (default on; `0` turns it off) and, like every row in
`cfg.c`, also a command-line flag.

What else changes: one extra thread; the loader allocates and frees about 0.7 MiB per file on that thread; PS5 files
of heads the game opens but never draws are read once for nothing. Nothing else in the replay or upload path moved.

## How it was checked

Cold runs need files that have not been read. For each run a script (`work/scratch/build_cold_root2.py`, not in the
repo) made a folder of hard links in which each of the match's 60 heads (179 index entries) points at the data of a
head nobody had read, of the same file shape, so the index, hashes and names stay real. Runs alternated prefetch off and
on, 170 s each, `MLB_TRACE=perf`, sampler off. "Demand loads" are the `hdtex: texture ... ms` lines the game logs for the
first 64 swaps.

| run | prefetch | demand loads: max / total | frames with 50 ms or more of texture upload |
| --- | --- | --- | --- |
| c1 (full 7,116-entry index) | off | 28.5 ms / 841 ms | 668 (631 upload), 292, 251, 196 ms |
| d2 | off | 27.1 ms / 670 ms | 447 (415), 305, 239 ms |
| d4 | off | 26.5 ms / 881 ms | 492 (454), 203 ms |
| d1 | on | 0.7 ms / 26 ms | none |
| d3 | on | 0.6 ms / 29 ms | none |

With prefetch on the background thread's own reads took 9 to 21 ms each (cold, as expected) and the replay thread
never saw them. No hdtex errors and no crash in either on run. Over a full window (frames from minute two) the on runs
had 0.0 and 0.0 frames over 100 ms per minute and the off runs 1.0, 0.0 and 2.0; with one window each that is not a
frame-rate result, only the texture-upload column is.

## Considered and not taken

- **Loading everything or a local pack file.** Not needed: the lead time is seconds and the read is 15 ms.
- **Remembering the last teams, or detecting the game mode.** Same reason.
- **Swap in the PS5 image later, when its read finishes.** Would also remove the read from the upload, but needs a
  poll hook and a texture-lifetime story. The prefetch gets the same result with no change to the texture code.
- **Forcing a cold cache with a memory hog or by emptying the standby list.** Needs admin or pushes the other programs
  out of memory. Hard links to unread heads were enough.
- **PGO or higher optimisation of the game's lifted code for the MSDF stall.** Upstream says game code never gets a
  profile ("a release must not carry" it). Not tried.
- **Caching the MSDF texture.** The result is a pure function of the stadium, but a cache means writing a texture back
  into guest memory by hash; too invasive for what it saves (about 1 s once per match).

## Not proven

- One PC and one hard disk. A different disk changes the size of stall 2, not the cause.
- "Cold" here means files not read since the machine started; the drive's own cache can still hold some of them. A full
  power-cycle was not tried. The measured 15 ms per file matches the earlier measurement, so the runs are cold enough.
- The prefetch result is three runs off and two on, one window each. The size of the stall frames varies a lot
  (200 to 670 ms), but with prefetch on there was none in either run.
- The 555 ms lineup stall's old cause is inferred (section 1).
- The 8 to 10 s frame at frame 14 seen once before the merge did not appear in any run made here.
- The hot spot of stall 3 was not isolated.
