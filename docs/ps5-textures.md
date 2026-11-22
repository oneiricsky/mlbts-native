# PS5 textures in place of the Switch ones

An optional feature (`MLB_HD_TEXTURES`): a player's face normal map from a PS5 dump of the game is used instead of the
Switch one. Nothing is shipped; it reads the user's own dump, and it does nothing without an index file. The colour
maps are left out because they break the face (see Known limits).

## Using it

```
python -I tools/make_hd_index.py --ps5 E:/PPSA30630/PPSA30630-app --romfs work/build/game/romfs \
    --out work/build/hdtex/index.txt --heads OHTANI_SHOHEI
```

`--heads` takes player folders under `CHARACTERS/HEADS` (their NORMAL maps; `--color` adds the COLOR maps), or pass
paths under `NSW/` directly. `--all-heads` takes every head that has a NORMAL map in both the Switch files and the dump
(2,411 in the 1.0.20 dump): it reads only the PS5 headers and takes about a minute. Entries whose Switch textures share
a hash cannot be told apart and are left out (41 of them). The result, 2,370 entries, loads at start in a few
milliseconds; a player's texture is only read when the game creates it.
`--max-dim` (default 1024) is the largest side of the PS5 image; `--scale` (default 4) how many times the Switch
size it aims for. The game then picks the index up from the `hdtex` folder of its working directory.
`MLB_HD_TEXTURES=<folder>` uses another folder, `off` or `0` turns it off. The log says `hdtex: N PS5 textures indexed`
at start and `hdtex: texture ... is PS5/...` for each one swapped in.

## How it works

The game does not take a texture's size from the `.TEX` file's header. It creates the texture at the Switch size
(Ohtani's colour map is a 512x256 BC1 texture, his normal map 256x128 BC7) and copies the file's decompressed storage
into it. A bigger file therefore cannot simply replace the Switch one (a converted file with the right header still
came out as noise, the PS5 BC7 blocks read as a 512x256 BC1 texture). So the swap happens in the port, at upload
(`vk_texture.c` `hd_apply`):

1. A texture whose size and mip count are in the index has the first 16 KiB of its storage hashed (FNV-1a, the same
   as `prompts.c`). The index holds that hash for each Switch texture, made by `tools/make_hd_index.py` from the
   decompressed file.
2. A match reads the PS5 file (`runtime/mlb/hdtex.c`), rearranges its blocks into plain rows and creates a second image
   from it. That image takes the place of the Switch-sized one in the texture's `VkTexImage`, so the replay's next
   binding samples it. The Switch-sized image stays and is uploaded as always; each upload puts it back for the copy and
   `hd_apply` decides again, because the storage may by then hold another texture (the PS5 image goes, or a new one
   comes).
3. Ohtani's normal map is made at 1024x512 BC7 (0.7 MiB; the Switch one is 256x128).

## The PS5 file

The same TX12 container as the Switch files (magic `TX12PS5`), raw instead of LZ4. The name fingerprint at 0x20 and
the name at 0x30 are the same in both builds, so the two files of a texture pair up. Everything else below was found by
decoding the files; none of it is documented.

- Header size is the file size minus the data size at 0x0c. Width and height at 0x84, mip count at 0x8c, the format
  code in the low 16 bits of the dword at 0x15c (13 is BC1, 22 is BC7; the Switch files use another numbering).
- One row of 32 bytes per level from 0x1a0: the level's size at +4. Levels 0 and 1 come first, then the smaller levels
  in reverse order, smallest first. The row's first dword is the bytes left after the level in that order.
- Blocks sit in 64-byte units along strips four block rows high: 2x4 blocks for 8-byte blocks (BC1), 1x4 blocks for
  16-byte blocks (BC7). The unit index runs across the whole width of the level, then down a strip. Widths that are
  not powers of two are padded to 128 pixels on the top level.

Checked on Ohtani's two textures (every level against the one above it) and on a sample of BC1 and BC7 textures of
other sizes; BC1 mip tails and cube maps and arrays are not checked.

## The Switch file

A 0x2A0-byte (one variant) or 0x3E0-byte (two variants, such as the head colour maps: 512x256 and its 256x128 lower
half) header, then one LZ4 block per segment. Decompressed, a texture is the NVN block-linear storage exactly as
`nvn_tex.c` lays it out with the automatic block height, so its first 16 KiB are what the game puts in the texture.

## Known limits

- **A PS5 colour map makes the face bright yellow and flat**, at 2048x1024 and at 1024x512. Swapped at the Switch's own
  size (512x256) it renders normally. What was found: the face's colour sampler has no mip filter, so the shader reads
  only the first level of the view; starting the view at the second level, or filling the first level with one skin
  block, removes the yellow; the PS5 levels have the same mean colour, alpha and block modes as each other; forcing
  alpha to one, a UNORM view and a mipmapped sampler change nothing; and a patched face shader that outputs the raw
  colour sample shows normal skin with the first level exposed, so the blow-up happens after the sample, in the lighting
  terms (the albedo is scaled by a value from other inputs). Fixed from the first frame, shifting only some readers
  to the Switch-size level never clears it: the main lit face pass (input id 0d34f3ae), the bake fragment shaders
  (0842012c, a11d58f0, 93e02c04, db0de8cd) and the reads that have no fragment shader (compute or blit passes) all
  go wrong when they see the 1024x512 level. Only the rare pass 23a1dc9a can keep it, so there is no gain over
  the 512x256 level. Not a shader fix; the base level's content or upload is the next suspect (see
  `docs/reports/2026-11-22-yellow-face-ps5-colour-maps.md`). Until it is found, `make_hd_index.py`
  leaves the colour maps out.
- Only PS5 files in BC1 or BC7 are handled; others are skipped with a message.
- The PS5 file is read on first use, from the replay thread, and only the levels the image keeps (the largest level,
  most of the file, is skipped). From the dump's drive that took 12 ms a file cold (31 ms read whole) and under 1 ms
  warm; a match loads about 58 heads, so about 0.7 s once at load. A background loader would remove that.
- Checked in the game up close: Ohtani's face (stubble shows) and the Dodgers catcher's face. The other 2,300 entries
  are not checked.
- Two textures with the same first 16 KiB would share an index entry.
