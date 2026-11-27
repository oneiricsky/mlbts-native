# Reading and writing the settings save without the game (proof of concept)

`tools/save_reader.py` reads the whole settings save into a list of classes, records and fields, and writes it back
from that list. On a copy of one real save the rewritten files are byte for byte the same as the originals. The game
was not started for any of this, so nothing new here has been seen in game.

In everyday words: we can now open the settings file, understand where every byte belongs, change any one setting in
any of the 30 preset slots, and save a copy. We know what only a few of those settings mean.

## The format

All numbers are little-endian. `[C]` marks what was read in the 1.0.20 code (offsets into `main`).

| Part | Layout | Source |
|---|---|---|
| Start | `LE56`, u32 length of the description, `[DESC]` | [C] `0xdf270c`, `0xdf2774` |
| Class | name (16 bytes), u32 payload length (4 + 32 per field), u32 field count, fields | [C] `0xdf1e90` |
| Field | name (16), u32 zero, u16 zero, u16 id, u16 element width, u16 element count, u32 byte size | [C] `0xdf1e90` |
| Values | `[DATA]`, then blocks: name (16), u32 record count, records | [C] `0xdf27d4`, `0xdf2818` |
| Record | each field in description order, byte size each, then any child blocks | [C] `0x181a2f0`, `0x181a170` |

Nesting is not written in the file. Each of the 30 preset records (`D_CSTM_SETTINGS`) is followed by its own user
settings block and franchise options block. The reader knows this from the game's writer (a loop at `0x18295e8`
calling `0x181a170`) and holds it in one small table, `CHILDREN`.

This corrects four statements in `tools/map_functions_doc.py` and `tools/save_schema.py` (not edited here):

- The name slot is 16 bytes, not 22. The older parser still lands on the right values because the bytes between are
  zero.
- The last two descriptor numbers are one u32, the field's size in bytes. It equals width times count in all 239
  settings fields, and the game's writer checks it. It is not a spare capacity.
- The u32 after a class name in `[DATA]` is the record count. The preset block holds 30 records, so the bytes after
  the first name are the rest of record 0 and then its child blocks, not more scalars of one record.
- The `4 | (n << 5)` word is the class's payload length, with n the field count.

## What is proven (offline)

| Check | Result |
|---|---|
| Bytes explained | 17,282 of 17,282; opaque 0 (0 %) |
| Of which values | 8,278 (47.9 %) |
| Of which structure | 9,004 (52.1 %): names 4,880, descriptor numbers 1,434, checked zeros 1,434, lengths and counts 1,240, tags and magic 16 |
| Contents | 4 classes, 239 field definitions, 62 data blocks, 91 records, 7,141 field values |
| Round trip | decompressed archive identical; `SAVE_000` (zlib level 6) and `SAVEINFO` identical too |
| No byte ignored | one bit flipped in each of the 17,282 bytes in turn: each copy is refused or written back exactly |
| Edit in preset 17 (one number, one string) | only the intended bytes differ; hash verifies; re-read gives the new values |
| Same edit as `save_edit.py` | identical archive |
| The edit already seen loading in game (2026-11-24) | reproduced byte for byte from the original save |
| Broken inputs | one byte added or removed, wrong element width, wrong lengths and counts: refused |
| Values that do not fit | out of range, wrong type, wrong length, over-long or non-ASCII text, unknown names: refused |

The writer computes every length and count from the model and keeps no copy of the input. A test also builds an
archive from objects alone and compares it with bytes packed by hand.

## What the values mean

| Values | Evidence available offline | Standing |
|---|---|---|
| Preset name | 30 records match the 30 16-byte name slots the game's constructor clears; record 0 matches the documented string; all 30 are NUL-terminated with zeros after | text, seen in game for record 0 |
| Preset organisation id | record 0 matches the value in the earlier memory-dump test | destination known, meaning of the numbers not checked |
| Two preset flags | only 0 and 1 occur; the earlier test showed the loader skips a preset when cleared | behaviour partly known |
| 222 user settings per preset | named by the file; every one-byte value is 100 or less | structure only: units and choices unknown |
| 12 franchise options per preset | named by the file; only 0 and 1 occur | structure only: on/off is a guess |
| 238 counters | one byte array, all zero in this save | structure only |

The earlier test reported a 24-byte organisation table in memory, while the file holds 30 presets. That difference is
not explained. The port's own settings (`cfg.c`) are separate from these and give nothing to compare with.

## What is not proven

- That the game accepts an edit made by this tool anywhere except the one already tested (the first preset's name,
  where the bytes are identical).
- Which preset record the game treats as active, and whether it clamps or rejects out-of-range choices. The tool only
  checks that a number fits its bytes.
- Whether numbers are signed. Every settings field is one byte per element and is read as unsigned.
- Whether a byte array is text. The file does not say, so the caller chooses.
- Other save types. Franchise saves have fields whose size is not width times count, which this version refuses.
- Only one distinct game-written settings save exists on this machine (the other copies are identical or are our own
  edit), so a save with different record counts has not been read. 1.0.15 was not checked.

## How to run

From the repository root. Work on a copy of the slot folder.

```text
python -I -m unittest discover -s tools -p test_save_reader.py -v
python -I tools/save_reader.py check <slot folder>
python -I tools/save_reader.py list  <slot folder>
python -I tools/save_reader.py get   <slot folder> CLASS RECORD FIELD
python -I tools/save_reader.py set   <slot folder> CLASS RECORD FIELD --int N --out <new folder>
```

`set` writes a new folder and refuses an existing one. The tests on a real save look for the copy in
`work/scratch/savepoc/profile/save/u/<settings slot>` (or `MLB_SAVE_COPY`) and are skipped without it; the in-game
proof test also needs `work/scratch/savepoc/proven/<settings slot>`. The one-bit test over the real archive takes
most of the run time (about 90 s in all).

## What an in-game check would need (not done)

1. Take the game lock and copy the whole profile to a scratch folder. A profile holding only the save slot fails,
   because the game makes a new user id and never reads it.
2. With `set`, change a visible user setting in one preset of the copied slot, and a preset name other than the first.
   Replace the slot in the scratch profile with the new folder.
3. Start the game with `--profile` on the scratch folder, open the settings screens and read both values. Load a
   different preset as a control.
4. Change one setting in the menu, let the game save, quit, and run `check` and `get` on the game-written file. That
   gives a second genuine sample, shows which record is active and maps one value to its on-screen choice.
