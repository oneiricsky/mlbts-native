"""Choose the functions to theme and build their reading dossiers (step 1 of the double-read pipeline).

    python -I tools/theme_prep.py [--theme work/theme] [--window 0x7000ac0000] [--limit 40] [--exclude-gold]

A target is a `main` function that does not yet have an accepted aspect label. Selection can be narrowed to one
256 KB window, which is how a pilot is drawn. The dossiers come from tools/map_read_prep.py: it normalises each
function's generated C and adds its callers, callees, vtable slot and window theme.

Writes under the theme folder:
  targets.jsonl        one line per target: address, its window theme and the prior aspect that theme gives
  addrs.txt            the address list handed to map_read_prep
  batches/             manifest.json and batch-NNN.md, the dossiers both readers see
  reads/{a,b,c}/       where each reader's out-NNN.jsonl goes (created empty)
  state.json           what has been prepared, so a rerun skips finished work
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from wiki_completeness import aspect_of


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    ap.add_argument("--window", default="", help="only functions inside this 256 KB window, e.g. 0x7000ac0000")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--exclude-gold", action="store_true", help="skip functions whose strings already name an aspect")
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--only", default="", help="file of addresses to read, in that order (an experiment on a known set)")
    ap.add_argument("--reuse", action="store_true", help="rebuild the dossiers for the addresses already in targets.jsonl")
    a = ap.parse_args()

    os.makedirs(f"{a.theme}/reads/a", exist_ok=True)
    os.makedirs(f"{a.theme}/reads/b", exist_ok=True)
    os.makedirs(f"{a.theme}/reads/c", exist_ok=True)
    os.makedirs(f"{a.theme}/batches", exist_ok=True)
    # the readers' instructions live in the repo, so the pipeline can be rerun after work/ is wiped
    src = ROOT + "/tools/theme_prompt.md"
    if os.path.exists(src):
        open(f"{a.theme}/PROMPT.md", "w", encoding="utf-8", newline="\n").write(
            open(src, encoding="utf-8").read())

    roles = [json.loads(l) for l in open(f"{a.index}/roles.jsonl", encoding="utf-8")]
    main = [r for r in roles if r["module"] == "main"]
    accepted = {r["addr"] for r in load_jsonl(f"{a.theme}/accepted.jsonl")}
    abstained = {r["addr"] for r in load_jsonl(f"{a.theme}/abstained.jsonl")}
    done = accepted | abstained

    if a.window:
        lo = int(a.window, 16)
        main = [r for r in main if lo <= int(r["addr"], 16) < lo + 0x40000]
    main.sort(key=lambda r: int(r["addr"], 16))

    by_addr = {r["addr"].lower(): r for r in main}
    if a.only:
        # a deliberate set, including addresses an earlier run abstained on: no done-check, the file order wins
        want = [x.strip().lower() for x in open(a.only, encoding="utf-8") if x.strip() and not x.startswith("#")]
        picked = [by_addr[x] for x in want if x in by_addr]
    elif a.reuse:
        old = [r["addr"].lower() for r in load_jsonl(f"{a.theme}/targets.jsonl")]
        picked = [by_addr[x] for x in old if x in by_addr]
    else:
        # A sample with no window is drawn with a fixed stride over the address space, so it spreads across every
        # region instead of piling into the first few windows. Same stride and limit give the same sample, which is
        # what the "fixed from frame 0" habit asks of a rerun.
        stride = max(1, len(main) // a.limit) if a.limit and not a.window else 1
        picked = []
        for i, r in enumerate(main):
            if r["addr"] in done:
                continue
            if a.exclude_gold and r["tag"] == "C":
                # tag C already carries a string-proven label; the pipeline is for the functions that do not
                continue
            if stride > 1 and i % stride:
                continue
            picked.append(r)
            if len(picked) >= a.limit:
                break

    state_path = f"{a.theme}/state.json"
    state = json.load(open(state_path)) if os.path.exists(state_path) else {"batches": {}, "reads": {}}
    state["prepared_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    with open(f"{a.theme}/targets.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in picked:
            sub = r.get("sub") or ""
            f.write(json.dumps({
                "addr": r["addr"],
                "window": hex(int(r["addr"], 16) & ~0x3FFFF),
                "window_theme": sub if sub and not sub.isdigit() else "",
                "prior_aspect": aspect_of(sub) if sub and not sub.isdigit() else "",
                "strings": (r.get("strings") or [])[:8],
                "read_role": r.get("role") if r.get("read") else "",
            }) + "\n")
    with open(f"{a.theme}/addrs.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(r["addr"] for r in picked) + "\n")

    cmd = [sys.executable, "-I", ROOT + "/tools/map_read_prep.py", "--index", a.index,
           "--out", f"{a.theme}/batches", "--addrs", f"{a.theme}/addrs.txt",
           "--batch-size", str(a.batch_size), "--all"]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    man = json.load(open(f"{a.theme}/batches/manifest.json"))
    for b in man.get("batches", []):
        num = b.get("id", 0) if isinstance(b, dict) else b
        state["batches"][str(num)] = {"addrs": b.get("addrs", []) if isinstance(b, dict) else []}
    json.dump(state, open(state_path, "w", encoding="utf-8"), indent=1)
    print(f"prepared {len(picked)} targets in {len(state['batches'])} batch(es) under {a.theme}")


if __name__ == "__main__":
    main()
