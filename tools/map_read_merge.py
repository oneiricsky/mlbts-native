"""Collect the answers of the body-reading batches into one overlay for the function map.

    python -I tools/map_read_merge.py [--read work/map/read [work/map/read-sdk ...]]
                                      [--out work/map/index/roles_read.jsonl] [--check-quotes]

Each batch agent writes `out-<id>.jsonl`, one line per function:
    {"addr":"0x7000000350","role":"...","tag":"I","evidence":"..."}
This tool validates every line (known address, tag in C/I/H, non-empty role and evidence, valid JSON), reports
coverage against the run's target list (work/map/read/<run>/targets.txt, else the manifest), and writes the overlay.
`tools/map_roles.py` applies the overlay when it rebuilds work/map/index/roles.jsonl, so the wiki and the census see
the read roles.

More than one --read directory is merged into the same overlay: the completeness pass reads `main` and `sdk` into
separate runs so each keeps its own target list and batch numbering. An answer is accepted only for an address on
its own run's target list, so a stray line cannot claim a function of another run.

--check-quotes machine-checks the reading: every double-quoted fragment in a role or its evidence has to appear in
that function's dossier (its own `strings:` line, a `class:` line, the ops, a callee role). A reader that invents a
string is reported with its address, so the claim can be re-read instead of trusted. Quote mismatches are reported
but do not fail the merge (an older batch paraphrased a few); rejected lines (bad JSON, an address outside the run's
target list, an empty field) do, with exit code 1.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
ADDR = re.compile(r"^0x[0-9a-f]{9,12}$")
HEAD = re.compile(r"(?m)^## (0x[0-9a-f]+) ")
QUOTED = re.compile(r'"([^"\n]{3,120})"')


def unescape(s):
    """A dossier prints its strings JSON-escaped ("C:\\\\dir"), a reader quotes them as printed in the game
    ("C:\\dir"). Compare one form: fold double backslashes, as both sides then name the same literal."""
    return s.replace("\\\\", "\\").lower()


def flat(s):
    """Quotes are compared with whitespace folded: a banner string prints with runs of spaces that a reader
    reproduces as one, which is the same text and not an invented one."""
    return unescape(" ".join(s.split()))


def targets_of(read):
    """The run's target addresses: the dossier headings, plus targets.txt and manifest batches (a slice's run may
    have both). The dossier headings are the assignments themselves, so a run whose target list was written by an
    earlier slice still validates every function it asked a reader to read."""
    target = set()
    tpath = f"{read}/targets.txt"
    if os.path.exists(tpath):
        target |= {x.strip().lower() for x in open(tpath, encoding="utf-8") if x.strip()}
    for name in sorted(os.listdir(read)):
        if not re.match(r"^batch-\d+\.md$", name):
            continue
        for m in HEAD.finditer(open(f"{read}/{name}", encoding="utf-8", errors="replace").read()):
            target.add(m.group(1))
    man_path = f"{read}/manifest.json"
    if os.path.exists(man_path):
        man = json.load(open(man_path))
        for b in man["batches"]:
            target.update(b["addrs"])
    return target


def dossier_blocks(read):
    """addr -> the dossier text of that function, for the quote check."""
    blocks = {}
    for name in sorted(os.listdir(read)):
        if not re.match(r"^batch-\d+\.md$", name):
            continue
        text = open(f"{read}/{name}", encoding="utf-8", errors="replace").read()
        heads = list(HEAD.finditer(text))
        for m, after in zip(heads, [h.start() for h in heads[1:]] + [len(text)]):
            blocks[m.group(1)] = text[m.start():after]
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read", nargs="+", default=[ROOT + "/work/map/read"])
    ap.add_argument("--out", default=ROOT + "/work/map/index/roles_read.jsonl")
    ap.add_argument("--check-quotes", action="store_true",
                    help="report quoted strings that the function's dossier does not contain")
    ap.add_argument("--fresh", action="store_true",
                    help="start from nothing instead of keeping rows already in the overlay (the overlay only grows)")
    a = ap.parse_args()

    got, bad = {}, []
    if not a.fresh and os.path.exists(a.out):
        # the overlay is the record of every body read so far. A run directory can be cleaned up or a dossier
        # regenerated without un-reading the functions it answered, so keep those rows and let today's answers win.
        for line in open(a.out, encoding="utf-8"):
            if line.strip():
                o = json.loads(line)
                got[o["addr"]] = o
        base_rows = len(got)
    else:
        base_rows = 0
    summary, quotes_all = [], []
    for read in a.read:
        target = targets_of(read)
        blocks = dossier_blocks(read) if a.check_quotes else {}
        quotes_bad, files, per_dir = [], [], {}
        for path in sorted(os.listdir(read)):
            if not re.match(r"^out-.*\.jsonl$", path):
                continue
            files.append(path)
            for ln, line in enumerate(open(f"{read}/{path}", encoding="utf-8"), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    # a reader occasionally writes "address": accept it, the overlay always stores "addr"
                    addr = str(r.get("addr") or r.get("address") or "").lower()
                    tag = str(r["tag"]).strip().upper()[:1]
                    role = " ".join(str(r["role"]).split())
                    ev = " ".join(str(r["evidence"]).split())
                except Exception as e:  # noqa: BLE001 - report the line, keep going
                    bad.append((f"{read}/{path}:{ln}", f"unreadable line: {e}"))
                    continue
                if not ADDR.match(addr) or addr not in target:
                    bad.append((f"{read}/{path}:{ln}", f"address {addr} is not one of this run's unread functions"))
                    continue
                if tag not in ("C", "I", "H") or not role or not ev:
                    bad.append((f"{read}/{path}:{ln}", f"bad tag/role/evidence: {tag!r} {role!r} {ev!r}"))
                    continue
                per_dir[addr] = 1
                if a.check_quotes:
                    block = flat(blocks.get(addr) or "")
                    missing = [q for q in QUOTED.findall(role + " " + ev) if flat(q) not in block]
                    if missing:
                        quotes_bad.append((addr, missing))
                got[addr] = dict(addr=addr, role=role[:160], tag=tag, evidence=ev[:160], batch=path[4:-6])
        missing = sorted(target - set(per_dir), key=lambda x: int(x, 16))
        open(f"{read}/missing.txt", "w", newline="\n").write("\n".join(missing) + ("\n" if missing else ""))
        summary.append((read, len(files), len(per_dir), len(target), len(missing)))
        quotes_all += [(read, addr, qs) for addr, qs in quotes_bad]
        if quotes_bad:
            print(f"{read}: {len(quotes_bad)} rows quote text their dossier does not contain; first:")
            for addr, qs in quotes_bad[:8]:
                print(f"  {addr}: {', '.join(repr(q) for q in qs[:3])}")

    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        for addr in sorted(got):
            fh.write(json.dumps(got[addr], ensure_ascii=False, separators=(",", ":")) + "\n")
    for read, nfiles, nread, ntarget, nmissing in summary:
        print(f"{read}: answer files {nfiles}; functions read {nread} of {ntarget} "
              f"({100 * nread / max(1, ntarget):.1f}%); missing {nmissing}")
    print(f"overlay: {a.out} ({len(got):,} functions; {base_rows:,} carried over)")
    if bad:
        print(f"rejected lines: {len(bad)}; first few: {bad[:6]}")
    if quotes_all:
        print(f"quote mismatches: {len(quotes_all)} rows in {len({q[0] for q in quotes_all})} run(s)")
    print(f"exit: {'rejected' if bad else 'clean'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
