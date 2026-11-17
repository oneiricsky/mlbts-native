"""Item pictures for cleats (2), elbow guards (9), chest protectors (11), batter shin guards (12), wrist guards (14),
catcher leg guards (15) and sliding mitts (17), rendered from the player's own install (see render_all.py).

Many accessory models are multi-stream: CLAS_VBO holds one 0x40-byte record per vertex buffer, (u32 vertex count,
u32 group, u16 stride, u16 stream, -1); the non-empty records sorted by (stream, group) pair up with the layout's
BufferDescs in order; the .0.MOD holds the VOID_VBO chunks in record order and one VOID_EBO per stream (16-bit
indices, relative to the stream's vertices).
"""
import os
import re
import struct

import numpy as np

import mod
from mod import chunks, parse_layout
from render import load_texture, render

TYPES = {2, 9, 11, 12, 14, 15, 17}

mod.FMT.setdefault('kSInt_Compressed', 2)        # PmLodTable (progressive-mesh LOD table): not needed, only sized

ACC = 'NSW/CHARACTERS/ACCESSORIES'
PLAYERACC = 'NSW/CHARACTERS/MASTERFILES/PLAYERACC.TEX'
SHOEBANK = 'NSW/CHARACTERS/MASTERFILES/SHOES_ALLBRANDSTEXTURES.TEX'
MITTBANK = 'NSW/CHARACTERS/MASTERFILES/SLIDINGMITT_TEXTURES.TEX'


def _decode(raw, n, stride, off, comps):
    if comps[0] == 'kSInt_Compressed':
        return np.zeros((n, len(comps)), np.float32)
    return mod.decode_attr(raw[:n * stride], n, stride, off, comps)     # buffers are padded past n * stride


class Meshes:
    """Every vertex stream of a model as {pos, nrm, uv, uv2, tris, name}."""

    def __init__(self, path_no_ext):
        desc = open(path_no_ext + '.MOD', 'rb').read()
        data = open(path_no_ext + '.0.MOD', 'rb').read()
        dc = chunks(desc)
        get = lambda tag: [p for t, _, p in dc if t == tag]
        layout = parse_layout(get('STRGINLA')[0].decode('latin1'))
        self.textures = [s.decode() for s in get('STRGTEXN')[0].split(b'\0') if s] if get('STRGTEXN') else []
        hdr = get('CLAS_VBO')[0]
        recs = []
        for i in range(len(hdr) // 0x40):
            cnt, group, stride, stream, tag = struct.unpack_from('<IIHHi', hdr, i * 0x40)
            if tag != -1:
                break
            recs.append(dict(k=i, count=cnt, group=group, stride=stride, stream=stream))
        dd = chunks(data)
        vbos = [p for t, _, p in dd if t == 'VOID_VBO']
        ebos = [p for t, _, p in dd if t == 'VOID_EBO']
        ecounts = [a for t, a, _ in dd if t == 'VOID_EBO']          # the chunk header's a = index count
        live = sorted((r for r in recs if r['count']), key=lambda r: (r['stream'], r['group']))
        streams = {}
        for (bname, attrs), r in zip(layout, live):
            s = streams.setdefault(r['stream'], dict(n=r['count'], attrs={}))
            raw, off = vbos[r['k']], 0
            for aname, sem, comps in attrs:
                s['attrs'].setdefault(aname, _decode(raw, r['count'], r['stride'], off, comps))
                off += mod.attr_size(comps)
        names = [s.decode('latin1') for s in get('STRGDGRP')[0].split(b'\0') if s][1:] if get('STRGDGRP') else []
        # Draw records (VOIDDRBL, each from 0xfffffffe): +0x0c vertex count, LOD0 (count, start) at words 12/13 in its
        # stream's index buffer; records fill the streams in order (several parts may share one stream, each at the
        # running vertex base).
        drbl = get('VOIDDRBL')[0] if get('VOIDDRBL') else b''
        recs_d, o = [], 0
        while drbl:
            o = drbl.find(b'\xfe\xff\xff\xff', o)
            if o < 0:
                break
            w = struct.unpack_from('<16I', drbl, o)
            recs_d.append((w[3], w[12], w[13]))
            o += 4
        order = [sid for sid in sorted(streams) if 'Position' in streams[sid]['attrs'] and sid < len(ebos)]
        self.meshes = []
        si, used = 0, 0
        for k, (vcount, count, start) in enumerate(recs_d):
            while si < len(order) and used + vcount > streams[order[si]]['n']:
                si, used = si + 1, 0
            if si >= len(order):
                break
            sid = order[si]
            s, a = streams[sid], streams[sid]['attrs']
            idx = np.frombuffer(ebos[sid][:ecounts[sid] * 2], '<u2').astype(np.int64)[start:start + count]
            idx = idx[:len(idx) // 3 * 3].reshape(-1, 3) + used
            idx = idx[(idx < s['n']).all(1)]
            uvs = [x for x in a if x.startswith('UV')]
            name = names[k] if k < len(names) else f'part{k}'
            self.meshes.append(dict(
                name=name.split('|')[1] if '|' in name else name,
                pos=a['Position'][:, :3], nrm=a.get('Normal', np.tile([0, 0, 1.0], (s['n'], 1)))[:, :3],
                uv=a[uvs[0]] if uvs else np.zeros((s['n'], 2), np.float32),
                uv2=a[uvs[1]] if len(uvs) > 1 else None, tris=idx))
            used += vcount


def merge(meshes):
    """One vertex set from several meshes (pos, nrm, uv, uv2, tris); parts sharing a stream share its arrays."""
    pos, nrm, uv, uv2, tris, base, seen = [], [], [], [], [], 0, {}
    for m in meshes:
        if id(m['pos']) in seen:
            tris.append(m['tris'] + seen[id(m['pos'])])
            continue
        seen[id(m['pos'])] = base
        pos.append(m['pos']); nrm.append(m['nrm']); uv.append(m['uv'])
        uv2.append(m['uv2'] if m['uv2'] is not None else np.full_like(m['uv'], -1))
        tris.append(m['tris'] + base)
        base += len(m['pos'])
    return np.vstack(pos), np.vstack(nrm), np.vstack(uv), np.vstack(uv2), np.vstack(tris)


def find_file(ctx, folder, stem):
    d = os.path.join(ctx.romfs, *folder.split('/'))
    want = stem.replace(' ', '').lower()
    for f in os.listdir(d):
        if f.endswith('.MOD') and '.0.' not in f and f[:-4].lower() == want:
            return os.path.join(d, f[:-4])
    return None


_cache = {}


def meshes(path):
    if path not in _cache:
        _cache[path] = Meshes(path)
    return _cache[path]


def tint_default(t):
    """Shoe base textures are tint masks: alpha = zone id in steps of 17 (0..136), RGB = grey shading; the game
    colours the zones with the player's choice at run time, and no default colourway is stored. Picture default:
    the largest zone white, the other zones near-black; texels at alpha ~1 are baked art and stay as they are."""
    if t is None:
        return t
    a = t[..., 3]
    mask = a < 0.6
    if mask.mean() < 0.5:                        # mostly baked artwork: leave it
        return t
    zone = np.rint(a * 255 / 17).astype(int)
    main = np.bincount(zone[mask].ravel()).argmax()
    shade = t[..., :3].mean(2, keepdims=True)
    colour = np.where((zone == main)[..., None], 0.93, 0.13)
    out = t.copy()
    out[..., :3] = np.where(mask[..., None], np.clip(colour * (0.55 + 0.6 * shade), 0, 1), t[..., :3])
    out[..., 3] = 1.0
    return out


def tex(ctx, bank, name):
    key = (bank, name.lower())
    if key not in _cache:
        t = load_texture(ctx.bank(bank), name)
        _cache[key] = tint_default(t) if bank == SHOEBANK and 'logo' not in name.lower() else t
    return _cache[key]


def pick_textures(ctx, model_textures, bank, override=None, no_logo=False):
    """(base color, logo color) for a model: its own '<x>-color' / '<x>_logos-color' names, or override base name."""
    colors = [t[:-6] for t in model_textures if t.lower().endswith('-color')]
    base = [c for c in colors if 'logo' not in c.lower()]
    logo = [c for c in colors if 'logo' in c.lower()]
    b = override or (base[0] if base else None)
    lg = None if no_logo else (f'{override}_logos' if override else (logo[0] if logo else None))
    bt = tex(ctx, bank, b + '-color') if b else None
    lt = tex(ctx, bank, lg + '-color') if lg else None
    if lg and lt is None and override:
        lt = tex(ctx, bank, logo[0] + '-color') if logo else None
    return bt, lt


VIEW = {  # type -> (yaw, pitch, roll)
    2: (-55, 12, 0), 9: (-30, 10, 0), 11: (-25, 8, 0), 12: (-35, 8, 0), 14: (-30, 15, 0), 15: (-35, 8, 0),
    17: (-70, 35, 0),
}
ONE_SIDE = {9, 14}          # left/right pieces sit an arm apart: draw one side so it fills the frame


def one_side(name):
    n = name.lower()
    return not (n.endswith('_r') or n.endswith('right') or '_r_' in n)


def draw(ctx, e, path, bank, override=None, no_logo=False, part_filter=None):
    ms = meshes(path)
    sel = [m for m in ms.meshes if len(m['tris']) and 'lowlod' not in m['name'].lower()
           and (part_filter is None or part_filter(m['name']))]
    if not sel:
        return None
    pos, nrm, uv, uv2, tris = merge(sel)
    color, logo = pick_textures(ctx, ms.textures, bank, override, no_logo)
    yaw, pitch, roll = VIEW[e['type']]
    return render(pos, nrm, tris, uv, color, uv2, logo, yaw=yaw, pitch=pitch, roll=roll)


def tokens(field):
    out = {}
    for part in field.split(','):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition('=')
        out[k.strip()] = v.strip() if _ else True
    return out


FOLDER = {9: ACC + '/ELBOWGUARDS', 11: ACC + '/CHESTPROTECTORS', 12: ACC + '/BATTERSHINGUARDS',
          14: ACC + '/WRISTGUARDS', 15: ACC + '/CATCHERLEGGUARDS'}


def render_item(e, ctx):
    t, mname = e['type'], e['modelname'].strip()
    g = tokens(e['gfxinfo'])
    if t in FOLDER:
        and_folder = FOLDER[t].replace('NSW/', 'AND/')                   # Android build: same format, more models
        path = (find_file(ctx, FOLDER[t], mname)
                or (os.path.isdir(os.path.join(ctx.romfs, *and_folder.split('/'))) and find_file(ctx, and_folder, mname))
                or find_file(ctx, FOLDER[t], mname.split('_')[0] + '_generic'))
        if path is None:
            return None
        override = None
        if 'tx' in g:                                  # e.g. tx=$jordan on the Nike model: the Jordan texture set
            override = f'{mname}_{g["tx"].lstrip("$")}'
            if load_texture(ctx.bank(PLAYERACC), override + '-color') is None:
                override = None
        return draw(ctx, e, path, PLAYERACC, override, no_logo='noLogo' in g,
                    part_filter=one_side if t in ONE_SIDE else None)
    if t == 2:
        # The Switch build ships 32 shoe models; the rest are in the install's Android build (AND/), same format.
        # Their textures are in the Switch shoe bank either way.
        path = find_file(ctx, ACC + '/SHOES', mname) or find_file(ctx, 'AND/CHARACTERS/ACCESSORIES/SHOES', mname)
        if path is None:
            return None
        return draw(ctx, e, path, SHOEBANK)
    if t == 17:
        if 'offslot' in g:
            return None                                 # "OFF": no mitt; the tile stays empty
        if mname.lower() == 'wristguardrunner':
            path = os.path.join(ctx.romfs, *(ACC + '/SLIDINGMITTS/SLIDING_MITTS').split('/'))
            return draw(ctx, e, path, MITTBANK, 'WristGuardRunner', no_logo=True,
                        part_filter=lambda n: 'wristguardrunner' in n.lower())
        brand = mname.replace('$_', '')                 # 44pro, evoshield2, franklin, ...
        path = os.path.join(ctx.romfs, *(ACC + '/SLIDINGMITTS/SLIDING_MITTS').split('/'))
        return draw(ctx, e, path, MITTBANK, f'slidingMitt_{brand}', no_logo='nologo' in g,
                    part_filter=lambda n: 'slidingmitt' in n.lower())
    return None
