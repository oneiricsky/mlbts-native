An optional feature, `MLB_HD_TEXTURES`, uses a player's face texture from a PS5 dump of the game in place of the Switch one. Nothing is shipped. It reads the user's own dump and does nothing without an index file.

## How it works

The game does not take a texture's size from the `.TEX` file's header. It creates the texture at the Switch size (Ohtani's colour map is 512x256, his normal map 256x128) and copies the file's decompressed storage into it. A bigger file cannot just replace the Switch one; a converted file with the right header still came out as noise. So the swap happens in the port, at upload (`hd_apply` in `vk_texture.c`):

1. A texture whose size and mip count are in the index has the first 16 KiB of its storage hashed (FNV-1a). The index holds that hash for each Switch texture.
2. A match reads the PS5 file (`runtime/mlb/hdtex.c`), rearranges its blocks into plain rows and creates a second image. That image takes the place of the Switch-sized one for the next binding.
3. Ohtani's normal map becomes 1024x512 BC7 (0.7 MiB) in place of 256x128.

`tools/make_hd_index.py --all-heads` builds the index from the Switch files and the dump's headers. 2,411 heads have a normal map in both, and 2,370 entries remain after 41 are dropped because their Switch textures share a hash with another entry. It takes about 70 s. `--check` validates an index.

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

## Normal maps: done

The PS5 normal map is a visible gain up close (stubble on Ohtani). A match swaps about 58 heads with no errors in the log and VRAM unchanged at about 2,593 MiB. Cold reads went from 31 ms to 12 ms per file after the loader was changed to read the header plus one block holding only the levels it keeps.

Performance: three configurations on the harness match, two runs of 400 s each (about 21,000 frames). Each cell gives run 1 and run 2.

| Config | Fps | Low | Slow |
|---|---|---|---|
| Off | 59.2, 59.1 | 45.5, 44.0 | 21, 23 |
| Normal maps | 57.5, 59.0 | 45.5, 43.7 | 30, 26 |
| Normal and colour | 58.9, 57.4 | 44.2, 42.4 | 29, 24 |

Low is the 1 percent low in fps (median of six one-minute windows); Slow counts frames over 100 ms. Once boot stalls are set aside all three run at about 59 fps. The 1 percent low is about 1 to 2 fps lower with PS5 textures, about the spread between repeats. The extra slow frames may be noise or about one more hitch a minute. RAM and GPU memory did not grow. Two of four PS5 runs had an 8.4 s or 10.1 s frame at frame 14; six start-up-only runs did not, and the cause was not found.

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

- Colour maps stay opt-in in the index tool. The fix was checked on two players' faces. The other 2,300 heads, the 2048 level, crowds, uniforms and stadiums are not checked. The branch's gate for making colour maps default is a check on about two dozen heads from both teams with the known-bad control, plus one full match.
- A PS5 file is read on first use on the replay thread, from the dump's drive. From a hard disk, cold, that cost 200 to 670 ms frames. A prefetch thread fixes it (see [Load stalls](Load-stalls)).
- Two Switch textures with the same first 16 KiB would share an index entry.
- A compute dispatch binds PS5 images from the Switch-size level, so a new PS5 category needs its compute consumers checked first.
