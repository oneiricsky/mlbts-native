# Report: PS5 normal maps for all heads

Status: done and committed on `main` (not pushed). Colour maps are not included (see the yellow-face report).

## What shipped

- `runtime/mlb/hdtex.c` plus the hook in `vk_texture.c` `hd_apply`: when the game uploads a head texture whose storage
  matches an index entry (FNV-1a of the first 16 KiB), the PS5 level data is uploaded in its place at 2x the size.
- `tools/make_hd_index.py --all-heads`: every head with a NORMAL map in both the Switch romfs and the PS5 dump.
  2,370 entries in about 70 s. 41 entries are dropped because their Switch textures share a hash with another entry.
  `--heads NAME ...` does chosen players; `--color` adds colour maps (known to turn faces yellow).
- The index is read from `hdtex/index.txt` in the working directory, or from the folder named by `MLB_HD_TEXTURES`
  (`off` or `0` disables it).

## Results

- 58 swaps per match, no errors in the log.
- VRAM unchanged at about 2,593 MiB across the run.
- Load cost: the loader now reads a 0x400-byte header and then one block covering only the levels it keeps. A cold read
  went from 31 ms to 12 ms per file; a warm read is under 1 ms. A match loads about 58 heads, so about 0.7 s once at
  load, on the replay thread.
- The PS5 normal map is a visible gain up close (stubble on Ohtani).

## Format notes

- PS5 `.TEX` files are raw: levels 0 and 1 first, then the smaller levels in reverse order, in 64-byte units
  (BC1 as 2x4 blocks, BC7 as 1x4). Level offsets: level 0 at 0, level 1 after level 0, levels 2 and up at
  `tail - run` from the end.
- Switch `.TEX` files hold LZ4 blocks of NVN block-linear storage. The game ignores the header's size and format: it
  creates the texture at the Switch size and copies the decompressed storage in, which is why the swap is done at
  upload and not by replacing the files.

## Checked and not checked

Checked in game up close: Ohtani and the Dodgers catcher. The other 2,300 or so heads were not looked at.
Not verified: other categories (crowd, uniforms, stadium), BC1 PS5 mip tails, cube maps, VRAM with many more HD
textures.

## Possible follow-up

A background loader for the PS5 reads would remove the 0.7 s load cost. Low value at the moment.
