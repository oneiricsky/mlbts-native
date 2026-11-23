At match start the game freezes for about 0.7 s while it draws a map of the field's edges. A code patch on the `research/msdf-skip` branch cuts that step to about 0.19 s. It is not merged into `main`.

## In plain words

The game builds a 512x512 picture in which each pixel says how far it is from the nearest edge of the field (the msdfgen step, MSDF for short). It then runs an error-correction pass over that picture to look for pixels that are wrong.

Most of the picture is empty space. Before the pass starts, 97.1 percent of the pixels hold plus or minus infinity in all three channels, which only means "inside" or "outside" with no distance. Only 2.9 percent (7,506 pixels) hold real distances. The pass still visits every pixel and computes `(a - 0.5) / (a - b)` for neighbours. With infinite inputs that is infinity minus infinity, which is not a number (a NaN). A NaN fails the "is there an edge here" test, so the answer for every empty pixel is "nothing to fix". The game spends most of the step proving that empty space has no edges.

It makes about 67 to 70 million NaN results per match start. About 18.4 million are born as `inf - inf`; the rest are those NaNs carried through later arithmetic. They come from the game's own data, not from a mistake in the port.

## The fix

A code patch set `msdf_skip`: at main+0x311a0 the pass already skips a flagged pixel, and the patch makes it also skip a pixel whose three channels are all infinite. It is 19 instructions using only free registers (x10 to x13). Setting `MLB_MSDF_SKIP`, default on, with a menu row "Shorter freeze at match start".

The functions are `f_7000030ec0` (the pass) with `f_7000031e70`, `f_7000033530`, `f_70000339a0` and `f_70000336bc`. The step is driven from `f_7000095390`, which logs "MSDF took ...".

## Numbers

Dodger Stadium, six runs of 35 s, alternating off and on: the MSDF step took 683, 706 and 673 ms with the skip off (mean 687) and 166, 221 and 182 ms with it on (mean 189).

Baltimore (BAL home, BOS away), four runs of 40 s: 723 and 727 ms off (mean 725), 187 and 186 ms on (mean 187).

The finished 512x512 field texture is byte for byte identical with the skip off and on, on both stadiums: all 1,048,576 bytes, same SHA-256 (Baltimore's starts 5f450eca81b5). The two stadiums give different pictures, so the team override really changed the stadium.

The grass step (about 155 ms) is unchanged.

## What is not proven

Two stadiums, each at the default time of day and weather. Reading the guest code showed the pass marks a pixel only through two classifier calls; the divide-based range tests give NaN for an infinite pixel whatever its neighbours hold, but a range test can pass for an infinite pixel and one classifier then checks the real stadium outline, which cannot be worked out offline. So identical output is shown for two stadiums, not for all. Still to do: more stadiums, times of day and weather, a whole match, and game 1.0.15.

The first run in a newly copied game folder took 37 s to reach the field picture; the next three took 22.5 s. The MSDF step itself did not change, but never take timing from a slot's first run.

## Related

The float fix-up on `research/float-fixup` made each NaN cheaper (702 to 525 ms). Once the NaNs are gone it matters much less; measure it again before merging.
