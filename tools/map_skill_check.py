"""Check that the addresses the mlbts-game-code skill cites exist in the local function map.

    python -I tools/map_skill_check.py        # exit 1 if a cited 1.0.20 function address is not a function entry

Reads .claude/skills/mlbts-game-code/**/*.md. Skips lines that mark an address as 1.0.15 (or "slot", "inside a function"),
and addresses in data (>= 0x7002000000). A cited address must be a generated function entry or a vtable. Needs work/map/index.
"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
IDX = ROOT + "/work/map/index"
entries = {json.loads(l)["addr"] for l in open(IDX + "/generated_functions.jsonl")}
vtables = {json.loads(l)["vtable"] for l in open(IDX + "/vtables.jsonl")}
bad, total = [], 0
for p in sorted(glob.glob(ROOT + "/.claude/skills/mlbts-game-code/**/*.md", recursive=True)):
    for n, line in enumerate(open(p, encoding="utf-8"), 1):
        if any(k in line for k in ("1.0.15", "slot `", "inside a function", "map_find.py", "strdump.py", "region 0x", "near 0x", "`-`",
                                   "Home Run Derby has its own")):
            continue
        for m in re.finditer(r"0x(7[0-9a-f]{9})\b", line):
            a = "0x" + m.group(1)
            total += 1
            if int(a, 16) >= 0x7002000000:
                continue
            tail = line[m.end():m.end() + 3]
            if line[m.start() - 1:m.start()] == "-" or tail.startswith("`-`") or "`-`" in line[m.end():m.end() + 4]:
                continue
            if a not in entries and a not in vtables:
                bad.append(f"{os.path.basename(p)}:{n} {a}")
print(f"{total} cited addresses checked, {len(bad)} not function entries")
for b in bad:
    print("  ", b)
sys.exit(1 if bad else 0)
