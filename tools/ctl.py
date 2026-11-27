"""Asks a running dev-build game questions through its control channel (runtime/mlb/ctl.c), so nothing is relaunched.

  python -I tools/ctl.py DIR [--map work/build/mlb.map] [--wait SECONDS] COMMAND...
  python -I tools/ctl.py DIR "dump 7000a00000 8" "watch 1234560 10 30000"      (several commands, one per argument)
  python -I tools/ctl.py DIR --read                                            (print out.txt so far, no command)

Start the game with MLB_CTL=DIR (DIR must exist), e.g.
  python -I tools/game.py run <slot> --detach --timeout 3000 --env MLB_CTL=D:/x/ctl
The commands are listed at the top of runtime/mlb/ctl.c. Chains in `hit` lines are module offsets; with --map they get the
name of the nearest generated function, so f_7000ad07e0+0x44 reads as an address you can look up with tools/disasm.py.
"""
import os
import re
import sys
import time


def load_map(path):
    syms = []
    rx = re.compile(r"\s*[0-9a-f]{4}:[0-9a-f]{8}\s+(\S+)\s+([0-9a-f]{16})\s")
    for line in open(path, errors="replace"):
        m = rx.match(line)
        if m:
            syms.append((int(m.group(2), 16) - 0x140000000, m.group(1)))
    syms.sort()
    return syms


def name(syms, rva):
    lo, hi = 0, len(syms)
    while lo < hi:
        mid = (lo + hi) // 2
        if syms[mid][0] <= rva:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return "%x" % rva
    s = syms[lo - 1]
    return "%s+0x%x" % (s[1], rva - s[0])


def annotate(text, syms):
    out = []
    for ln in text.splitlines():
        if syms and " chain:" in ln:
            head, chain = ln.split(" chain:", 1)
            ln = head + " chain:\n    " + "\n    ".join(name(syms, int(x, 16)) for x in chain.split())
        out.append(ln)
    return "\n".join(out)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    d = a.pop(0)
    opts = {"--map": "work/build/mlb.map", "--wait": "60"}
    for k in opts:
        if k in a:
            i = a.index(k)
            opts[k] = a[i + 1]
            del a[i:i + 2]
    read_only = "--read" in a
    if read_only:
        a.remove("--read")
    outp = os.path.join(d, "out.txt")
    size = os.path.getsize(outp) if os.path.exists(outp) else 0
    if read_only:
        size = 0
    else:
        donep = os.path.join(d, "done.txt")
        before = open(donep).read() if os.path.exists(donep) else ""
        tmp = os.path.join(d, "cmd.tmp")
        open(tmp, "w", newline="\n").write("\n".join(a) + "\n")
        os.replace(tmp, os.path.join(d, "cmd.txt"))
        end = time.time() + float(opts["--wait"])
        while time.time() < end:
            time.sleep(0.1)
            if os.path.exists(donep) and open(donep).read() != before:
                break
        else:
            sys.exit("no answer in %s s (is the game running with MLB_CTL=%s?)" % (opts["--wait"], d))
    data = open(outp, errors="replace").read().encode("latin1", "replace")[size:].decode("latin1")
    syms = load_map(opts["--map"]) if os.path.exists(opts["--map"]) else []
    print(annotate(data, syms))


main()
