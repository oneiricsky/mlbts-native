# Report: yellow faces with PS5 colour maps

Status: open. Not fixed. PS5 colour maps stay out of the default index (`make_hd_index.py --color` adds them).

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

## Reading of the evidence

The yellow seems to be fixed in a value computed earlier and kept, probably by the bake passes when the head is first
shown, using the colour map as it was then. A live view shift cannot undo that. Whether the bake shaders alone explain
it is not shown: the bake-only rule did not clear the close-up, and no run has yet kept the shifted view for all
shaders from the first frame of the head show and compared against the baseline in the same scene.

## Fixed-mode runs (same scene, sunny shot of Ohtani, frames 3000 to 4000, one run per mode)

Compared by eye on matching crops, so treat as indicative:

| Mode (set from the first frame) | Face |
| --- | --- |
| PS5 colour map off | natural tan |
| every shader reads the shifted level (512x256) | natural, close to the baseline |
| only the two known bake shaders shifted | blown out, near-white yellow |
| every shader shifted except the two main lit ones | better, still warm orange |

This fits the "baked at head show" reading: the two extra bake candidates (`93e02c04…`, `db0de8cd…`) matter, and
something in the two main passes adds more warmth. The all-shifted mode is not a fix: level 1 of the PS5 file is the
Switch's size, so there is no gain. It is the known workaround. Modes that expose only one of the two main passes
(all shifted except `23a1dc9a…`, or except `0d34f3ae…`) were being run when this was written.

## Not done / not verified

- The comparison is by eye and by frame number inside each run; pacing differs between runs, so the scenes match only
  roughly.
- No run compares off, no-fix and shifted at the same game moment. Needed: capture by game event, not frame number.
- The two main lit shaders were never given the shifted view from head show onward in a clean A/B.
- Only Ohtani's colour map was tested.

## Next steps

1. Fix the comparison first: a capture tied to a game event (for example a set number of frames after the stat panel
   appears) so off, no-fix, bake-shifted and all-shifted show the same moment.
2. Run all-shifted from the first frame (static, not cycled) and check the face against `off` at that event.
3. If all-shifted is natural and bake-only is not, bisect over the four shader ids above (the experiment supports
   modes that shift everything except a named set).
4. If all-shifted is also yellow, the cause is not the colour map's base level; look at what else changes when the
   texture is replaced (size query, image dimensions fed to a constant buffer, the bake render target size).

## Where the experiment lives

`git stash` entries on `main` hold the shader-matching rule (`hd_shift`, `cur_bake`, `hd_bake_fs`), the `[hdview]`
log and the `[cyc]` run-time mode cycling. The committed notes are in `docs/ps5-textures.md`.
