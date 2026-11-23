# PS5 textures in place of the Switch ones

An optional feature (`MLB_HD_TEXTURES`): a player's face normal map from a PS5 dump of the game is used instead of the
Switch one. Nothing is shipped; it reads the user's own dump, and it does nothing without an index file. The colour
maps are left out because they break the face (see Known limits).

## Using it

```
python -I tools/make_hd_index.py --ps5 <PS5 dump folder> --romfs work/build/game/romfs \
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

### Checking an index

```
python -I tools/make_hd_index.py --check work/build/hdtex/index.txt [--ps5 <PS5 dump folder>]
```

Reads only the headers of the PS5 files an index names (no Switch files needed) and prints one line per problem, then
`N index lines checked, M problems in K lines`. Exit status is 0 when clean and 1 otherwise. `--ps5` replaces the
index's `root` line, for a dump that has moved. About a minute per 2,400 lines from the dump's drive. A problem line
means the game would skip that texture or load it wrong; fix it by building the index again, not by editing it.
`python -I -m unittest discover -s tools -p test_hd_index.py` runs the tests, which need no dump.

| Message | What it means |
| --- | --- |
| `not a line of the form <hash> <width> <height> <levels> <drop> <PS5 file>` | The line cannot be read; the game ignores it. |
| `no root line in the index and no --ps5 folder given` | There is no dump folder to look in. |
| `not a path of the form PS5/.../<name>.TEX` | The file path is outside `PS5/`, has `..`, or is not a `.TEX` file. |
| `the file name does not start with its folder name X` | The name and folder disagree (`AAA/BBB-NORMAL.TEX`), so the entry may belong to another player. |
| `another PS5 file has the same hash and size, the two cannot be told apart` | Two files share an index key; the builder drops these, so this means the index was edited or built by hand. |
| `file not found under <root>` | The dump is missing, on another drive letter, or the file was renamed. |
| `not a PS5 TX12 file`, `file is only N bytes, shorter than a header` | Wrong or empty file. |
| `odd header: ...` | The level count is outside 2 to 16, or the level table does not fit before the texture data. |
| `file is shorter than its header says` | The file is cut off inside its texture data. |
| `header is N bytes, every PS5 file seen so far has 1440: the file is probably cut short` | The loader finds the data as file size minus data size, so a cut file passes its other checks and loads shifted data. This catches it. A different header size could also be a kind of texture not seen before. |
| `level sizes add up to X bytes, the header says Y` | The level table does not match the data size. |
| `format code N is not BC1 (13) or BC7 (22)` | The loader handles only BC1 and BC7. |
| `largest level is ...`, `level i (WxH) is ... bytes, less than ...`, `level i lies outside the file` | A level is smaller than its dimensions need, or runs past the end of the file. |
| `drop D leaves no level (the file has N)` | The index drops more levels than the file has. |
| `after dropping D levels the image is WxH, which is not the Switch size ... times a power of two` | The image would not contain a level of exactly the Switch size, which the compute passes need (`hd_shift`). |
| `only N levels are left at the Switch size, the Switch texture has L` | The PS5 chain is too short below the Switch size. |

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

- **PS5 colour maps (fixed 2026-11-22; still opt-in in the index tool).** A larger colour map used to make the face bright
  yellow and flat. The cause: a compute pass the game runs when a head is shown measures the skin tone by `texelFetch` over a
  rectangle of the colour map given in the Switch texture's texel coordinates (and queries the size it normalises by). On a
  1024x512 image that rectangle is the wrong quarter of the map; the average comes out wrong and the lit face shaders
  divide the albedo by it, so the face blows out. The fix is in `get_view` (`runtime/gfx/vk_exec_draw.c`): while a compute
  dispatch is recorded, a PS5 image is bound from the level that has the Switch texture's size (`hd_shift`, set in
  `hd_apply`); fragment shaders sample by normalised coordinates and keep the large level. Checked: with only that
  rule, 0 of 101 harness shots show the blown colour (no fix: 50), and Ohtani's and Springer's faces look natural with
  stubble and skin detail. Not checked: other heads, the 2048 level, the crowd and other categories. What was ruled out on
  the way: the data (levels are a consistent mip chain with the same colour), alpha (forcing it to one helped only a
  little), the sampler, the view format, game copies of the texture, and size queries in the lit shaders. See
  `docs/reports/2026-11-22-yellow-face-ps5-colour-maps.md`. `make_hd_index.py --color` adds the colour maps; the default
  index still leaves them out until more heads are looked at.
- Only PS5 files in BC1 or BC7 are handled; others are skipped with a message.
- The PS5 file is read on first use, from the replay thread, and only the levels the image keeps (the largest level,
  most of the file, is skipped). From the dump's drive that took 12 ms a file cold (31 ms read whole) and under 1 ms
  warm; a match loads about 58 heads, so about 0.7 s once at load. A background loader would remove that.
- Checked in the game up close: Ohtani's face (stubble shows) and the Dodgers catcher's face. The other 2,300 entries
  are not checked.
- Two textures with the same first 16 KiB would share an index entry.
