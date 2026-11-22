"""A PNG writer for looking at rendered pictures (render_all.py --out / --sheet), with the standard library and numpy.

    write(path, px)      px: (h, w, 4) uint8 RGBA. Every row uses the same filter: None, Sub or Up, whichever is smallest.
"""
import struct
import zlib

import numpy as np

SIG = b'\x89PNG\r\n\x1a\n'


def _chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))


def write(path, px):
    px = np.ascontiguousarray(px, np.uint8)
    h, w = px.shape[:2]
    sub, up = px.copy(), px.copy()
    sub[:, 1:] -= px[:, :-1]
    up[1:] -= px[:-1]
    best = None
    for f, data in ((0, px), (1, sub), (2, up)):                 # one row filter for the file: whichever packs smallest
        rows = np.full((h, 1 + w * 4), f, np.uint8)              # filter byte + the row
        rows[:, 1:] = data.reshape(h, w * 4)
        z = zlib.compress(rows.tobytes(), 9)
        if best is None or len(z) < len(best):
            best = z
    with open(path, 'wb') as f:
        f.write(SIG + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + _chunk(b'IDAT', best) +
                _chunk(b'IEND', b''))
