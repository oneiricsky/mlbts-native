"""Renders equipment models from the player's own install into 512x512 RGBA item pictures (the format of the game's
item images), in numpy alone: orthographic view fitted to the frame, depth-tested triangles, a colour texture and up to
two logo layers per mesh (bilinear, repeat, mip-mapped), simple key / fill lighting, 3x3 supersampling. Output stays
local; it is only used by the game's own Equipment screen.

    render(pos, nrm, tris, uv, color, uv2=None, logo=None, size=512, yaw=-40, pitch=20, roll=0, margin=0.08)
      one mesh: pos (n,3), nrm (n,3), tris (m,3) vertex indices, uv/uv2 (n,2); color/logo float RGBA arrays (h,w,4)
      or None. yaw/pitch/roll in degrees; the model is fitted to the frame (margin each side).
    render_items(items, yaw, pitch, roll, margin, size)
      several meshes in one view (shared fit and depth); see item() for what a mesh carries.
Both return a (size, size, 4) uint8 RGBA array with a transparent background.
"""
import math

import numpy as np

from tx12 import decode_bcn

FORMAT_BCN = {6: 3, 7: 3, 13: 1, 19: 4, 22: 7}   # TX12 entry byte +0x12c -> BCn (19: one-channel BC4; 22: BC7, the format
                                                 # of every picture in the game's own LIVE.TEX)
SIZE = 512
SS = 3                                           # samples per pixel side
KEY = np.array([-0.45, 0.6, 0.66]) / np.linalg.norm([-0.45, 0.6, 0.66])
FILL = np.array([0.6, -0.1, 0.8]) / np.linalg.norm([0.6, -0.1, 0.8])
HALF = (KEY + [0, 0, 1]) / np.linalg.norm(KEY + [0, 0, 1])


def load_texture(bank, name):
    """RGBA float array (h, w, 4) in 0..1 of a bank texture, or None. BC4 comes back grey and opaque."""
    e = bank.find(name)
    if e is None or not e.levels:
        return None
    n = FORMAT_BCN.get(e.raw[0x12c])
    if n is None:
        return None
    L = e.levels[0]
    return decode_bcn(bank.level0_bytes(e), L.w, L.h, n).astype(np.float32) / 255.0


def rotation(yaw, pitch, roll=0.0):
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    cr, sr = math.cos(roll), math.sin(roll)
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return rz @ rx @ ry


def item(pos, nrm, tris, uv, color=None, uv2=None, logo=None, uv3=None, logo2=None, flat=(0.6, 0.6, 0.6), gloss=0.18,
         cutout=0.0):
    """One mesh to draw: its base colour is `color` at uv (or `flat` without a texture); `logo` at uv2 and `logo2` at
    uv3 are laid over it by their alpha where their UVs are inside 0..1. gloss: strength of the highlight. cutout:
    where the colour texture's alpha is below it the mesh is not drawn at all (and hides nothing behind it)."""
    return dict(pos=pos, nrm=nrm, tris=np.asarray(tris).reshape(-1, 3), uv=uv, uv2=uv2, uv3=uv3, color=color,
                logo=logo, logo2=logo2, flat=flat, gloss=gloss, cutout=cutout)


# ---- textures ---------------------------------------------------------------------------------------------------------

_mip_cache = {}     # id(texture) -> (texture, [level 0, level 1, ...]); holding the texture keeps its id from being reused


def _mips(tex):
    hit = _mip_cache.get(id(tex))
    if hit is not None and hit[0] is tex:
        return hit[1]
    if len(_mip_cache) >= 48:
        _mip_cache.clear()
    levels = [tex]
    while min(levels[-1].shape[:2]) >= 2:
        t = levels[-1]
        h, w = t.shape[0] // 2 * 2, t.shape[1] // 2 * 2
        levels.append(t[:h, :w].reshape(h // 2, 2, w // 2, 2, -1).mean((1, 3), dtype=np.float32))
    _mip_cache[id(tex)] = (tex, levels)
    return levels


def _bilinear(tex, uv):
    """Bilinear, repeat-wrapped lookup of an (h, w, c) float texture at uv (n, 2); v = 0 is the first row."""
    h, w = tex.shape[:2]
    x = uv[:, 0] * w - 0.5
    y = uv[:, 1] * h - 0.5
    x0, y0 = np.floor(x), np.floor(y)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0 = x0.astype(np.int64) % w
    y0 = y0.astype(np.int64) % h
    x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    return ((tex[y0, x0] * (1 - fx) + tex[y0, x1] * fx) * (1 - fy) +
            (tex[y1, x0] * (1 - fx) + tex[y1, x1] * fx) * fy)


def _sample(tex, uv, level):
    """tex at uv (n, 2), each sample from its own mip level (n,)."""
    mips = _mips(tex)
    level = np.minimum(level, len(mips) - 1)
    out = np.empty((len(uv), tex.shape[2]), np.float64)
    for lv in np.unique(level):
        m = level == lv
        out[m] = _bilinear(mips[lv], uv[m])
    return out


def _levels(tex, uv, tris, px_area):
    """The mip level of every triangle: the one whose texels are about the size of a sample."""
    a, b, c = uv[tris[:, 0]], uv[tris[:, 1]], uv[tris[:, 2]]
    texels = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) \
        * tex.shape[0] * tex.shape[1]
    lod = 0.5 * np.log2(np.maximum(texels, 1e-12) / np.maximum(px_area, 1e-12))
    return np.clip(np.floor(lod + 0.5), 0, 30).astype(np.int64)


# ---- drawing ----------------------------------------------------------------------------------------------------------

def render_items(items, yaw=-40, pitch=20, roll=0, margin=0.08, size=SIZE):
    R = rotation(math.radians(yaw), math.radians(pitch), math.radians(roll))
    views = [np.asarray(it['pos'], np.float64) @ R.T for it in items]
    used = np.concatenate([P[np.unique(it['tris'])] for P, it in zip(views, items)])
    lo, hi = used.min(0), used.max(0)
    center = (lo + hi) / 2
    scale = 2 * (1 - 2 * margin) / max(hi[0] - lo[0], hi[1] - lo[1], 1e-6)
    N = int(size * SS)
    zbuf = np.full((N, N), -np.inf)
    owner = np.full((N, N), -1, np.int32)            # which item
    tid = np.zeros((N, N), np.int32)                 # which of its triangles
    bary = np.zeros((N, N, 2), np.float32)
    areas = []
    for k, (P, it) in enumerate(zip(views, items)):
        tris = it['tris']
        sx = ((P[:, 0] - center[0]) * scale + 1) * 0.5 * N        # sample column
        sy = (1 - (P[:, 1] - center[1]) * scale) * 0.5 * N        # sample row (top = +y)
        depth = P[:, 2]                                           # larger = nearer the camera
        X, Y = sx[tris], sy[tris]                                 # (m, 3)
        area = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (Y[:, 1] - Y[:, 0]) * (X[:, 2] - X[:, 0])
        areas.append(np.abs(area) / 2)
        bx0 = np.maximum(np.floor(X.min(1)).astype(np.int64), 0)
        bx1 = np.minimum(np.ceil(X.max(1)).astype(np.int64), N - 1)
        by0 = np.maximum(np.floor(Y.min(1)).astype(np.int64), 0)
        by1 = np.minimum(np.ceil(Y.max(1)).astype(np.int64), N - 1)
        ok = (np.abs(area) > 1e-12) & (bx1 >= bx0) & (by1 >= by0)
        cut = it.get('cutout', 0) if it['color'] is not None else 0
        if cut:                                      # the alpha that decides, from the mip that matches each triangle
            uv = np.asarray(it['uv'], np.float64)
            cut_mips = _mips(it['color'])
            cut_lod = np.minimum(_levels(it['color'], uv, tris, np.abs(area) / 2), len(cut_mips) - 1)
        for t in np.nonzero(ok)[0]:
            a, b, c = tris[t]
            xa, ya, xb, yb, xc, yc = X[t, 0], Y[t, 0], X[t, 1], Y[t, 1], X[t, 2], Y[t, 2]
            x0, x1, y0, y1 = bx0[t], bx1[t], by0[t], by1[t]
            px = np.arange(x0, x1 + 1)[None, :] + 0.5
            py = np.arange(y0, y1 + 1)[:, None] + 0.5
            w1 = ((px - xa) * (yc - ya) - (py - ya) * (xc - xa)) / area[t]      # weight of b
            w2 = ((xb - xa) * (py - ya) - (yb - ya) * (px - xa)) / area[t]      # weight of c
            w0 = 1 - w1 - w2
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            if cut:
                tex = cut_mips[cut_lod[t]]
                u = w0[inside] * uv[a, 0] + w1[inside] * uv[b, 0] + w2[inside] * uv[c, 0]
                v = w0[inside] * uv[a, 1] + w1[inside] * uv[b, 1] + w2[inside] * uv[c, 1]
                keep = tex[np.floor(v * tex.shape[0]).astype(np.int64) % tex.shape[0],
                           np.floor(u * tex.shape[1]).astype(np.int64) % tex.shape[1], 3] >= cut
                if not keep.all():
                    inside[inside] = keep
                    if not inside.any():
                        continue
            z = w0 * depth[a] + w1 * depth[b] + w2 * depth[c]
            zb = zbuf[y0:y1 + 1, x0:x1 + 1]
            win = inside & (z > zb)
            if not win.any():
                continue
            zb[win] = z[win]
            owner[y0:y1 + 1, x0:x1 + 1][win] = k
            tid[y0:y1 + 1, x0:x1 + 1][win] = t
            bb = bary[y0:y1 + 1, x0:x1 + 1]
            bb[win, 0] = w1[win]
            bb[win, 1] = w2[win]
    rgb = np.zeros((N, N, 3))
    for k, it in enumerate(items):
        cov = owner == k
        if not cov.any():
            continue
        tris = it['tris']
        hit = tid[cov]
        T = tris[hit]
        w1, w2 = bary[cov, 0][:, None].astype(np.float64), bary[cov, 1][:, None].astype(np.float64)
        w0 = 1 - w1 - w2

        def interp(attr):
            return attr[T[:, 0]] * w0 + attr[T[:, 1]] * w1 + attr[T[:, 2]] * w2

        def layer(tex, uv):
            return _sample(tex, interp(uv), _levels(tex, uv, tris, areas[k])[hit])

        if it['color'] is not None:
            base = layer(it['color'], it['uv'])[:, :3]
        else:
            base = np.tile(np.asarray(it['flat'], np.float64), (len(T), 1))
        for tex, uv in ((it['logo'], it['uv2']), (it['logo2'], it['uv3'])):
            if tex is None or uv is None:
                continue
            u = interp(uv)
            inside = ((u >= 0) & (u <= 1)).all(1)
            if inside.any():
                lg = _sample(tex, u[inside], _levels(tex, uv, tris, areas[k])[hit][inside])
                base[inside] = base[inside] * (1 - lg[:, 3:4]) + lg[:, :3] * lg[:, 3:4]
        n = interp(np.asarray(it['nrm'], np.float64)) @ R.T
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        n *= np.where(n[:, 2:3] < 0, -1.0, 1.0)                   # two-sided: light the side that faces the camera
        diff = 0.32 + 0.62 * np.maximum(n @ KEY, 0) + 0.18 * np.maximum(n @ FILL, 0)
        spec = it['gloss'] * np.maximum(n @ HALF, 0) ** 24
        rgb[cov] = np.clip(base * diff[:, None] + spec[:, None], 0, 1)
    # resolve: average colour of the covered samples, alpha = covered share
    cov = owner >= 0
    c4 = cov.reshape(size, SS, size, SS).sum((1, 3)).astype(np.float64)
    s4 = rgb.reshape(size, SS, size, SS, 3).sum((1, 3))
    out = np.zeros((size, size, 4))
    out[..., :3] = np.where(c4[..., None] > 0, s4 / np.maximum(c4[..., None], 1), 0)
    out[..., 3] = c4 / (SS * SS)
    return np.clip(np.rint(out * 255), 0, 255).astype(np.uint8)


def render(pos, nrm, tris, uv, color, uv2=None, logo=None, size=SIZE, yaw=-40, pitch=20, roll=0, margin=0.08):
    return render_items([item(pos, nrm, tris, uv, color, uv2, logo)], yaw, pitch, roll, margin, size)
