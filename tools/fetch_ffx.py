"""Put AMD's FSR 3.1 / 4 Vulkan runtime next to the dev tree's mlb.exe (runtime/gfx/vk_ffx.c).

    .venv/Scripts/python -I tools/fetch_ffx.py [--out work/build]

The two signed DLLs of AMD's FSR SDK 2.4.0 (amd_fidelityfx_loader_vk.dll, amd_fidelityfx_upscaler_vk.dll), from the
pinned revision and checked by size and SHA-256: the same files the setup downloads for players (installer/steps.py
FFX_DLLS). They are AMD's, never committed; work/ is ignored.
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from installer.steps import FFX_DLLS, FFX_URL  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=Path, default=ROOT / 'work' / 'build', help='the folder of mlb.exe')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for name, size, sha in FFX_DLLS:
        target = a.out / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
            print(f'{name}: already there')
            continue
        with urllib.request.urlopen(FFX_URL + name, timeout=60) as r:
            data = r.read()
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
            sys.exit(f'{name}: {len(data)} bytes, not the expected file')
        part = target.with_suffix('.part')
        part.write_bytes(data)
        part.replace(target)
        print(f'{name}: {len(data)} bytes into {a.out}')


if __name__ == '__main__':
    main()
