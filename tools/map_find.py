"""Look things up in the local function map (work/map/index, built by tools/map_all.py).

    python -I tools/map_find.py fn 0x7000e54c00        # one game function: size, callers, callees, strings, vtables, neighbours
    python -I tools/map_find.py str "MSDF took"        # game functions that reference a string (substring, case-insensitive)
    python -I tools/map_find.py near 0x700108b628 [N]  # N (default 6) functions each side that reference strings
    python -I tools/map_find.py region 0x7001000000    # what the code around an address is about (string themes)
    python -I tools/map_find.py src mlb_hd_load        # a source function of this repo (file, lines, callees)
    python -I tools/map_find.py callers 0x70005a1a90   # who calls a game function (direct calls only)
    python -I tools/map_find.py name nvnQueue          # SDK/libc symbols by name (demangled substring)
    python -I tools/map_find.py role 0x700108b628      # the complete map's row (tools/map_roles.py), or role text

Game addresses are 1.0.20's (`f_<addr>` in work/gen). Everything here is read-only. The data is derived from game
code and lives under work/ (git-ignored): rebuild it with `python -I tools/map_all.py`.
"""
import json, os, re, sys, bisect
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
IDX = ROOT + "/work/map/index"
_cache = {}


def rows(name):
    if name not in _cache:
        p = f"{IDX}/{name}.jsonl"
        if not os.path.exists(p):
            sys.exit(f"missing {p}: run python -I tools/map_all.py first")
        _cache[name] = [json.loads(l) for l in open(p, encoding="utf-8")]
    return _cache[name]


def gen():
    if "gen_by" not in _cache:
        _cache["gen_by"] = {r["addr"]: r for r in rows("generated_functions")}
        _cache["gen_sorted"] = sorted(int(a, 16) for a in _cache["gen_by"])
    return _cache["gen_by"], _cache["gen_sorted"]


def strs():
    if "str_by" not in _cache:
        _cache["str_by"] = {r["addr"]: r["strings"] for r in rows("function_strings")}
    return _cache["str_by"]


def names():
    if "nm" not in _cache:
        _cache["nm"] = {r["addr"]: r for r in rows("binary_names")}
    return _cache["nm"]


def norm(a):
    return hex(int(a, 16))


def label(a):
    g, _ = gen()
    f = g.get(a)
    n = names().get(a)
    s = strs().get(a, [])
    return (f"{a} {f['lines']}L {f['callers']} callers" if f else a) + (f"  [{n['demangled'][:60]}]" if n else "") + \
        (f"  {[x[:48] for x in s[:2]]}" if s else "")


def cmd_fn(a):
    a = norm(a)
    g, srt = gen()
    f = g.get(a)
    if not f:
        sys.exit("no generated function at " + a + " (is it a function entry? try: near / region)")
    print(f"{a}  module={f['module']}  {f['file']}:{f['line']}  {f['lines']} generated lines")
    print(f"callers={f['callers']}  direct callees={len(f['calls'])}  indirect branches (rt_dispatch)={f['dispatch']}"
          f"  trap sites={f['udf']}")
    n = names().get(a)
    if n:
        print("symbol:", n["demangled"])
    for s in strs().get(a, []):
        print("  string:", s[:140])
    for v in rows("vtables"):
        if a in v["functions"]:
            print(f"  in vtable {v['vtable']} slot {v['functions'].index(a)} of {v['size']}")
    print("callees:")
    for c in f["calls"][:25]:
        print("  ", label(c))
    print("neighbours with strings:")
    cmd_near(a, 3, quiet=True)


def cmd_str(t):
    t = t.lower()
    hits = [(r["addr"], s) for r in rows("function_strings") for s in r["strings"] if t in s.lower()]
    for a, s in hits[:60]:
        print(label(a), "<-", s[:100])
    print(len(hits), "matches")


def cmd_near(a, n=6, quiet=False):
    a = norm(a)
    g, srt = gen()
    i = bisect.bisect_left(srt, int(a, 16))
    s = strs()
    for rng in (range(i - 1, -1, -1), range(i + 1, len(srt))):
        out = []
        for k in rng:
            x = hex(srt[k])
            if x in s:
                out.append(x)
                if len(out) >= n:
                    break
        for x in (reversed(out) if rng.step < 0 else out):
            print("  ", label(x))
        if rng.step < 0:
            print("   ---", a, "---")


def cmd_region(a):
    lo = int(a, 16) & ~0x3FFFF
    hi = lo + 0x40000
    stop = set("the and for with not failed error invalid assertion index could from this that have size null value type name file line state data into when game vector".split())
    c, n = Counter(), 0
    for r in rows("function_strings"):
        v = int(r["addr"], 16)
        if lo <= v < hi:
            n += 1
            for s in r["strings"]:
                for t in re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", s):
                    if t.lower() not in stop:
                        c[t] += 1
    g, srt = gen()
    nf = bisect.bisect_left(srt, hi) - bisect.bisect_left(srt, lo)
    print(f"{hex(lo)}-{hex(hi)}: {nf} functions, {n} reference strings")
    print("themes:", ", ".join(f"{t}({k})" for t, k in c.most_common(25)))


def cmd_src(name):
    hits = [r for r in rows("source_functions") if name.lower() in r["name"].lower()]
    for r in hits[:40]:
        print(f"{r['file']}:{r['line']}-{r['end']}  {r['name']}  {r['signature'][:70]}  calls: {', '.join(r['calls'][:8])}")
    print(len(hits), "matches")


def cmd_callers(a):
    a = norm(a)
    g, _ = gen()
    cs = [x for x, f in g.items() if a in f["calls"]]
    for x in cs[:60]:
        print(label(x))
    print(len(cs), "direct callers")


def cmd_name(t):
    t = t.lower()
    hits = [n for n in names().values() if t in n["demangled"].lower()]
    for n in hits[:60]:
        print(n["module"], n["addr"], n["size"], n["demangled"][:100])
    print(len(hits), "matches")


def cmd_role(arg):
    """The complete map's row for one function, or the functions whose role mentions a word."""
    if arg.lower().startswith("0x"):
        a = norm(arg)
        hit = [r for r in rows("roles") if r["addr"] == a]
        if not hit:
            sys.exit(f"no role row for {a}: run python -I tools/map_roles.py")
        r = hit[0]
        print(f"{r['addr']}  {r['module']}  {r['span']} bytes  {r['lines']} generated lines  shape={r['shape']}")
        print(f"kind={r['kind']} tag={r['tag']}  role: {r['role']}")
        print(f"basis: {r['basis']}  callers={r['callers']}  callees={r['ncallees']}")
        if r["apis"]:
            print("calls:", ", ".join(r["apis"]))
        if r["vtable"]:
            print(f"vtable {r['vtable']} slot {r['slot']} of {r['vtable_size']}")
        if r["sub"]:
            print("window:", r["sub"])
        for s in r["strings"]:
            print("  string:", s[:120])
        return
    t = arg.lower()
    hits = [r for r in rows("roles") if t in r["role"].lower()]
    for r in hits[:60]:
        print(f"{r['addr']} {r['module']:4} {r['tag']} {r['span']:5} {r['callers']:5}  {r['role'][:90]}")
    print(len(hits), "matches")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    c, arg = sys.argv[1], sys.argv[2]
    if c == "fn": cmd_fn(arg)
    elif c == "str": cmd_str(arg)
    elif c == "near": cmd_near(arg, int(sys.argv[3]) if len(sys.argv) > 3 else 6)
    elif c == "region": cmd_region(arg)
    elif c == "src": cmd_src(arg)
    elif c == "callers": cmd_callers(arg)
    elif c == "name": cmd_name(arg)
    elif c == "role": cmd_role(arg)
    else: sys.exit(__doc__)


if __name__ == "__main__":
    main()
