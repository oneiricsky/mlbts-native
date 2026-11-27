"""Apply a re-theming pass to the accepted labels.

    python -I tools/theme_retheme.py [--theme work/theme] [--dry-run]

Reads `retheme.jsonl` (written by the re-theming agent) and, for each row:

  * `to: Shared engine code`  the accepted row's aspect changes, the old aspect is kept as `old_aspect`, and the
    reason is recorded;
  * `to: Library code`        the row leaves accepted.jsonl and is appended to library.jsonl, because a library
    function has no aspect of the game.

The applied rows are appended to `retheme-applied.jsonl`, so a rerun does not re-apply them. `--dry-run` prints the
changes without writing.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")


def load(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def dump(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=ROOT + "/work/theme")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    accepted = load(f"{a.theme}/accepted.jsonl")
    proposals = load(f"{a.theme}/retheme.jsonl")
    library = load(f"{a.theme}/library.jsonl")
    applied = {(r.get("addr"), r.get("to")) for r in load(f"{a.theme}/retheme-applied.jsonl")}

    by_addr = {r["addr"]: r for r in accepted}
    lib_addrs = {r["addr"] for r in library}
    changed, moved, log = 0, 0, []
    for p in proposals:
        addr, to = p.get("addr"), p.get("to")
        if not addr or to not in ("Shared engine code", "Library code"):
            print(f"skip malformed proposal: {p}")
            continue
        if (addr, to) in applied:
            continue
        row = by_addr.get(addr)
        if not row:
            print(f"skip {addr}: not in accepted.jsonl")
            continue
        if to == "Shared engine code":
            if row.get("aspect") == to:
                continue
            log.append({"addr": addr, "from": row.get("aspect"), "to": to, "reason": p.get("reason", "")})
            row["old_aspect"] = row.get("aspect")
            row["aspect"] = to
            row["retheme"] = p.get("reason", "")
            changed += 1
        else:
            if addr in lib_addrs:
                continue
            log.append({"addr": addr, "from": row.get("aspect"), "to": to, "reason": p.get("reason", "")})
            library.append({"addr": addr, "reason": p.get("reason", ""), "role": ""})
            lib_addrs.add(addr)
            accepted.remove(row)
            moved += 1

    if a.dry_run:
        print(f"would retheme {changed}, move to library {moved}")
        for r in log:
            print(" ", r["addr"], r["from"], "->", r["to"], "|", r["reason"][:80])
        return
    dump(f"{a.theme}/accepted.jsonl", accepted)
    dump(f"{a.theme}/library.jsonl", library)
    with open(f"{a.theme}/retheme-applied.jsonl", "a", encoding="utf-8", newline="\n") as f:
        for r in log:
            f.write(json.dumps(r) + "\n")
    print(f"rethemed {changed} to Shared engine code, moved {moved} to library code; "
          f"accepted now {len(accepted)}")


if __name__ == "__main__":
    main()
