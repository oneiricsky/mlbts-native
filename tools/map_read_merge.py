"""Collect the answers of the body-reading batches into one overlay for the function map.

    python -I tools/map_read_merge.py [--read work/map/read] [--out work/map/read/roles_read.jsonl]

Each batch agent writes `out-<id>.jsonl`, one line per function:
    {"addr":"0x7000000350","role":"...","tag":"I","evidence":"..."}
This tool validates every line (known address, tag in C/I/H, non-empty role and evidence, valid JSON), reports
coverage against work/map/read/manifest.json, and writes the overlay. `tools/map_roles.py` applies the overlay when
it rebuilds work/map/index/roles.jsonl, so the wiki and the census see the read roles.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
ADDR = re.compile(r"^0x[0-9a-f]{9,12}$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read", default=ROOT + "/work/map/read")
    ap.add_argument("--out", default=ROOT + "/work/map/index/roles_read.jsonl")
    a = ap.parse_args()
    man = json.load(open(f"{a.read}/manifest.json"))
    # the target set is every address in the manifest, whatever batch layout produced it; an answer is accepted by
    # address, so a batch split into parts (out-5-a.jsonl, out-5-b.jsonl) and an older batching both merge fine
    target = set()
    for b in man["batches"]:
        target.update(b["addrs"])
    tpath = f"{a.read}/targets.txt"
    if os.path.exists(tpath):
        target = {x.strip() for x in open(tpath, encoding="utf-8") if x.strip()} or target
    got, bad, files = {}, [], []
    for path in sorted(os.listdir(a.read)):
        if not re.match(r"^out-.*\.jsonl$", path):
            continue
        files.append(path)
        for ln, line in enumerate(open(f"{a.read}/{path}", encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                addr = str(r["addr"]).lower()
                tag = str(r["tag"]).strip().upper()[:1]
                role = " ".join(str(r["role"]).split())
                ev = " ".join(str(r["evidence"]).split())
            except Exception as e:  # noqa: BLE001 - report the line, keep going
                bad.append((f"{path}:{ln}", f"unreadable line: {e}"))
                continue
            if not ADDR.match(addr) or addr not in target:
                bad.append((f"{path}:{ln}", f"address {addr} is not one of the unread functions"))
                continue
            if tag not in ("C", "I", "H") or not role or not ev:
                bad.append((f"{path}:{ln}", f"bad tag/role/evidence: {tag!r} {role!r} {ev!r}"))
                continue
            got[addr] = dict(addr=addr, role=role[:160], tag=tag, evidence=ev[:160], batch=path[4:-6])
    missing = sorted(target - set(got), key=lambda x: int(x, 16))
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        for addr in sorted(got):
            fh.write(json.dumps(got[addr], ensure_ascii=False, separators=(",", ":")) + "\n")
    open(f"{a.read}/missing.txt", "w", newline="\n").write("\n".join(missing) + ("\n" if missing else ""))
    print(f"answer files: {len(files)}")
    print(f"functions read: {len(got)} of {len(target)} ({100 * len(got) / max(1, len(target)):.1f}%)")
    if missing:
        print(f"missing: {len(missing)} addresses, written to {a.read}/missing.txt (first {missing[:5]})")
    if bad:
        print(f"rejected lines: {len(bad)}; first few: {bad[:6]}")
    print(f"overlay: {a.out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
