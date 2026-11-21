# PS5 textures in place of the Switch ones

An optional feature (`MLB_HD_TEXTURES`): a player's face textures from a PS5 dump of the game are used instead of the
Switch ones. Nothing is shipped; it reads the user's own dump, and it does nothing without an index file.

## Using it

```
python -I tools/make_hd_index.py --ps5 E:/PPSA30630/PPSA30630-app --romfs work/build/game/romfs \
    --out work/build/hdtex/index.txt --heads OHTANI_SHOHEI
```

`--heads` takes player folders under `CHARACTERS/HEADS` (COLOR and NORMAL), or pass paths under `NSW/` directly.
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
3. Both textures of Ohtani's face are made at 1024x512 BC7 (0.7 MiB each) by default.

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

- A 2048x1024 colour map for Ohtani's face (4x the Switch size) comes out too bright and yellow in the game; 1024x512
  is fine. The data is the same at every size (mean colour per level matches the Switch's), the draw's face shader
  samples the colour map with others that stay at their Switch size, and nothing in the port's view or sampler code
  changed with the size, so the cause is likely in the shader. `--max-dim` is 1024 for that reason.
- Only PS5 files in BC1 or BC7 are handled; others are skipped with a message.
- The PS5 file is read on first use, about 2 to 3 ms for Ohtani's, from the replay thread.
- Two textures with the same first 16 KiB would share an index entry.
