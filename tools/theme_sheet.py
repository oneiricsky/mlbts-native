"""A fixed answer sheet for the theming pipeline: about 200 functions with known verdicts.

    python -I tools/theme_sheet.py --build      # writes work/theme/sheet.jsonl
    python -I tools/theme_sheet.py --score      # scores accepted.jsonl against it

The sheet is the regression test for every rule change. Each row carries the verdict the pipeline should produce and
where that verdict comes from:

  gold        the function's own string names the aspect outright (decisive evidence, not a guess)
  known-bad   a row an earlier run accepted on a bare callee; the audit said those are right about half the time, so
              the pipeline must now reject them
  library     a function tools/theme_filter.py calls library code; it must not be labelled with a game aspect
  shared      a function whose read role is generic machinery; the correct label is Shared engine code
  noise       a random function with no verdict; it is scored only for "was it accepted", to catch a rule that
              labels everything

Run the score after every change to a rule: a change that lowers the gold score or lets known-bad rows back in is a
regression, whatever the accepted count says.
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from theme_aspects import ASPECTS, hits

TARGET = 200


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def build(index, theme):
    roles = [json.loads(l) for l in open(f"{index}/roles.jsonl", encoding="utf-8")]
    main = [r for r in roles if r["module"] == "main"]
    rows = []

    # gold: the function's own strings name exactly one aspect
    for r in main:
        found = set()
        for s in r.get("strings") or []:
            for a in ASPECTS:
                if hits(s, a):
                    found.add(a)
        if len(found) == 1:
            rows.append({"addr": r["addr"], "expected": found.pop(), "why": "own string names the aspect",
                         "category": "gold"})
    random.seed(11)
    random.shuffle(rows)
    rows = rows[:80]

    # known-bad: previously accepted on a bare callee only
    old = load_jsonl(f"{theme}/accepted-run0.jsonl") or load_jsonl(f"{theme}/accepted.jsonl")
    bad = [r for r in old if r.get("strength") and all(s == "callee without a label" for s in r["strength"]
                                                         if isinstance(s, str))]
    for r in bad[:40]:
        rows.append({"addr": r["addr"], "expected": "reject", "why": "accepted earlier on a bare callee only",
                     "category": "known-bad"})

    # library code must not get a game aspect
    for r in load_jsonl(f"{theme}/library.jsonl")[:30]:
        rows.append({"addr": r["addr"], "expected": "Library code", "why": r.get("reason", ""),
                     "category": "library"})

    # generic machinery should be Shared engine code
    shared = [r for r in main if r.get("read") and any(
        w in (r.get("role") or "").lower() for w in ("vector", "container", "allocator", "memcpy", "string buffer",
                                                     "hash table", "list node", "refcount"))]
    for r in shared[:30]:
        rows.append({"addr": r["addr"], "expected": "Shared engine code", "why": r.get("role", "")[:80],
                     "category": "shared"})

    # noise: no verdict, only used to see whether the pipeline labels everything
    for r in random.sample(main, 20):
        rows.append({"addr": r["addr"], "expected": "", "why": "", "category": "noise"})

    seen, unique = set(), []
    for r in rows:
        if r["addr"] in seen:
            continue
        seen.add(r["addr"])
        unique.append(r)
    with open(f"{theme}/sheet.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in unique:
            f.write(json.dumps(r) + "\n")
    from collections import Counter
    print(f"sheet: {len(unique)} rows " + ", ".join(f"{k} {v}" for k, v in Counter(r['category'] for r in unique).items()))


def score(theme):
    sheet = load_jsonl(f"{theme}/sheet.jsonl")
    judged = load_jsonl(f"{theme}/judged.jsonl")
    source = judged if judged else load_jsonl(f"{theme}/accepted.jsonl")
    accepted = {r["addr"]: r for r in source if r.get("judge") != "does not follow"}
    stats = {}
    bad = []
    for row in sheet:
        c = stats.setdefault(row["category"], {"n": 0, "right": 0, "wrong": 0, "missed": 0, "accepted": 0})
        c["n"] += 1
        got = accepted.get(row["addr"])
        if got:
            c["accepted"] += 1
        exp = row["expected"]
        if exp == "reject":
            # the old verdict was "do not label this on a bare callee"; a label is acceptable now only if the
            # evidence is no longer a bare callee
            bare = got and any(s == "callee without a label" for s in (got.get("strength") or []) if isinstance(s, str))
            if bare:
                c["wrong"] += 1
                bad.append((row["addr"], "still accepted on a bare callee"))
            else:
                c["right"] += 1
        elif exp == "Library code":
            if got:
                c["wrong"] += 1
                bad.append((row["addr"], f"library code labelled {got['aspect']}"))
            else:
                c["right"] += 1
        elif exp:
            if not got:
                c["missed"] += 1
            elif got.get("aspect") == exp:
                c["right"] += 1
            else:
                c["wrong"] += 1
                bad.append((row["addr"], f"want {exp}, got {got.get('aspect')}"))
    print(f"{'category':10s} {'rows':>5} {'right':>6} {'wrong':>6} {'missed':>7} {'accepted':>9}")
    for k, c in stats.items():
        print(f"{k:10s} {c['n']:>5} {c['right']:>6} {c['wrong']:>6} {c['missed']:>7} {c['accepted']:>9}")
    if bad:
        print("first failures:")
        for a, why in bad[:8]:
            print(f"  {a}  {why}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.build:
        build(a.index, a.theme)
    if a.score:
        score(a.theme)


if __name__ == "__main__":
    main()
