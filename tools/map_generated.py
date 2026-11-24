"""Index every function in the recompiler's generated C (the game binary as the port sees it).

    python -I tools/map_generated.py [--gen work/gen] [--out work/map/index]

Each recompiled game function is `void f_<address>(Cpu *c) {`, so the address is its identity in the Switch
binary (modules `main` and `sdk`). Writes generated_functions.jsonl (module, addr, file, line, lines, direct
callees, caller count, rt_dispatch count = indirect branches/calls, rt_udf count = undefined/trap sites) and
generated_summary.json (counts against each module's manifest function_count). The output is large and stays
under work/ (git-ignored); docs/map/ holds the readable per-region summary built from it.
"""
import argparse, json, os, re
from collections import Counter

DEF = re.compile(r"^void f_([0-9a-f]+)\(Cpu \*c\) \{")
CALL = re.compile(r"\bf_([0-9a-f]+)\(c\)")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")


def scan_module(gen, mod):
    man = json.load(open(f"{gen}/{mod}/manifest.json"))
    funcs = []
    for name in sorted(os.listdir(f"{gen}/{mod}")):
        if not name.endswith(".c") or name.endswith("_table.c"):
            continue
        cur = None
        with open(f"{gen}/{mod}/{name}", encoding="utf-8", errors="replace") as fh:
            for ln, line in enumerate(fh, 1):
                m = DEF.match(line)
                if m:
                    if cur:
                        cur["lines"] = ln - cur["line"]
                        funcs.append(cur)
                    cur = dict(module=mod, addr="0x" + m.group(1), file=f"{mod}/{name}", line=ln, lines=0,
                               calls=[], dispatch=0, udf=0)
                    own = m.group(1)
                    continue
                if cur is None:
                    continue
                if "f_" in line:
                    for c in CALL.findall(line):
                        if c != own and "0x" + c not in cur["calls"]:
                            cur["calls"].append("0x" + c)
                if "rt_dispatch(" in line:
                    cur["dispatch"] += line.count("rt_dispatch(")
                if "rt_udf(" in line:
                    cur["udf"] += line.count("rt_udf(")
            if cur:
                cur["lines"] = ln + 1 - cur["line"]
                funcs.append(cur)
                cur = None
    return man, funcs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    ap.add_argument("--out", default=ROOT + "/work/map/index")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    summ, allf = {}, []
    for mod in ("main", "sdk"):
        man, funcs = scan_module(a.gen, mod)
        addrs = Counter(f["addr"] for f in funcs)
        summ[mod] = dict(manifest_function_count=man["function_count"], indexed=len(funcs),
                         unique_addresses=len(addrs), duplicates=sum(1 for v in addrs.values() if v > 1),
                         base=man["base"], text=man["text"], chunks=len(set(f["file"] for f in funcs)),
                         generated_lines=sum(f["lines"] for f in funcs))
        allf.extend(funcs)
    callers = Counter()
    known = set(f["addr"] for f in allf)
    unresolved = Counter()
    for f in allf:
        for c in f["calls"]:
            callers[c] += 1
            if c not in known:
                unresolved[c] += 1
    for f in allf:
        f["callers"] = callers.get(f["addr"], 0)
    with open(a.out + "/generated_functions.jsonl", "w", newline="\n") as fh:
        for f in allf:
            fh.write(json.dumps(f, separators=(",", ":")) + "\n")
    summ["total_indexed"] = len(allf)
    summ["callee_addresses_not_defined"] = len(unresolved)
    summ["uncalled_functions"] = sum(1 for f in allf if f["callers"] == 0)
    summ["with_indirect_dispatch"] = sum(1 for f in allf if f["dispatch"])
    json.dump(summ, open(a.out + "/generated_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
