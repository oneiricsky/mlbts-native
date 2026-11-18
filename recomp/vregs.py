"""Function-local FP/SIMD registers for recomp/gen.py (fastball).

The SIMD lowering (recomp/simd_c.py, runtime/core/simd.h) works on the guest's V0-V31 in the Cpu (c->v[n]). Guest
stores go through pointers that may alias the Cpu, so clang reloads every V register after each guest store and
stores every result back: in MLB's matches about a tenth of the samples in game code were such c->v accesses. A
generated function that uses V registers instead works on a local array `vreg VB[32]` (simd.h's macros and register
helpers take it as VB), which no guest pointer can reach; clang keeps each register in an XMM register (SROA) where
every index is constant. All accesses are whole-vector ones (simd.h VGET/VSET, element reads, vector lanes): with
4- and 8-byte pointer views clang kept a register as a 128-bit integer in two general registers. The function loads
the registers it uses at its entry and syncs with the Cpu like recomp/regs.py does for the general registers: before
a call, an SVC, a trap, a return or a tail exit it stores the V registers it changed (spill), and after a call it
reloads V0-V7 and V16-V31, after an SVC all of them.

V8-V15 are kept like X19-X28 (regs.LAZY): AAPCS64 has a callee preserve their low 64 bits (D8-D15), so a call does
not spill them; the callee saves and restores the Cpu copy, and the caller's local stays right (their upper halves
are unknown after a call on the guest too). Functions without a plan (an unresolved computed br) use
`vreg *const VB = (vreg *)c->v`.

The registers each instruction writes and reads are found in its C after rewrite(): simd.h's register macros and the
register arguments of its helpers (HELPERS). Anything else makes the instruction touch all 32 registers, which only
costs speed.
"""
import re

from regs import RELOAD, RELOAD_CALL, SPILL, SPILL_CALL

ALL = frozenset(range(32))
LAZY = frozenset(range(8, 16))

# simd.h helpers that take (Cpu *c, vreg *VB, ...): positions, among the arguments after VB, of the written and the
# read register numbers (a negative number is no register); None: a multi-register helper, decoded in _helper().
HELPERS = {
    'fp_op_s': ([1], [2, 3]), 'fp_op_d': ([1], [2, 3]),
    'fp_fma_s': ([2], [3, 4, 5]), 'fp_fma_d': ([2], [3, 4, 5]),
    'sl_gen': ([3], [3, 7, 10]),
    'sl_addlp': ([4], [4, 5]), 'sl_across': ([4], [5]),
    'sl_pmull64': ([1], [2, 3]),
    'sv_fred_s': ([1], [2]),
    'sv_fcvtl': ([2], [3]), 'sv_fcvtn': ([3], [3, 4]),
    'sv_aes': ([1], [1, 2]), 'sv_sha1hash': ([1], [1, 2, 3]), 'sv_sha256hash': ([1], [1, 2, 3]),
    'sv_sha_misc': ([1], [1, 2, 3]),
    'sv_tbl': None, 'sl_ldm': None, 'sl_stm': None, 'sl_lds': None, 'sl_sts': None, 'sl_ldr': None,
}
CALL = re.compile(r'\b(' + '|'.join(HELPERS) + r')\(c, ')
VBCALL = re.compile(r'\b(' + '|'.join(HELPERS) + r')\(c, VB, ')
MACRO = re.compile(r'\b(VREG|VQ|VS8|VS16|VS32|VS64|VSF32|VSF64|VHI64|VW|FP_SETS|FP_SETD|SV_FOP_S|SV_FOP_D|VGET|VSET)\(')
LANE = re.compile(r'\(\((uint8_t|sa16|sa32|sa64) \*\)&c->v\[(\d+)\]\)\[')
LANE_T = {'uint8_t': 'vu8', 'sa16': 'vu16', 'sa32': 'vu32', 'sa64': 'vu64'}
WRITE = re.compile(r'\bc->v\[(\d+)\] = ')
READ = re.compile(r'\bc->v\[(\d+)\]')
WRITTEN_AFTER = re.compile(r'\s*(\[[^\]]*\]\s*)?=(?!=)')   # what follows a macro written to (lane or whole)


def _statement_end(text, i):
    """Index of the ';' ending the expression that starts at text[i]."""
    depth = 0
    while i < len(text):
        ch = text[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ';' and depth == 0:
            return i
        i += 1
    raise ValueError('no end of statement')


def rewrite(text):
    """Lifted C on the Cpu's V registers -> the same on VB: lane pointers ((sa32 *)&c->v[n])[i] become vector lanes
    VREG(vu32, n)[i], c->v[n] = x becomes VSET(n, x), other c->v[n] VGET(n), and the register helpers get VB."""
    if 'c->v[' not in text and not CALL.search(text):
        return text
    text = LANE.sub(lambda m: f'VREG({LANE_T[m.group(1)]}, {m.group(2)})[', text)
    while True:
        m = WRITE.search(text)
        if not m:
            break
        e = _statement_end(text, m.end())
        text = f'{text[:m.start()]}VSET({m.group(1)}, {text[m.end():e]}){text[e:]}'
    text = READ.sub(lambda m: f'VGET({m.group(1)})', text)
    return CALL.sub(lambda m: f'{m.group(1)}(c, VB, ', text)


def _args(text, start):
    """Top-level comma-separated arguments of the call whose '(' is at text[start - 1]; (args, end)."""
    depth, cur, out, i = 0, '', [], start
    while i < len(text):
        ch = text[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            if depth == 0:
                out.append(cur.strip())
                return out, i + 1
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
        i += 1
    raise ValueError('unbalanced call')


def _int(s):
    return int(s, 0)


def _helper(name, a):
    """(writes, reads) of a helper call; a = its arguments after (c, VB)."""
    spec = HELPERS[name]
    if spec is not None:
        w, r = spec
        regs = [_int(a[k]) for k in r]
        return {_int(a[k]) for k in w}, {x for x in regs if x >= 0}
    if name == 'sv_tbl':   # (Q, len, tbx, d, n, m)
        ln, d, n, m = _int(a[1]), _int(a[3]), _int(a[4]), _int(a[5])
        return {d}, {d, m} | {(n + i) & 31 for i in range(ln + 1)}
    if name in ('sl_ldm', 'sl_stm'):   # (Q, sz, selem, rpt, t, ea)
        selem, rpt, t = _int(a[2]), _int(a[3]), _int(a[4])
        rs = {(t + i) & 31 for i in range(rpt + selem - 1)}
        return (rs, set()) if name == 'sl_ldm' else (set(), rs)
    if name in ('sl_lds', 'sl_sts'):   # (sz, selem, idx, t, ea)
        selem, t = _int(a[1]), _int(a[3])
        rs = {(t + i) & 31 for i in range(selem)}
        return (rs, rs) if name == 'sl_lds' else (set(), rs)
    if name == 'sl_ldr':   # (Q, sz, selem, t, ea)
        selem, t = _int(a[2]), _int(a[3])
        return {(t + i) & 31 for i in range(selem)}, set()
    raise ValueError(name)


def effect(text):
    """(written, read) V registers of one instruction's C (after rewrite()), or None when it cannot tell."""
    w, r = set(), set()
    try:
        if 'c->v[' in text or re.search(r'\bVB\[', text):
            return None   # a form rewrite() does not know
        for m in MACRO.finditer(text):
            name = m.group(1)
            a, end = _args(text, m.end())
            if name in ('VW', 'SV_FOP_S', 'SV_FOP_D'):
                w.add(_int(a[2]))
            elif name in ('FP_SETS', 'FP_SETD', 'VSET'):
                w.add(_int(a[0]))
            else:
                n = _int(a[-1])
                if WRITTEN_AFTER.match(text, end):   # VREG(T, n)[i] = x: a lane written, the others kept
                    w.add(n)
                r.add(n)
        for m in VBCALL.finditer(text):
            a, _ = _args(text, m.end(1) + 1)   # a: c, VB, then the helper's own arguments
            hw, hr = _helper(m.group(1), a[2:])
            w |= hw
            r |= hr
    except (ValueError, IndexError):
        return None
    return w, r


class Plan:
    def __init__(self, used, spill, spill_call, lazy=LAZY, unparsed=0):
        self.used = sorted(used)
        self.spill = spill
        self.spill_call = spill_call
        self.lazy = lazy             # registers a call neither spills nor reloads
        self.unparsed = unparsed     # instructions whose V registers effect() could not read (taken as all)

    def decl(self):
        if not self.used:
            return ''
        return 'vreg VB[32]; ' + ' '.join(f'VB[{k}] = *(vreg *)&c->v[{k}];' for k in self.used)

    def resolve(self, i, text):
        """text with the V register syncs added next to the general registers' sync markers."""
        if not self.used:
            return text
        sp = ''.join(f'*(vreg *)&c->v[{k}] = VB[{k}]; ' for k in sorted(self.spill[i]))
        spc = ''.join(f'*(vreg *)&c->v[{k}] = VB[{k}]; ' for k in sorted(self.spill_call[i]))
        rl = ''.join(f' VB[{k}] = *(vreg *)&c->v[{k}];' for k in self.used)
        rlc = ''.join(f' VB[{k}] = *(vreg *)&c->v[{k}];' for k in self.used if k not in self.lazy)
        sub = {SPILL: sp + SPILL, SPILL_CALL: spc + SPILL_CALL, RELOAD: RELOAD + rl, RELOAD_CALL: RELOAD_CALL + rlc}
        return re.sub('|'.join(map(re.escape, sub)), lambda m: sub[m.group(0)], text)


def plan(texts, succ, clean, lazy=LAZY):
    """texts[i]: instruction i's C (rewritten, with regs.py's markers); succ, clean as for regs.plan; lazy: registers
    a call keeps (LAZY, or none without the callee-saved trust)."""
    n = len(texts)
    eff = [effect(t) for t in texts]
    unparsed = sum(e is None for e in eff)
    eff = [(set(ALL), set(ALL)) if e is None else e for e in eff]
    used = set()
    for w, r in eff:
        used |= w | r
    if not used:
        return Plan(set(), [set()] * n, [set()] * n)
    writes = [e[0] for e in eff]
    call = [SPILL_CALL in t and RELOAD not in t for t in texts]
    dirty = [set() for _ in range(n)]
    seen = [False] * n
    work = [0] if n else []
    if n:
        seen[0] = True
    while work:
        i = work.pop()
        out = dirty[i] | writes[i]
        if i in clean:
            out = out & lazy if call[i] else set()
        for s in succ[i]:
            if not seen[s] or not out <= dirty[s]:
                seen[s] = True
                dirty[s] |= out
                work.append(s)
    every = set().union(*writes)
    for i in range(n):
        if not seen[i]:   # not reached from the entry in the plan's flow: anything may be dirty
            dirty[i] = every
    # A sync point stores what was dirty on entry to its instruction and what the instruction wrote.
    spill = [dirty[i] | writes[i] if SPILL in texts[i] else set() for i in range(n)]
    spill_call = [(dirty[i] | writes[i]) - lazy if SPILL_CALL in texts[i] else set() for i in range(n)]
    return Plan(used, spill, spill_call, lazy, unparsed)
