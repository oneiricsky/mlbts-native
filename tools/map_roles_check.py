"""Check the complete function map (work/map/index/roles.jsonl) against facts that do not come from it.

    python -I tools/map_roles_check.py [--index work/map/index] [--gen work/gen]

Exits 1 on the first failed check. Checks:
  1. every recompiled function has exactly one row (counts against each module's manifest), and no address repeats;
  2. every row is complete (kind, tag, shape, role) and within the taxonomy;
  3. the import thunks are named: 724 in `main`, 7,961 in `sdk`, all distinct targets, and the known ones match;
  4. addresses documented elsewhere in the repo keep their documented properties (caller counts, vtable slots, names);
  5. the census adds up: the 256 KB window counts equal the module totals;
  6. a sample of structural labels is true of the generated C (a getter really loads and returns, an empty stub
     really returns at once).
Derived from game code, so it needs work/map/index and work/gen; it is not part of the CI content check.
"""
import argparse, json, os, random, re, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
KINDS = {"import", "sdk", "symbol", "game", "library", "boilerplate"}
TAGS = {"C", "I", "H"}
SHAPES = {"empty", "trap", "const", "getter", "setter", "tailcall", "thunk", "dispatch", "unknown"}
FAIL = []


def check(ok, what):
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAIL.append(what)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(f"{a.index}/roles.jsonl", encoding="utf-8")]
    summary = json.load(open(f"{a.index}/generated_summary.json"))
    by = {r["addr"]: r for r in rows}

    # 1. completeness and uniqueness
    check(len(rows) == len(by), f"{len(rows)} rows, {len(by)} unique addresses")
    for mod in ("main", "sdk"):
        want = summary[mod]["manifest_function_count"]
        got = sum(1 for r in rows if r["module"] == mod)
        check(got == want, f"{mod}: {got} rows against {want} manifest functions")

    # 2. every row complete and in the taxonomy
    bad = [r["addr"] for r in rows if r["kind"] not in KINDS or r["tag"] not in TAGS or r["shape"] not in SHAPES
           or not r["role"].strip()]
    check(not bad, f"every row has a kind, tag, shape and role (bad: {bad[:5]})")

    # 3. import thunks
    imp = [r for r in rows if r["kind"] == "import"]
    mi = sum(1 for r in imp if r["module"] == "main")
    si = sum(1 for r in imp if r["module"] == "sdk")
    check(mi == 724, f"main import thunks: {mi} (the module has 724 JUMP_SLOT imports)")
    check(si == 7961, f"sdk import thunks: {si} (the module has 7,961 JUMP_SLOT imports)")
    for mod in ("main", "sdk"):
        names = [r.get("raw") or r["name"] for r in imp if r["module"] == mod]
        check(len(set(names)) == len(names), f"{mod}: no two import thunks share a target")
    known = {"0x7001c1fb70": "memset", "0x7001c1f920": "malloc", "0x70005b30a0": "operator new",
             "0x7000000880": "nnMain"}
    for ad, want in known.items():
        got = (by.get(ad) or {}).get("name") or ""
        check(got.startswith(want), f"{ad} is {want} (got {got!r})")

    # 4. documented facts elsewhere in the repo
    facts = [
        ("0x700108b628", "slot", 5, "BATTER_UP slot 5 (known-functions.md)"),
        ("0x700108b628", "vtable", "0x70021e2708", "BATTER_UP vtable"),
        ("0x70005a1a90", "callers", 47, "GPU kick wait has 47 direct callers (AGENTS.md)"),
        ("0x70005b30a0", "callers", 4060, "operator new has 4,060 callers (known-functions.md)"),
    ]
    for ad, field, want, why in facts:
        got = (by.get(ad) or {}).get(field)
        check(got == want, f"{ad} {field} == {want}: {why} (got {got!r})")

    # 5. census adds up
    for mod in ("main", "sdk"):
        total = sum(1 for r in rows if r["module"] == mod)
        wins = sum(len(v) for v in _windows(rows, mod).values())
        check(total == wins, f"{mod}: window counts add up ({wins} of {total})")

    # 6. structural labels are true of the generated C
    random.seed(7)
    bybody = defaultdict(dict)
    for r in rows:
        if r["module"] in ("main", "sdk"):
            bybody[r["file"]][r["line"]] = r
    samples = {}
    for shape in ("getter", "empty", "trap", "const"):
        cand = [r for r in rows if r["kind"] == "boilerplate" and r["shape"] == shape]
        samples[shape] = random.sample(cand, min(5, len(cand)))
    ok = True
    for shape, rs in samples.items():
        for r in rs:
            lines = open(f"{a.gen}/{r['file']}", encoding="utf-8", errors="replace").read().split("\n")
            body = "\n".join(lines[r["line"] - 1:r["line"] + r["lines"] - 1])
            if shape == "getter":
                good = bool(re.search(r"\bLD(?:64|32|U16|U8|S8|16|8)\(", body)) and "c->x[0] = x0" in body
            elif shape == "empty":
                good = body.count("\n") <= 4 and "return;" in body and "rt_dispatch" not in body
            elif shape == "trap":
                good = "rt_udf(" in body
            else:
                good = bool(re.search(r"x0 = \((?:uint64_t|uint32_t)\)\((?:[0-9a-f]+ull \| [0-9a-f]+|0x[0-9a-f]+|0)ull\);",
                                      body)) and "c->x[0] = x0; return;" in body and "rt_dispatch" not in body
            if not good:
                ok = False
                print(f"  sample {r['addr']} labelled {shape} does not look like it:\n{body}")
    check(ok, "sampled structural labels match their bodies")

    # 7. the body-read overlay, when present, is well formed and applied to the same addresses
    op = f"{a.index}/roles_read.jsonl"
    if os.path.exists(op):
        ov = [json.loads(l) for l in open(op, encoding="utf-8")]
        badov = [o["addr"] for o in ov if o["addr"] not in by or o.get("tag") not in TAGS or not o.get("role", "").strip()]
        applied = sum(1 for r in rows if r.get("read"))
        check(not badov and applied == len(ov),
              f"read overlay: {len(ov)} rows, {applied} applied (bad: {badov[:3]})")

    print(f"\nFailed checks: {len(FAIL)}")
    sys.exit(1 if FAIL else 0)


def _windows(rows, mod):
    g = defaultdict(list)
    for r in rows:
        if r["module"] == mod:
            g[int(r["addr"], 16) >> 18].append(r)
    return g


if __name__ == "__main__":
    main()
