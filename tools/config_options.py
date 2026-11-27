"""Lists every boot-config option the 1.0.20 game looks up (docs/dev-config.md), with the names that can be recovered.

    python -I tools/config_options.py [--names] [--check]

--names also hashes every word in main, sdk and the small RomFS files (about 800 MB) to recover unlisted names.
--check exits 1 when a documented name does not hash to its documented value, or a documented hash is not looked up.
Needs capstone. Reads the player's own game files in work/build/game; the output is derived from game code.
"""
import argparse
import bisect
import collections
import os
import re
import struct
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from nsoinfo import Nso  # noqa: E402

GAME = ROOT / 'work/build/game'
# The accessors of the two option tables (number table 0x2ca5ff8, text table 0x2ca6010). No other code reads them.
READERS = {0x5398c0: 'has', 0x539920: 'equals', 0x539980: 'get', 0x53a690: 'text'}
WRITERS = {0x5399f0: 'set', 0x539af0: 'erase'}
# Call sites whose hash is not a plain constant just before the call, read from the disassembly.
BY_HAND = {0x400c: 0x8D669109, 0x21bc68: 0x21108949, 0xbafe9c: 0x21108949, 0xb38abc: 0x21108949,
           0xdcd3cc: 0xD24CB85D, 0xf30498: 0xBBBDD089, 0xf306ec: 0xBBBDD089}
BY_NAME = 0x4a7990   # hashes a string handed in at run time
DATA_EXT = {'TXT', 'XML', 'JSON', 'SCR', 'CB', 'TBL', 'CSV', 'INI', 'CFG', 'FSO', 'XBN', 'KEY', 'CTL', 'BIN', 'PLB',
            'DAT', 'FBN', 'MG', 'EN_SRT', 'LANG_EN'}


def option_hash(name):
    v = 0
    for c in name.upper():
        v = ((v << 4) + c) & 0xffffffff
        g = v & 0xf0000000
        if g:
            v = (v & 0x0fffffff) ^ (g >> 24)
    return (v * 0x9E3779B7 + (~v & 0xffffffff) * 0x61C88641) & 0xffffffff


def signed(v, bits):
    return v - (1 << bits) if v >> (bits - 1) else v


def function_starts():
    starts = set()
    for f in (ROOT / 'work/gen/main').glob('*.c'):
        starts.update(int(m, 16) - 0x7000000000 for m in re.findall(r'^void f_(70[0-9a-f]{8})\(Cpu', f.read_text(), re.M))
    if not starts:
        sys.exit('work/gen/main is empty: build the game first (tools/build.py)')
    return sorted(starts)


def constant_w0(md, img, starts, site):
    """The value of w0 at the call, following mov/movk/add back to the start of the function."""
    lo = starts[bisect.bisect_right(starts, site) - 1]
    ins = list(md.disasm(img[lo:site], lo))
    if not ins or ins[-1].address != site - 4:
        return None

    def value(reg, k, depth=0):
        for n in range(k, -1, -1):
            x = ins[n]
            ops = [o.strip() for o in x.op_str.split(',')]
            if x.mnemonic == 'bl' and int(reg[1:]) < 19:
                return None
            if (not ops or ops[0][:1] not in ('w', 'x') or ops[0][1:] != reg[1:]
                    or x.mnemonic.startswith(('st', 'cmp', 'cb', 'tb'))):
                continue
            shift = int(ops[-1].split('#')[1], 0) if ops[-1].startswith('lsl') else 0
            if x.mnemonic in ('mov', 'movz') and ops[1].startswith('#'):
                return (int(ops[1][1:], 0) << shift) & 0xffffffff
            if x.mnemonic == 'movk':
                low = value(reg, n - 1, depth)
                return None if low is None else (low & ~(0xffff << shift) | int(ops[1][1:], 0) << shift) & 0xffffffff
            if depth < 4 and x.mnemonic == 'mov' and ops[1][0] == 'w':
                return 0 if ops[1] == 'wzr' else value(ops[1], n - 1, depth + 1)
            if depth < 4 and x.mnemonic == 'add' and ops[1][0] == 'w' and ops[2].startswith('#'):
                base = value(ops[1], n - 1, depth + 1)
                return None if base is None else (base + (int(ops[2][1:], 0) << shift)) & 0xffffffff
            return None
        return None
    return value('w0', len(ins) - 1)


def scan():
    nso = Nso(str(GAME / 'exefs/main'))
    img = bytes(nso.image)
    text_off, text_size, _ = nso.segments['text']
    targets = {**READERS, **WRITERS}
    starts = function_starts()
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    sites = collections.Counter()
    used = collections.defaultdict(set)
    per_hash = collections.Counter()
    unresolved = []
    for i, w in enumerate(struct.unpack_from('<%dI' % (text_size // 4), img, text_off)):
        if (w & 0x7C000000) != 0x14000000:
            continue
        at = text_off + i * 4
        fn = targets.get(at + signed(w & 0x3FFFFFF, 26) * 4)
        if not fn:
            continue
        sites[fn] += 1
        h = BY_HAND[at] if at in BY_HAND else constant_w0(md, img, starts, at)
        if h is None:
            unresolved.append(at)
        elif h > 1:   # 0 is the by-name lookup with no name; two calls pass a plain 1
            used[h].add(fn)
            per_hash[h] += 1
    return sites, used, unresolved, per_hash


def documented():
    doc = (ROOT / 'docs/dev-config.md').read_text(encoding='utf-8')
    return {int(m.group(2), 16): m.group(1) for m in re.finditer(r'^\| `(\w+)` \| `0x([0-9A-Fa-f]{8})` \|', doc, re.M)}


def recover(wanted):
    words = {}

    def feed(blob, src):
        for t in re.findall(rb'[A-Za-z_][A-Za-z0-9_.\-]{2,48}', blob):
            for p in {t, t.strip(b'-._'), *re.split(rb'[.\-]', t)}:
                if len(p) >= 3:
                    words.setdefault(p.upper(), (p, src))
    for m in ('main', 'sdk'):
        feed(bytes(Nso(str(GAME / 'exefs' / m)).image), 'exefs/' + m)
    for d, _, files in os.walk(GAME / 'romfs'):
        for f in files:
            p = os.path.join(d, f)
            if f.rsplit('.', 1)[-1].upper() in DATA_EXT and os.path.getsize(p) < 64 << 20:
                feed(Path(p).read_bytes(), os.path.relpath(p, GAME / 'romfs').replace(os.sep, '/'))
    found = collections.defaultdict(list)
    for u, (p, src) in words.items():
        h = option_hash(u)
        if h in wanted:
            found[h].append(f'{p.decode()} ({src})')
    print(f'{len(words)} words hashed; about {len(words) * len(wanted) / 2 ** 32:.2f} matches expected by chance')
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--names', action='store_true')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    sites, used, unresolved, per_hash = scan()
    doc = documented()
    read = {h for h, f in used.items() if f & set(READERS.values())}
    wrong = {h: n for h, n in doc.items() if option_hash(n.encode()) != h}
    missing = {h: n for h, n in doc.items() if h not in read}
    print('call sites:', ', '.join(f'{k} {v}' for k, v in sorted(sites.items())))
    print('unresolved sites:', [hex(s) for s in unresolved], f'(expected: {BY_NAME:#x}, the by-name lookup)')
    print(f'distinct hashes read: {len(read)}; documented: {len(doc)}; documented name hashes wrong: '
          f'{[(n, hex(h)) for h, n in wrong.items()]}; documented but not read: {list(missing.values())}')
    found = recover(set(used)) if a.names else {}
    for h in sorted(used):
        name = doc.get(h, '') if h not in wrong else ''
        print(f'0x{h:08X}  {per_hash[h]:3} {",".join(sorted(used[h])):14} {name or "; ".join(found.get(h, [])[:3])}')
    if a.check and (wrong or missing or unresolved != [BY_NAME]):
        sys.exit(1)


if __name__ == '__main__':
    main()
