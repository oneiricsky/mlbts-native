"""Count the prose habits listed on Wikipedia:Signs of AI writing in the built wiki pages.

    python -I tools/wiki_style_check.py [--wiki work/wiki] [--top 12]

Exit status is 1 when a page still has bold sentence leads, so the check can gate a rebuild.
These are heuristics, not proof: a page can use one and still read like a person wrote it.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")

PATTERNS = {
    "em dashes": re.compile(r"—"),
    "bold sentence lead": re.compile(r"\*\*[A-Z][^*]{0,70}\*\*[.,:]"),
    "bold bullet lead": re.compile(r"^\s*[-*] \*\*", re.M),
    "negative parallelism": re.compile(r"\b(not just|not merely|not only|rather than)\b", re.I),
    "ai vocabulary": re.compile(r"\b(crucial|pivotal|robust|seamless|leverage|delv\w+|testament|underscor\w+|"
                                r"showcas\w+|tapestry|landscape|realm|foster\w+|intricate|vibrant|"
                                r"holistic|renowned|meticulous\w*|comprehensive|multifaceted)\b", re.I),
    "hedge opener": re.compile(r"\b(It is important to note|It's worth noting|In today's|It is worth noting)\b", re.I),
    "at a glance": re.compile(r"at a glance", re.I),
}


def prose(text):
    """Only prose counts: table rows and fenced code quote game strings and field data."""
    lines, in_fence = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line.lstrip().startswith("|"):
            continue
        lines.append(line)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default=ROOT + "/work/wiki")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    rows = []
    totals = {k: 0 for k in PATTERNS}
    for fn in sorted(os.listdir(a.wiki)):
        if not fn.endswith(".md"):
            continue
        text = prose(open(os.path.join(a.wiki, fn), encoding="utf-8").read())
        counts = {k: len(p.findall(text)) for k, p in PATTERNS.items()}
        for k, v in counts.items():
            totals[k] += v
        rows.append((fn, counts))
    print(f"pages checked: {len(rows)} (tables and code excluded)")
    for k in PATTERNS:
        print(f"  {k:22s} {totals[k]:5d}")
    worst = sorted(rows, key=lambda r: -sum(r[1].values()))[:a.top]
    print("\nworst pages:")
    for fn, c in worst:
        hot = ", ".join(f"{k} {v}" for k, v in c.items() if v)
        print(f"  {fn:22s} {hot}")
    bad = [fn for fn, c in rows if c["bold sentence lead"]]
    print(f"\npages with bold sentence leads: {len(bad)} {bad[:6]}")
    return 1 if bad else 0
    print(f"pages checked: {len(rows)}")
    for k in PATTERNS:
        print(f"  {k:22s} {totals[k]:5d}")
    worst = sorted(rows, key=lambda r: -sum(r[1].values()))[:a.top]
    print("\nworst pages:")
    for fn, c in worst:
        hot = ", ".join(f"{k} {v}" for k, v in c.items() if v)
        print(f"  {fn:22s} {hot}")
    bad = [fn for fn, c in rows if c["bold sentence lead"]]
    print(f"\npages with bold sentence leads: {len(bad)} {bad[:6]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
