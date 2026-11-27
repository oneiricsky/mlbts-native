"""Check which C/I/H tags tools/wiki_build.py raises to superscript.

    python -I tools/wiki_sup_test.py        # exit 1 on any mismatch
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wiki_build import superscript_tags

RAISED = [
    ("the same interface [C, vtables]: each", "the same interface<sup>[C, vtables]</sup>: each"),
    ("readings of the bodies [I].", "readings of the bodies<sup>[I]</sup>."),
    ("| event 0x13d [C]; uses `x` | 2 |", "| event 0x13d<sup>[C]</sup>; uses `x` | 2 |"),
    ("a time window [I], and the rest", "a time window<sup>[I]</sup>, and the rest"),
    ("the log (2026-11-26) [C, `a[0].c`] shows", "the log (2026-11-26)<sup>[C, `a[0].c`]</sup> shows"),
]
KEPT = [
    "| C, vtables | [C] |",
    "| the table | [C] strings, [I] role |",
    "[I] starts the line",
    "Tags: [C] confirmed from a measurement, [I] inferred, [H] guess.",
    "Tag meaning: **[C]** a string or code read proves it.",
    "Most meanings below are [I].",
    "Treat roles tagged [I] or [H] as leads.",
    "see [C](Functions-C) and `x [C]` in code",
    "```\nlog [C]\n```",
]

bad = [(s, want, superscript_tags(s)) for s, want in RAISED + [(k, k) for k in KEPT] if superscript_tags(s) != want]
for s, want, got in bad:
    print(f"FAIL {s!r}\n  want {want!r}\n  got  {got!r}")
print(f"{len(RAISED) + len(KEPT) - len(bad)} of {len(RAISED) + len(KEPT)} cases pass")
sys.exit(1 if bad else 0)
