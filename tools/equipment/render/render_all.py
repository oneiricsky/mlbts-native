"""Renders the item picture of equipment items from the player's own install: the part pictures.py calls for every
item, and a small command for looking at results.

    python -I tools/equipment/render/render_all.py --game <install folder> [--only slot_bats,slot_gear]
                                                   [--ids 54,1,2] [--out DIR] [--sheet sheet.png]

Slot modules (slot_*.py) each handle some MLBEQUIPMENT.JSON "type"s. Contract for a slot module:
    TYPES = {0, 8}                       # MLBEQUIPMENT.JSON eqlist "type" values it handles
    def render_item(e, ctx) -> (512, 512, 4) uint8 RGBA array, or None (None = could not render; reported)
        e   : the eqlist dict of one item (id, type, name, brand, tier, modelname, gfxinfo, ...)
        ctx : Ctx below (paths, makers, cached banks/models)
The command writes RTTSMOD_EQ_<id>.png into --out and, with --sheet, a contact sheet of what it rendered.
Needs numpy and lz4.
"""
import argparse
import importlib
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import png  # noqa: E402
from mod import Model  # noqa: E402
from tx12 import Bank  # noqa: E402

MODULES = ['slot_bats', 'slot_gloves', 'slot_gear']


def equipment_list(romfs):
    """The game's equipment list as it shipped (its .orig when equipment.py has changed the file)."""
    f = Path(romfs) / 'FRONTEND' / 'EQUIPMENT' / 'MLBEQUIPMENT.JSON'
    orig = f.with_name(f.name + '.orig')
    return orig if orig.exists() else f


class Ctx:
    def __init__(self, romfs):
        self.romfs = Path(romfs)
        eq = json.loads(equipment_list(romfs).read_text(encoding='utf-8'))
        self.makers = {m['id']: m for m in eq['makers']}
        self.all_items = eq['eqlist']                            # every entry, file order (the game's record order)
        # what equipment.py adds: enabled entries, without tier -1 and the "OFF" entries
        self.items = [e for e in eq['eqlist']
                      if e.get('enb') and e.get('tier', 0) >= 0 and e['name'].strip().upper() != 'OFF']
        self._banks, self._models = {}, {}

    def bank(self, rel):
        """A TX12 bank by romfs-relative path (cached), e.g. 'NSW/OBJECTS/G4BATTEXTURES.TEX'."""
        if rel not in self._banks:
            self._banks[rel] = Bank(self.romfs / rel)
        return self._banks[rel]

    def model(self, rel):
        """A model by romfs-relative path without extension (cached), e.g. 'NSW/OBJECTS/G4GAMEBAT'."""
        if rel not in self._models:
            self._models[rel] = Model(self.romfs / (rel + '.MOD'))
        return self._models[rel]

    def maker(self, e):
        return self.makers.get(e['brand'], {}).get('name', '')


def modules(names=None):
    return [importlib.import_module(n) for n in (names or MODULES) if (HERE / f'{n}.py').exists()]


def out_name(e):
    return f'RTTSMOD_EQ_{e["id"]}'


def render_one(e, ctx, mods):
    """(picture, '') or (None, why not)."""
    m = next((m for m in mods if e['type'] in m.TYPES), None)
    if m is None:
        return None, f'no renderer for type {e["type"]}'
    try:
        px = m.render_item(e, ctx)
    except Exception as ex:                                      # a model or texture this install lacks, a bad file
        return None, f'{type(ex).__name__}: {ex}' + '\n' + traceback.format_exc()
    if px is None:
        return None, 'its model or textures were not found'
    return px, ''


def sheet(pictures, cols=12, cell=128, bg=(34, 38, 50)):
    """A contact sheet (uint8 RGBA) of 512x512 pictures over a dark background."""
    rows = (len(pictures) + cols - 1) // cols
    out = np.zeros((rows * cell, cols * cell, 4), np.float64)
    out[..., :3], out[..., 3] = bg, 255
    k = 512 // cell
    for i, px in enumerate(pictures):
        p = px.astype(np.float64)
        a = p[..., 3:4] / 255
        small_a = a.reshape(cell, k, cell, k, 1).mean((1, 3))
        small = (p[..., :3] * a).reshape(cell, k, cell, k, 3).mean((1, 3))      # premultiplied average
        y, x = (i // cols) * cell, (i % cols) * cell
        out[y:y + cell, x:x + cell, :3] = small + out[y:y + cell, x:x + cell, :3] * (1 - small_a)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', type=Path, required=True, help='the install folder (the one with mlb.exe)')
    ap.add_argument('--only', help='comma-separated slot modules (default: all)')
    ap.add_argument('--ids', help='comma-separated eqlist ids to render')
    ap.add_argument('--out', type=Path, help='folder for RTTSMOD_EQ_<id>.png')
    ap.add_argument('--sheet', type=Path, help='write a contact sheet PNG of what was rendered')
    a = ap.parse_args()
    ctx = Ctx(a.game / 'game' / 'romfs')
    mods = modules(a.only.split(',') if a.only else None)
    ids = {int(x) for x in a.ids.split(',')} if a.ids else None
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
    done, failed, thumbs = 0, [], []
    t0 = time.time()
    for e in ctx.items:
        if ids and e['id'] not in ids:
            continue
        px, why = render_one(e, ctx, mods)
        if px is None:
            failed.append((e, why))
            continue
        if a.out:
            png.write(a.out / f'{out_name(e)}.png', px)
        thumbs.append(px)
        done += 1
    print(f'rendered {done}, failed {len(failed)} in {time.time() - t0:.0f}s')
    for e, why in failed:
        print(f'  failed: {e["id"]} type {e["type"]} {ctx.maker(e)} {e["name"]!r} [{e["modelname"].strip()} | '
              f'{e["gfxinfo"].strip()}]: {why.splitlines()[0]}')
    if a.sheet and thumbs:
        png.write(a.sheet, sheet(thumbs))


if __name__ == '__main__':
    main()
