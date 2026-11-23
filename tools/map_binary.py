"""Name the game binary's functions and check the generated-code index against the original machine code.

    python -I tools/map_binary.py [--exefs work/build/game/exefs] [--gen work/gen] [--out work/map/index]

Needs tools/map_generated.py to have run first (generated_functions.jsonl). Two jobs:
 1. names: every dynamic-symbol function (exports of main/sdk) is matched to its generated function and demangled
    with llvm-cxxfilt, written to binary_names.jsonl (module, addr, size, mangled, demangled, in_index).
 2. check: independent of the recompiler, scan the original .text for every direct `bl` (call). Each target must be
    an indexed function entry, and so must each named function symbol. Words inside the generated "folded" ranges
    (jump-table data in .text) are skipped. Results go to binary_check.json.
Output is derived from game code: it stays under work/ and is never committed.
"""
import argparse, json, os, struct, subprocess, sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from nsoinfo import Nso  # noqa: E402

CXXFILT = "C:/Program Files/LLVM/bin/llvm-cxxfilt.exe"


def demangle(names):
    if not names or not os.path.exists(CXXFILT):
        return {n: n for n in names}
    out = subprocess.run([CXXFILT], input="\n".join(names) + "\n", capture_output=True, text=True).stdout.split("\n")
    return dict(zip(names, out))


def folded_ranges(gen, mod):
    r = []
    for ln in open(f"{gen}/{mod}/folded.txt"):
        if ln.startswith("#") or not ln.strip():
            continue
        a, b = ln.split()
        r.append((int(a, 16), int(b, 16)))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exefs", default=ROOT + "/work/build/game/exefs")
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    ap.add_argument("--out", default=ROOT + "/work/map/index")
    a = ap.parse_args()
    funcs = {}
    for ln in open(a.out + "/generated_functions.jsonl"):
        f = json.loads(ln)
        funcs[int(f["addr"], 16)] = f
    result, names_out = {}, []
    for mod in ("main", "sdk"):
        man = json.load(open(f"{a.gen}/{mod}/manifest.json"))
        base = int(man["base"], 16)
        t0, t1 = (int(x, 16) for x in man["text"])
        nso = Nso(f"{a.exefs}/{mod}")
        nso.parse_dynamic()
        img = bytes(nso.image)
        skip = folded_ranges(a.gen, mod)
        text_off, text_size, _ = nso.segments["text"]
        assert base + text_off == t0, (mod, hex(base + text_off), hex(t0))
        bl_targets, scanned, skipped = set(), 0, 0
        lo, hi = text_off, min(t1 - base, text_off + text_size)
        words = struct.unpack_from(f"<{(hi - lo) // 4}I", img, lo)
        sk = sorted(skip)
        si = 0
        for i, w in enumerate(words):
            off = lo + i * 4
            if (w & 0xFC000000) != 0x94000000:
                continue
            while si < len(sk) and sk[si][1] <= off:
                si += 1
            if si < len(sk) and sk[si][0] <= off < sk[si][1]:
                skipped += 1
                continue
            imm = w & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            tgt = base + off + imm * 4
            scanned += 1
            if t0 <= tgt < t1:
                bl_targets.add(tgt)
        missing = sorted(t for t in bl_targets if t not in funcs)
        syms = [s for s in nso.syms if s["shndx"] and s["name"] and s["value"] and s.get("type", 2) == 2 and
                text_off <= s["value"] < text_off + text_size]
        sym_missing = [s["name"] for s in syms if base + s["value"] not in funcs]
        dm = demangle([s["name"] for s in syms])
        for s in syms:
            ad = base + s["value"]
            names_out.append(dict(module=mod, addr=hex(ad), size=s["size"], mangled=s["name"],
                                  demangled=dm.get(s["name"], s["name"]), in_index=ad in funcs))
        result[mod] = dict(bl_instructions_scanned=scanned, bl_in_folded_data_skipped=skipped,
                           distinct_bl_targets_in_text=len(bl_targets), bl_targets_not_indexed=len(missing),
                           first_missing=[hex(m) for m in missing[:10]], named_function_symbols=len(syms),
                           named_symbols_not_indexed=len(sym_missing), first_unindexed_symbols=sym_missing[:10])
    with open(a.out + "/binary_names.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for n in names_out:
            fh.write(json.dumps(n, ensure_ascii=False, separators=(",", ":")) + "\n")
    json.dump(result, open(a.out + "/binary_check.json", "w"), indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
