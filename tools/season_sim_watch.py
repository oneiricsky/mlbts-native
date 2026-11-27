"""Time the Season/Franchise calendar simulation in a running game (Windows, 1.0.20), reading its memory only.

usage: python -I tools/season_sim_watch.py <pid> [--seconds 30] [--wait 600]

Start it with the game on the Season home or Schedule screen, then sim a few weeks. It finds the calendar-sim
object, polls its game index (+0x398) and game count (+0x3c5), and prints the time per game, the time per day and
the extra time at every third game, which is where the game draws a frame (f_700075d8d0 sims up to three games per
call). Guest addresses are host addresses, so no hook or restart is needed.
"""
import argparse
import ctypes as C
import statistics as st
import struct
import time
from ctypes import wintypes as W

CALLBACK_SLOT = 0x7002288CC8   # the pointer the constructor (f_700075a960) stores at object+0x400
OBJ_CALLBACK, OBJ_INDEX, OBJ_STATE, OBJ_COUNT, OBJ_SIZE = 0x400, 0x398, 0x3B8, 0x3C5, 0x420


class MBI(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p), ('AllocationProtect', W.DWORD),
                ('PartitionId', W.WORD), ('RegionSize', C.c_size_t), ('State', W.DWORD), ('Protect', W.DWORD),
                ('Type', W.DWORD)]


k32 = C.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = W.HANDLE
k32.VirtualQueryEx.restype = C.c_size_t
k32.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MBI), C.c_size_t]
k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]


def read(h, addr, n):
    buf = C.create_string_buffer(n)
    got = C.c_size_t()
    k32.ReadProcessMemory(h, addr, buf, n, C.byref(got))
    return buf.raw[:got.value]


def find_objects(h):
    needle = read(h, CALLBACK_SLOT, 8)
    if len(needle) != 8:
        raise SystemExit('cannot read the game: wrong process, or not game version 1.0.20')
    addr, m, found = 0x10000, MBI(), set()
    while addr < 0x7000000000 and k32.VirtualQueryEx(h, addr, C.byref(m), C.sizeof(m)):
        base, size = m.BaseAddress or 0, m.RegionSize
        if m.State == 0x1000 and m.Protect & 0x04 and not m.Protect & 0x101:
            for off in range(0, size, 1 << 24):
                data = read(h, base + off, min((1 << 24) + 8, size - off))
                i = data.find(needle)
                while i >= 0:
                    if (base + off + i) % 8 == 0:
                        found.add(base + off + i - OBJ_CALLBACK)
                    i = data.find(needle, i + 1)
        addr = base + size
    out = []
    for o in sorted(found):
        d = read(h, o, OBJ_SIZE)
        if (len(d) == OBJ_SIZE and d[OBJ_COUNT] <= 46 and -1 <= struct.unpack_from('<i', d, OBJ_INDEX)[0] <= 46
                and 0 <= struct.unpack_from('<i', d, OBJ_STATE)[0] <= 8):
            out.append(o)
    return out


def state(h, obj):
    d = read(h, obj + OBJ_INDEX, OBJ_COUNT - OBJ_INDEX + 1)
    if len(d) != OBJ_COUNT - OBJ_INDEX + 1:
        return None
    return struct.unpack_from('<i', d, 0)[0], d[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pid', type=int)
    ap.add_argument('--seconds', type=float, default=30, help='how long to measure once the sim moves')
    ap.add_argument('--wait', type=float, default=600, help='how long to wait for a sim to start')
    a = ap.parse_args()
    h = k32.OpenProcess(0x0410, False, a.pid)
    if not h:
        raise SystemExit(f'cannot open process {a.pid}')
    deadline, obj = time.time() + a.wait, None
    while obj is None:
        objs = find_objects(h)
        first = {o: state(h, o) for o in objs}
        until = time.time() + 15
        while obj is None and time.time() < until:
            obj = next((o for o in objs if state(h, o) not in (None, first[o])), None)
            time.sleep(0.02)
        if obj is None and time.time() > deadline:
            raise SystemExit(f'no simulation seen in {a.wait:.0f} s')
    changes, last, end = [], None, time.perf_counter() + a.seconds
    while time.perf_counter() < end:
        s = state(h, obj)
        if s and s != last:
            changes.append((time.perf_counter(), *s))
            last = s
    games = {0: [], 1: [], 2: []}
    starts = []
    for (t0, i0, n0), (t1, i1, n1) in zip(changes, changes[1:]):
        if i1 == 0 and i0 != 0:
            starts.append((t1, n1))
        if i1 == i0 + 1 and i0 >= 0 and n1 == n0 and t1 - t0 < 0.1:
            games[i1 % 3].append((t1 - t0) * 1000)
    every = [x for v in games.values() for x in v]
    if not every:
        raise SystemExit('the object moved but no consecutive games were seen')
    print(f'object {obj:#x}, {len(starts)} game lists started, sizes {sorted({n for _, n in starts})}')
    print(f'time per game: {len(every)} games, median {st.median(every):.1f} ms')
    for k, v in games.items():
        if v:
            print(f'  index%3 == {k}: median {st.median(v):.2f} ms ({len(v)})')
    days = [b[0] - a_[0] for a_, b in zip(starts, starts[1:]) if a_[1] >= 30 and b[0] - a_[0] < 3]
    if days:
        print(f'time per day (lists of 30+ games): median {st.median(days) * 1000:.0f} ms over {len(days)} days')


if __name__ == '__main__':
    main()
