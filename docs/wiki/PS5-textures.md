An optional feature, `MLB_HD_TEXTURES`, uses a player's face texture from a PS5 dump of the game in place of the Switch one. Nothing is shipped. It reads the user's own dump and does nothing without an index file.

## How it works

The game does not take a texture's size from the `.TEX` file's header. It creates the texture at the Switch size (Ohtani's colour map is 512x256, his normal map 256x128) and copies the file's decompressed storage into it. A bigger file cannot just replace the Switch one; a converted file with the right header still came out as noise. So the swap happens in the port, at upload (`hd_apply` in `vk_texture.c`):

1. A texture whose size and mip count are in the index has the first 16 KiB of its storage hashed (FNV-1a). The index holds that hash for each Switch texture.
2. A match reads the PS5 file (`runtime/mlb/hdtex.c`), rearranges its blocks into plain rows and creates a second image. That image takes the place of the Switch-sized one for the next binding.
3. Ohtani's normal map becomes 1024x512 BC7 (0.7 MiB) in place of 256x128.

`tools/make_hd_index.py --all-heads` builds the index from the Switch files and the dump. It covers the colour maps of
2,409 heads and the normal maps of 2,411, every head that has the map on both sides. 13 heads cannot be used: 12 have no
PS5 file and one is only in the dump. Switch textures that share their first 16 KiB are told apart by a hash of the
whole storage, or, for four pairs with identical Switch colour maps, by which head file the game opened. `--check`
validates an index. The setting `MLB_HD_TEXTURES` (menu: Graphics, PS5 face textures) is on by default.

## The PS5 file format

Found by decoding the files; none of it is documented. Same TX12 container as the Switch files (magic `TX12PS5`), raw instead of LZ4. Only BC1 and BC7 are handled.

| Field | Where |
|---|---|
| Header size | file size minus the data size at 0x0c |
| Width, height | 0x84 |
| Mip count | 0x8c |
| Format | low 16 bits of the dword at 0x15c (13 is BC1, 22 is BC7) |
| Level table | one 32-byte row per level from 0x1a0 |
| Level order | levels 0 and 1 first, then the smaller levels in reverse order |
| Blocks | 64-byte units along strips four block rows high |

## Performance

Matched short runs on an RX 6700 XT held about 59 fps with the textures on and off. A match loads 50 to 60 heads; with
the files read ahead, the loads cost the drawing thread 62 ms over one played match.

An older measurement, before the 0.2.0 merge: three configurations, two runs of 400 s each. Each cell gives run 1 and
run 2.

| Config | Fps | Low | Slow |
|---|---|---|---|
| Off | 59.2, 59.1 | 45.5, 44.0 | 21, 23 |
| Normal maps | 57.5, 59.0 | 45.5, 43.7 | 30, 26 |
| Normal and colour | 58.9, 57.4 | 44.2, 42.4 | 29, 24 |

Low is the 1 percent low in fps (median of six one-minute windows); Slow counts frames over 100 ms.

## The yellow face (fixed)

Swapping in the PS5 colour map made faces bright yellow-orange and flat in lit scenes, at 2048x1024 and at 1024x512. A PS5 map cut to the Switch size rendered normally.

The cause: a compute shader that runs when a head is shown measures the skin tone with an integer `texelFetch` over a rectangle given in the Switch texture's texel coordinates, and queries the size it normalises by. On a 1024x512 image that rectangle is the wrong quarter of the map, so the skin-tone average comes out wrong. The lit face shaders divide the albedo by that average, and the face blows out. It was found by logging which binding each reader uses and disassembling the compute shader.

The fix is in `get_view` (`runtime/gfx/vk_exec_draw.c`). While a compute dispatch is recorded, a PS5 image is bound from the level that has the Switch texture's size (`hd_shift`). Fragment shaders still sample by normalised coordinates and keep the large level.

How it was counted: each configuration fixed from frame 0, one shot every 10 frames from frame 2850 (101 shots), and a count of blown-yellow skin pixels outside the stat panel (more than 1,500 flags a blown face), checked against a face-to-jersey brightness ratio (natural 0.45 to 0.58, blown 0.86 to 0.94).

| Config | Blown |
|---|---|
| Colour map off | 0 of 101 |
| No fix | 50 to 52 of 101 |
| Fix | 0 of 101 (peak 101 pixels, against 4,565 unfixed) |

An earlier conclusion in the investigation, that every reader group needs the small level, was wrong. It came from comparing runs whose readers were shifted in combination, and only the compute group needs it.

## Known limits

- Colour maps are on by default since 2026-11-27. Few faces have been looked at close up; the rest are checked offline
  only (the right file is found and loads).
- Stadiums turned black now and then in one played match. Not reproduced; the cause is not known.
- Crowd heads, created-player layers, mascots, uniforms and stadiums are not replaced.
- A PS5 file is read on first use on the replay thread, from the dump's drive. From a hard disk, cold, that cost 200 to 670 ms frames. A prefetch thread fixes it (see [Load stalls](Load-stalls)).
- A compute dispatch binds PS5 images from the Switch-size level, so a new PS5 category needs its compute consumers checked first.
