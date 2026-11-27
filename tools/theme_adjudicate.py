"""Adjudicate the independent reads (step 3 of the double-read pipeline).

    python -I tools/theme_adjudicate.py [--theme work/theme]

Reads `reads/a/out-*.jsonl`, `reads/b/out-*.jsonl` and `reads/c/out-*.jsonl` (the third read, for disagreements).
Two answers are accepted only when they name the same aspect and each one rests on evidence the machine can check:

  * a string the reader quotes, which must be one of the function's own strings; at most 20 `main` functions quote a
    `rare string`, otherwise it is a `common string`;
  * a callee address, which must be a direct callee; if that callee's role or strings name the aspect's vocabulary
    (`tools/theme_aspects.py`) it is `callee names the aspect`, else only `callee without a label`;
  * for a vtable method, a string its class's other methods quote (`class method string`), a string one hop out
    (`class near string`), or a sibling method whose role names the aspect (`sibling names the aspect`). The class
    context comes from `tools/vtable_class.py` and is the same block the reader saw in the dossier.

The window theme is never evidence: it is 37.5% right per function and the readers are told so. The weakest row of an
agreeing pair sets the row's `tier`: `strong` (rank 0 or 1: own rare string, naming callee, class method string,
naming sibling), `medium` (class near string, common own string), `weak` (a bare callee). The hand audit reports
precision per tier.

Writes:

  accepted.jsonl   rows the reads agree on whose evidence checks out, with tier, strengths and details
  abstained.jsonl  rows not labelled, with a reason
  queue-c.jsonl    addresses the reads disagree on; the third read's input
  state.json       counts, updated in place

Every run rebuilds accepted/abstained/queue from the read files, so it is safe to rerun and safe to interrupt. A
batch whose reads are missing leaves its addresses "pending"; it is not an error.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from theme_aspects import ASPECTS, hits
import vtable_class

ADDR = re.compile(r"(?:0x|f_)([0-9a-f]{9,12})")
RARE = 20  # a quoted string that at most this many main functions quote is specific evidence
ASPECTS = set(ASPECTS) | {"Unclear"}
NOT_PROOF = {
    "rare string": 0,
    "callee names the aspect": 1,
    "sibling names the aspect": 1,
    "class method string": 1,
    "class near string": 2,
    "common string": 2,
    "callee without a label": 3,
}


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            print(f"  bad JSON in {os.path.basename(path)} line {i}, skipped")
            continue
        if isinstance(r, dict) and r.get("addr"):
            rows.append(r)
    return rows


def load_reads(folder):
    out = {}
    for path in sorted(glob.glob(f"{folder}/out-*.jsonl")):
        for r in load_jsonl(path):
            addr = r["addr"].lower()
            r["addr"] = addr
            out.setdefault(addr, []).append(r)
    return out


def _better(a, b):
    """Pick the stronger of two candidate evidences; ties keep the earlier (own evidence before class evidence)."""
    if not a:
        return b
    if not b:
        return a
    return b if NOT_PROOF[b[0]] < NOT_PROOF[a[0]] else a


def quoted_segments(ev):
    """The text the reader put inside quotation marks: double, curly or single.

    Only quoted game text counts as string evidence. Without this, a sentence like "this could be a menu row" would
    match the word menu in a helper that has nothing to do with menus.
    """
    segs = re.findall(r'"([^"]{2,200})"', ev)
    segs += re.findall(r"\u201c([^\u201d]{2,200})\u201d", ev)
    segs += re.findall(r"'([^']{2,200})'", ev)
    return segs


def quoted_has(needle, segs):
    """True when `needle` appears as whole words inside one quoted segment."""
    n = needle.strip().lower()
    if len(n) < 4:
        return False
    pat = re.compile(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])")
    return any(pat.search(s.strip().lower()) for s in segs)


def grounding(row, own_strings, calls, string_count, roles, vt, class_cache, known):
    """How well the row's evidence supports its aspect. Returns (strength, rarity, detail) or (None, ...)."""
    ev = (row.get("evidence") or "").strip()
    segs = quoted_segments(ev)
    best = None
    for s in own_strings:
        s = s.strip()
        if len(s) < 4 or not quoted_has(s, segs):
            continue
        n = string_count.get(s, 0)
        best = _better(best, ("rare string" if n <= RARE else "common string", n, s))
    for m in ADDR.findall(ev):
        m = "0x" + m.lower()
        if m in calls:
            cr = roles.get(m) or {}
            said = " ".join([str(cr.get("role") or ""), str(cr.get("name") or "")] + list(cr.get("strings") or []))
            other = known.get(m)
            if other and other == row["aspect"]:
                best = _better(best, ("callee names the aspect", 0, m))
            elif hits(said, row["aspect"]):
                best = _better(best, ("callee names the aspect", 0, m))
            else:
                best = _better(best, ("callee without a label", 10 ** 6, m))
    # the vtable class, for methods whose own body is bare
    c = vt.class_of(row["addr"])
    if c:
        vtable, slot, size = c
        if vtable not in class_cache:
            class_cache[vtable] = (vt.method_strings(vtable), vt.near_strings(vtable), set(vt.members(vtable)))
        method, near, members = class_cache[vtable]
        for s in method:
            if len(s) >= 4 and quoted_has(s, segs):
                best = _better(best, ("class method string", 0, s))
        for s in near:
            if len(s) >= 4 and quoted_has(s, segs):
                best = _better(best, ("class near string", 0, s))
        for m in ADDR.findall(ev):
            m = "0x" + m.lower()
            if m in members:
                mr = roles.get(m) or {}
                said = " ".join([str(mr.get("role") or "")] + list(mr.get("strings") or []))
                if hits(said, row["aspect"]):
                    best = _better(best, ("sibling names the aspect", 0, m))
    return best or (None, None, None)


def tier_of(*strengths):
    ranks = [NOT_PROOF[s] for s in strengths if s]
    if not ranks:
        return "none"
    if max(ranks) <= 1:
        return "strong"
    if max(ranks) <= 2:
        return "medium"
    return "weak"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    a = ap.parse_args()

    man = json.load(open(f"{a.theme}/batches/manifest.json"))
    batch_of = {}
    for b in man["batches"]:
        for x in b.get("addrs", []):
            batch_of[x.lower()] = b.get("id", 0)
    addrs = list(batch_of)

    roles = {}
    string_count = Counter()
    for line in open(f"{a.index}/roles.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["module"] != "main":
            continue
        roles[r["addr"].lower()] = r
        for s in r.get("strings") or []:
            string_count[s.strip()] += 1
    calls = {}
    want = set(addrs)
    for line in open(f"{a.index}/generated_functions.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["module"] == "main" and r["addr"].lower() in want:
            calls[r["addr"].lower()] = {x.lower() for x in (r.get("calls") or [])}
    vt = vtable_class.load(a.index)
    class_cache = {}

    known = {r["addr"].lower(): r["aspect"] for r in load_jsonl(f"{a.theme}/accepted.jsonl")}
    library = {r["addr"].lower() for r in load_jsonl(f"{a.theme}/library.jsonl")}
    A = load_reads(f"{a.theme}/reads/a")
    B = load_reads(f"{a.theme}/reads/b")
    C = load_reads(f"{a.theme}/reads/c")

    ok_rows, abstained, queue = [], [], []
    pending = 0
    for addr in addrs:
        ra, rb = A.get(addr, []), B.get(addr, [])
        if not ra or not rb:
            pending += 1
            continue
        a1, b1 = ra[0], rb[0]
        if addr in library:
            abstained.append({"addr": addr, "reason": "library code"})
            continue
        if a1.get("aspect") not in ASPECTS or b1.get("aspect") not in ASPECTS:
            abstained.append({"addr": addr, "reason": "aspect outside the list"})
            continue
        own = roles.get(addr, {}).get("strings") or []
        ca = calls.get(addr, set())
        ga, na, da = grounding(a1, own, ca, string_count, roles, vt, class_cache, known)
        gb, nb, db = grounding(b1, own, ca, string_count, roles, vt, class_cache, known)
        if a1["aspect"] == b1["aspect"]:
            if a1["aspect"] == "Unclear":
                abstained.append({"addr": addr, "reason": "both reads found no decisive evidence"})
            elif ga and gb and "callee without a label" in (ga, gb):
                abstained.append({"addr": addr, "aspect": a1["aspect"],
                                  "reason": "rests only on calling an unlabelled function",
                                  "strength": [ga, gb]})
            elif ga and gb:
                ok_rows.append({"addr": addr, "aspect": a1["aspect"], "reads": 2, "batch": batch_of[addr],
                                "tier": tier_of(ga, gb), "strength": [ga, gb], "detail": [da, db],
                                "evidence": [a1.get("evidence", ""), b1.get("evidence", "")]})
            else:
                abstained.append({"addr": addr, "aspect": a1["aspect"], "reason": "agreed but evidence failed",
                                  "strength": [ga, gb], "evidence": [a1.get("evidence", ""), b1.get("evidence", "")]})
            continue
        rc = C.get(addr, [])
        if not rc:
            queue.append({"addr": addr, "batch": batch_of[addr], "a": a1.get("aspect"), "b": b1.get("aspect")})
            continue
        c1 = rc[0]
        gc, nc, dc = grounding(c1, own, ca, string_count, roles, vt, class_cache, known)
        votes = [a1["aspect"], b1["aspect"], c1.get("aspect")]
        winner = next((v for v in votes if v != "Unclear" and votes.count(v) >= 2), None)
        grounded = [g for i, g in enumerate([ga, gb, gc]) if g and votes[i] == winner]
        text_only = {"rare string", "common string", "class method string"}
        had_unclear = "Unclear" in votes[:2]
        settles = len(grounded) >= 2 and any(g in text_only for g in grounded) \
            and not (had_unclear and not any(g in text_only for g in grounded))
        if winner and settles:
            ok_rows.append({"addr": addr, "aspect": winner, "reads": 3, "batch": batch_of[addr],
                            "tier": tier_of(*grounded), "strength": [ga, gb, gc], "detail": [da, db, dc],
                            "evidence": [x.get("evidence", "") for x in (a1, b1, c1)]})
        else:
            abstained.append({"addr": addr, "votes": votes, "reason": "three reads did not settle it",
                              "strength": [ga, gb, gc]})

    def dump(path, rows):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    dump(f"{a.theme}/accepted.jsonl", ok_rows)
    dump(f"{a.theme}/abstained.jsonl", abstained)
    dump(f"{a.theme}/queue-c.jsonl", queue)
    state_path = f"{a.theme}/state.json"
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    tiers = Counter(r["tier"] for r in ok_rows)
    state["adjudicated"] = {"targets": len(addrs), "accepted": len(ok_rows), "tiers": dict(tiers),
                            "abstained": len(abstained), "needs_third_read": len(queue), "pending": pending}
    json.dump(state, open(state_path, "w", encoding="utf-8"), indent=1)
    print(f"targets {len(addrs)}: accepted {len(ok_rows)} "
          f"(strong {tiers['strong']}, medium {tiers['medium']}, weak {tiers['weak']}), "
          f"abstained {len(abstained)}, need a third read {len(queue)}, pending {pending}")
    for r in ok_rows[:6]:
        strengths = " / ".join(s or "ungrounded" for s in r["strength"])
        print(f"  {r['addr']}  {r['aspect']:<28} {r['tier']:<7} {strengths}  {' | '.join(r['evidence'])[:80]}")


if __name__ == "__main__":
    main()
