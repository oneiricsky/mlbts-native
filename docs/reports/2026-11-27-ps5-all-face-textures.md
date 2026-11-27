# Report: every PS5 face texture, colour maps on by default

Status: committed on `main`, not pushed. One thing is open: stadiums turning black now and then in the played match,
cause unknown (below).

In plain words: with a PS5 copy of the game, almost every player now gets the sharper PlayStation face, both its colour
and its surface detail. A switch in the F1 menu turns this off.

## Coverage

Dump: `D:\Games\PPSA30630\eboot\app0` (it was on `E:` before). Romfs: 1.0.20, 2,423 head folders. The dump has 2,412.

| Map | Before | Now | Not usable |
|---|---|---|---|
| Normal | 2,370 heads | 2,411 heads (every head that has it on both sides) | 12 Switch heads with no PS5 file; `DAVIS_ERIC` is only in the dump |
| Colour | not in the default index | 2,409 heads (every head that has it on both sides) | the same 13 |

The index has 7,190 lines. `docs/ps5-textures.md` names the 12 heads.

## Why heads were missing

A texture is recognised by a hash of the first 16 KiB of its storage. 56 groups of Switch textures share that hash, and
the index tool dropped them all. Now:

- one PS5 picture under both names: one line, correct for either;
- different further on: a hash of the whole storage decides;
- identical Switch textures with different PS5 pictures (the colour maps of four pairs, 8 heads): the head whose file
  the game opened is used, and the Switch texture stays when both or neither were opened.

Found on the way: the tool only compared heads that had a PS5 file, so a Switch-only head sharing 16 KiB with one of
them could have been given its face. Every Switch head is now compared. A colour map's large variant is two LZ4 blocks;
the offline harness caught a first version of the whole-storage hash that read only the first.

## Settings and fallback

`MLB_HD_TEXTURES` has a row in `cfg.c` (`--hd-textures`, `--no-hd-textures`) and a toggle, F1 → Graphics → PS5 face
textures, on by default. Without an index, with an unlisted texture, with a PS5 file that cannot be read or with two
candidates that cannot be told apart, the Switch texture stays.

## Checks

| Check | Result |
|---|---|
| `tools/test_hd_index.py` | 26 tests pass |
| `make_hd_index.py --check` | 7,190 lines, 0 problems |
| `tools/hdtex_test.c`: every Switch head texture through the runtime lookup and PS5 loader | 0 failed checks. Colour: 4,798 variants got their own file, 20 an identical twin's, 24 stayed Switch (the 12 heads, two variants each). Normal: 2,392, 19, 12. All 7,190 lines load; a missing dump loads nothing |
| Harness match, TOR at LAD, 170 s | 58 heads, 116 swaps, both maps each, 0 errors; `MUNCY_MAX`, which needs the whole-storage hash, was recognised |
| Played match, SEA and AZ, Quick Counts and Fast Play, to the post-game menu | 53 heads (4 umpires among them), 110 swaps, both maps each, 0 hdtex errors, no FATAL; PS5 reads on the replay thread 62 ms in all, 0.8 ms at most |

### Known-bad control

A build with the compute fix switched off (`hd_shift` forced to 0, not committed) against the shipped build and
`MLB_HD_TEXTURES=off`, one 178 s run each, a shot every 50 frames (125 shots), the largest connected blob of blown
yellow, shots over 300 pixels at half size:

| Build | Shots over 300 px | What they were, by eye |
|---|---|---|
| Fix off (control) | 11 | Ohtani's face, blown flat yellow |
| Fix on | 0 | the same mound scene shows a natural face |
| PS5 textures off | 5 | stadium seats |

The count alone does not tell a face from Dodger Stadium's yellow seats, so flagged shots were looked at. The older
whole-picture count (`work/scratch/ycount.py`) flags seats and dirt in this scene. Runs are not repeatable even with a
seed and a fixed clock (22 to 95 % of pixels differ between two equal runs), so shots cannot be compared one to one.

### Faces looked at

Close up in screenshots: only a few (Ohtani, Springer, Barger, the Blue Jays lineup portrait). The research branch asks
for about two dozen heads from both teams before colour maps are the default. The played match loaded 53 heads and the
owner reported no wrong face, but did not say that faces were checked, so that item counts as **not confirmed**.

### Speed and memory

Matched runs of the new build, second minute, same settings apart from the textures (screenshots being taken):

| | Mean fps, three runs | 1 % low |
|---|---|---|
| PS5 textures on | 59.2, 58.7, 58.8 | 31.5, 26.0, 26.8 |
| Off | 58.9, 59.4, 58.2 | 27.8, 34.5, 26.1 |

The ranges overlap: no difference seen. A partial 1080p run with PS5 textures sampled 3.68 GB of RAM and 2.72 GB of GPU
memory at 84 s; memory over a whole match was not recorded.

The played match ran slower: after the first minute (58.2 fps, mostly menus) the 28 full minutes had a median of about
44 fps (38 to 50). It had a person playing, the full performance overlay turned on part way, and no run with the
textures off to compare, so the cause is **not known**.

## Open: stadiums turn black now and then

Reported by the owner from the played match. Not reproduced.

- The log records nothing about it. No stadium texture was swapped: all 110 swaps are head files.
- About 500 screenshots from computer-played runs show no black stadium. One near-black frame appears at about the same
  point with the textures on, off and in the control, and was not examined.
- FSR was switched to native in the menu during the match; it applies only at the next start.
- Upstream issue sam110411/fastball#30 (open) reports bases, the rubber and the rosin bag turning black on an RX 9070
  XT. Whether it is the same fault is a guess.
- Untested guesses: the `walkup_light` patch with Fast Play's shorter gaps (a lighting buffer shown before its bake),
  the PS5 textures, a driver fault.

To settle it: a screenshot and the moment it happens; then the same kind of match with `--no-hd-textures`, and with
`--no-walkup-light`.

## Not covered

Crowd heads (1,036 PS5 textures), created-player layers and mascots. The PS5 files are used at 1024x512; their 2048
level is not.
