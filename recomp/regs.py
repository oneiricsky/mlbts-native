"""Function-local general registers for recomp/gen.py.

The lifter reads and writes the guest's X0-X30 and SP in the Cpu (c->x[n], c->sp), so every guest instruction loads
and stores memory, and the C compiler cannot keep a register in a host register across a guest store: guest stores go
through pointers that may alias the Cpu. A generated function instead copies the LOCALS registers it uses most into
locals at its entry (xN, sp_), works on those, and syncs with the Cpu only where something else reads or writes them:
before a call, an SVC, a trap, a return or a tail exit it stores the registers it changed since the last sync (spill),
and after an SVC it loads them all again (reload). The other registers stay in the Cpu.

After a call it reloads only X0-X18 and X30: AAPCS64 has the callee preserve X19-X29 and SP, so their locals still
hold what the Cpu holds. What would break that does not occur in TotK: main and subsdk0 import neither longjmp nor
the C++ unwinder, sdk's longjmp, __cxa_throw and _Unwind_* have no direct callers, and the runtime writes no register
above X3 of a running thread's Cpu except X30, which rt_call restores (runtime/hostfn.c). Guest fibers each run on a host fiber of their own with their own Cpu (runtime/kernel.c),
and ExitThread leaves by longjmp without returning. gen.py --no-callee-saved-trust reloads those registers too.

Only plain assignments write registers in the lifted C (`c->x[n] = ...`, `c->sp = ...`), and no code takes a
register's address, so the rewrite is textual. A register counts as dirty from a write until the next spill on some
path: plan() runs that forward over the function's control flow, so a call spills only what changed since the
previous call or the entry. Spilling a register that is not dirty is harmless (the local equals the Cpu), so where a
case is unclear the plan errs on spilling more.

fastball: X19-X28 stay in locals across calls (LAZY). A callee only saves them to its stack and puts them back,
so the Cpu copy a call sees may be stale: the callee saves and restores the stale value, and the caller's local still
holds the real one. A function therefore keeps every X19-X28 it uses in a local and spills them only where it leaves
(return, tail exit, SVC, trap), not before a call (SPILL_CALL). In MLB these registers hold the game's working values
in most bigger functions, and with 6 locals per function most of them lived in the Cpu: a load after every guest
store (the stores may alias the Cpu) and a store before every call. X29 and SP stay synced at calls: the runtime walks
the guest frame chain from c->x[29] (crash reports, MLB_FS_STACK, svc and ipc traces) and callees use SP. Reading a
caller's X19-X28 is outside AAPCS64: setjmp (main imports it) saves stale values, but only longjmp would use them,
and longjmp cannot work in lifted code anyway (its `ret` returns to its own caller); the unwinder is not imported.
--no-callee-saved-trust turns this off with the reloads.
"""
import re
from collections import Counter

REG = re.compile(r'c->x\[(\d+)\]|c->sp\b')
WRITE = re.compile(r'c->(?:x\[(\d+)\]|(sp))\s*=(?!=)')
# Lifted instructions that hand the Cpu to the runtime: SVCs return, BRK and undefined words do not.
ESCAPE = re.compile(r'\brt_(?:svc|brk|udf)\(c\b')
SP = 31   # index of SP in the register sets
# Markers gen.py puts where the Cpu must be current, resolved by Plan.resolve(): spill before; reload all, or reload
# what a call may change, after. SPILL_CALL is the spill before a call, which leaves LAZY registers out.
SPILL, RELOAD, RELOAD_CALL, SPILL_CALL = '\x00S', '\x00R', '\x00C', '\x00s'
CALLEE_SAVED = frozenset(range(19, 30)) | {SP}
LAZY = frozenset(range(19, 29))   # fastball: in locals whenever used, not spilled at calls (module docstring)
# Locals per function besides LAZY: the most used registers. More cost more than they save, as clang then spills them to the stack
# and the syncs stay (300 hot TotK functions: fewest instructions and memory operands at 4-6).
LOCALS = 6


def name(r):
    return 'sp_' if r == SP else f'x{r}'


def cpu(r):
    return 'c->sp' if r == SP else f'c->x[{r}]'


def refs(text):
    """Registers text reads or writes, once per occurrence."""
    return [SP if m.group(0) == 'c->sp' else int(m.group(1)) for m in REG.finditer(text)]


def written(text):
    return {SP if m.group(2) else int(m.group(1)) for m in WRITE.finditer(text)}


class Plan:
    def __init__(self, regs, spill, kept, spill_call):
        self.regs = regs     # sorted registers the function keeps in locals
        self.local = set(regs)
        self.spill = spill   # per instruction: registers to store at its sync points
        self.spill_call = spill_call   # per instruction: registers to store before a call
        self.kept = kept     # registers a call leaves as they were (CALLEE_SAVED, or none)

    def decl(self):
        """Locals at the top of the function, loaded from the Cpu."""
        return 'uint64_t ' + ', '.join(f'{name(r)} = {cpu(r)}' for r in self.regs) + ';' if self.regs else ''

    def resolve(self, i, text):
        """text of instruction i with its registers on the locals and its sync markers expanded."""
        def local(m):
            r = SP if m.group(0) == 'c->sp' else int(m.group(1))
            return name(r) if r in self.local else m.group(0)

        text = REG.sub(local, text)
        spill = ''.join(f'{cpu(r)} = {name(r)}; ' for r in sorted(self.spill[i]))
        spill_call = ''.join(f'{cpu(r)} = {name(r)}; ' for r in sorted(self.spill_call[i]))
        reload = ''.join(f' {name(r)} = {cpu(r)};' for r in self.regs)
        reload_call = ''.join(f' {name(r)} = {cpu(r)};' for r in self.regs if r not in self.kept)
        return (text.replace(SPILL_CALL, spill_call).replace(SPILL, spill).replace(RELOAD, reload)
                .replace(RELOAD_CALL, reload_call))


def plan(texts, succ, clean, n_locals=LOCALS, kept=CALLEE_SAVED):
    """texts[i]: instruction i's C with markers; succ[i]: successor indices inside the function; clean: instructions
    after which every local equals the Cpu (a call or an SVC that spills and reloads on every path through it; a
    call leaves the LAZY ones as they were); n_locals: how many registers besides LAZY to keep in locals; kept:
    registers a call does not reload."""
    n = len(texts)
    lazy = LAZY & kept
    uses = Counter(r for t in texts for r in refs(t))
    regs = {r for r in uses if r in lazy}
    regs |= {r for r, _ in sorted(((r, k) for r, k in uses.items() if r not in lazy),
                                  key=lambda kv: (-kv[1], kv[0]))[:n_locals]}
    writes = [written(t) & regs for t in texts]
    # A call (SPILL_CALL without an SVC's RELOAD) syncs everything but the LAZY registers.
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
    every = set().union(*writes) if writes else set()
    for i in range(n):
        if not seen[i]:   # not reached from the entry in the plan's flow: anything may be dirty
            dirty[i] = every
    # A sync point stores what was dirty on entry to its instruction and what the instruction wrote before it
    # (c->x[30] of a call): all the instruction's writes, which is at most a little more.
    return Plan(sorted(regs), [dirty[i] | writes[i] if SPILL in texts[i] else set() for i in range(n)], kept,
                [(dirty[i] | writes[i]) - lazy if SPILL_CALL in texts[i] else set() for i in range(n)])
