#!/usr/bin/env python3
"""Run one recompiled game function in a small test program, without the game.

    python -I tools/guestfn_test.py                 # extract, compile, run tools/guestfn_errorjudge.c
    python -I tools/guestfn_test.py --gen work/gen  # take the generated C from another folder
    python -I tools/guestfn_test.py --replay FILE   # compare with calls recorded live (tools/guestfn_capture.py)

Starting at ENTRY, the script follows every direct call through the generated C (work/gen*/{main,sdk}/*.c), copies
those functions into work/scratch/guestfn/extract.c, compiles that with the harness and runs it. It stops if the
closure needs anything the harness does not stand in for: an indirect call, a patch switch, a system call. The
extract and the program are made from game code: they stay under work/ and are never committed.

The exit code is the harness's (number of failed checks, capped at 125), or 2 if the program could not be built.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = 'f_7000d42f20'
HARNESS = ROOT / 'tools' / 'guestfn_errorjudge.c'
OUT = ROOT / 'work' / 'scratch' / 'guestfn'
CLANG = r'C:/Program Files/LLVM/bin/clang.exe'
# as tools/build.py compiles generated code (GEN_FLAGS)
CFLAGS = ['-O2', '-fno-strict-aliasing', '-Wno-return-type', '-Wno-unused-label', '-march=x86-64-v3', '-std=gnu11',
          '-D_CRT_SECURE_NO_WARNINGS']
# what the harness defines; any other rt_ / g_ name in the extract is a missing stand-in
PROVIDED = {'rt_udf', 'fnprof_hit', 'g_fnprof'}

DEF = re.compile(r'^void (f_[0-9a-f]{10})\(Cpu \*c\) \{\r?$', re.M)
CALL = re.compile(r'\b(f_[0-9a-f]{10})\b')
RUNTIME = re.compile(r'\b(rt_[a-z]\w*|g_[a-z]\w*)\b')


def index(gen):
    """name -> (file text, start offset) for every generated function."""
    files = sorted(gen.glob('main/*.c')) + sorted(gen.glob('sdk/*.c'))
    if not files:
        sys.exit(f'no generated C under {gen}')
    found = {}
    for path in files:
        text = path.read_text(encoding='utf-8', errors='replace')
        for m in DEF.finditer(text):
            found[m.group(1)] = (text, m.start(), path.name)
    return found


def closure(found, entry):
    bodies, todo = {}, [entry]
    while todo:
        name = todo.pop()
        if name in bodies:
            continue
        if name not in found:
            sys.exit(f'{name} is called but not defined in the generated C')
        text, start, _ = found[name]
        end = re.compile(r'^\}\r?$', re.M).search(text, start).end()
        bodies[name] = text[start:end]
        todo += [c for c in CALL.findall(bodies[name]) if c != name]
    return bodies


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gen', default='work/gen_cheats', help='folder of generated C (default: %(default)s)')
    ap.add_argument('--clang', default=CLANG)
    ap.add_argument('--replay', help='a file of recorded calls to run instead of the made-up plays')
    ap.add_argument('--broken', action='store_true', help='with --replay: feed wrong runner states (a control)')
    args = ap.parse_args()

    t0 = time.perf_counter()
    found = index(ROOT / args.gen)
    bodies = closure(found, ENTRY)
    joined = '\n'.join(bodies.values())
    missing = sorted(set(RUNTIME.findall(joined)) - PROVIDED)
    if missing:
        sys.exit(f'the closure of {ENTRY} needs runtime names the harness does not provide: {missing}')

    OUT.mkdir(parents=True, exist_ok=True)
    extract = OUT / 'extract.c'
    parts = ['// Extracted from generated game code by tools/guestfn_test.py. Do not commit.',
             '#include "cpu.h"', '#include "simd.h"', '']
    parts += [f'void {n}(Cpu *c);' for n in sorted(bodies)]
    parts += ['', *(bodies[n] + '\n' for n in sorted(bodies))]
    extract.write_text('\n'.join(parts), encoding='utf-8')
    t1 = time.perf_counter()

    lines = sum(b.count('\n') + 1 for b in bodies.values())
    print(f'closure of {ENTRY}: {len(bodies)} functions, {lines} generated lines')
    for name in sorted(bodies):
        print(f'  {name}  {bodies[name].count(chr(10)) + 1:4d} lines  {found[name][2]}')

    exe = OUT / 'guestfn_errorjudge.exe'
    exe.unlink(missing_ok=True)
    cmd = [args.clang, *CFLAGS, '-I', str(ROOT / 'runtime' / 'core'), '-o', str(exe), str(extract), str(HARNESS)]
    if subprocess.run(cmd).returncode:
        return 2
    t2 = time.perf_counter()

    sys.stdout.flush()
    if args.replay:
        extra = ['--broken'] if args.broken else []
        code = subprocess.run([str(exe), '--replay', args.replay, *extra], timeout=600).returncode
        return 2 if code < 0 or code >= 125 else code
    code = subprocess.run([str(exe)], timeout=60).returncode
    # the control for the memory setup: without the one mapped global, the call must fault, not answer
    fault = subprocess.run([str(exe), '--no-global'], timeout=60, capture_output=True, text=True)
    t3 = time.perf_counter()
    print(fault.stdout.strip())
    fault_ok = fault.returncode == 77
    print(f'control, global page not mapped: {"faulted as it must" if fault_ok else "DID NOT FAULT"} '
          f'(exit {fault.returncode})')
    print(f'time: extract {t1 - t0:.1f} s, compile {t2 - t1:.1f} s, run {t3 - t2:.1f} s, total {t3 - t0:.1f} s')
    if code < 0 or code > 125:
        print(f'the harness crashed (exit {code})')
        return 2
    return code if code else (0 if fault_ok else 1)


if __name__ == '__main__':
    sys.exit(main())
