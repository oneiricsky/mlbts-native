"""Index every `this`-relative field access in the game's generated C: who reads and writes which offset.

    python -I tools/map_fields.py [--gen work/gen] [--index work/map/index] [--out work/map/fields]

For each recompiled function, the generated C accesses object fields through x0 (`this`) or through a register
copied from x0. This pass records, per function, every (offset, width, read/write) it uses, then groups the
result by vtable: the functions in a table are that class's methods, so their accesses are its field map.

Writes work/map/fields/fields.jsonl (per function) and work/map/fields/summary.json (counts + the largest class
field maps). Derived from game code: stays under work/, like the rest of the index.
"""
import argparse, json, os, re, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
DEF = re.compile(r"^void f_([0-9a-f]+)\(Cpu \*c\) \{")
ALIAS = re.compile(r"^(?:uint64_t )?x(\d+) = \(uint64_t\)\(0ull \| x0\);|^(?:uint64_t )?x(\d+) = x0;")
EA = re.compile(r"\{ uint64_t ea = (x\d+) \+ (0x[0-9a-f]+)ull;")
LD = re.compile(r"\b(LD(?:64|32|16|8|U16|U8|S8))\(ea\)")
ST = re.compile(r"\b(ST(?:64|32|16|8))\(ea,")


def width_of(op):
    m = re.search(r"(64|32|16|8)", op)
    return int(m.group(1)) // 8 if m else 0


def scan_module(gen, mod, funcs):
    by_file = defaultdict(list)
    for f in funcs:
        by_file[f["file"]].append(f)
    out = {}
    for path, fl in by_file.items():
        want = {f["line"]: f["addr"] for f in fl}
        cur, acc, aliases = None, None, None
        with open(f"{gen}/{path}", encoding="utf-8", errors="replace") as fh:
            for ln, line in enumerate(fh, 1):
                if ln in want:
                    if cur is not None:
                        out[cur] = acc
                    cur, acc, aliases = want[ln], [], {"x0"}
                    continue
                if acc is None:
                    continue
                m = ALIAS.match(line.strip())
                if m:
                    aliases.add("x" + (m.group(1) or m.group(2)))
                m = EA.search(line)
                if not m:
                    continue
                base, off = m.group(1), int(m.group(2), 16)
                if base not in aliases:
                    continue
                r, w = LD.search(line), ST.search(line)
                if r:
                    acc.append((off, width_of(r.group(1)), "r"))
                elif w:
                    acc.append((off, width_of(w.group(1)), "w"))
        if cur is not None:
            out[cur] = acc
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--out", default=ROOT + "/work/map/fields")
    a = ap.parse_args()
    funcs = [json.loads(l) for l in open(f"{a.index}/generated_functions.jsonl", encoding="utf-8")]
    vtables = [json.loads(l) for l in open(f"{a.index}/vtables.jsonl", encoding="utf-8")]
    roles = {r["addr"]: r for r in (json.loads(l) for l in open(f"{a.index}/roles.jsonl", encoding="utf-8"))}
    os.makedirs(a.out, exist_ok=True)
    fields = {}
    for mod in ("main", "sdk"):
        fields.update(scan_module(a.gen, mod, [f for f in funcs if f["module"] == mod]))
    # vtable -> union of its methods' field accesses (a class's field map), with the readable users
    class_fields = {}
    for v in vtables:
        acc = Counter()
        who = defaultdict(list)
        for fn in v["functions"]:
            r = roles.get(fn) or {}
            role = " ".join(str(r.get("role") or r.get("name") or "")[:70].split())
            for off, w, rw in fields.get(fn, []):
                acc[(off, w, rw)] += 1
                if role and len(who[(off, w, rw)]) < 3:
                    who[(off, w, rw)].append([fn, role, r.get("tag", "")])
        if acc:
            rows = []
            for (o, w, rw), n in sorted(acc.items()):
                rows.append([o, w, rw, n, who[(o, w, rw)]])
            wins = Counter(int(fn, 16) >> 18 for fn in v["functions"])
            coherence = round(max(wins.values()) / max(1, len(v["functions"])), 3)
            class_fields[v["vtable"]] = dict(size=v["size"], coherence=coherence, fields=rows)
    with open(f"{a.out}/fields.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for addr in sorted(fields, key=lambda x: int(x, 16)):
            fh.write(json.dumps(dict(addr=addr, fields=fields[addr]), separators=(",", ":")) + "\n")
    with open(f"{a.out}/classes.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for vt in sorted(class_fields, key=lambda x: int(x, 16)):
            fh.write(json.dumps(dict(vtable=vt, **class_fields[vt]), separators=(",", ":")) + "\n")
    summary = dict(functions_scanned=len(funcs), functions_with_fields=sum(1 for f in fields.values() if f),
                   accesses=sum(len(f) for f in fields.values()),
                   distinct_offsets=len({o for f in fields.values() for o, _, _ in f}),
                   vtables_with_fields=len(class_fields),
                   largest_classes=[dict(vtable=v, size=d["size"], fields=len(d["fields"]))
                                    for v, d in sorted(class_fields.items(), key=lambda kv: -len(kv[1]["fields"]))[:10]])
    json.dump(summary, open(f"{a.out}/summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
