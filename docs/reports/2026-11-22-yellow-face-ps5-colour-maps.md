# Report: yellow faces with PS5 colour maps

Status: FIXED for the heads checked (commit b4a839e). PS5 colour maps stay opt-in in the index tool until more heads are looked at.

## Resolution (2026-11-22)

A compute shader (cache key 5acda9c0, dispatch 23x10 groups of 8x8) runs when a head is shown. It reads the colour map at binding 1 with an integer
`texelFetch` over a rectangle given in the Switch texture's texel coordinates, gated by a mask from another texture, and queries the size it
normalises the mask lookup by. It sums the masked pixels into a skin-tone average that the lit face shaders later divide by. On a 1024x512
image the game's rectangle is the wrong quarter of the map, so the average is wrong and the albedo blows out. Found by logging which binding
each reader uses and disassembling the compute shader (an independent second opinion reached the same mechanism).

Fix: while a compute dispatch is recorded, a PS5 image is bound from the level that has the Switch texture's size (`hd_shift`); fragment shaders
keep the large level. Result: 0 of 101 harness shots show blown colour (no fix: 50); Ohtani's and Springer's faces are natural with skin detail.
The earlier conclusion in this report that every reader group needs the small level was wrong: it came from comparing runs whose readers were
shifted in combination, and only the compute group needs it.

Not checked: other heads, the 2048 level, other categories.

---

The rest of this report is the investigation record up to the point the cause was found.

## Problem

Swapping a head's Switch colour map for the PS5 one at upload (`hd_apply`, `runtime/gfx/vk_texture.c`) makes the face
bright yellow-orange and flat in the lit scenes. It happens at 2048x1024 and at 1024x512. A PS5 map cut to the Switch's
own size (512x256) renders normally. PS5 normal maps do not have the problem and ship for 2,370 heads.

## Setup used to look at it

- Dev harness: `AIvAI`, `GameOnly`, TOR at LAD, Ohtani pitching. `MLB_SHOT=<frames>` saves pictures.
- Test index: Ohtani's colour map only, 1024x512 (drop 1 from the 2048 file).
- Baseline: `MLB_HD_TEXTURES=off`. In the sunlit scene of Ohtani on the mound his face is a natural tan in shade.
- Run pacing differs by hundreds of frames between runs, so frame numbers cannot be compared across runs.

## What is established

1. The face's colour sampler has no mip filter, so the shaders read only the first level of the view.
2. In earlier runs, starting the view at the second level, or filling only the first level with one skin block,
   removed the yellow. All levels one block, a UNORM view, alpha forced to one and a mip-filtered sampler did not
   change anything.
3. The PS5 levels have the same mean colour, alpha and BC7 block modes as each other.
4. A patched face fragment shader that outputs the raw colour sample shows normal skin with the first level exposed.
   The blow-up is after the sample, in the lighting terms: the albedo is the colour times a value built from other
   inputs, and those terms saturate only when the first level is exposed.
5. Four fragment shaders read the colour map (logged by input id, `[hdview]` diagnostic):
   - `0842012c054ab3e9`: a small shader with explicit level 0, run when a head is shown (the bake).
   - `a11d58f0ed0070d1`: the second small level-0 shader seen in earlier runs (not logged in the latest run).
   - `93e02c04e8629d26` and `db0de8cde73bba62`: rarely used, so probably more bake passes.
   - `0d34f3aedaae8131` and `23a1dc9aaca6e3df`: used on most frames, probably the lit face passes.
   Only about 3 draws per frame bind the colour map.
6. A rule that gives only the bake shaders the Switch-size level (a view shifted by one level, per draw) fires
   correctly, but the sunlit close-up of Ohtani stays yellow-orange.
7. New this session: switching the colour map's view between the full level and the shifted level every 20 frames in
   one run (all shaders, then none, then various subsets) did not change the face at all, although the shift was
   confirmed applied (shifted count equals total view count in the shifted intervals). The face looked equally bright
   in both. So the live per-frame view of the colour map does not decide the yellow in that scene.

## Result of the fixed-from-frame-0 runs (2026-11-22, second pass)

Event-aligned capture did not work: the game's intro camera cuts differ between runs even at the same offset from the
same event (the lit face shader's first draw), so scenes do not line up. Two things replaced it:

- Runtime toggling of a mode mid-run (the earlier `[cyc]` runs) is discarded: the head-show bake keeps what it first
  computed, and the results were inconsistent with the fixed runs.
- Each configuration is now fixed from frame 0, with one shot every 10 frames from 2850 to 3850 (101 shots per run),
  and a scene-independent count of blown-yellow skin pixels (R above 225, G/R 0.78 to 0.92, B/R 0.38 to 0.62, outside
  the stat panel; more than 1,500 flags a blown face). It was checked against a face-to-jersey luminance ratio:
  natural faces 0.45 to 0.58, blown faces 0.86 to 0.94.

Timeline per run, one character per shot from frame 2850 (`.` natural, `+` borderline, `#` blown):

| Configuration | Shots flagged blown |
| --- | --- |
| PS5 colour map off | 0 of 101 |
| no fix | 52 of 101 |
| every reader shifted to level 1 (512x256) | 9 of 101, all in the first 90 frames, none after |
| only `0d34f3ae` shifted | 25 of 101 |
| `0d34f3ae` plus the four bake shaders shifted | 41 of 101 (up to about frame 3380) |
| every fragment shader except `23a1dc9a` shifted | 0 until about 3400, then blown to the end |
| `0d34f3ae`, the four bake shaders and every read that has no fragment shader (compute/blit) shifted; `23a1dc9a` and anything else left at the full level | 0 of 101 |
| reads without a fragment shader shifted, nothing else | 0 flagged blown, 48 borderline (the baseline has 10) |

What this says:

- Three groups of readers each go wrong when they see the 1024x512 base level: the main lit pass `0d34f3ae…`, the bake
  fragment shaders (`0842012c…`, `a11d58f0…`, `93e02c04…`, `db0de8cd…`) and the reads that happen outside a
  fragment shader (compute or blit passes). Shifting any two of the three is not enough.
- The only reader that can keep the full level is `23a1dc9a…`, and it is rare: about 1,000 reads against about 6,000
  for `0d34f3ae…` in the same run. So there is no useful gain: the visible face reads the 512x256 level of the PS5
  file. That is the known workaround, now confirmed for each reader, not a fix.
- None of the four face fragment shaders has a derivative or an image-size query on the colour map's binding, so
  the earlier idea that the shader measures the texture's high-frequency detail does not hold for them.

Because every kind of reader breaks, the cause is more likely in the base level itself (its decoded content or how it
is laid out and uploaded) than in one shader's maths.

## Not done / not verified

- Nothing in `main` changes. Colour maps stay opt-in.
- The counter is a pixel-colour rule; it was checked against the baseline and against ratio measurements, not against
  a per-pixel reference. The face-to-jersey measure only works on close-ups, where the locator finds the cap.
- Only Ohtani's colour map was tested.
- No run decodes level 0 on the CPU and compares it with level 1. That is the next test.

## Next steps

1. Decode level 0 and level 1 of Ohtani's PS5 colour map on the CPU and compare them (downsample level 0 and compare
   with level 1, look at block mode usage and edge blocks), and dump level 0 as a picture.
2. Check the upload of level 0 in `hd_apply` (`runtime/gfx/vk_texture.c`): row length and image height per level, the
   strip layout of the largest level, and whether level 0 needs different padding from the others.
3. If level 0 decodes correctly, test an image whose level 0 is a CPU downsample-then-upsample of level 1 (so the
   content is smooth but the size is 1024x512) to separate content from size.

## Where the experiment lives

`git stash` entries on `main` hold the shader-matching rule (`hd_shift`, `cur_bake`, `hd_bake_fs`), the `[hdview]`
log and the `[cyc]` run-time mode cycling. The committed notes are in `docs/ps5-textures.md`.
