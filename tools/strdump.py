"""Print the C string at a guest address in a game module (default `main`, base 0x7000000000).

    python -I tools/strdump.py 0x7001c7d37f [0xADDR ...]
    python -I tools/strdump.py --module sdk 0x7004c1234

Reads the module image through tools/nsoinfo.py, because a guest address is not a file offset: the segments
have their own memory offsets. Useful when a disassembly or a log line names a string address.
"""
import argparse, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from nsoinfo import Nso  # noqa: E402

BASE = {"main": 0x7000000000, "sdk": 0x7004c00000}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addrs", nargs="+")
    ap.add_argument("--module", default="main", choices=sorted(BASE))
    ap.add_argument("--exefs", default=ROOT + "/work/build/game/exefs")
    a = ap.parse_args()
    img = bytes(Nso(f"{a.exefs}/{a.module}").image)
    base = BASE[a.module]
    for arg in a.addrs:
        addr = int(arg, 16)
        off = addr - base
        if off < 0 or off >= len(img):
            print(f"{addr:#x}: outside the {a.module} image (0x{len(img):x} bytes)")
            continue
        end = img.find(b"\0", off, off + 400)
        if end < 0:
            end = off + 400
        raw = img[off:end]
        txt = raw.decode("utf-8", "replace")
        if not txt or not all(31 < ord(ch) < 127 or ch in "\r\n\t" for ch in txt):
            print(f"{addr:#x}: not text: {raw[:48]!r}")
            continue
        print(f"{addr:#x}: {txt!r}")


if __name__ == "__main__":
    main()
