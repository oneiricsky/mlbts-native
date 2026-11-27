"""Shows what changes when a boot option is set: the code on each side of the branch after every lookup.

    python -I tools/config_effects.py [HASH ...]      # default: every option without a documented name

For each `has` lookup it follows the first test of the result and walks both sides up to their next
conditional branch, return or meeting point, listing calls (with the map's read role), strings, stores and
constants. A short look at each side, not a full data-flow reading. Needs tools/map_all.py to have run.
"""
import bisect
import json
import re
import sys
from pathlib import Path

import capstone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_options as c  # noqa: E402

BASE = 0x7000000000
STEPS = 22


def load(name, field):
    out = {}
    for line in (c.ROOT / 'work/map/index' / name).read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r.get('module', 'main') == 'main' and r.get(field):
            out[int(r['addr'], 16) - BASE] = r[field]
    return out


class Image:
    def __init__(self):
        nso = c.Nso(str(c.GAME / 'exefs/main'))
        self.img = bytes(nso.image)
        self.md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        self.roles = load('roles.jsonl', 'role')
        self.roles.update(load('roles_read.jsonl', 'role'))

    def at(self, a):
        return next(self.md.disasm(self.img[a:a + 4], a), None)

    def string(self, a):
        s = self.img[a:a + 80].split(b'\0')[0] if 0 < a < len(self.img) else b''
        return s.decode() if len(s) >= 4 and all(32 <= x < 127 for x in s) else None

    def side(self, start, other):
        """Walk one side of the branch. Returns (what it does, addresses visited)."""
        a, seen, did, pages = start, [], [], {}
        for _ in range(STEPS):
            x = self.at(a)
            if x is None or a == other:
                did.append('(joins the other side)' if a == other else '(undecodable)')
                break
            seen.append(a)
            m, ops = x.mnemonic, [o.strip() for o in x.op_str.split(',')]
            if m == 'adrp':
                pages[ops[0]] = int(ops[1][1:], 0)
            elif m == 'add' and len(ops) == 3 and ops[1] in pages and ops[2].startswith('#'):
                t = pages[ops[1]] + int(ops[2][1:], 0)
                s = self.string(t)
                pages[ops[0]] = t
                did.append(f'"{s}"' if s else f'&{t:#x}')
            elif m in ('bl', 'b') and ops[0].startswith('#'):
                t = int(ops[0][1:], 0)
                if m == 'b' and abs(t - a) < 0x4000 and t not in self.roles:
                    a = t
                    continue
                did.append(f'{"call" if m == "bl" else "jump"} {t:#x}'
                           + (f' <{self.roles[t][:70]}>' if t in self.roles else ''))
                if m == 'b':
                    break
            elif m in ('str', 'strb', 'strh', 'stp') and 'sp' not in x.op_str and 'x29' not in x.op_str:
                base = re.search(r'\[(\w+)', x.op_str)
                where = f' (global {pages[base[1]]:#x})' if base and base[1] in pages else ''
                did.append(f'{m} {x.op_str}{where}')
            elif m in ('mov', 'movz', 'cmp', 'fmov') and '#' in x.op_str:
                did.append(f'{m} {x.op_str}')
            elif m == 'ret':
                did.append('return')
                break
            elif m.startswith(('b.', 'cb', 'tb')):
                did.append(f'then tests {m} {x.op_str}')
                break
            a += 4
        return did, seen

    def effect(self, site):
        """(side when set, side when not set) for a `has` call at `site`, or None if the result is not tested here."""
        holders = {'w0', 'x0'}
        a = site + 4
        for _ in range(12):
            x = self.at(a)
            ops = [o.strip() for o in x.op_str.split(',')]
            if x.mnemonic in ('tbz', 'tbnz', 'cbz', 'cbnz') and ops[0] in holders:
                target, fall = int(ops[-1][1:], 0), a + 4
                on, off = (target, fall) if x.mnemonic.endswith('nz') else (fall, target)
                return self.side(on, off)[0], self.side(off, on)[0]
            if x.mnemonic in ('mov', 'and', 'eor') and len(ops) > 1 and ops[1] in holders:
                holders.add(ops[0])
                if x.mnemonic == 'eor':
                    return [f'result is inverted: {x.op_str}'], self.side(a + 4, None)[0]
            elif x.mnemonic in ('strb', 'str') and ops[0] in holders:
                return [f'result is stored: {x.mnemonic} {x.op_str}'], self.side(a + 4, None)[0]
            elif x.mnemonic in ('bl', 'b', 'ret'):
                return None
            a += 4
        return None


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    _, used, _, per_hash = c.scan()
    doc = c.documented()
    wanted = [int(a, 16) for a in sys.argv[1:]] or sorted(h for h in used if h not in doc)
    img = Image()
    starts = c.function_starts()
    tested = untested = 0
    for h in wanted:
        print(f'## 0x{h:08X} ({",".join(sorted(used[h]))}, {len(per_hash[h])} sites)')
        shown = set()
        for site in per_hash[h]:
            e = img.effect(site)
            tested += e is not None
            untested += e is None
            fn = starts[bisect.bisect_right(starts, site) - 1]
            text = None if e is None else ('; '.join(e[0]) or '-', '; '.join(e[1]) or '-')
            if text in shown or len(shown) >= 3:
                continue
            shown.add(text)
            print(f' {fn:x}@{site:x} {img.roles.get(fn, "")[:90]}')
            if text:
                print(f'   set:   {text[0][:330]}\n   unset: {text[1][:330]}')
            else:
                print('   result not tested right after the call')
    print(f'sites followed {tested}, not followed {untested}')


if __name__ == '__main__':
    main()
