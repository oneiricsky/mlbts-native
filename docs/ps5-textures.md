# PS5 textures in place of the Switch ones

An optional feature (`MLB_HD_TEXTURES`): a player's face colour and normal maps from a PS5 dump of the game are used
instead of the Switch ones. Nothing is shipped; it reads the user's own dump, and it does nothing without an index
file.

## Using it

```
python -I tools/make_hd_index.py --ps5 <PS5 dump folder> --romfs work/build/game/romfs \
    --out work/build/hdtex/index.txt --all-heads
```

`--all-heads` takes every head under `CHARACTERS/HEADS`; `--heads NAME ...` takes some of them, or pass paths under
`NSW/` directly. Both maps are indexed unless `--no-color` is given. The build takes under a minute from an SSD and
ends with a count for each map type and one line for every head it could not use.
`--max-dim` (default 1024) is the largest side of the PS5 image; `--scale` (default 4) how many times the Switch
size it aims for. The game then picks the index up from the `hdtex` folder of its working directory.

The setting is `MLB_HD_TEXTURES` (`--hd-textures`, or F1 → Graphics → PS5 face textures; applies after a restart).
On (`1`, the default) uses the `hdtex` folder; `0` or `off` uses none; a folder name uses that folder's index. The log
says `hdtex: N PS5 textures indexed` at start and `hdtex: texture ... is PS5/...` for each of the first 512 swaps.

When something is missing the Switch texture stays: no index, a texture the index does not list, a PS5 file that cannot
be opened or read (logged, and tried again at the next upload), an unexpected format, or two PS5 files that cannot be
told apart (below).

## Coverage

The 1.0.20 romfs has 2,423 head folders and the dump 2,412.

| Map | Heads on both sides | Used | Not usable |
|---|---|---|---|
| Colour | 2,409 | 2,409 | 13: 12 Switch heads with no PS5 file, and `DAVIS_ERIC`, which only the dump has |
| Normal | 2,411 | 2,411 | 13, the same heads |

The 12 are `CANZONE_DOMINIC`, `ESCARRA_JC`, `KELLY_KEVIN`, `MACHIN_VIMAEL`, `PALACIOS_RICHIE`, `RITCHIE_JR`,
`RODRIGUEZCRUZ_ELMER`, `SCHRIER_CODY`, `SEYMOUR_IAN`, `TENG_KAIWEI`, `VOTH_AUSTIN` and `WARREN_WILL`.
(`REDMOND_MIKE` and `WEISS_WALT` have a normal map and no colour map.) All the PS5 head maps are 2048x1024 BC7.

Players whose Switch textures start with the same 16 KiB are told apart like this:

- one PS5 picture under both names: one index line, either name is right;
- the Switch textures differ further on: their lines carry a hash of the whole storage;
- the Switch textures are the same and the PS5 pictures are not (the colour maps of `CORA_JOEY` and
  `EXTRA_MALEMATURE6`, `FESTA_DAVID` and `TOGLIA_MICHAEL`, `LACKEY_VAHN` and `ROBINSON_KRISTIAN`, `UMP_02` and
  `WILSON_VANCE`): the one whose head file the game has opened is used. If it has opened both, or neither, the Switch
  texture stays.

The 20 colour and 19 normal Switch textures that get a twin's file are the first kind.

Not covered: the crowd's heads (1,036 textures under `PS5/STADIUMS/COMMON/CROWD/HEADS`), the created-player layers
(`PS5/CREATEPLAYER`) and mascots. Each is a different category whose compute passes have not been checked.

### Checking an index

```
python -I tools/make_hd_index.py --check work/build/hdtex/index.txt [--ps5 <PS5 dump folder>]
```

Reads only the headers of the PS5 files an index names (no Switch files needed) and prints one line per problem, then
`N index lines checked, M problems in K lines`. Exit status is 0 when clean and 1 otherwise. `--ps5` replaces the
index's `root` line, for a dump that has moved. About a minute per 2,400 lines from the dump's drive. A problem line
means the game would skip that texture or load it wrong; fix it by building the index again, not by editing it.
`python -I -m unittest discover -s tools -p test_hd_index.py` runs the tests, which need no dump.
`tools/hdtex_test.c` (build line at its top) feeds every head texture of the game through the runtime's own lookup
and PS5 loader, and needs the dump.

| Message | What it means |
| --- | --- |
| `not a line of the form <hash> <width> <height> <levels> <drop> [=<full>/<bytes>] <PS5 file>` | The line cannot be read; the game ignores it. |
| `no root line in the index and no --ps5 folder given` | There is no dump folder to look in. |
| `not a path of the form PS5/.../<name>.TEX` | The file path is outside `PS5/`, has `..`, or is not a `.TEX` file. |
| `the file name does not start with its folder name X` | The name and folder disagree (`AAA/BBB-NORMAL.TEX`), so the entry may belong to another player. |
| `another PS5 file has the same hash and size, the two cannot be told apart` | Two files share an index key and a line lacks the whole-storage hash; the builder always adds it, so the index was edited or built by hand. |
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
   decompressed file. Where several textures share it, a hash of the whole storage decides as well.
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
half) header, then one LZ4 block per segment. With two variants the first block holds the large level only (the size at
0x10 less the one at 0x104) and the second, at the offset at 0x10c, the half-size chain, which is also the rest of the
large variant's storage. Decompressed, a texture is the NVN block-linear storage exactly as
`nvn_tex.c` lays it out with the automatic block height, so its first 16 KiB are what the game puts in the texture.

## Known limits

- **PS5 colour maps (fixed 2026-11-22, on by default since 2026-11-27).** A larger colour map used to make the face
  bright yellow and flat. The cause: a compute pass the game runs when a head is shown measures the skin tone by
  `texelFetch` over a rectangle of the colour map given in the Switch texture's texel coordinates (and queries the size
  it normalises by). On a 1024x512 image that rectangle is the wrong quarter of the map; the average comes out wrong and
  the lit face shaders divide the albedo by it, so the face blows out. The fix is in `get_view`
  (`runtime/gfx/vk_exec_draw.c`): while a compute dispatch is recorded, a PS5 image is bound from the level that has the
  Switch texture's size (`hd_shift`, set in `hd_apply`); fragment shaders sample by normalised coordinates and keep the
  large level. See `docs/reports/2026-11-22-yellow-face-ps5-colour-maps.md`, and
  `docs/reports/2026-11-27-ps5-all-face-textures.md` for the check made before the default changed.
- Only PS5 files in BC1 or BC7 are handled; others are skipped with a message.
- The PS5 file is read on first use, from the replay thread, and only the levels the image keeps (the largest level,
  most of the file, is skipped). From the dump's drive that took 12 ms a file cold (31 ms read whole) and under 1 ms
  warm; a match loads about 58 heads, so about 0.7 s once at load. A background loader would remove that.
- Only part of the heads have been looked at in the game (the report above lists them). The rest are checked offline
  only: the right file is found and loads.
- A texture outside `CHARACTERS/HEADS` with a head texture's size, mip count and first 16 KiB would be taken for it.
