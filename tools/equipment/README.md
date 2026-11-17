# Road to the Show equipment, offline

Offline, the Equipment screen of Road to the Show is empty ("You do not own any of this item"): the game gets its
equipment items from the online Packages. This tool adds them from the player's own game files, so the screen works
without a connection. It is an option of the setup ("Unlock all Road to the Show equipment for offline play") and a
button on its launcher screen; it can also be run by hand:

```
python -I tools/equipment/equipment.py install   --game <install folder>
python -I tools/equipment/equipment.py uninstall --game <install folder>
python -I tools/equipment/equipment.py status    --game <install folder>
```

Close the game first. `install` can be run again at any time; `uninstall` puts every file back as it was.

## What the player gets

- Every enabled entry of the game's equipment list (bats, gloves, cleats, catcher's gear, guards, sleeves, bat grips,
  eyewear, sliding mitts), the pregame rituals and the socks: 491 items in 1.0.20, all owned from the start.
- Each item works as the game means it to: its slot boosts a perk category by a percentage that depends on the item's
  rarity (`FRONTEND/RTTS/EQUIPMENTDESCRIPTIONS.XML`), and it shows on the player.
- A picture for every item, rendered on the player's PC from the item's own model and textures.

Nothing is downloaded, and no game file leaves the PC.

Owning everything from the start is one of two ways to play. The other is the setup's packages option
([`tools/packages`](../packages/README.md)), where the player earns the equipment from packs as in the online game:
the setup then adds the items with `install --no-own`, so they are in the game but none is owned yet.

## What it changes

Four files under `game/romfs`, each kept beside itself as `<name>.orig` first:

| File | Change |
| --- | --- |
| `FRONTEND/RTTS/INVENTORYDATA.XML` | the items, added to the item catalog between two `rtts-equipment` comments |
| `FRONTEND/RTTS/INVQUANTITYDATA.XML` | one of each, in the starting inventory |
| `FRONTEND/EQUIPMENT/MLBEQUIPMENT.JSON` | `enb_mobile` set on the added entries: this Switch build only draws entries that have it |
| `NSW/LIVECONTENT/LIVE.TEX` | the item pictures, appended to the game's image bank (the original is a 1.4 GB copy) |

`game/romfs_list.tsv` gets the new sizes of those four, so the index stays true to the files (`mlb.exe --probe-fs`
sizes a sample of them against it). The pictures are kept in `<install folder>/equipment-pictures` (about 115 MB), so a later install does not render them
again. A changed file is written beside the old one and swapped in, never written in place.

Added items have ids from 800000, away from the game's own (46000 to 50000). A save made with the equipment keeps
those ids for what the player has equipped.

## The pieces

| File | What it does |
| --- | --- |
| `equipment.py` | the command: which items, the two XML files, `enb_mobile`, install / uninstall / status |
| `rarities.json` | each item's rarity, one row per item |
| `pictures.py` | renders every item once, on several cores at low priority, into the picture folder |
| `live_bank.py` | the image bank's format; appends pictures to it and checks the result |
| `render/` | readers for the game's models (`mod.py`) and texture banks (`tx12.py`, BC1/3/4/5/7 in numpy), a small numpy rasteriser (`render.py`), one module per kind of item (`slot_*.py`), and the BC7 encoder (`bc7.py`) |
| `romfs_index.py` | keeps `romfs_list.tsv` in step |
| `tests/` | tests that need no game files: `python -I -m unittest discover -s tools/equipment/tests` |

It needs numpy and lz4, which the setup's Python has.

`render/render_all.py --game <install folder> --ids 54,469 --out <folder> --sheet sheet.png` writes pictures as PNG
files, for looking at what the renderer makes.

## Rarities

A rarity is not in the game files: the game receives it with the online catalog. `rarities.json` therefore lists one
for each item (an item it does not list is Silver). For the 422 items the game's public item database has, the
rarity is the one shown there. The other 69 are not in it and were assigned by hand: unbranded gear is Common, the
legends' bats are Diamond, and the rest take the rarity of the nearest item of the same maker, or Silver.

## Checked on

Game version 1.0.20: in the game, each of the 16 slots lists its items with their pictures, names and rarities;
`mlb.exe --probe-fs` passes with the equipment in place; `uninstall` returns the four files and the index byte for
byte; and the setup's add, repair, remove and add-again paths behave as described above.

1.0.15 has not been run. The tool reads everything from the game data and changes no code, so nothing in it is tied
to an address of one version; an equipment entry of 1.0.15 that `rarities.json` does not list would be Silver.
