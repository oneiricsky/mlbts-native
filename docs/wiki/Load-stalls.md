Where the time goes when the game loads something, measured on the 0.2.0 merge with the harness match (AI against AI, Toronto at Los Angeles), on one PC with the PS5 texture dump on an 8 TB hard disk and the repo and game files on an SSD.

There are four separate stalls, and only one is caused by the fork.

| # | Stall | Size | Cause | State |
|---|---|---|---|---|
| 1 | Lineup card | about 64 ms now, was 555 ms | The forced lighting bake, removed by upstream's walk-up patch (inferred) | Gone in 0.2.0 |
| 2 | Head textures with PS5 textures on | 200 to 670 ms frames, cold file cache only | The PS5 file was read from the hard disk on the replay thread | Fixed, in `main` |
| 3 | Match start, once | 1.4 to 1.6 s frame | The game's own CPU work: grass tiles plus a 512x512 distance-field render | MSDF part fixed, in `main`; see [Match-start freeze](Match-start-freeze) |
| 4 | Match start, a few frames | 140 to 250 ms | A burst of 52 GPU waits, shader loading, a UI event wait | Counted, not investigated |

## Cold file reads

Reading the 58 colour-map files of a match (the part of each file the loader keeps, 0.67 MiB):

| Read | Median | Total |
|---|---|---|
| Cold (never read since boot) | 15.2 ms | 998 ms |
| Warm (in the system cache) | 0.25 ms | 15 ms |

`hd_apply` read the file on the replay thread at the texture's first upload, so a batch of new heads cost their cold reads in one frame. The game opens each head's Switch files long before the texture is first uploaded:

| Gap | Seconds |
|---|---|
| minimum | 1.7 |
| median | 23 |
| maximum | 122 |

That is about 100 times a cold read, so a read started at the open is done long before it is needed.

The fix: when the game opens `NSW/CHARACTERS/HEADS/<NAME>/<NAME>-COLOR.TEX` or `-NORMAL.TEX`, a hook hands the matching PS5 file to one low-priority background thread, which runs the normal loader and throws the result away. That pulls the file into the system cache. Setting `MLB_HD_PREFETCH`, default on.

Loads is the slowest single demand load and the total for the first 64. Upload lists the frames with 50 ms or more of texture upload.

| Run | Prefetch | Loads | Upload |
|---|---|---|---|
| c1 | off | 28.5 ms / 841 ms | 668 (631 upload), 292, 251, 196 ms |
| d2 | off | 27.1 ms / 670 ms | 447 (415), 305, 239 ms |
| d4 | off | 26.5 ms / 881 ms | 492 (454), 203 ms |
| d1 | on | 0.7 ms / 26 ms | none |
| d3 | on | 0.6 ms / 29 ms | none |

To get cold files without admin rights, a script made a folder of hard links in which each of the match's 60 heads points at the data of a head nobody had read.

## Match-start CPU work

One frame of 1.4 to 1.6 s at match start. The game logs the cause itself just before it: "grass tiles generated in 172 to 177 ms" and "MSDF took 775 to 968 ms". The replay thread is busy 100 to 154 ms in that frame, uploads 5 to 11 ms, waits under 15 ms, so this is CPU work in the lifted game code on the main thread. A sampler profile showed no single hot function.

## Untraced frames

Frames of 100 ms or more besides the above, from a 230 s run: 245 ms at frame 1127 (a 52-wait GPU burst at the Pitch History and Pitch Meter initialisation), 186 ms at frame 432 during "Loading shader" lines, 171 ms at frame 3 (a first-frame fence wait), 138 ms at frame 1474 (an event wait while the game allocates UI nodes).

## Open questions

One PC, one hard disk; a different disk changes the size of stall 2, not its cause. "Cold" means not read since boot. The prefetch result is three runs off and two on, one window each. The 555 ms lineup stall's old cause is inferred from the matching shape, not traced.

## Rejected options

Loading everything or a local pack file (the lead time is seconds and the read is 15 ms), remembering the last teams, swapping the PS5 image in later, forcing a cold cache with a memory hog, PGO for the game's own code (upstream's release must not carry it), caching the MSDF texture (too invasive for about 1 s once per match).
