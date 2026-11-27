"""Report what a theme run has produced so far, in numbers.

    python -I tools/theme_stats.py [--theme work/theme]

Reads the batch manifest, both readers' output and the adjudicated files, and prints:

  * per batch: how many addresses both readers answered, how many agreed, disagreed or both said Unclear;
  * the readers' agreement rate on the addresses where both named an aspect (the number that predicts how much
    the pipeline can accept);
  * the accepted rows by tier, by aspect, and how often their label is merely the window's prior aspect, which is
    the baseline the pipeline has to beat (37.5% right per function in the earlier measurement);
  * why the rest were abstained.

It reads files only; nothing is written.
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from wiki_completeness import aspect_of


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_folder(folder):
    out = {}
    for path in sorted(glob.glob(f"{folder}/out-*.jsonl")):
        for r in load_jsonl(path):
            if not r.get("aspect"):
                continue
            out.setdefault(r["addr"].lower(), []).append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    a = ap.parse_args()
    man = json.load(open(f"{a.theme}/batches/manifest.json"))
    A, B = load_folder(f"{a.theme}/reads/a"), load_folder(f"{a.theme}/reads/b")
    prior = {r["addr"]: r.get("prior_aspect", "") for r in load_jsonl(f"{a.theme}/targets.jsonl")}
    accepted = load_jsonl(f"{a.theme}/accepted.jsonl")
    abstained = load_jsonl(f"{a.theme}/abstained.jsonl")

    both = agree = unclear = differ = one_unclear = 0
    per_batch = defaultdict(lambda: Counter())
    for b in man["batches"]:
        for addr in b.get("addrs", []):
            x = addr.lower()
            ra, rb = A.get(x, []), B.get(x, [])
            c = per_batch[b.get("id", 0)]
            c["addrs"] += 1
            if not ra or not rb:
                continue
            c["both"] += 1
            both += 1
            ua, ub = ra[0]["aspect"] == "Unclear", rb[0]["aspect"] == "Unclear"
            if ua and ub:
                unclear += 1
                c["both unclear"] += 1
            elif ua or ub:
                one_unclear += 1
                c["one unclear"] += 1
            elif ra[0]["aspect"] == rb[0]["aspect"]:
                agree += 1
                c["agree"] += 1
            else:
                differ += 1
                c["differ"] += 1

    print(f"addresses with both reads: {both}")
    print(f"  both Unclear: {unclear}   one Unclear: {one_unclear}   disagree: {differ}   agree: {agree}")
    labelled = agree + differ
    if labelled:
        print(f"agreement where both named an aspect: {agree}/{labelled} = {100.0 * agree / labelled:.0f}%")
    print("\nper batch (batch: both / agree / differ / one unclear / both unclear)")
    for k in sorted(per_batch):
        c = per_batch[k]
        print(f"  {k}: {c['both']} / {c['agree']} / {c['differ']} / {c['one unclear']} / {c['both unclear']}")

    tiers = Counter(r.get("tier") for r in accepted)
    print(f"\naccepted {len(accepted)} of {len(prior)} targets: " +
          ", ".join(f"{k} {v}" for k, v in tiers.most_common()))
    aspects = Counter(r["aspect"] for r in accepted)
    print("by aspect: " + ", ".join(f"{k} {v}" for k, v in aspects.most_common()))
    same = sum(1 for r in accepted if prior.get(r["addr"]) == r["aspect"])
    if accepted:
        print(f"label equals the window's prior aspect: {same}/{len(accepted)} = {100.0 * same / len(accepted):.0f}%")
    reasons = Counter(r.get("reason") for r in abstained)
    print("abstained: " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
