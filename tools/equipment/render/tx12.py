"""Reader for the game's TX12NSW texture banks (*.TEX): name table, LZ4-compressed data, Tegra block-linear tiling,
BCn decoding (BC1, BC3, BC4, BC5, BC7, in numpy). Works on the files of the player's own install; nothing is written back
to the game. Needs numpy and lz4.

Layout (from the files; fields not listed are unknown):
  header  'TX12NSW\\0', u32 version (0xc), u32 data size, u32 ?, u32 entry count, u32 ?, u32 0, u64 hash
  entries from 0x30, 0x140 bytes each:
    +0x00  name[64]                      e.g. "shoes_nike_trout9-color"
    +0x40  4 x { hash[16], u32 size, u16 w, u16 h, u16 depth, u16 layers, u32 mips }   the quality levels, largest first
    +0x124 u32 data offset in the file
  data: LZ4 blocks; the first block of a texture unpacks to its largest level's mip chain.
"""
import struct
from dataclasses import dataclass

import lz4.block
import numpy as np

ENTRY = 0x140


@dataclass
class Level:
    size: int
    w: int
    h: int
    mips: int


@dataclass
class Entry:
    name: str
    levels: list
    offset: int
    raw: bytes


class Bank:
    def __init__(self, path):
        self.path = path
        self.b = open(path, 'rb').read()
        assert self.b[:7] == b'TX12NSW', path
        count = struct.unpack_from('<I', self.b, 0x14)[0]
        self.entries = {}
        for i in range(count):
            o = 0x30 + i * ENTRY
            name = self.b[o:o + 0x40].split(b'\0')[0].decode('ascii', 'replace')
            levels = []
            for k in range(4):
                size, w, h, _d, _l, mips = struct.unpack_from('<IHHHHI', self.b, o + 0x40 + k * 0x20 + 0x10)
                if w and h:
                    levels.append(Level(size, w, h, mips))
            off = struct.unpack_from('<I', self.b, o + 0x124)[0]
            self.entries[name.lower()] = Entry(name, levels, off, self.b[o:o + ENTRY])

    def find(self, name):
        return self.entries.get(name.lower())

    def level0_bytes(self, e):
        """The largest quality level's data: the first LZ4 block at the entry's offset. Its sizes are at +0xc0
        (u32 unpacked, u32 packed)."""
        unpacked, packed = struct.unpack_from('<II', e.raw, 0xc0)
        return lz4.block.decompress(self.b[e.offset:e.offset + packed], uncompressed_size=unpacked)


# ---- Tegra block-linear ------------------------------------------------------------------------------------------------

def deswizzle(data, width_bytes, height_rows, block_height_gobs):
    """Untile Tegra block-linear data: GOBs of 64 bytes x 8 rows, block_height_gobs GOBs stacked per block."""
    bh = block_height_gobs
    gobs_x = (width_bytes + 63) // 64
    out = np.zeros((height_rows, width_bytes), dtype=np.uint8)
    src = np.frombuffer(data, dtype=np.uint8)
    y = np.arange(height_rows)[:, None]
    x = np.arange(width_bytes)[None, :]
    gob = (y // (8 * bh)) * (gobs_x * bh * 512) + (x // 64) * (bh * 512) + ((y % (8 * bh)) // 8) * 512
    xi, yi = x % 64, y % 8
    inner = (xi // 32) * 256 + (yi // 2) * 64 + ((xi % 32) // 16) * 32 + (yi % 2) * 16 + (xi % 16)
    addr = gob + inner
    ok = addr < src.size
    out[ok] = src[addr[ok]]
    return out.tobytes()


def default_block_height(height_blocks):
    """The usual block height for a level of height_blocks rows of 4x4 blocks: up to 16 GOBs (NVN's default)."""
    gobs = (height_blocks + 7) // 8
    bh = 1
    while bh < gobs and bh < 16:
        bh *= 2
    return bh


BCN_BYTES = {1: 8, 3: 16, 4: 8, 5: 16, 7: 16}


def _rgb565(c):
    """(N,) 16-bit colours -> (N, 3) 8-bit, bits replicated."""
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], 1)


def _color_blocks(c, four):
    """BC1 colour blocks (N, 8) -> (N, 16, 4) RGBA; texel k = 4 * row + column. four: always the 4-colour form (the
    colour half of BC3); otherwise c0 <= c1 means 3 colours + transparent black."""
    c = c.astype(np.int64)
    c0, c1 = c[:, 0] | (c[:, 1] << 8), c[:, 2] | (c[:, 3] << 8)
    p0, p1 = _rgb565(c0), _rgb565(c1)
    pal = np.zeros((len(c), 4, 4), np.int64)
    pal[:, 0, :3], pal[:, 1, :3] = p0, p1
    pal[:, 2, :3], pal[:, 3, :3] = (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3
    pal[:, :, 3] = 255
    if not four:
        three = c0 <= c1
        pal[three, 2, :3] = ((p0 + p1) // 2)[three]
        pal[three, 3] = 0
    lut = c[:, 4] | (c[:, 5] << 8) | (c[:, 6] << 16) | (c[:, 7] << 24)
    idx = (lut[:, None] >> (2 * np.arange(16))[None, :]) & 3
    return np.take_along_axis(pal, idx[:, :, None], 1)


def _alpha_blocks(a):
    """BC4 / BC3-alpha blocks (N, 8) -> (N, 16) values."""
    a = a.astype(np.int64)
    a0, a1 = a[:, 0], a[:, 1]
    pal = np.zeros((len(a), 8), np.int64)
    pal[:, 0], pal[:, 1] = a0, a1
    eight = a0 > a1
    for i in range(1, 7):
        pal[:, i + 1] = ((7 - i) * a0 + i * a1) // 7
    six = ~eight
    for i in range(1, 5):
        pal[six, i + 1] = (((5 - i) * a0 + i * a1) // 5)[six]
    pal[six, 6], pal[six, 7] = 0, 255
    lut = np.zeros(len(a), np.int64)
    for i in range(6):
        lut |= a[:, 2 + i] << (8 * i)
    idx = (lut[:, None] >> (3 * np.arange(16))[None, :]) & 7
    return np.take_along_axis(pal, idx, 1)


def _image(texels, bw, bh, w, h):
    """(bw * bh, 16, C) block texels -> (h, w, C) uint8."""
    c = texels.shape[-1]
    im = texels.reshape(bh, bw, 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, c)
    return np.ascontiguousarray(im[:h, :w]).astype(np.uint8)


# ---- BC7 --------------------------------------------------------------------------------------------------------------

# BC7 (BPTC) tables of the format itself: which subset each of the 16 texels belongs to for the 64 two-subset and
# 64 three-subset partitions, and the anchor texel (one index bit fewer) of the second and third subsets.
_P2 = ('001100110011001100010001000100010111011101110111000100110011011100000001000100110011011101111111'
    '000100110111111100000001001101110000000000010011001101111111111100000001011111110000000000010111'
    '000101111111111100000000111111110000111111111111000000000000111100001000111011110111000100000000'
    '000000001000111001110011000100000011000100000000000010001100111000000000100011000111001100110001'
    '001100010001000000001000100011000110011001100110001101100110110000010111111010000000111111110000'
    '011100011000111000111001100111000101010101010101000011110000111101011010010110100011001111001100'
    '001111000011110001010101101010100110100101101001010110101010010101110011110011100001001111001000'
    '001100100100110000111011110111000110100110010110001111001100001101100110100110010000011001100000'
    '010011100100000000100111001000000000001001110010000001001110010001101100100100110011011011001001'
    '011000111001110000111001110001100110110011001001011000110011100101111110100000010001100011100111'
    '0000111100110011001100111111000000100010111011100100010001110111')
_P3 = ('001100110221222200010011221122210000200122112211022200220011011100000000112211220011001100220022'
    '002200221111111100110011221122110000000011112222000011111111222200001111222222220012001200120012'
    '011201120112011201220122012201220011011211221222001120012200222000010011011211220111001120012200'
    '000011221122112200220022002211110111011102220222000100012221222100000011012201220000110022102210'
    '012201220011000000120012112222220110122112210110000001101221122100221102110200220110011020022222'
    '001101220122001100002000221122210000000211221222022200220012001100110012002202220120012001200120'
    '000011112222000001201201201201200120201212010120001122001122001100111122220000110101010122222222'
    '000000002121212100221122002211220022001100220011022012210220122101012222222201010000212121212121'
    '010101010101222202220111022201110002111200021112000021122112211202220111011102220002111211120002'
    '011001100110222200000000211221120110011022222222002200110011002200221122112200220000000000002112'
    '0002000100020001022212220222122201012222222222220111201122012220')
_A2 = [15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 2, 8, 2, 2, 8, 8, 15, 2, 8, 2, 2, 8, 8, 2, 2, 15, 15, 6, 8, 2, 8, 15, 15, 2, 8, 2, 2, 2, 15, 15, 6, 6, 2, 6, 8, 15, 15, 2, 2, 15, 15, 15, 15, 15, 2, 2, 15]
_A3A = [3, 3, 15, 15, 8, 3, 15, 15, 8, 8, 6, 6, 6, 5, 3, 3, 3, 3, 8, 15, 3, 3, 6, 10, 5, 8, 8, 6, 8, 5, 15, 15, 8, 15, 3, 5, 6, 10, 8, 15, 15, 3, 15, 5, 15, 15, 15, 15, 3, 15, 5, 5, 5, 8, 5, 10, 5, 10, 8, 13, 15, 12, 3, 3]
_A3B = [15, 8, 8, 3, 15, 15, 3, 8, 15, 15, 15, 15, 15, 15, 15, 8, 15, 8, 15, 3, 15, 8, 15, 8, 3, 15, 6, 10, 15, 15, 10, 8, 15, 3, 15, 10, 10, 8, 9, 10, 6, 15, 8, 15, 3, 6, 6, 8, 15, 3, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 3, 15, 15, 8]
_PART2 = np.frombuffer(_P2.encode(), np.uint8).reshape(64, 16) - 48
_PART3 = np.frombuffer(_P3.encode(), np.uint8).reshape(64, 16) - 48
_ANCH2, _ANCH3A, _ANCH3B = np.array(_A2), np.array(_A3A), np.array(_A3B)
# mode: subsets, partition bits, rotation bits, index-selection bits, colour bits, alpha bits, p-bits per endpoint,
#       p-bits shared per subset, index bits, second index bits
_BC7 = {0: (3, 4, 0, 0, 4, 0, 1, 0, 3, 0), 1: (2, 6, 0, 0, 6, 0, 0, 1, 3, 0), 2: (3, 6, 0, 0, 5, 0, 0, 0, 2, 0),
        3: (2, 6, 0, 0, 7, 0, 1, 0, 2, 0), 4: (1, 0, 2, 1, 5, 6, 0, 0, 2, 3), 5: (1, 0, 2, 0, 7, 8, 0, 0, 2, 2),
        6: (1, 0, 0, 0, 7, 7, 1, 0, 4, 0), 7: (2, 6, 0, 0, 5, 5, 1, 0, 2, 0)}
_WEIGHTS = {2: np.array([0, 21, 43, 64]), 3: np.array([0, 9, 18, 27, 37, 46, 55, 64]),
            4: np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64])}


def _bc7_mode(bits, m):
    """The blocks of one mode, as their 128 bits each (n, 128), lowest bit first -> (n, 16, 4) RGBA."""
    ns, pb, rb, isb, cb, ab, epb, spb, ib, ib2 = _BC7[m]
    n = len(bits)
    pos = m + 1
    rows = np.arange(n)[:, None]

    def take(k):
        nonlocal pos
        v = (bits[:, pos:pos + k].astype(np.int64) << np.arange(k)).sum(1) if k else np.zeros(n, np.int64)
        pos += k
        return v

    part, rot, swap = take(pb), take(rb), take(isb)
    ne = 2 * ns
    ep = np.zeros((n, ne, 4), np.int64)
    for ch in range(3):
        for e in range(ne):
            ep[:, e, ch] = take(cb)
    for e in range(ne):
        ep[:, e, 3] = take(ab)
    cbits, abits = cb, ab
    if epb:                                          # one p-bit per endpoint: the lowest bit of all its channels
        for e in range(ne):
            ep[:, e] = (ep[:, e] << 1) | take(1)[:, None]
        cbits, abits = cb + 1, ab + 1 if ab else 0
    if spb:                                          # one p-bit per subset, shared by its two endpoints
        for s in range(ns):
            ep[:, 2 * s:2 * s + 2] = (ep[:, 2 * s:2 * s + 2] << 1) | take(1)[:, None, None]
        cbits = cb + 1
    ep[..., :3] = (ep[..., :3] << (8 - cbits)) | (ep[..., :3] >> (2 * cbits - 8))
    if ab:
        ep[..., 3] = (ep[..., 3] << (8 - abits)) | (ep[..., 3] >> (2 * abits - 8))
    else:
        ep[..., 3] = 255

    sub = np.zeros((n, 16), np.int64) if ns == 1 else (_PART2 if ns == 2 else _PART3)[part].astype(np.int64)
    anchor = np.zeros((n, 16), bool)
    anchor[:, 0] = True
    if ns == 2:
        anchor[rows[:, 0], _ANCH2[part]] = True
    elif ns == 3:
        anchor[rows[:, 0], _ANCH3A[part]] = True
        anchor[rows[:, 0], _ANCH3B[part]] = True

    def indices(k, anchors):
        """16 indices of k bits each, the anchors one bit shorter, read from the current position."""
        nonlocal pos
        width = k - anchors
        start = pos + np.cumsum(width, 1) - width
        idx = np.zeros((n, 16), np.int64)
        for j in range(k):
            idx |= (bits[rows, np.minimum(start + j, 127)].astype(np.int64) * (j < width)) << j
        pos += 16 * k - int(anchors[0].sum())
        return idx

    i1 = indices(ib, anchor)
    w1 = _WEIGHTS[ib][i1]
    wc = wa = w1
    if ib2:                                          # modes 4 and 5: colour and alpha have their own indices
        first = np.zeros((n, 16), bool)
        first[:, 0] = True
        w2 = _WEIGHTS[ib2][indices(ib2, first)]
        use2 = (swap == 1)[:, None]
        wc, wa = np.where(use2, w2, w1), np.where(use2, w1, w2)
    e0 = ep[rows, 2 * sub]
    e1 = ep[rows, 2 * sub + 1]
    out = np.empty((n, 16, 4), np.int64)
    out[..., :3] = ((64 - wc)[..., None] * e0[..., :3] + wc[..., None] * e1[..., :3] + 32) >> 6
    out[..., 3] = ((64 - wa) * e0[..., 3] + wa * e1[..., 3] + 32) >> 6
    for r in (1, 2, 3):                              # rotation: alpha changes places with red, green or blue
        k = rot == r
        if k.any():
            a = out[k, :, 3].copy()
            out[k, :, 3] = out[k, :, r - 1]
            out[k, :, r - 1] = a
    return out


def _bc7_blocks(b):
    """BC7 blocks (N, 16) uint8 -> (N, 16, 4) RGBA; texel k = 4 * row + column. A block with no mode bit is empty."""
    bits = np.unpackbits(b, axis=1, bitorder='little')
    first = b[:, 0].astype(np.int64)
    mode = np.full(len(b), 8)
    for m in range(7, -1, -1):
        mode[(first >> m) & 1 == 1] = m              # the lowest set bit of the first byte
    out = np.zeros((len(b), 16, 4), np.int64)
    for m in range(8):
        sel = np.nonzero(mode == m)[0]
        if len(sel):
            out[sel] = _bc7_mode(bits[sel], m)
    return out


def decode_bcn(data, w, h, n, block_height=None):
    """Mip 0 of a block-linear BCn texture as an (h, w, 4) uint8 RGBA array. n: 1 (BC1), 3 (BC3), 4 (BC4: the value in
    R, G and B, opaque), 5 (BC5: R and G, B 0, opaque), 7 (BC7)."""
    bpb = BCN_BYTES[n]
    bw, bh = (w + 3) // 4, (h + 3) // 4
    lin = deswizzle(data, bw * bpb, bh, block_height or default_block_height(bh))
    b = np.frombuffer(lin, np.uint8).reshape(bw * bh, bpb)
    if n == 1:
        px = _color_blocks(b, False)
    elif n == 3:
        px = _color_blocks(b[:, 8:], True)
        px[:, :, 3] = _alpha_blocks(b[:, :8])
    elif n == 4:
        v = _alpha_blocks(b)
        px = np.stack([v, v, v, np.full_like(v, 255)], 2)
    elif n == 5:
        r, g = _alpha_blocks(b[:, :8]), _alpha_blocks(b[:, 8:])
        px = np.stack([r, g, np.zeros_like(r), np.full_like(r, 255)], 2)
    else:
        px = _bc7_blocks(b)
    return _image(px, bw, bh, w, h)
