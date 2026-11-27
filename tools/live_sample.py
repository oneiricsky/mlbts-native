"""Sample the threads of an already running game (Windows), for when MLB_SAMPLER was not set at launch.

usage: python -I tools/live_sample.py <pid> <out> [--seconds 60] [--period-ms 10] [--threads 8] [--dbg-path DIR]

Each tick suspends one busy thread at a time, walks its stack and resumes it. Only the --threads busiest threads (by
CPU time over the first second) are sampled. Writes two files:
  <out>          the "totk-prof 1" format of tools/prof_report.py (pass the exe's mlb.map to it)
  <out>.raw      one line per sample: time tid cpu_ms_since_last_sample rip caller...   (hex addresses)
A thread that used no CPU since its previous sample was blocked; the report can be told to skip those with
--busy-only here, which leaves them out of <out> (they stay in .raw).
"""
import argparse
import collections
import ctypes as C
import time
from ctypes import wintypes as W

k32 = C.WinDLL('kernel32', use_last_error=True)
dbg = C.WinDLL('dbghelp', use_last_error=True)
psapi = C.WinDLL('psapi', use_last_error=True)

DEPTH = 64


class THREADENTRY32(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ThreadID', W.DWORD), ('th32OwnerProcessID', W.DWORD),
                ('tpBasePri', W.LONG), ('tpDeltaPri', W.LONG), ('dwFlags', W.DWORD)]


class ADDRESS64(C.Structure):
    _fields_ = [('Offset', C.c_uint64), ('Segment', W.WORD), ('Mode', C.c_int)]


class STACKFRAME64(C.Structure):
    _fields_ = [('AddrPC', ADDRESS64), ('AddrReturn', ADDRESS64), ('AddrFrame', ADDRESS64), ('AddrStack', ADDRESS64),
                ('AddrBStore', ADDRESS64), ('FuncTableEntry', C.c_void_p), ('Params', C.c_uint64 * 4), ('Far', W.BOOL),
                ('Virtual', W.BOOL), ('Reserved', C.c_uint64 * 3), ('KdHelp', C.c_uint64 * 32)]


class MODULEINFO(C.Structure):
    _fields_ = [('base', C.c_void_p), ('size', W.DWORD), ('entry', C.c_void_p)]


def sig(fn, res, *args):
    fn.restype, fn.argtypes = res, list(args)
    return fn


OpenProcess = sig(k32.OpenProcess, W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
OpenThread = sig(k32.OpenThread, W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
Snapshot = sig(k32.CreateToolhelp32Snapshot, W.HANDLE, W.DWORD, W.DWORD)
Thread32First = sig(k32.Thread32First, W.BOOL, W.HANDLE, C.POINTER(THREADENTRY32))
Thread32Next = sig(k32.Thread32Next, W.BOOL, W.HANDLE, C.POINTER(THREADENTRY32))
SuspendThread = sig(k32.SuspendThread, W.DWORD, W.HANDLE)
ResumeThread = sig(k32.ResumeThread, W.DWORD, W.HANDLE)
GetThreadContext = sig(k32.GetThreadContext, W.BOOL, W.HANDLE, C.c_void_p)
GetThreadTimes = sig(k32.GetThreadTimes, W.BOOL, W.HANDLE, *[C.POINTER(C.c_uint64)] * 4)
CloseHandle = sig(k32.CloseHandle, W.BOOL, W.HANDLE)
SymSetOptions = sig(dbg.SymSetOptions, W.DWORD, W.DWORD)
SymInitializeW = sig(dbg.SymInitializeW, W.BOOL, W.HANDLE, W.LPCWSTR, W.BOOL)
FuncTable = C.cast(dbg.SymFunctionTableAccess64, C.c_void_p)
ModBase = C.cast(dbg.SymGetModuleBase64, C.c_void_p)
StackWalk64 = sig(dbg.StackWalk64, W.BOOL, W.DWORD, W.HANDLE, W.HANDLE, C.POINTER(STACKFRAME64), C.c_void_p,
                  C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p)
EnumModules = sig(psapi.EnumProcessModules, W.BOOL, W.HANDLE, C.POINTER(C.c_void_p), W.DWORD, C.POINTER(W.DWORD))
ModuleInfo = sig(psapi.GetModuleInformation, W.BOOL, W.HANDLE, C.c_void_p, C.POINTER(MODULEINFO), W.DWORD)
ModuleName = sig(psapi.GetModuleBaseNameW, W.DWORD, W.HANDLE, C.c_void_p, W.LPWSTR, W.DWORD)


def thread_ids(pid):
    snap = Snapshot(4, 0)
    e = THREADENTRY32()
    e.dwSize = C.sizeof(e)
    out, ok = [], Thread32First(snap, C.byref(e))
    while ok:
        if e.th32OwnerProcessID == pid:
            out.append(e.th32ThreadID)
        ok = Thread32Next(snap, C.byref(e))
    CloseHandle(snap)
    return out


def cpu_ms(h):
    c, x, k, u = (C.c_uint64() for _ in range(4))
    GetThreadTimes(h, C.byref(c), C.byref(x), C.byref(k), C.byref(u))
    return (k.value + u.value) / 1e4


def modules(proc):
    arr = (C.c_void_p * 1024)()
    need = W.DWORD()
    EnumModules(proc, arr, C.sizeof(arr), C.byref(need))
    out = []
    for i in range(need.value // C.sizeof(C.c_void_p)):
        mi, name = MODULEINFO(), C.create_unicode_buffer(260)
        ModuleInfo(proc, arr[i], C.byref(mi), C.sizeof(mi))
        ModuleName(proc, arr[i], name, 260)
        out.append((mi.base, mi.size, name.value))
    return out


def walk(proc, h, ctxbuf):
    ctx = C.c_void_p((C.addressof(ctxbuf) + 15) & ~15)
    C.c_uint32.from_address(ctx.value + 0x30).value = 0x10000B   # CONTEXT_AMD64 control | integer | floating
    if not GetThreadContext(h, ctx):
        return []
    q = lambda off: C.c_uint64.from_address(ctx.value + off).value
    fr = STACKFRAME64()
    for a, off in ((fr.AddrPC, 0xF8), (fr.AddrStack, 0x98), (fr.AddrFrame, 0xA0)):
        a.Offset, a.Mode = q(off), 3
    chain = [q(0xF8)]
    for i in range(DEPTH):
        if not StackWalk64(0x8664, proc, h, C.byref(fr), ctx, None, FuncTable, ModBase, None) or not fr.AddrPC.Offset:
            break
        if i:
            chain.append(fr.AddrPC.Offset)
    return chain


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pid', type=int)
    ap.add_argument('out')
    ap.add_argument('--seconds', type=float, default=60)
    ap.add_argument('--period-ms', type=float, default=10)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--busy-only', action='store_true')
    a = ap.parse_args()

    proc = OpenProcess(0x0410, False, a.pid)   # query information | vm read
    if not proc:
        raise SystemExit(f'cannot open process {a.pid}: error {C.get_last_error()}')
    SymSetOptions(0x00000004)   # deferred loads
    if not SymInitializeW(proc, None, True):
        raise SystemExit(f'SymInitialize failed: {C.get_last_error()}')
    handles = {t: OpenThread(0x004A, False, t) for t in thread_ids(a.pid)}   # suspend | get context | query
    before = {t: cpu_ms(h) for t, h in handles.items()}
    time.sleep(1)
    hot = sorted(handles, key=lambda t: cpu_ms(handles[t]) - before[t], reverse=True)[:a.threads]
    mods = modules(proc)
    exe_base, exe_size = mods[0][0], mods[0][1]
    ctxbuf = C.create_string_buffer(1232 + 16)
    for t in hot:   # first walk of each loads unwind tables; not recorded
        if SuspendThread(handles[t]) != 0xFFFFFFFF:
            walk(proc, handles[t], ctxbuf)
            ResumeThread(handles[t])

    rips, stacks = collections.Counter(), collections.Counter()
    per = collections.Counter()
    per_exe = collections.Counter()
    last = {t: cpu_ms(handles[t]) for t in hot}
    total = 0
    t_end = time.time() + a.seconds
    with open(a.out + '.raw', 'w') as raw:
        while time.time() < t_end:
            tick = time.time()
            for t in hot:
                h = handles[t]
                if SuspendThread(h) == 0xFFFFFFFF:
                    continue
                try:
                    chain = walk(proc, h, ctxbuf)
                finally:
                    ResumeThread(h)
                if not chain:
                    continue
                now_cpu = cpu_ms(h)
                used, last[t] = now_cpu - last[t], now_cpu
                raw.write(f'{tick:.3f} {t} {used:.1f} ' + ' '.join(f'{x:x}' for x in chain) + '\n')
                if a.busy_only and used <= 0:
                    continue
                total += 1
                per[t] += 1
                per_exe[t] += exe_base <= chain[0] < exe_base + exe_size
                rips[chain[0]] += 1
                stacks[tuple(chain)] += 1
            time.sleep(max(0, a.period_ms / 1000 - (time.time() - tick)))

    with open(a.out, 'w') as f:
        f.write(f'totk-prof 1\nbase {exe_base:x}\nperiod_us {int(a.period_ms * 1000)}\nsamples {total}\ndropped 0\n')
        for t in hot:
            f.write(f'thread {t} {per[t]} {per_exe[t]}\n')
        for base, size, name in mods:
            f.write(f'module {base:x} {size:x} {name}\n')
        for r, n in rips.most_common():
            f.write(f'rip {r:x} {n}\n')
        for s, n in stacks.most_common():
            f.write(f'stack {n} ' + ' '.join(f'{x:x}' for x in s) + '\n')
    print(f'{total} samples of {len(hot)} threads {hot} -> {a.out}')


if __name__ == '__main__':
    main()
