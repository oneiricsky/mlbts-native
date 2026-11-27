"""The judge: a separate agent checks one accepted label against the function body, with no other votes.

    python -I tools/theme_judge.py --prepare      # writes work/theme/judge-batch-NNN.md
    python -I tools/theme_judge.py --merge        # reads work/theme/judge/out-NNN.jsonl into judged.jsonl

The adjudicator proves two readers agreed and that each quoted real text. It cannot prove the aspect follows from the
body. The judge sees one entry at a time: the function's dossier section, the accepted aspect, and the readers'
evidence. It does not see the other votes or the window theme, and it answers `follows`, `does not follow` or
`unsure` with one sentence.

Run the judge in its own agent, with the same model if that is all that is available: what matters is that it sees
no votes and no window theme, so it cannot lean on the readers' agreement.
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
BATCH = 25


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def entry_of(dossier_text, addr):
    hits = list(re.finditer(r"^## (" + re.escape(addr) + r")\b", dossier_text, re.M))
    if not hits:
        return ""
    start = hits[0].start()
    nxt = re.search(r"^## ", dossier_text[start + 3:], re.M)
    end = start + 3 + nxt.start() if nxt else len(dossier_text)
    return dossier_text[start:end].strip()


def dossier_text(theme, batch):
    path = f"{theme}/batches/batch-{batch:03d}.md"
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def prepare(theme):
    judged = {r["addr"] for r in load_jsonl(f"{theme}/judged.jsonl") if r.get("judge")}
    accepted = [r for r in load_jsonl(f"{theme}/accepted.jsonl") if r["addr"] not in judged]
    by_batch = {}
    for r in accepted:
        by_batch.setdefault(r.get("batch", 0), []).append(r)
    os.makedirs(f"{theme}/judge", exist_ok=True)
    n = 0
    prompt = open(ROOT + "/tools/theme_judge_prompt.md", encoding="utf-8").read()
    for b, rows in sorted(by_batch.items(), key=lambda kv: kv[0]):
        text = dossier_text(theme, b)
        if not text:
            print(f"batch {b}: no dossier, skipped")
            continue
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            num = n
            n += 1
            lines = [prompt, f"# Judge batch {num} ({len(chunk)} entries)", ""]
            for r in chunk:
                ev = " | ".join(x for x in (r.get("evidence") or []) if x)
                lines += [f"## {r['addr']}", f"label: {r['aspect']}", f"evidence: {ev[:400]}", "",
                          "```", entry_of(text, r["addr"]), "```", ""]
            open(f"{theme}/judge/judge-batch-{num:03d}.md", "w", encoding="utf-8", newline="\n").write(
                "\n".join(lines) + "\n")
    print(f"prepared {n} judge batch(es) from {len(accepted)} accepted rows")


def merge(theme):
    rows = []
    for path in sorted(glob.glob(f"{theme}/judge/out-*.jsonl")):
        rows.extend(load_jsonl(path))
    verdicts = {r["addr"]: {"verdict": r["judge"], "reason": r.get("judge_reason", "")}
                for r in load_jsonl(f"{theme}/judged.jsonl") if r.get("judge")}
    for r in rows:
        addr = (r.get("addr") or "").lower()
        v = (r.get("verdict") or "").strip().lower()
        if addr and v in ("follows", "does not follow", "unsure"):
            verdicts[addr] = {"verdict": v, "reason": r.get("reason", "")}
    judged = []
    for r in load_jsonl(f"{theme}/accepted.jsonl"):
        v = verdicts.get(r["addr"])
        if v:
            r["judge"] = v["verdict"]
            r["judge_reason"] = v["reason"]
        judged.append(r)
    with open(f"{theme}/judged.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in judged:
            f.write(json.dumps(r) + "\n")
    from collections import Counter
    c = Counter(r.get("judge", "not judged") for r in judged)
    print(f"{len(judged)} accepted rows: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    bad = [r for r in judged if r.get("judge") == "does not follow"]
    for r in bad[:6]:
        print(f"  {r['addr']} {r['aspect']}: {r.get('judge_reason', '')[:100]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    if a.prepare:
        prepare(a.theme)
    if a.merge:
        merge(a.theme)


if __name__ == "__main__":
    main()
