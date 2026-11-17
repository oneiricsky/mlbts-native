"""BC7 encoder for the equipment pictures: modes 6, 5 and 4, chosen per block by error.

After tools/make_prompts.py (W2 .. encode), with Bits packing all blocks at once in numpy
(the original loops in Python per block, which is slow for 16384-block textures).
"""
import numpy as np

W2 = np.array([0, 21, 43, 64])
W3 = np.array([0, 9, 18, 27, 37, 46, 55, 64])
W4 = np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64])


def interp(e0, e1, w):
    """BC7 interpolation between integer endpoints (N, C) at weights w (K,): (N, K, C)."""
    return ((64 - w)[None, :, None] * e0[:, None, :] + w[None, :, None] * e1[:, None, :] + 32) >> 6


class Quant:
    """Endpoint precision: bits per channel, expanded to 8 by bit replication; pbit: mode 6's shared lowest bit."""
    def __init__(self, bits, pbit=False):
        self.bits, self.pbit = bits, pbit

    def codes(self, e):
        if not self.pbit:
            m = (1 << self.bits) - 1
            return np.clip(np.round(e * m / 255.0), 0, m).astype(np.int64)
        best = None
        for p in (0, 1):   # the p-bit that brings the endpoint closest
            c = np.clip(np.round((e - p) / 2.0), 0, 127).astype(np.int64)
            err = ((c * 2 + p - e) ** 2).sum(1)
            c = np.concatenate([c, np.full((len(e), 1), p)], 1)
            if best is None:
                best = (c, err)
            else:
                b = err < best[1]
                best = (np.where(b[:, None], c, best[0]), np.where(b, err, best[1]))
        return best[0]

    def expand(self, c):
        if self.pbit:
            return c[:, :-1] * 2 + c[:, -1:]
        b = self.bits
        return (c << (8 - b)) | (c >> (2 * b - 8))


def principal(x, wt):
    """Weighted mean and principal axis of x (N, 16, C) with weights wt (N, 16)."""
    s = wt.sum(1)[:, None] + 1e-9
    mean = (x * wt[..., None]).sum(1) / s
    d = (x - mean[:, None]) * np.sqrt(wt)[..., None]
    cov = np.einsum('nkc,nkd->ncd', d, d)
    v = x.max(1) - x.min(1) + 1e-3
    for _ in range(12):
        v = np.einsum('ncd,nd->nc', cov, v)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return mean, v


def fit(x, wt, weights, q):
    """One index set: x (N, 16, C) in 0..255, wt (N, 16) error weights, weights the interpolation table, q a Quant.
    Endpoints at the ends of the principal axis, then twice least squares for the indices found; keeps the best.
    Returns codes0, codes1, indices (N, 16), error (N,)."""
    mean, axis = principal(x, wt)
    t = np.einsum('nkc,nc->nk', x - mean[:, None], axis)
    e0 = mean + np.where(wt > 0, t, np.inf).min(1)[:, None] * axis
    e1 = mean + np.where(wt > 0, t, -np.inf).max(1)[:, None] * axis
    e0, e1 = np.nan_to_num(e0, posinf=0, neginf=0), np.nan_to_num(e1, posinf=0, neginf=0)
    best = None
    sw = np.sqrt(wt)
    for _ in range(3):
        c0, c1 = q.codes(np.clip(e0, 0, 255)), q.codes(np.clip(e1, 0, 255))
        pal = interp(q.expand(c0), q.expand(c1), weights)                  # (N, K, C)
        dist = ((x[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)      # (N, 16, K)
        idx = dist.argmin(-1)
        err = (np.take_along_axis(dist, idx[..., None], -1)[..., 0] * wt).sum(1)
        if best is None:
            best = [c0, c1, idx, err]
        else:
            b = err < best[3]
            best = [np.where(b[:, None], c0, best[0]), np.where(b[:, None], c1, best[1]),
                    np.where(b[:, None], idx, best[2]), np.where(b, err, best[3])]
        f = weights[idx] / 64.0 * sw
        g = sw - f
        xs = x * sw[..., None]
        a11, a12, a22 = (g * g).sum(1), (g * f).sum(1), (f * f).sum(1)
        b1, b2 = np.einsum('nk,nkc->nc', g, xs), np.einsum('nk,nkc->nc', f, xs)
        det = a11 * a22 - a12 * a12
        ok = (np.abs(det) > 1e-6)[:, None]
        det = np.where(ok[:, 0], det, 1.0)[:, None]
        e0 = np.where(ok, (a22[:, None] * b1 - a12[:, None] * b2) / det, e0)
        e1 = np.where(ok, (a11[:, None] * b2 - a12[:, None] * b1) / det, e1)
    return best


def anchor_fix(c0, c1, idx, nbits):
    """Texel 0's index must have its top bit clear: where it has not, swap the endpoints and mirror the indices."""
    top = 1 << (nbits - 1)
    s = idx[:, 0] >= top
    return (np.where(s[:, None], c1, c0), np.where(s[:, None], c0, c1), np.where(s[:, None], 2 * top - 1 - idx, idx))


class Bits:
    """BC7 blocks written field by field, least significant bit first (two 64-bit halves per block)."""
    def __init__(self, n):
        self.lo, self.hi, self.pos = np.zeros(n, np.uint64), np.zeros(n, np.uint64), 0

    def put(self, vals, nbits):
        v = np.broadcast_to(np.asarray(vals, dtype=np.int64), self.lo.shape).astype(np.uint64)
        v &= np.uint64((1 << nbits) - 1)
        p = self.pos
        if p < 64:
            self.lo |= v << np.uint64(p)
            if p + nbits > 64:
                self.hi |= v >> np.uint64(64 - p)
        else:
            self.hi |= v << np.uint64(p - 64)
        self.pos += nbits

    def indices(self, idx, nbits):
        self.put(idx[:, 0], nbits - 1)
        for k in range(1, 16):
            self.put(idx[:, k], nbits)

    def blocks(self):
        assert self.pos == 128, self.pos
        both = np.stack([self.lo, self.hi], 1).astype('<u8')
        return [both[i].tobytes() for i in range(len(both))]


def encode(px):
    """BC7 blocks of px (N, 16, 4) uint8: per block the best of mode 6 (RGBA together, 4-bit indices) and modes 5 and 4
    (colour and alpha apart, which keeps antialiased edges over transparency clean)."""
    x = px.astype(np.float64)
    a = x[..., 3]
    cov = a / 255.0
    # a transparent texel's colour does not count: it takes the block's mean colour, so the colours stay on a line
    mean_rgb = (x[..., :3] * cov[..., None]).sum(1) / np.maximum(cov.sum(1), 1e-9)[:, None]
    rgb = np.where(cov[..., None] > 0, x[..., :3], mean_rgb[:, None, :])
    cw = cov + 1e-3
    ones = np.ones_like(a)

    def colour_err(q, c0, c1, idx, w):
        got = np.take_along_axis(interp(q.expand(c0), q.expand(c1), w), idx[..., None], 1)
        return (((got - rgb) ** 2).sum(-1) * cw).sum(1)

    def alpha_err(q, c0, c1, idx, w):
        got = np.take_along_axis(interp(q.expand(c0), q.expand(c1), w)[..., 0], idx, 1)
        return ((got - a) ** 2).sum(1)

    q6 = Quant(7, pbit=True)
    m6 = fit(np.concatenate([rgb, a[..., None]], -1), ones, W4, q6)
    got = np.take_along_axis(interp(q6.expand(m6[0]), q6.expand(m6[1]), W4), m6[2][..., None], 1)
    e6 = (((got[..., :3] - rgb) ** 2).sum(-1) * cw + (got[..., 3] - a) ** 2).sum(1)

    q7, q8 = Quant(7), Quant(8)
    m5c, m5a = fit(rgb, cw, W2, q7), fit(a[..., None], ones, W2, q8)
    e5 = colour_err(q7, *m5c[:3], W2) + alpha_err(q8, *m5a[:3], W2)

    q5b, q6b = Quant(5), Quant(6)
    m4c, m4a = fit(rgb, cw, W3, q5b), fit(a[..., None], ones, W2, q6b)   # index mode 1: 3-bit colour, 2-bit alpha
    e4 = colour_err(q5b, *m4c[:3], W3) + alpha_err(q6b, *m4a[:3], W2)

    choice = np.argmin(np.stack([e6, e5, e4]), 0)
    out = [None] * len(px)
    for mode, sel in ((6, np.nonzero(choice == 0)[0]), (5, np.nonzero(choice == 1)[0]),
                      (4, np.nonzero(choice == 2)[0])):
        if not len(sel):
            continue
        b = Bits(len(sel))
        if mode == 6:
            c0, c1, idx = anchor_fix(m6[0][sel], m6[1][sel], m6[2][sel], 4)
            b.put(1 << 6, 7)
            for ch in range(4):
                b.put(c0[:, ch], 7)
                b.put(c1[:, ch], 7)
            b.put(c0[:, 4], 1)
            b.put(c1[:, 4], 1)
            b.indices(idx, 4)
        else:
            mc, ma = (m5c, m5a) if mode == 5 else (m4c, m4a)
            cbits, abits, cidx_bits = (7, 8, 2) if mode == 5 else (5, 6, 3)
            c0, c1, ci = anchor_fix(mc[0][sel], mc[1][sel], mc[2][sel], cidx_bits)
            a0, a1, ai = anchor_fix(ma[0][sel], ma[1][sel], ma[2][sel], 2)
            if mode == 5:
                b.put(1 << 5, 6)
                b.put(0, 2)        # rotation: none
            else:
                b.put(1 << 4, 5)
                b.put(0, 2)        # rotation: none
                b.put(1, 1)        # index mode 1: the 3-bit indices are the colour's
            for ch in range(3):
                b.put(c0[:, ch], cbits)
                b.put(c1[:, ch], cbits)
            b.put(a0[:, 0], abits)
            b.put(a1[:, 0], abits)
            if mode == 5:
                b.indices(ci, 2)
                b.indices(ai, 2)
            else:
                b.indices(ai, 2)   # the 2-bit set comes first; in index mode 1 that is alpha's
                b.indices(ci, 3)
        for i, blk in zip(sel, b.blocks()):
            out[i] = blk
    return out

