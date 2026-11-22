"""Merge the counts of an instrumented runtime into tools/data/runtime.profdata, the profile tools/build.py builds the
runtime with (profile-guided optimisation; the game's code is never instrumented or optimised with a profile).

    python -I tools/build.py --pgo gen                      # a work/build/mlb.exe whose runtime counts
    work/build/mlb.exe                                      # the attract match, a few minutes; close the window
    python -I tools/build.py --toolchain <llvm-mingw> --out work/build-mingw --pgo gen    # the same, release toolchain
    work/build-mingw/mlb.exe
    python -I tools/pgo.py merge                            # both builds' pgo/*.profraw -> tools/data/runtime.profdata
    python -I tools/build.py                                # the normal build, now with the profile

The instrumented mlb.exe adds its counts to work/build/pgo/mlb_<id>.profraw every minute and at exit; several runs add
up. The release's toolchain compiles some functions differently from the dev build's (other inlined helpers, so another
control flow), so both train and the profile holds each one's records. llvm-profdata comes from the compiler that built
each (the raw format is tied to its version). Beside the profile goes runtime.profdata.json, the training record: the
commit of runtime/ the counts were taken from and the compilers.

The profile matches functions by name and by a hash of their control flow: a function changed since the training
compiles as without a profile, and the rest keep theirs. Train again after large changes to the replay
(runtime/gfx/vk_exec*.c, vk_texture.c, vk_memory.c, vk_usnap.c, vk_rec.c). After TotK Recomp tools/pgo.py @ ae30a61.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLANG = r'C:\Program Files\LLVM\bin\clang.exe'
OUT = ROOT / 'tools' / 'data' / 'runtime.profdata'


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def profdata_tool(build, clang):
    """llvm-profdata of the compiler that built <build> (its build.ninja's cc line), else of --clang."""
    nf = build / 'build.ninja'
    lines = nf.read_text().splitlines() if nf.is_file() else []
    cc = next((ln[5:].strip().strip('"') for ln in lines if ln.startswith('cc = ')), None)
    tool = Path(cc or clang).parent / 'llvm-profdata.exe'
    if not tool.is_file():
        sys.exit(f'{tool} not found: pass --clang (the compiler of the instrumented build)')
    return tool


def run(cmd):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f'llvm-profdata failed: {(p.stdout + p.stderr).strip()[-2000:]}')


def merge(builds, clang, out, note):
    # One build per toolchain: the dev build (MSVC target) and the release's (llvm-mingw) compile some functions with
    # other inlined helpers, so their control flow differs; the profile holds a record of each, and either compiler
    # finds its own. Each build's raw files are merged by its own llvm-profdata (the raw format is the compiler's).
    parts, nraw, size, compilers = [], 0, 0, []
    for i, build in enumerate(builds):
        raw = sorted((build / 'pgo').glob('*.profraw'))
        if not raw:
            sys.exit(f'no .profraw in {build / "pgo"}: build with tools/build.py --pgo gen and run that mlb.exe first')
        tool = profdata_tool(build, clang)
        part = out.with_suffix(f'.part{i}.tmp')
        run([tool, 'merge', '--failure-mode=all', '-o', part, *raw])
        parts.append((tool, part))
        nraw += len(raw)
        size += sum(f.stat().st_size for f in raw)
        cc = tool.parent / 'clang.exe'
        version = subprocess.run([str(cc), '--version'], capture_output=True, text=True).stdout.splitlines()
        compilers.append(version[0] if version else str(cc))
    tmp = out.with_suffix('.profdata.tmp')
    run([parts[-1][0], 'merge', '-o', tmp, *(p for _, p in parts)])
    for _, part in parts:
        part.unlink()
    tmp.replace(out)
    record = {'merged': datetime.date.today().isoformat(), 'commit': git('rev-parse', 'HEAD'),
              'runtime_changed_since_commit': bool(git('status', '--porcelain', '--', 'runtime')),
              'compilers': compilers, 'raw_files': nraw, 'training': note}
    out.with_suffix('.profdata.json').write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')
    print(f'{os.path.relpath(out, ROOT)}: {nraw} raw files ({size / 2**20:.1f} MiB) -> '
          f'{out.stat().st_size / 2**20:.2f} MiB')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('merge', help='merge <build>/pgo/*.profraw into tools/data/runtime.profdata and its record')
    m.add_argument('builds', type=Path, nargs='*', help='the instrumented build folders (default: work/build and, '
                   'when it has counts, work/build-mingw)')
    m.add_argument('--clang', default=os.environ.get('CLANG', DEFAULT_CLANG),
                   help='the compiler of a build without build.ninja')
    m.add_argument('--out', type=Path, default=OUT)
    m.add_argument('--note', default='attract match', help='what was played, for the record')
    a = ap.parse_args()
    mingw = ROOT / 'work' / 'build-mingw'
    builds = a.builds or [ROOT / 'work' / 'build'] + ([mingw] if any(mingw.glob('pgo/*.profraw')) else [])
    merge([b.resolve() for b in builds], a.clang, a.out.resolve(), a.note)


if __name__ == '__main__':
    main()
