"""Reader for the game's IFF0 MODL models (X.MOD + X.0.MOD) from the player's own install.

X.MOD holds the description: the vertex layout as XML (STRGINLA), buffer headers (CLAS_VBO / CLAS_EBO: vertex count,
buffer index, stride), the texture names (STRGTEXN). X.0.MOD holds the data: VOID_VBO chunks (one per buffer, in
order) and VOID_EBO (16-bit triangle-list indices).
"""
import re
import struct
from pathlib import Path

import numpy as np


def chunks(b):
    """[(tag, a, payload)] of the top level of an IFF0 file (16-byte chunk headers: tag[8], u32 a, u32 size)."""
    out, off = [], 0x10
    while off + 16 <= len(b):
        tag = b[off:off + 8]
        if not re.fullmatch(rb'[A-Z0-9_]{8}', tag):
            break
        a, size = struct.unpack_from('<II', b, off + 8)
        out.append((tag.decode(), a, b[off + 16:off + 16 + size]))
        off += 16 + size
    return out


FMT = {  # component format -> (bytes, decoder)
    'kFloat_16': 2, 'kFloat_32': 4, 'kUInt_8': 1, 'kFP_0_0_8': 1, 'kSInt_Compressed': 2,
}


def parse_layout(xml):
    """[(buffer name, [(attribute name, semantic, [component formats])])]"""
    bufs = []
    for bm in re.finditer(r'<BufferDesc name="([^"]+)">(.*?)</BufferDesc>', xml, re.S):
        attrs = []
        for am in re.finditer(r'<AttributeDesc name="([^"]+)" semantic="([^"]+)">(.*?)</AttributeDesc>', bm.group(2), re.S):
            comps = re.findall(r'format="([^"]+)"', am.group(3))
            attrs.append((am.group(1), am.group(2), comps))
        bufs.append((bm.group(1), attrs))
    return bufs


def attr_size(comps):
    if all(c.startswith('kFP_') and c != 'kFP_0_0_8' for c in comps):
        return 4                                    # a packed 10-10-10-2 word
    return sum(FMT[c] for c in comps)


def decode_attr(raw, n, stride, off, comps):
    """(n, k) float array for one attribute."""
    if comps[0] == 'kSInt_Compressed':              # progressive-mesh LOD table: not needed for rendering
        return np.zeros((n, len(comps)), np.float32)
    raw = raw[:n * stride]                          # buffers are padded past n * stride
    if comps[0] == 'kFloat_16':
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, stride)[:n, off:off + 2 * len(comps)]
        return a.copy().view('<f2').astype(np.float32)
    if comps[0] == 'kFloat_32':
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, stride)[:n, off:off + 4 * len(comps)]
        return a.copy().view('<f4')
    if comps[0] in ('kUInt_8', 'kFP_0_0_8'):
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, stride)[:n, off:off + len(comps)].astype(np.float32)
        return a / 255.0 if comps[0] == 'kFP_0_0_8' else a
    # packed signed 10-10-10 (+2): kFP_1_0_9 x3, kFP_0_0_2
    w = np.frombuffer(raw, dtype=np.uint8).reshape(-1, stride)[:n, off:off + 4].copy().view('<u4')[:, 0]
    out = []
    for k in range(3):
        v = ((w >> (10 * k)) & 0x3FF).astype(np.int32)
        v = np.where(v >= 512, v - 1024, v)
        out.append(v / 511.0)
    return np.stack(out, 1).astype(np.float32)


def parse_layouts(xml):
    """[[(buffer name, [(attribute name, semantic, [component formats])])] per InputLayout], every BufferDesc kept
    (also ones with extra XML attributes such as blendshapes="true"), so the VBO headers' buffer indices line up."""
    out = []
    for lm in re.finditer(r'<InputLayout[^>]*>(.*?)</InputLayout>', xml, re.S):
        bufs = []
        for bm in re.finditer(r'<BufferDesc name="([^"]+)"[^>]*>(.*?)</BufferDesc>', lm.group(1), re.S):
            attrs = [(am.group(1), am.group(2), re.findall(r'format="([^"]+)"', am.group(3)))
                     for am in re.finditer(r'<AttributeDesc name="([^"]+)" semantic="([^"]+)">(.*?)</AttributeDesc>',
                                           bm.group(2), re.S)]
            bufs.append((bm.group(1), attrs))
        out.append(bufs)
    return out or [parse_layout(xml)]


class Model:
    """Vertices of all the model's InputLayouts are concatenated (layout 0 first): .attrs[name] has one row per vertex
    of the whole model (zeros for layouts without that attribute). .layout_base[i] / .layout_count[i] give each
    layout's vertex range; each part has a 'layout' key."""

    def __init__(self, path):
        path = Path(path)
        desc = path.read_bytes()
        data = path.with_name(path.stem + '.0.MOD').read_bytes()
        dc = chunks(desc)
        get = lambda tag: [p for t, _, p in dc if t == tag]
        xml = get('STRGINLA')[0].decode('latin1').strip('\0')
        self.layout = parse_layout(xml)
        layouts = parse_layouts(xml)
        self.textures = [s.decode() for s in get('STRGTEXN')[0].split(b'\0') if s] if get('STRGTEXN') else []
        nvbo = next(a for t, a, _ in dc if t == 'CLAS_VBO')
        vbo_hdrs = get('CLAS_VBO')[0]
        # VBO header (0x40 each): u32 vertex count, u32 buffer index in its layout, u16 stride, u16 layout index
        hdrs = [struct.unpack_from('<IIHH', vbo_hdrs, i * 0x40) for i in range(nvbo)]
        dd = chunks(data)
        vbos = [p for t, _, p in dd if t == 'VOID_VBO']
        ebos = [(a, p) for t, a, p in dd if t == 'VOID_EBO']
        nl = len(layouts)
        lcount = [0] * nl
        for cnt, bi, stride, li in hdrs:
            if bi == 0 and li < nl:
                lcount[li] = cnt
        self.layout_count = lcount
        self.layout_base = [sum(lcount[:i]) for i in range(nl)]
        self.nverts = sum(lcount)
        # index buffers: one per layout, in order (chunk 'a' = index count; 16-bit, or 32-bit when the payload fits)
        lidx = []
        for k, (a, p) in enumerate(ebos):
            if k == 0 and nl == 1:
                a = struct.unpack_from('<I', get('CLAS_EBO')[0], 8)[0] or a
            wide = a > 8 and len(p) >= 4 * a and lcount[min(k, nl - 1)] > 0xFFFF
            dt = '<u4' if wide else '<u2'
            lidx.append(np.frombuffer(p[:a * (4 if wide else 2)], dtype=dt).astype(np.int64))
        # Draw records (VOIDDRBL): each starts with 0xfffffffe; +0x0c vertex count; from +0x28 (count, start) pairs of
        # its LOD chain in its layout's index buffer, LOD 0 second (LODs follow each other). Indices are relative to the
        # part's first vertex: a layout's parts' vertices follow each other. Names from STRGDGRP, in the same order.
        # The layout of a record: a chain starting at 0 opens the next layout; otherwise the layout whose previous
        # chain ended where this one starts.
        names = [s.decode('latin1') for s in get('STRGDGRP')[0].split(b'\0') if s][1:] if get('STRGDGRP') else []
        # A draw group can own several records: INT0DGRP (16 bytes each: u32 record count, pad, u32 first record, 0)
        # gives each record its group's name.
        dg = get('INT0DGRP')[0] if get('INT0DGRP') else b''
        rec_names = []
        for i in range(min(len(dg) // 16, len(names))):
            cnt, _, first = struct.unpack_from('<III', dg, i * 16)
            if first != len(rec_names) or cnt > 4096:
                rec_names = []
                break
            rec_names += [names[i]] * cnt
        if rec_names:
            names = rec_names
        drbl = get('VOIDDRBL')[0] if get('VOIDDRBL') else b''
        self.parts, o, k = [], 0, 0
        nxt = [None] * nl           # expected next chain start per layout
        vbase = [0] * nl
        opened = 0
        cur = 0
        # record offsets: from INT0DRBL (16 bytes each: u32 index, pad, u32 offset, 0) when it agrees, else a scan for
        # the marker (the scan can also hit float data inside long records)
        tab = get('INT0DRBL')[0] if get('INT0DRBL') else b''
        offs = [struct.unpack_from('<I', tab, i * 16 + 8)[0] for i in range(len(tab) // 16)]
        if not offs or any(ro + 64 > len(drbl) or drbl[ro:ro + 4] != b'\xfe\xff\xff\xff' for ro in offs):
            offs = []
            while drbl:
                o = drbl.find(b'\xfe\xff\xff\xff', o)
                if o < 0:
                    break
                offs.append(o)
                o += 4
        for o in offs:
            w = struct.unpack_from('<16I', drbl, o)
            vcount, count, start = w[3], w[12], w[13]
            end, q = start + count, o + 0x38
            while q + 8 <= len(drbl):
                c2, s2 = struct.unpack_from('<II', drbl, q)
                if s2 != end or c2 == 0 or c2 > 0x1000000:
                    break
                end += c2
                q += 8
            if nl > 1:
                hit = [i for i in range(nl) if nxt[i] == start and nxt[i] is not None]
                if start == 0 and opened < nl:
                    cur = opened
                    opened += 1
                elif hit:
                    cur = hit[0]
            li = cur
            nxt[li] = end
            name = names[k].split('|')[1] if k < len(names) and '|' in names[k] else f'part{k}'
            idx = lidx[min(li, len(lidx) - 1)] if lidx else np.zeros(0, np.int64)
            tri = idx[start:start + count]
            tri = tri[:len(tri) // 3 * 3]
            base = self.layout_base[li] + vbase[li]
            self.parts.append(dict(name=name, base=base, vcount=vcount, layout=li, tris=(tri + base).reshape(-1, 3)))
            vbase[li] += vcount
            k += 1
        if not self.parts:
            all_idx = lidx[0] if lidx else np.zeros(0, np.int64)
            self.parts.append(dict(name='all', base=0, vcount=self.nverts, layout=0,
                                   tris=all_idx[:len(all_idx) // 3 * 3].reshape(-1, 3)))
        live = [p['tris'] for p in self.parts if 'lowlod' not in p['name'].lower()]
        self.indices = np.concatenate(live) if live else np.zeros((0, 3), np.int64)
        self.attrs = {}
        for (cnt, bi, stride, li), raw in zip(hdrs, vbos):
            if li >= nl or bi >= len(layouts[li]) or cnt != lcount[li] or cnt == 0:
                continue                                # e.g. ProgressiveMesh / empty blendshape buffers
            off = 0
            for aname, sem, comps in layouts[li][bi][1]:
                arr = decode_attr(raw, cnt, stride, off, comps)
                off += attr_size(comps)
                if aname not in self.attrs:
                    self.attrs[aname] = np.zeros((self.nverts, arr.shape[1]), np.float32)
                    self.attrs[aname + '#set'] = set()
                if li in self.attrs[aname + '#set'] or self.attrs[aname].shape[1] != arr.shape[1]:
                    continue
                self.attrs[aname + '#set'].add(li)
                self.attrs[aname][self.layout_base[li]:self.layout_base[li] + cnt] = arr
        for key in [k for k in self.attrs if k.endswith('#set')]:
            del self.attrs[key]

    @property
    def positions(self):
        return self.attrs['Position'][:, :3]

    def uv(self, name=None):
        uvs = [k for k in self.attrs if k.startswith('UV')]
        return self.attrs[name or uvs[0]]
