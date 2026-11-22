"""Item pictures for batting gloves (type 1), fielding gloves (3), eyewear (7), catcher masks (10) and compression
sleeves (13), rendered from the game's own models and textures on the player's disk (see render_all.py for the contract).

Resolution rules (all from the install's own data):
  batting gloves  NSW G4BATGLOVE_L_MLB15 (part batGloveHand_L): color batglove_<modelname minus '$_'>-color via UV_color,
                  logo layer <same>_logos-color via UV_logo<uv=N> (none when gfxinfo says 'nologo'), generic
                  'BatGlove1..3' -> batglove1..3. Strap: BAT_GLOVE_STRAPS part from gfxinfo 'dg=' ('$_' ->
                  batGloveStrap_, '$(B)' -> maker name without spaces, + '_L'; 'batGloveWrist' for generics).
  fielding gloves the PS4 build's own glove tables (PS4/CHARACTERS/MASTERFILES/ACCESSORIES/ACCMODELS_FIELDGLOVES.CSV,
                  ACCMODELS_FGLOVEWEBS.CSV, ACCPARTS_FIELDGLOVES.CSV): row (brand, tier, glove type) -> back
                  draw group (GloveInfielder / GloveMizuno / ...), extra draw group, base texture, brand-logo
                  texture (UV_brand), tier-logo texture (UV_tier, prefixed infielder_/catcher_); the web table
                  -> web draw group + web texture. Catcher-only items (split=C) use the catcher mitt.
  eyewear         AND/CHARACTERS/ACCESSORIES/EYEWEAR/<modelname>.MOD (NSW for the 3 that exist there), color texture
                  and _logos layer named in the model, from NSW PLAYERACC.TEX.
  catcher masks   per-item table MASKS below (model + textures named by the models themselves).
  sleeves         the item's 'tx=' texture (PLAYERACC.TEX: colour masks + an alpha that says where the sleeve is) on
                  MALEBODY24's Arm_L mesh, drawn only where that alpha is set (the sleeve is a texture layer on the
                  arm); G-Form adds COMPSLEEVEPAD_GFORM.
Colours: glove / bat-glove / mask / frame / sleeve textures carry run-time tint regions (team / user colours), so
pictures use one fixed default colourway per slot (tinted(), shaded(), sleeve_colour()); pre-coloured artwork kept.
Strap fallback: a brand without a strap of the item's tier uses the brand's strap of another tier (ARiA T1).
"""
import csv
import math
import re
from pathlib import Path

import numpy as np

import render as R

TYPES = {1, 3, 7, 10, 13}

MF = 'NSW/CHARACTERS/MASTERFILES'
PLAYERACC = MF + '/PLAYERACC.TEX'

_tex_cache = {}


def tex(ctx, bank, name):
    """float RGBA array of a texture (case-insensitive name, '-color' added when missing) or None."""
    if not name:
        return None
    n = name.lower()
    if not n.endswith(('-color', '-normal')):
        n += '-color'
    key = (bank, n)
    if key not in _tex_cache:
        _tex_cache[key] = R.load_texture(ctx.bank(bank), n)
    return _tex_cache[key]


def mesh(m, tris, color=None, uv='UV_color', logo=None, uv2=None, logo2=None, uv3=None, flat=(0.6, 0.6, 0.6),
         gloss=0.18, cutout=0.0):
    """A draw item from Model m: triangles (absolute indices), textures and the UV attribute names to use."""
    def att(name):
        if name is None or name not in m.attrs:
            return np.zeros((m.nverts, 2), np.float32)
        return m.attrs[name][:, :2]
    return R.item(m.positions, m.attrs['Normal'][:, :3], tris, att(uv), color, att(uv2), logo, att(uv3), logo2,
                  flat, gloss, cutout)


def draw(items, yaw=-40, pitch=20, roll=0, margin=0.06, size=512):
    """Render several draw items in one view (shared fit), into a 512x512 RGBA picture (transparent background)."""
    return R.render_items(items, yaw, pitch, roll, margin, size)


def tinted(arr, palette, keep, ref, key):
    """The game colours glove textures at run time: alpha holds a tint-region id (multiples of 8/255), rgb the
    shading. Pictures use a fixed default colourway: region -> palette colour * (luminance / ref); regions in `keep`
    (pre-coloured artwork) and unknown ids stay as they are."""
    if arr is None:
        return None
    if key in _tex_cache:
        return _tex_cache[key]
    out = arr.copy()
    ids = np.round(arr[..., 3] * 255 / 8).astype(int) * 8
    lum = arr[..., :3].mean(-1, keepdims=True) / ref
    for rid, col in palette.items():
        if rid in keep:
            continue
        msk = ids == rid
        if msk.any():
            out[msk, :3] = np.clip(lum * np.array(col, np.float32), 0, 1)[msk]
    out[..., 3] = 1.0
    _tex_cache[key] = out
    return out


def parts(m, pred):
    return [p for p in m.parts if pred(p['name']) and len(p['tris'])]


def part(m, name):
    """First part with this exact name (case-insensitive) having triangles, else None."""
    n = name.lower()
    return next((p for p in m.parts if p['name'].lower() == n and len(p['tris'])), None)


def btoken(maker):
    return re.sub(r'[^A-Za-z0-9]', '', maker)


# ---------------------------------------------------------------- batting gloves (type 1)
BATTEX = MF + '/G4BATGLOVESTEXTURES.TEX'
BATMODEL = MF + '/BODIES/STANDARDMALE/G4BATGLOVE_L_MLB15'
STRAPS = 'NSW/CHARACTERS/ACCESSORIES/BATTINGGLOVES/BAT_GLOVE_STRAPS'


def gfx(e):
    """gfxinfo as {key: value} (bare tokens -> True)."""
    out = {}
    for tok in e.get('gfxinfo', '').split(','):
        tok = tok.strip()
        if not tok:
            continue
        k, _, v = tok.partition('=')
        out[k.strip().lower()] = v.strip() if _ else True
    return out


def strap_part(m, e, ctx, g):
    dg = g.get('dg')
    if not dg:
        return None
    name = dg.replace('$_', 'batGloveStrap_').replace('$(B)', btoken(ctx.maker(e)))
    cands = [name + '_L']
    if name.lower().startswith('batglovestrap_cooperstownbatco'):
        cands.append('batGloveStrap_Cooperstown' + name[len('batGloveStrap_CooperstownBatCo'):] + '_L')
    if name.lower() == 'batglovewrist':
        cands = ['batGloveWrist_L']
    for c in cands:
        p = part(m, c)
        if p:
            return p
    for c in cands:                                   # an older / numbered variant of the same strap
        ps = [p for p in m.parts if p['name'].lower().startswith(c.lower() + '_') and len(p['tris'])]
        if ps:
            return ps[-1]
    # no strap of this tier: the brand's strap of another tier (e.g. ARiA T1 -> AriaT2)
    pre = 'batglovestrap_' + btoken(ctx.maker(e)).lower()
    ps = [p for p in m.parts if p['name'].lower().startswith(pre) and p['name'].lower().endswith('_l')
          and len(p['tris'])]
    return ps[0] if ps else None


# default colourway for the run-time tint regions: black shell, white finger/knuckle panels, grey trims
BAT_PAL = {224: (0.13, 0.13, 0.15), 256: (0.13, 0.13, 0.15), 240: (0.30, 0.30, 0.33), 208: (0.93, 0.93, 0.93),
           184: (0.55, 0.55, 0.58), 0: (0.13, 0.13, 0.15)}


def render_batglove(e, ctx, debug=None):
    g = gfx(e)
    mn = e['modelname'].strip()
    base = mn.replace('$_', 'batglove_').lower()
    color = tinted(tex(ctx, BATTEX, base), BAT_PAL, (168,), 0.95, ('tint', base))
    if color is None:
        return None
    logo = None if g.get('nologo') else tex(ctx, BATTEX, base + '_logos')
    uvn = g.get('uv')
    m = ctx.model(BATMODEL)
    items = [mesh(m, m.parts[0]['tris'], color, 'UV_color', logo, f'UV_logo{uvn}' if uvn else None)]
    sm = ctx.model(STRAPS)
    sp = strap_part(sm, e, ctx, g)
    if sp is not None:
        items.append(mesh(sm, sp['tris'], color, 'UV_color', logo, 'UV_decal' if logo is not None else None))
    if debug is not None:
        debug['strap'] = sp['name'] if sp else None
    return draw(items, **CAM_BAT)


CAM_BAT = dict(yaw=260, pitch=35, roll=200)


# ---------------------------------------------------------------- fielding gloves (type 3)
ACC = 'PS4/CHARACTERS/MASTERFILES/ACCESSORIES'
GLOVE_BANKS = [MF + '/GLOVEWEBSTEXTURES.TEX', MF + '/G4GLOVESALLTIERTEXTURES.TEX', MF + '/GLOVEBRANDLOGOSTEXTURES.TEX']
GLOVE_MODELS = {'IF': MF + '/BODIES/STANDARDMALE/G4GLOVEINFIELDER_L', 'C': MF + '/BODIES/STANDARDMALE/G4GLOVECATCHER_L',
                '1B': MF + '/BODIES/STANDARDMALE/G4GLOVEFIRSTBASE_L'}
BRAND_ABBR = {'zgeneric': 'GEN', 'nike': 'NIKE', 'rawlings': 'RAWL', 'wilson': 'WLSN', 'adidas': 'ADDS',
              'all-star': 'ASTR', 'marucci': 'MRCI', 'mizuno': 'MZNO', 'ssk': 'SSK', 'under armour': 'UARM',
              'easton': 'ESTN', '44 pro': '44PR', 'b45': 'B45', 'tater': 'TATR', 'asics': 'ASIC', 'warstic': 'WARS',
              'aria': 'ARIA', 'force3': 'FRC3', 'vintage/nlb': 'VNTG', 'louisville slugger': 'LSLG'}
WEB_ORDER = ['DG_PROI', 'DG_PROH', 'DG_1PC', 'DG_2PC', 'DG_TRAP', 'DG_POST', 'DG_BSKT']
_glove_tables = None


def _rows(ctx, name):
    rows = []
    for line in (ctx.romfs / ACC / name).read_text(encoding='latin1').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        rows.append([c.strip() for c in line.split(',')])
    return rows


def glove_tables(ctx):
    global _glove_tables
    if _glove_tables is None:
        parts_ = {r[0]: r[1] for r in _rows(ctx, 'ACCPARTS_FIELDGLOVES.CSV') if len(r) >= 2}
        models = {}
        for r in _rows(ctx, 'ACCMODELS_FIELDGLOVES.CSV'):
            if len(r) >= 15 and r[0] == 'T':
                models.setdefault((r[1], int(r[2]), r[3]), dict(
                    pattern=r[4], web_brand=r[7] == 'T', back=r[8], palm=r[9], extra=r[10], base=r[11],
                    blogo=r[13], tlogo=r[14]))
        webs = {}
        for r in _rows(ctx, 'ACCMODELS_FGLOVEWEBS.CSV'):
            if len(r) >= 15 and r[0] == '1':
                webs.setdefault((r[1], int(r[2]), r[3]), dict(tier_tx=r[5] == 'T', sel=r[6], dg=r[7], tx=r[8:15]))
        _glove_tables = parts_, models, webs
    return _glove_tables


def gtex(ctx, name):
    for b in GLOVE_BANKS:
        t = tex(ctx, b, name)
        if t is not None:
            return t
    return None


def glove_spec(e, ctx):
    """(glove type, model row, web dg name, web texture name) for a fielding glove item."""
    parts_, models, webs = glove_tables(ctx)
    abbr = BRAND_ABBR.get(ctx.maker(e).lower(), 'GEN')
    split = gfx(e).get('split', '')
    gtype = 'C' if split == 'C' else 'IF'
    row = models.get((abbr, e['tier'], gtype)) or models.get((abbr, e['tier'], 'IF'))
    if row is None:                                  # nearest tier of the brand, else generic
        cands = sorted((abs(k[1] - e['tier']), k) for k in models if k[0] == abbr and k[2] == gtype)
        row = models[cands[0][1]] if cands else models[('GEN', 0, gtype)]
    w = webs.get((abbr, e['tier'], gtype)) or webs.get(('GEN', 0, 'IF'))
    if w['sel'] == 'DG_ALL':
        web_dg, web_tx = w['dg'], w['tx'][0]
    elif w['sel'] in WEB_ORDER:
        web_dg, web_tx = w['dg'], w['tx'][WEB_ORDER.index(w['sel'])]
    else:
        web_dg, web_tx = 'DG_PROI', w['tx'][0]
    return gtype, row, web_dg, web_tx


# default colourway for the run-time tint regions: classic tan leather, darker laces and binding
GLOVE_PAL = {0: (0.74, 0.48, 0.27), 16: (0.74, 0.48, 0.27), 32: (0.56, 0.35, 0.19), 48: (0.70, 0.45, 0.25),
             64: (0.34, 0.21, 0.12), 88: (0.80, 0.55, 0.32), 104: (0.62, 0.40, 0.22), 120: (0.70, 0.45, 0.25)}


def render_fglove(e, ctx, debug=None):
    parts_, models, webs = glove_tables(ctx)
    gtype, row, web_dg, web_tx = glove_spec(e, ctx)
    m = ctx.model(GLOVE_MODELS[gtype])
    pn = lambda dg: parts_.get(dg, '') if dg not in ('DG_NONE', 'DG_ALL') else ''
    bn = parts_.get(row['base'])
    base = tinted(gtex(ctx, bn), GLOVE_PAL, (256,), 0.42, ('tint', bn))
    blogo = gtex(ctx, parts_.get(row['blogo'])) if row['blogo'] != 'TX_NOP' else None
    tl = parts_.get(row['tlogo']) if row['tlogo'] != 'TX_NOP' else None
    prefix = {'IF': 'infielder_', 'C': 'catcher_', '1B': 'firstbase_'}[gtype]
    tlogo = gtex(ctx, prefix + tl) if tl else None
    items, names = [], []
    body = part(m, pn(row['back']))
    if body is None:
        return None
    items.append(mesh(m, body['tris'], base, 'UV_color', blogo, 'UV_brand', tlogo, 'UV_tier', gloss=0.12))
    names.append(body['name'])
    for dg in (row['palm'], row['extra']):
        p = part(m, pn(dg)) if pn(dg) else None
        if p is not None:
            items.append(mesh(m, p['tris'], base, 'UV_color', blogo, 'UV_brand', tlogo, 'UV_tier', gloss=0.12))
            names.append(p['name'])
    if gtype == 'IF' and pn(web_dg):
        wp = part(m, pn(web_dg))
        wn = parts_.get(web_tx)
        wt = tinted(gtex(ctx, wn), GLOVE_PAL, (256,), 0.42, ('tint', wn))
        if wp is not None:
            items.append(mesh(m, wp['tris'], wt if wt is not None else base, 'UV_color', blogo, 'UV_brand', tlogo,
                              'UV_tier', gloss=0.12))
            names.append(wp['name'])
    if debug is not None:
        debug.update(parts=names, base=parts_.get(row['base']), blogo=parts_.get(row['blogo']), tlogo=tl,
                     web=(web_dg, parts_.get(web_tx)))
    return draw(items, **(CAM_GLOVE if gtype == 'IF' else CAM_CATCH))


CAM_GLOVE = dict(yaw=330, pitch=30, roll=0)
CAM_CATCH = dict(yaw=330, pitch=30, roll=0)


# ---------------------------------------------------------------- eyewear (type 7)
def model_any(ctx, rel_under_characters):
    """(rel path, Model) from NSW, else the AND build's copy of the same model (same IFF0 format)."""
    for plat in ('NSW', 'AND'):
        rel = f'{plat}/CHARACTERS/{rel_under_characters}'
        if (ctx.romfs / (rel + '.MOD')).exists() and (ctx.romfs / (rel + '.0.MOD')).exists():
            return rel, ctx.model(rel)
    return None, None


def color_and_logos(ctx, m, bank=PLAYERACC):
    """The model's own '-color' textures: (base, logos) arrays (logos = the '_logos' one)."""
    cols = [t[:-6] for t in m.textures if t.lower().endswith('-color')]
    logos = next((t for t in cols if t.lower().endswith('_logos')), None)
    base = next((t for t in cols if not t.lower().endswith('_logos') and not t.lower().startswith(('gray_', 'helmet', 'cap'))), None)
    return tex(ctx, bank, base), tex(ctx, bank, logos), base, logos


def render_eyewear(e, ctx, debug=None):
    mn = e['modelname'].strip()
    rel, m = model_any(ctx, 'ACCESSORIES/EYEWEAR/' + mn.upper())
    if m is None:
        return None
    col, logo, bn, ln = color_and_logos(ctx, m)
    col = shaded(col, FRAME_COL, ('frame', bn), max_sat=0.12)
    items = [mesh(m, p['tris'], col, 'UV_color', logo, 'UV_color' if logo is not None else None, gloss=0.35)
             for p in m.parts if len(p['tris']) and 'lowlod' not in p['name'].lower()]
    if debug is not None:
        debug.update(model=rel, base=bn, logos=ln, parts=[p['name'] for p in m.parts])
    return draw(items, **CAM_EYE)


FRAME_COL = (0.16, 0.16, 0.18)     # default frame colour for the run-time tinted (grey) frame texels
CAM_EYE = dict(yaw=40, pitch=15, roll=0)


# ---------------------------------------------------------------- catcher masks (type 10)
# item id -> (model under CHARACTERS/MASTERFILES, base texture, logos texture); the item's own model where the data
# names it (CatcherMask_Evo / _Evo2Pc), else the brand's mask model + textures of the same name in PLAYERACC.TEX
MASKS = {
    210: ('CATCHERMASK', 'catchermaskold', None, [0, 1]),                           # zGeneric Traditional (no skull cap)
    211: ('CATCHERMASKNEW', 'catchermasknew_gen', None),                            # zGeneric Hockey
    212: ('CATCHERMASKNEW_EVOSHIELD', 'catchermasknew_evo', 'catchermasknew_evo_logos'),
    546: ('CATCHERMASKASG_EVOSHIELD', 'catchermasknew_evo_asg', 'catchermasknew_evo_asg_logos'),
    742: ('CATCHERMASK_EVO2PC', 'catchermask_evo2pc', 'catchermask_evo2pc_logos', [0, 2]),
    213: ('CATCHERMASKNEW_ALLSTAR', 'catchermasknew_allstar_mvp5', 'catchermasknew_allstar_mvp5_logos'),
    437: ('CATCHERMASKNEW_EASTON', 'catchermasknew_easton', 'catchermasknew_easton_logos'),
    454: ('CATCHERMASK_FORCE3', 'catchermask_force3', 'catchermask_force3_logos', [0, 2]),
    428: ('CATCHERMASKNEW_MARUCCI', 'catchermasknew_marucci', 'catchermasknew_marucci_logos'),
    214: ('CATCHERMASKNEW_RAWLINGS', 'catchermasknew_rawlings_mach', 'catchermasknew_rawlings_mach_logos'),
    215: ('CATCHERMASKNEW_UA', 'catchermasknew_ua', 'catchermasknew_ua_logos'),
}


def mask_parts(m):
    """The mask's own geometry: drop the cap / helmet that some mask models carry (separate input layouts with
    the cap's UV set, or parts beyond the first layout of a multi-layout old mask)."""
    out = []
    chk = m.attrs.get('UV_checkme')
    for p in m.parts:
        if not len(p['tris']) or 'lowlod' in p['name'].lower():
            continue
        if chk is not None and np.abs(chk[np.unique(p['tris'])]).max() > 0:
            continue
        out.append(p)
    return out or [p for p in m.parts if len(p['tris'])]


MASK_COL = (0.24, 0.25, 0.28)      # default colourway for the run-time tinted shell/cage: matte charcoal


def shaded(arr, col, key, max_sat=1.0):
    """Grey (run-time tinted) texels multiplied by a default colour; saturated texels (> max_sat) kept."""
    if arr is None:
        return None
    if key in _tex_cache:
        return _tex_cache[key]
    out = arr.copy()
    sat = arr[..., :3].max(-1) - arr[..., :3].min(-1)
    msk = sat <= max_sat
    out[msk, :3] = arr[msk, :3] * np.array(col, np.float32)
    out[..., 3] = 1.0
    _tex_cache[key] = out
    return out


def render_mask(e, ctx, debug=None, only=None):
    spec = MASKS.get(e['id'])
    if spec is None:
        return None
    rel, m = model_any(ctx, 'MASTERFILES/' + spec[0])
    if m is None:
        return None
    col = shaded(tex(ctx, PLAYERACC, spec[1]), MASK_COL, ('mask', spec[1]))
    logo = tex(ctx, PLAYERACC, spec[2]) if spec[2] else None
    ps = mask_parts(m)
    if len(spec) > 3:                                # parts of the mask itself (the rest is the skull cap / helmet)
        ps = [m.parts[i] for i in spec[3] if i < len(m.parts)]
    if only is not None:
        ps = [ps[i] for i in only if i < len(ps)]
    items = [mesh(m, p['tris'], col, 'UV_color', logo, 'UV_color' if logo is not None else None, gloss=0.3)
             for p in ps]
    if debug is not None:
        debug.update(model=rel, parts=[(p['name'], p['layout'], p['vcount']) for p in ps])
    return draw(items, **CAM_MASK)


CAM_MASK = dict(yaw=30, pitch=8, roll=0)


# ---------------------------------------------------------------- compression sleeves (type 13)
BODY = MF + '/BODIES/STANDARDMALE/MALEBODY24'
SKIN = (0.80, 0.60, 0.47)


# default colourway of the picture (the game colours sleeves at run time, from the player's accessory colours)
SLEEVE_MAIN = np.array((0.40, 0.42, 0.48), np.float32)    # the fabric: slate grey (reads on dark and light tiles)
SLEEVE_SECOND = np.array((0.93, 0.93, 0.93), np.float32)  # logos and second-colour panels
SLEEVE_TRIM = np.array((0.80, 0.81, 0.84), np.float32)    # the cuff line


def sleeve_colour(arr, key):
    """A sleeve's '-color' texture is a set of masks the game colours at run time: G = the fabric with its knit
    shading and tonal pattern, B = how much of the second colour (logos, panels), R = the cuff line, A = where the
    sleeve is at all (the arm is bare elsewhere). -> the picture's colourway, alpha kept for the cut-out."""
    if key in _tex_cache:
        return _tex_cache[key]
    r, g, b = arr[..., 0:1], arr[..., 1:2], arr[..., 2:3]
    rgb = SLEEVE_MAIN * (0.40 + 0.85 * g)
    rgb = rgb * (1 - b) + SLEEVE_SECOND * b
    rgb = rgb * (1 - r) + SLEEVE_TRIM * r
    out = np.concatenate([np.clip(rgb, 0, 1), arr[..., 3:4]], -1).astype(np.float32)
    _tex_cache[key] = out
    return out


def render_sleeve(e, ctx, debug=None):
    g = gfx(e)
    tn = g.get('tx')
    col = tex(ctx, PLAYERACC, tn)
    if col is None:
        return None
    col = sleeve_colour(col, ('sleeve', tn))
    m = ctx.model(BODY)
    arm = part(m, 'Arm_L')
    items = [mesh(m, arm['tris'], col, 'UV_color', gloss=0.25, cutout=0.5)]
    mn = e['modelname'].strip()
    padded = False
    if mn:                                           # a padded sleeve: its elbow pad is a model of its own
        rel, pm = model_any(ctx, 'ACCESSORIES/ELBOWGUARDS/' + mn.upper())
        if pm is not None:
            pc, pl, bn, _ = color_and_logos(ctx, pm)
            pc = shaded(pc, PAD_COL, ('pad', bn), max_sat=0.12)
            pp = part(pm, mn + '_L') or next(p for p in pm.parts if len(p['tris']))
            items.append(mesh(pm, pp['tris'], pc, 'UV_color', pl, 'UV_color' if pl is not None else None, gloss=0.25))
            padded = True
    if debug is not None:
        debug.update(tx=tn, padded=padded)
    return draw(items, **(CAM_SLEEVE_PAD if padded else CAM_SLEEVE))


CAM_SLEEVE = dict(yaw=-10, pitch=10, roll=35)
CAM_SLEEVE_PAD = dict(yaw=170, pitch=10, roll=-35)     # from behind: the pad sits on the back of the elbow
PAD_COL = (0.62, 0.63, 0.67)                           # default colour for the pad's run-time tinted (grey) texels


# ---------------------------------------------------------------- entry point
def render_item(e, ctx):
    t = e['type']
    if t == 1:
        return render_batglove(e, ctx)
    if t == 3:
        return render_fglove(e, ctx)
    if t == 7:
        return render_eyewear(e, ctx)
    if t == 10:
        return render_mask(e, ctx)
    if t == 13:
        return render_sleeve(e, ctx)
    return None
