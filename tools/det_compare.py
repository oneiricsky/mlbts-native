#!/usr/bin/env python3
"""Compare two harness_det traces: python -I tools/det_compare.py a.trace b.trace
Per presented frame: tick, nvn call count, and the 64 KiB-chunk hashes of main's data/bss."""
import struct, sys

def load(p):
    d = open(p, "rb").read()
    assert d[:4] == b"HDT1"
    chunk, base, size = struct.unpack_from("<IQQ", d, 4)
    o, fr = 24, []
    while o + 48 <= len(d):
        f, tick, calls, dist, n, _ = struct.unpack_from("<QQQQII", d, o)
        o += 40
        if o + 8 * n > len(d): break
        fr.append((f, tick, calls, dist, struct.unpack_from(f"<{n}Q", d, o)))
        o += 8 * n
    return chunk, base, fr

ca, ba, a = load(sys.argv[1]); cb, bb, b = load(sys.argv[2])
bf = {x[0]: x for x in b}
common = [x for x in a if x[0] in bf]
print(f"frames: a {len(a)} (first {a[0][0]}, last {a[-1][0]}), b {len(b)}, common {len(common)}")
def first_bad(key):
    for i, x in enumerate(common):
        if key(x) != key(bf[x[0]]): return i
    return None
for name, key in (("tick", lambda x: x[1]), ("nvn_calls", lambda x: x[2]), ("nvn_distinct", lambda x: x[3]),
                  ("data hash (all chunks)", lambda x: x[4])):
    i = first_bad(key)
    same = sum(key(x) == key(bf[x[0]]) for x in common)
    print(f"{name}: {same}/{len(common)} frames equal; first difference: " +
          ("none" if i is None else f"frame {common[i][0]} (index {i})"))
i = first_bad(lambda x: x[4])
if i is not None:
    x = common[i]; y = bf[x[0]]
    bad = [k for k in range(min(len(x[4]), len(y[4]))) if x[4][k] != y[4][k]]
    print(f"frame {x[0]}: {len(bad)} chunks differ; offsets from main data start: {[hex(k * ca) for k in bad[:12]]}")
    # how many chunks differ in the common frames, on average, and which chunks differ most
    cnt = {}
    for x in common:
        y = bf[x[0]]
        for k in range(min(len(x[4]), len(y[4]))):
            if x[4][k] != y[4][k]: cnt[k] = cnt.get(k, 0) + 1
    top = sorted(cnt.items(), key=lambda kv: -kv[1])[:8]
    print("chunks differing in most frames:", [(hex(k * ca), v) for k, v in top])
