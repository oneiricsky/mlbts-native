"""Bats (MLBEQUIPMENT.JSON type 0) and bat grips (type 8), rendered from NSW/OBJECTS/G4GAMEBAT + G4BATTEXTURES.TEX.

Which bat the game actually draws (bat loader main+0x16cc5f0, lifted in work/gen/main/main_0161.c):
  This Switch build runs in the game's "mobile" mode (flag byte main+0x463cb48): an equipped bat whose MLBEQUIPMENT.JSON
  'enb_mobile' is not 1 is swapped for the FIRST entry in the file of the same type and maker with enb_mobile == 1
  (main+0x1757b80). Each maker has one such bat (Axe two); BWP has none, so its bats fall back to style 0 (zGeneric
  'Basic'). Entries are looked up by their 'style' (record +6), which is also what the player's appearance stores;
  legend bats (style > 129) take the bat-skin path instead, see bat_spec().
  equipment.py sets enb_mobile = 1 on every item it adds, so each bat is drawn from its own fields
  (MOD_SETS_ENB_MOBILE below); set it False to picture the game's substitution instead.

Item fields (comma-separated tokens in modelname + gfxinfo), as the game parses them:
  dg=<part>     geometry part of G4GAMEBAT ('$_torpedo' -> bat_Torpedo); default 'bat' (no maker-specific shape:
                the binary has no 'bat_Axe' reference, so Axe bats use 'bat' too)
  cup=off       cupless end -> part bat_noCup
  bclr=<tex>    finish/colour texture on UV_color ('$_LS_T3' -> bat_ls_t3-color); default 'bat' (natural wood)
  tx=<tex>      bats: the brand/model decal (BC4 single-channel mask, format code 19) on UV_logo0; default
                'zmissing' (not in the bank) -> no decal
                grips: the grip's colour texture, put on the batGrip_spiral wrap
'$_' expands to 'bat_' / 'batGrip_', '$(B)' to the maker name with spaces removed (texture lookup ignores case), except
the special cases in the game: zGeneric -> generic, Lizard Skins -> lizardskin, and for bats also Sam Bat -> sambats,
Cooperstown BatCo -> cooperstown.

Pictures: bats whole, barrel up-right on the diagonal, decal turned to the camera; grips: the handle half of a natural
wood bat with the grip wrapped on it, same diagonal, filling the frame.
"""
import math
import re

import numpy as np

from render import render, rotation
from tx12 import decode_bcn

TYPES = {0, 8}
BANK = 'NSW/OBJECTS/G4BATTEXTURES.TEX'
MODEL = 'NSW/OBJECTS/G4GAMEBAT'
YAW, PITCH, ROLL = 90, 12, 42
GRIP_PART = 'batGrip_spiral'

_cache = {}


# ---- textures ---------------------------------------------------------------------------------------------------------

def _tex(bank, name):
    """(kind, float array) of '<name>' or None. kind 'rgba' -> (h,w,4); 'mask' (BC4, format 19) -> (h,w)."""
    key = ('tex', name.lower())
    if key in _cache:
        return _cache[key]
    e = bank.find(name)
    out = None
    if e is not None:
        fmt = e.raw[0x12c]
        L = e.levels[0]
        data = bank.level0_bytes(e)
        n = {6: 3, 7: 3, 13: 1, 19: 4, 22: 7}.get(fmt)
        if n is not None:
            px = decode_bcn(data, L.w, L.h, n).astype(np.float32) / 255.0
            out = ('mask', px[..., 0]) if fmt == 19 else ('rgba', px)       # BC4: one channel
    _cache[key] = out
    return out


def _brand_tokens(bank):
    if 'brands' not in _cache:
        s = set()
        for n in bank.entries:
            m = re.match(r'(bat|batgrip)_([a-z0-9]+)', n)
            if m:
                s.add(m.group(2))
        _cache['brands'] = s
    return _cache['brands']


def brand_token(maker, bank):
    full = re.sub(r'[^a-z0-9]', '', maker.lower())
    words = re.findall(r'[a-z0-9]+', maker.lower())
    known = _brand_tokens(bank)
    cands = [full, full[:-1] if full.endswith('s') else full + 's', words[0] if words else '']
    if full.startswith('z'):
        cands.append(full[1:])                                   # zGeneric -> generic
    for c in cands:
        if c in known:
            return c
    return full


def fields(e):
    out = {}
    for tok in (e.get('modelname', '') + ',' + e.get('gfxinfo', '')).split(','):
        if '=' in tok:
            k, v = tok.split('=', 1)
            out[k.strip().lower()] = v.strip()
    return out


def expand(v, prefix, brand):
    return v.replace('$_', prefix + '_').replace('$(B)', brand)


# ---- geometry -----------------------------------------------------------------------------------------------------------

def _model(ctx):
    if 'model' not in _cache:
        m = ctx.model(MODEL)
        parts = {p['name'].lower(): p for p in m.parts}
        _cache['model'] = (m, m.positions[:, :3].astype(np.float32), m.attrs['Normal'].astype(np.float32),
                           m.uv('UV_color').astype(np.float32), m.uv('UV_logo0').astype(np.float32), parts)
    return _cache['model']


def _turn_to_camera(pos, nrm, face_normal):
    """Rotate about the bat axis (z) so face_normal (model space) faces the camera of YAW/PITCH/ROLL."""
    R = rotation(math.radians(YAW), math.radians(PITCH), math.radians(ROLL))
    view = R.T @ np.array([0.0, 0.0, 1.0])                       # camera direction in model space
    a = math.atan2(view[1], view[0]) - math.atan2(face_normal[1], face_normal[0])
    c, s = math.cos(a), math.sin(a)
    Rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float32)
    return pos @ Rz.T, nrm @ Rz.T


WOOD_BASE = np.array([0.84, 0.62, 0.61])        # mean of the untinted 'bat-color' wood
NATURAL = np.array([0.87, 0.71, 0.49])          # natural maple, for the picture
GRIP_DARK = [(0.07, 0.07, 0.08), (0.74, 0.10, 0.12), (0.10, 0.16, 0.38), (0.45, 0.45, 0.47)]
GRIP_LIGHT = [(0.93, 0.93, 0.92), (0.74, 0.10, 0.12), (0.10, 0.16, 0.38), (0.45, 0.45, 0.47)]
GRIP_CAMO = [(0.36, 0.38, 0.24), (0.17, 0.20, 0.12), (0.52, 0.44, 0.31), (0.10, 0.10, 0.08)]


def _finish(t):
    """Opaque copy of a bat finish texture. Tintable finishes (alpha < 0.5 everywhere: alpha = colour zone, e.g.
    handle 0.05 / barrel 0.15; the player picks the colours) get the natural-wood tint; painted ones are kept."""
    c = t.copy()
    if c[..., 3].max() < 0.5:
        c[..., :3] = np.clip(c[..., :3] * (NATURAL / WOOD_BASE), 0, 1)
    c[..., 3] = 1.0
    return c


def _grip_colors(t, name):
    """Opaque grip texture. Texels with alpha >= 0.5 are the fixed print; the rest are player-tinted zones
    (zone = round(alpha * 20)) whose white base is multiplied by a default colourway: camo greens for camo, white
    tape for the generic tape, else black with red/navy/grey accents (white when the fixed print is dark)."""
    c = t.copy()
    a = c[..., 3]
    tint = a < 0.5
    if tint.any():
        fixed = ~tint
        name = name.lower()
        if "camo" in name:
            pal = GRIP_CAMO
        elif name.endswith('_generic'):
            pal = GRIP_LIGHT
        elif fixed.any() and float(c[..., :3][fixed].mean()) < 0.5:
            pal = GRIP_LIGHT
        else:
            pal = GRIP_DARK
        z = np.clip(np.rint(a * 20).astype(int), 0, len(pal) - 1)
        col = np.asarray(pal, np.float32)[z]
        c[..., :3] = np.where(tint[..., None], c[..., :3] * col, c[..., :3])
    c[..., 3] = 1.0
    return c


def _ink(color):
    """Decal ink: black on light finishes, near-white on dark ones (the decal texture is only a mask)."""
    lum = float((color[..., :3] @ np.array([0.3, 0.59, 0.11])).mean())
    return np.array([0.04, 0.04, 0.04]) if lum > 0.42 else np.array([0.93, 0.92, 0.88])


def render_bat(ctx, part, bclr, tx, color_bank=BANK):
    m, pos, nrm, uvc, uvl, parts = _model(ctx)
    bank = ctx.bank(BANK)
    p = parts.get(part.lower())
    t = _tex(ctx.bank(color_bank), bclr + '-color')
    if p is None or t is None or t[0] != 'rgba':
        return None
    color = _finish(t[1])
    logo = None
    tris = p['tris']
    idx = np.unique(tris)
    face = np.array([1.0, 0.0, 0.0])
    if tx:
        mk = _tex(bank, tx + '-color')
        if mk is None:
            return None
        if mk[0] == 'mask':
            a = mk[1]
        else:
            a = mk[1][..., 3]
        logo = np.zeros(a.shape + (4,), np.float32)
        logo[..., :3] = _ink(color)
        logo[..., 3] = a
        # where the decal sits on the bat: the vertices whose logo UV lands on non-empty mask texels
        u = uvl[idx]
        inside = (u[:, 0] >= 0) & (u[:, 0] <= 1) & (u[:, 1] >= 0) & (u[:, 1] <= 1)
        if inside.any():
            h, w = a.shape
            ui = np.clip((u[inside, 0] * (w - 1)).astype(int), 0, w - 1)
            vi = np.clip((u[inside, 1] * (h - 1)).astype(int), 0, h - 1)
            wt = a[vi, ui] + 1e-3
            fn = (nrm[idx][inside] * wt[:, None]).sum(0)
            if np.hypot(fn[0], fn[1]) > 1e-6:
                face = fn
    P, N = _turn_to_camera(pos, nrm, face)
    return render(P, N, tris, uvc, color, uv2=uvl, logo=logo, yaw=YAW, pitch=PITCH, roll=ROLL, margin=0.04)


def render_grip(ctx, tx):
    m, pos, nrm, uvc, uvl, parts = _model(ctx)
    bank = ctx.bank(BANK)
    g = _tex(bank, tx + '-color')
    wood = _tex(bank, 'bat-color')
    if g is None or g[0] != 'rgba' or wood is None:
        return None
    grip = _grip_colors(g[1], tx)
    woodt = _finish(wood[1])
    bat, gp = parts['bat'], parts[GRIP_PART.lower()]
    z = pos[:, 2]
    bt = bat['tris'][(z[bat['tris']] < -0.1).all(1)]             # the handle of the bat
    tris = np.vstack([bt, gp['tris']])
    # one draw, two textures: grip in the colour slot (wraps), wood through the decal slot on the bat's own vertices
    uv2 = np.full_like(uvc, -5.0)
    bidx = np.unique(bt)
    uv2[bidx] = np.clip(uvc[bidx], 0.0, 1.0)
    return render(pos, nrm, tris, uvc, grip, uv2=uv2, logo=woodt, yaw=YAW, pitch=PITCH, roll=ROLL, margin=0.04)


GAME_BAT_BRANDS = {'zGeneric': 'generic', 'Lizard Skins': 'lizardskin', 'Sam Bat': 'sambats',
                   'Cooperstown BatCo': 'cooperstown'}


def game_bat_brand(maker):
    """'$(B)' for bats, as the bat loader builds it (special cases, else the maker name without spaces)."""
    return GAME_BAT_BRANDS.get(maker, maker).replace(' ', '').lower()


MOD_SETS_ENB_MOBILE = True


def resolve_bat(e, ctx):
    """The entry the game really draws for bat e (None = item id 0: zGeneric, no fields). See the module docstring."""
    if MOD_SETS_ENB_MOBILE or e.get('enb_mobile') == 1:
        return e
    return next((x for x in ctx.all_items
                 if x['type'] == e['type'] and x['brand'] == e['brand'] and x.get('enb_mobile') == 1), None)


SKIN_BANK = 'NSW/OBJECTS/BATSKINS.TEX'
SKIN_CSV = 'PS4/CHARACTERS/MASTERFILES/ACCESSORIES/'


def skin_color(ctx, index):
    """Colour texture name of bat skin <index> (ACCMODELS_BATSKINS.CSV row 'T, SKIN, index, ...' -> TXC_ abbreviation
    -> ACCPARTS_BATSKINS.CSV asset name), without '-color'; None when there is no such skin."""
    if 'skins' not in _cache:
        d = ctx.romfs / SKIN_CSV
        parts = {}
        for line in (d / 'ACCPARTS_BATSKINS.CSV').read_text(encoding='latin-1').splitlines():
            p = [x.strip() for x in line.split(',')]
            if len(p) >= 2 and not p[0].startswith('#'):
                parts[p[0]] = p[1]
        rows = {}
        for line in (d / 'ACCMODELS_BATSKINS.CSV').read_text(encoding='latin-1').splitlines():
            p = [x.strip() for x in line.split(',')]
            if len(p) > 5 and p[0] == 'T' and p[1] == 'SKIN':
                rows[int(p[2])] = parts.get(p[5])
        _cache['skins'] = rows
    name = _cache['skins'].get(index)
    return name[:-len('-color')] if name and name.lower().endswith('-color') else name


def bat_spec(e, ctx):
    """(part, bclr, tx or None, colour bank) of the bat the game shows for entry e.

    The player's appearance stores the entry's 'style' (equipment.py writes it as servoy_equipment_id). The bat
    loader (main+0x16cc5f0) sends a style above 129 to the skin path (main+0x16cbf40): skin index = style - 130, a row
    of ACCMODELS_BATSKINS.CSV, drawn with that skin's own colour texture from BATSKINS.TEX and no decal. All legend
    bats (TheShow) are such skins (e.g. M. Mantle M110: style 171 -> skin 41 batskin_lsmickeymantle)."""
    if e.get('style', 0) > 129:
        skin = skin_color(ctx, e['style'] - 130)
        if skin:
            f = fields(e)
            part = 'bat_noCup' if f.get('cup', '').lower() == 'off' else 'bat'
            return part, skin, None, SKIN_BANK
    r = resolve_bat(e, ctx)
    maker = ctx.maker(r) if r is not None else 'zGeneric'
    brand = game_bat_brand(maker)
    f = fields(r) if r is not None else {}
    part = expand(f.get('dg', 'bat'), 'bat', brand)
    if f.get('cup', '').lower() == 'off' and part.lower() == 'bat':
        part = 'bat_noCup'
    bclr = expand(f.get('bclr', 'bat'), 'bat', brand)
    tx = expand(f.get('tx', 'zmissing'), 'bat', brand)
    if _tex(ctx.bank(BANK), tx + '-color') is None:
        tx = None                                                # e.g. 'zmissing': the game draws no decal
    return part, bclr, tx, BANK


def render_item(e, ctx):
    bank = ctx.bank(BANK)
    if e['type'] == 8:
        brand = brand_token(ctx.maker(e), bank)
        return render_grip(ctx, expand(fields(e).get('tx', '$_$(B)'), 'batgrip', brand))
    return render_bat(ctx, *bat_spec(e, ctx))
