At match start the game freezes for about 0.7 s while it draws a map of the field's edges. A code patch cuts that step to about 0.19 s. It has been in `main` since 2026-11-26 (commit `ec0370d`), for game 1.0.20.

## Overview

The game builds a 512x512 picture in which each pixel says how far it is from the nearest edge of the field (the msdfgen step, MSDF for short). It then runs an error-correction pass over that picture to look for pixels that are wrong.

Most of the picture is empty space. Before the pass starts:

- 97.1 percent of the pixels hold plus or minus infinity in all three channels, which only means "inside" or "outside" with no distance.
- Only 2.9 percent (7,506 pixels) hold real distances.

The pass still visits every pixel and computes `(a - 0.5) / (a - b)` for neighbours. With infinite inputs that is infinity minus infinity, which is not a number (a NaN). A NaN fails the "is there an edge here" test, so the answer for every empty pixel is "nothing to fix".

It makes about 67 to 70 million NaN results per match start. About 18.4 million are born as `inf - inf`; the rest are those NaNs carried through later arithmetic. They come from the game's own data, not from a mistake in the port.

## Fix

A code patch set `msdf_skip`: at main+0x311a0 the pass already skips a flagged pixel, and the patch makes it also skip a pixel whose three channels are all infinite. It is 19 instructions using only free registers (x10 to x13). Setting `MLB_MSDF_SKIP`, default on, with a menu row "Shorter freeze at match start".

| Function | Role |
|---|---|
| `f_7000030ec0` | the error-correction pass |
| `f_7000031e70`, `f_7000033530`, `f_70000339a0`, `f_70000336bc` | its helpers; the last two are the classifier calls that mark a pixel |
| `f_7000095390` | drives the step and logs "MSDF took ..." |

## Measurements

Timing, the MSDF step in ms, runs alternating skip off and on:

| Stadium | Runs | Off | On |
|---|---|---|---|
| Dodger Stadium (LAD home, TOR away) | 6 of 35 s | 683, 706, 673 (mean 687) | 166, 221, 182 (mean 189) |
| Baltimore (BAL home, BOS away) | 4 of 40 s | 723, 727 (mean 725) | 187, 186 (mean 187) |

Output, the finished 512x512 field texture (format 0x25), skip off against on:

| Stadium | Bytes | Differing | Sum | SHA-256 |
|---|---|---|---|---|
| Dodger Stadium | 1,048,576 | 0 | 147739026 | starts 7a11da1b54bb16d3 |
| Baltimore | 1,048,576 | 0 | 127082744 | 5f450eca81b533dcc436c911e5fb081f35641ccc7170588480f6d55a3bc4e6a0 |

The two stadiums give different pictures, so the team override really changed the stadium. The grass step (about 155 ms) is unchanged.

## Open questions

Identical output is shown for two stadiums, each at the default time of day and weather, and not for all.

Reading the guest code showed the pass marks a pixel only through two classifier calls. The divide-based range tests give NaN for an infinite pixel whatever its neighbours hold. A range test can still pass for an infinite pixel, and one classifier then checks the real stadium outline, which cannot be worked out offline.

Still to do: more stadiums, times of day and weather, a whole match, and game 1.0.15.

The first run in a newly copied game folder took 37 s to reach the field picture; the next three took 22.5 s. The MSDF step itself did not change, but never take timing from a slot's first run.

## Related work

The float fix-up (`MLB_FP_FIXUP`, default on) made each NaN cheaper (702 to 525 ms, measured without this patch). It reached `main` in the same commit, `ec0370d`, and was not measured again there. With the NaNs gone it should matter much less; that still needs measuring.
