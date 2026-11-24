"""Ordered string references inside one game function, by disassembling the original ARM64.

    python -I tools/fnxref.py 0x70003dde10 [0xADDR ...]

`tools/map_find.py str` attributes a string to every function whose generated C mentions the address; when a
large string blob is shared, that over-attributes (a string used by three functions looks used by thirty).
Disassembling instead resolves `adrp`/`add` and `adrp`/`ldr` in code order, so a log line can be tied to the
store that follows it. The function's end is the next entry in work/map/index/generated_functions.jsonl.

Read-only. Needs capstone (`python -I -m pip install capstone --target work/pylib`, already used by tools/disasm.py).
"""
import bisect, json, os, sys

import capstone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from nsoinfo import Nso  # noqa: E402

BASE = 0x7000000000
IDX = ROOT + "/work/map/index/generated_functions.jsonl"
EXEFS = ROOT + "/work/build/game/exefs/main"


def load_addrs():
    addrs = []
    for line in open(IDX, encoding="utf-8"):
        line = line.strip()
        if line:
            addrs.append(int(json.loads(line)["addr"], 16))
    addrs.sort()
    return addrs


def cstr(img, off, limit=300):
    if off < 0 or off >= len(img):
        return None
    end = img.find(b"\0", off, off + limit)
    if end < 0:
        return None
    raw = img[off:end]
    if len(raw) < 3:
        return None
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not all(31 < ord(ch) < 127 or ch in "\r\n\t" for ch in txt):
        return None
    return txt


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    nso = Nso(EXEFS)
    img = bytes(nso.image)
    addrs = load_addrs()
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    md.detail = True
    for arg in sys.argv[1:]:
        a = int(arg, 16)
        j = bisect.bisect_right(addrs, a)
        nxt = addrs[j] if j < len(addrs) else a + 0x800
        size = nxt - a
        code = img[a - BASE:a - BASE + size]
        print(f"=== {a:#x} .. {a + size:#x} ({size} bytes)")
        page = {}
        for ins in md.disasm(code, a):
            m = ins.mnemonic
            ops = ins.operands
            if m == "adrp":
                page[ins.reg_name(ops[0].reg)] = ops[1].imm
                continue
            if m not in ("add", "ldr") or len(ops) < 2 or ops[1].type != capstone.arm64.ARM64_OP_REG:
                continue
            dst = ins.reg_name(ops[0].reg)
            src = ins.reg_name(ops[1].reg)
            if src not in page:
                page.pop(dst, None)
                continue
            op = ops[2] if len(ops) > 2 else None
            if op is not None and op.type == capstone.arm64.ARM64_OP_IMM:
                tgt = page[src] + op.imm
            elif op is not None and op.type == capstone.arm64.ARM64_OP_MEM:
                tgt = page[src] + op.mem.disp
            else:
                continue
            page[dst] = tgt
            s = cstr(img, tgt - BASE)
            if s:
                print(f"  +{ins.address - a:#07x} {ins.address:#x} {dst} {tgt:#x}  {s!r}")


if __name__ == "__main__":
    main()
