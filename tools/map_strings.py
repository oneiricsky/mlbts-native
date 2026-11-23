"""Tie game functions to the text they use, and find vtables, from the original machine code.

    python -I tools/map_strings.py [--exefs work/build/game/exefs] [--gen work/gen] [--out work/map/index]

The game was built without RTTI, so classes have no names in the binary. What it does have is text: log and assert
messages, asset names, UI screen names. This tool walks each function's original ARM64 words, follows every
`adrp` + `add`/`ldr` pair to its target, and keeps targets that are C strings in .rodata or .data. Writes:
  function_strings.jsonl  per function: module, addr, strings it references (printable C strings, up to 12)
  vtables.jsonl           runs of 3+ relocated function pointers in .rodata/.data (virtual-method tables), with the
                          vtable address, the function addresses, and the strings the first function references
  strings_summary.json    counts
Needs generated_functions.jsonl (tools/map_generated.py). Derived from game code: stays under work/.
"""
import argparse, json, os, re, struct, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from nsoinfo import Nso  # noqa: E402

PRINT = re.compile(rb"^[\x20-\x7e\t]{4,200}$")


def reloc_slots(nso):
    img, tags, slots = nso.image, nso.dyn, {}
    if 7 in tags:
        for i in range(tags.get(8, 0) // 24):
            off, info, add = struct.unpack_from("<QQq", img, tags[7] + i * 24)
            if (info & 0xFFFFFFFF) == 1027:
                slots[off] = add
    if 0x24 in tags:
        a = 0
        for i in range(tags.get(0x23, 0) // 8):
            e = struct.unpack_from("<Q", img, tags[0x24] + i * 8)[0]
            if e & 1 == 0:
                slots[e] = struct.unpack_from("<Q", img, e)[0]
                a = e + 8
            else:
                bits, k = e >> 1, 0
                while bits:
                    if bits & 1:
                        s = a + k * 8
                        slots[s] = struct.unpack_from("<Q", img, s)[0]
                    bits >>= 1
                    k += 1
                a += 63 * 8
    return slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exefs", default=ROOT + "/work/build/game/exefs")
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    ap.add_argument("--out", default=ROOT + "/work/map/index")
    a = ap.parse_args()
    funcs = {}
    for ln in open(a.out + "/generated_functions.jsonl"):
        f = json.loads(ln)
        funcs.setdefault(f["module"], []).append(int(f["addr"], 16))
    rows_f, rows_v, summ = [], [], {}
    for mod in ("main", "sdk"):
        base = int(json.load(open(f"{a.gen}/{mod}/manifest.json"))["base"], 16)
        nso = Nso(f"{a.exefs}/{mod}")
        nso.parse_dynamic()
        img = bytes(nso.image)
        t_off, t_size, _ = nso.segments["text"]
        r_off, r_size, _ = nso.segments["rodata"]
        d_off, d_size, _ = nso.segments["data"]
        end_img = len(img)
        cache = {}

        def cstr(v):
            if v in cache:
                return cache[v]
            r = None
            if r_off <= v < r_off + r_size or d_off <= v < d_off + d_size:
                e = img.find(b"\0", v, v + 201)
                if e > v and PRINT.match(img[v:e]):
                    r = img[v:e].decode("ascii")
            cache[v] = r
            return r

        addrs = sorted(funcs[mod])
        nstr_fn = 0
        for i, ad in enumerate(addrs):
            lo = ad - base
            hi = (addrs[i + 1] - base) if i + 1 < len(addrs) else t_off + t_size
            if hi - lo > 0x40000:
                hi = lo + 0x40000
            n = (hi - lo) // 4
            words = struct.unpack_from(f"<{n}I", img, lo)
            adrp, found = {}, []
            for k, w in enumerate(words):
                if (w & 0x9F000000) == 0x90000000:
                    rd = w & 31
                    immlo, immhi = (w >> 29) & 3, (w >> 5) & 0x7FFFF
                    imm = (immhi << 2) | immlo
                    if imm & 0x100000:
                        imm -= 0x200000
                    adrp[rd] = (((lo + k * 4) & ~0xFFF) + (imm << 12))
                elif (w & 0xFF800000) == 0x91000000:
                    rn = (w >> 5) & 31
                    if rn in adrp:
                        imm = (w >> 10) & 0xFFF
                        if (w >> 22) & 1:
                            imm <<= 12
                        s = cstr(adrp[rn] + imm)
                        if s and s not in found:
                            found.append(s)
            if found:
                nstr_fn += 1
                rows_f.append(dict(module=mod, addr=hex(ad), strings=found[:12], nstrings=len(found)))
        fn_set = set(a_ - base for a_ in addrs)
        slots = reloc_slots(nso)
        keys = sorted(slots)
        nvt, j = 0, 0
        while j < len(keys):
            s = keys[j]
            run = [s]
            while j + 1 < len(keys) and keys[j + 1] == run[-1] + 8:
                j += 1
                run.append(keys[j])
            j += 1
            fl = []
            for q in run:
                if slots[q] in fn_set:
                    fl.append(slots[q])
                elif fl:
                    break
            if len(fl) >= 3 and slots[run[0]] in fn_set:
                nvt += 1
                rows_v.append(dict(module=mod, vtable=hex(base + run[0]), size=len(fl),
                                   functions=[hex(base + x) for x in fl]))
        summ[mod] = dict(functions=len(addrs), functions_with_strings=nstr_fn, vtable_like_runs=nvt)
    with open(a.out + "/function_strings.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in rows_f:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    with open(a.out + "/vtables.jsonl", "w", newline="\n") as fh:
        for r in rows_v:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    json.dump(summ, open(a.out + "/strings_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
