"""Where the setup finds what it runs: the one place that maps the release folder and a repository checkout.

Release (docs/release.md, "Release layout"), root = the unpacked folder:

    python/python.exe     runs every tool (numpy, lz4, tkinter); its ._pth puts .., ../tools and ../recomp on sys.path
    llvm/                 llvm-mingw: clang, lld, llvm-ar, llvm-windres and the mingw-w64 headers and libraries
    runtime/              libmlbrt.a (the runtime, no game code), the headers the game code and modules.c include,
                          runtime/deps (Vulkan, VMA and SDL3 headers, lib/vulkan-1.lib, bin/SDL3.dll)
    bin/                  ninja.exe, totk_xlate.exe and totk_xlate.id (the shader translator)
    recomp/, tools/       the lifter and the extraction and build scripts; tools/equipment (optional setup step)
    VERSION               the release version, one line
    temp/                 the default temp folder (created)

Dev mode, root = a repository checkout (no python/python.exe): the venv's Python, work/toolchain/llvm-mingw-*,
work/rtlib/libmlbrt.a (tools/build.py --toolchain ... --make-runtime-lib --out work/rtlib), work/deps, the venv's ninja,
work/xlate and work/install-temp. Its version is VERSION plus -dev.
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# The game versions the port builds, newest first: each has tools/data/expected-<version>.json (ExeFS hashes, RomFS
# size). A setup builds the version of the update NSP it is given (steps.Context.pick_version).
GAME_VERSIONS = ('1.0.20', '1.0.15')


@dataclass(frozen=True)
class Layout:
    root: Path
    dev: bool
    release: str
    python: Path
    tools: Path
    recomp: Path
    llvm: Path
    deps: Path
    runtime_lib: Path
    ninja: Path
    xlate: Path          # totk_xlate.exe; the totk_xlate.id beside it is copied too
    temp: Path

    def expected(self, version):
        return self.tools / 'data' / f'expected-{version}.json'

    def missing(self):
        """Paths the steps need that do not exist."""
        need = [self.python, self.tools / 'build.py', self.tools / 'romfs_dump.py', self.tools / 'nxextract.py',
                self.tools / 'equipment' / 'equipment.py',
                self.recomp / 'gen.py', self.llvm / 'bin' / 'clang.exe', self.deps / 'lib' / 'vulkan-1.lib',
                self.deps / 'bin' / 'SDL3.dll', self.runtime_lib, self.ninja, self.xlate]
        need += [self.expected(v) for v in GAME_VERSIONS]
        return [str(p) for p in need if not p.exists()]


def release_layout(root):
    version = root / 'VERSION'
    return Layout(root=root, dev=False,
                  release=version.read_text(encoding='utf-8').strip() if version.is_file() else 'unknown',
                  python=root / 'python' / 'python.exe', tools=root / 'tools', recomp=root / 'recomp',
                  llvm=root / 'llvm', deps=root / 'runtime' / 'deps', runtime_lib=root / 'runtime' / 'libmlbrt.a',
                  ninja=root / 'bin' / 'ninja.exe', xlate=root / 'bin' / 'totk_xlate.exe', temp=root / 'temp')


def dev_layout(root):
    venv = root / '.venv' / 'Scripts'
    trees = sorted((root / 'work' / 'toolchain').glob('llvm-mingw-*-ucrt-x86_64'))
    return Layout(root=root, dev=True, release=(root / 'VERSION').read_text(encoding='utf-8').strip() + '-dev',
                  python=venv / 'python.exe' if (venv / 'python.exe').is_file() else Path(sys.executable),
                  tools=root / 'tools', recomp=root / 'recomp',
                  llvm=trees[-1] if trees else root / 'work' / 'toolchain' / 'llvm-mingw-missing',
                  deps=root / 'work' / 'deps', runtime_lib=root / 'work' / 'rtlib' / 'libmlbrt.a',
                  ninja=venv / 'ninja.exe', xlate=root / 'work' / 'xlate' / 'totk_xlate.exe',
                  temp=root / 'work' / 'install-temp')


def find(root=None):
    """The layout of root (default: the folder above this package)."""
    root = Path(root or Path(__file__).resolve().parent.parent).resolve()
    return release_layout(root) if (root / 'python' / 'python.exe').is_file() else dev_layout(root)


def settings_dir():
    """%LOCALAPPDATA%\\MLBTS-Native: the setup's memory of the last install (paths only, never key contents)."""
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    return Path(base) / 'MLBTS-Native'
