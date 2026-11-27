"""Lay out accepted labels for a hand audit, and score the filled sheet.

    python -I tools/theme_audit.py [--theme work/theme] [--sample 20]
    python -I tools/theme_audit.py --score work/theme/audit-001.md

`theme_adjudicate.py` can prove that two readers agreed and that each quoted a real string or named a real callee.
It cannot prove the aspect follows from the evidence. This tool prints a fixed sample of accepted rows with the
evidence the readers saw and a verdict slot; a person fills each slot with `right`, `wrong` or `unsure`, and the
score mode prints the counts and the precision (right / (right + wrong)).

The sample is drawn with a fixed stride over the accepted rows sorted by address, so the same `--sample` gives the
same rows on the same accepted set, and a rerun can be compared.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def entry_of(dossier, addr):
    """The dossier section for one address, verbatim."""
    text = open(dossier, encoding="utf-8").read()
    hits = list(re.finditer(r"^## (" + re.escape(addr) + r")\b", text, re.M))
    if not hits:
        return ""
    start = hits[0].start()
    nxt = re.search(r"^## ", text[start + 3:], re.M)
    end = start + 3 + nxt.start() if nxt else len(text)
    return text[start:end].strip()


def score(path):
    text = open(path, encoding="utf-8").read()
    verdicts = re.findall(r"^verdict:\s*(right|wrong|unsure)\b", text, re.M)
    n = {"right": verdicts.count("right"), "wrong": verdicts.count("wrong"),
         "unsure": verdicts.count("unsure")}
    done = n["right"] + n["wrong"]
    pct = (100.0 * n["right"] / done) if done else 0.0
    print(f"audited {len(verdicts)}: right {n['right']}, wrong {n['wrong']}, unsure {n['unsure']}")
    print(f"precision on decided rows: {n['right']}/{done} = {pct:.0f}%" if done else "nothing decided yet")
    return 0 if done else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--tier", default="", help="only rows of this tier: strong, medium or weak")
    ap.add_argument("--out", default="")
    ap.add_argument("--score", default="")
    a = ap.parse_args()
    if a.score:
        return score(a.score)

    man = json.load(open(f"{a.theme}/batches/manifest.json"))
    batch = {}
    for b in man["batches"]:
        for x in b.get("addrs", []):
            batch[x.lower()] = b.get("file", "")
    where = {}
    for line in open(f"{a.index}/roles.jsonl", encoding="utf-8"):
        r = json.loads(line)
        where[r["addr"].lower()] = f"work/gen/{r['file']}:{r['line']}"
    accepted = sorted(load_jsonl(f"{a.theme}/accepted.jsonl"), key=lambda r: int(r["addr"], 16))
    if a.tier:
        accepted = [r for r in accepted if r.get("tier") == a.tier]
    if not accepted:
        print("no accepted rows" + (f" of tier {a.tier}" if a.tier else "") + " yet")
        return 1
    step = max(1, len(accepted) // a.sample)
    sample = accepted[::step][: a.sample]
    out = a.out or f"{a.theme}/audit-{(a.tier + '-') if a.tier else ''}{len(accepted):04d}.md"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# Hand audit of accepted theme labels\n\nSample {len(sample)} of {len(accepted)} accepted rows. For each row: does the\n"
                "aspect follow from what the dossier shows? Fill `verdict: right`, `verdict: wrong` or `verdict: unsure`.\n"
                "Then run `python -I tools/theme_audit.py --score <this file>`.\n")
        for r in sample:
            f.write(f"\n## {r['addr']}  {r['aspect']}\n")
            f.write(f"strength: {', '.join(str(x) for x in r.get('strength', []))}\n")
            f.write(f"reader A: {r['evidence'][0]}\n")
            if len(r.get("evidence", [])) > 1:
                f.write(f"reader B: {r['evidence'][1]}\n")
            if len(r.get("evidence", [])) > 2:
                f.write(f"reader C: {r['evidence'][2]}\n")
            f.write(f"\n```\n{entry_of(batch[r['addr']], r['addr'])}\n```\n")
            f.write(f"\nfull body: {where.get(r['addr'], '?')}\n")
            f.write("\nverdict:\n")
    print(f"wrote {out} ({len(sample)} rows of {len(accepted)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
