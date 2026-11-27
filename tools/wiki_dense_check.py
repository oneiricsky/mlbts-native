"""List the wall-of-text paragraphs and list items, and the long headings, in the built wiki pages.

    python -I tools/wiki_dense_check.py [--wiki work/wiki] [--max 400] [--full]

A block is a paragraph or one list item, with wrapped lines joined. Tables and fenced code are skipped. Length is
counted on the text a reader sees (no link targets, tags or backticks). A heading may have up to five words and no
parentheses. Exit status 1 when a block or a heading breaks the rule.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def blocks(text):
    out, cur, fence = [], [], False

    def flush():
        if cur:
            out.append((cur[0][0], " ".join(l for _, l in cur)))
            cur.clear()

    for n, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            fence = not fence
            flush()
            continue
        s = line.strip()
        if fence or not s or s.startswith(("|", "#", "<", "![")):
            flush()
            continue
        if ITEM.match(line):
            flush()
        cur.append((n, s))
    flush()
    return out


def visible(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\]\([^)]*\)", "", s)
    return s.replace("`", "").replace("[", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default=ROOT + "/work/wiki")
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--full", action="store_true", help="print each long block whole")
    a = ap.parse_args()
    hits, heads = [], []
    for fn in sorted(os.listdir(a.wiki)):
        if fn.endswith(".md") and fn != "_Sidebar.md":
            text = open(os.path.join(a.wiki, fn), encoding="utf-8").read()
            for line in re.sub(r"(?ms)^```.*?^```", "", text).split("\n"):
                m = re.match(r"#{2,4} (.*)", line)
                words = visible(m.group(1)).split() if m else []
                if m and (len(words) > 5 or "(" in m.group(1)):
                    heads.append((fn, m.group(1)))
            hits += [(fn, n, len(visible(b)), b) for n, b in blocks(text) if len(visible(b)) > a.max]
    for fn, n, size, b in hits:
        print(f"{fn}:{n} {size}  {b if a.full else b[:90]}")
    print(f"{len(hits)} blocks over {a.max} characters")
    for fn, h in heads:
        print(f"{fn}  heading: {h}")
    print(f"{len(heads)} headings over five words or with parentheses")
    return 1 if hits or heads else 0


if __name__ == "__main__":
    sys.exit(main())
