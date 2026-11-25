"""Prepare batches of unread game functions for body reading, with the generated C normalised to a compact form.

    python -I tools/map_read_prep.py [--index work/map/index] [--gen work/gen] [--out work/map/read]
                                     [--batch-size 150] [--max-ir 12] [--only main|sdk] [--limit N]

The 47,000 functions that have no string, symbol or simple shape are the ones left to read. Their generated C is
~4.4 M lines: too much to hand to a subagent whole. This tool streams the generated C once, strips the recompiler's
prologue/epilogue and register shuffling, and rewrites the interesting operations (calls, loads, stores, comparisons,
branches) in a compact pseudo-code. Each function also gets its callers, callees and their known roles, its vtable
slot and its window's subsystem.

Writes work/map/read/manifest.json plus batch-<n>.md dossiers. Reading them is a separate step (tools/map_read_merge.py
collects the answers). Derived from game code: stays under work/.
"""
import argparse, json, os, re, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
DEF = re.compile(r"^void f_([0-9a-f]+)\(Cpu \*c\) \{")

# recompiler boilerplate: prologue, register save/restore, epilogue
DROP = re.compile(r"^(FN_ENTER|uint64_t x0 = c->x|uint64_t FPCR|Flags F|vreg VB|/\* hint \*/|sp_ = \(uint64_t\)\(sp_ -"
                  r"|uint64_t sp_ = c->sp)")
DROP_TAIL = re.compile(r"c->x\[[0-9]+\] = .*; return;$")
DROP_UDF = re.compile(r"rt_udf\(c,")
LD1 = re.compile(r"\{ uint64_t ea = ([^;]+); uint64_t v = (LD[A-Z0-9]*)\(ea\); (\w+) = \(uint64_t\)\(v\); \}")
LD2 = re.compile(r"\{ uint64_t ea = ([^;]+); uint64_t a = LD(\d+)\(ea\), b = LD\d+\(ea \+ 8\); (\w+) = \(uint64_t\)\(a\);"
                 r" (\w+) = \(uint64_t\)\(b\); \}")
ST = re.compile(r"\{ uint64_t ea = ([^;]+); (ST\d+)\(ea, ([^)]+)\); \}")
CALL = re.compile(r"\bf_([0-9a-f]+)\(c\)")
TAIL = re.compile(r"musttail\)\) return f_([0-9a-f]+)\(c\);")
SP = re.compile(r"\{ uint64_t ea = ([^;]+); (ST64|LD64)\(ea, (x\d+)\); \}")
SP2 = re.compile(r"\{ uint64_t ea = ([^;]+); (ST64|LD64)\(ea, (x\d+)\); (ST64|LD64)\(ea \+ 8, (x\d+)\); \}")


def norm(s):
    """Generated-C text to plain op text: no c->, no casts, no declarations, short register names."""
    s = s.strip()
    s = re.sub(r"c->x\[(\d+)\]", r"x\1", s)
    s = s.replace("c->sp", "sp").replace("sp_", "sp").replace("c->fpcr", "fpcr").replace("c->nzcv", "nzcv")
    s = re.sub(r"\((?:uint|int)(?:8|16|32|64)_t\)|\(vreg \*\)", "", s)
    s = re.sub(r"\b(?:u?int(?:8|16|32|64)_t|vreg|Flags)\b", "", s)
    s = s.replace("ull", "").replace("c->", "")
    # decimal offsets become hex, so one set of patterns covers both
    s = re.sub(r"([+-]) (\d+)\b", lambda m: f"{m.group(1)} {hex(int(m.group(2)))}", s)
    return re.sub(r"\s+", " ", s).strip()


def mem_ops(s):
    """Memory operations inside one generated-C statement block, with the effective address."""
    out, ea = [], None
    body = s.strip()
    if body.startswith("{"):
        body = body[1:]
    if body.endswith("}"):
        body = body[:-1]
    for part in (p.strip() for p in body.split(";")):
        if not part:
            continue
        m = re.match(r"^(?:ea = )(.+)$", part)
        if m and "=" in part and not part.startswith(("x", "v ", "a ", "b ")):
            ea = m.group(1)
            continue
        m = re.match(r"^(?:\w+ )?v = (LD[A-Z0-9]*)\(ea\)$", part)
        if m:
            out.append(("load", m.group(1), ea))
            continue
        m = re.match(r"^(?:\w+ )?a = (LD\d+)\(ea\), b = (LD\d+)\(ea \+ (?:0x)?[0-9a-f]+\)$", part)
        if m:
            out.append(("load2", m.group(1), ea))
            continue
        m = re.match(r"^(ST\d+)\(ea( [+-] 0x[0-9a-f]+| [+-] \d+)?, (.+)\)$", part)
        if m:
            if ea is None:
                out.append(("text", part))
                continue
            addr = ea + (m.group(2) or "")
            out.append(("store", m.group(1), addr, m.group(3)))
            continue
        m = re.match(r"^(\w+) = \(?v\)?$", part)
        if m and out and out[-1][0] == "load":
            kind, width, addr = out.pop()
            out.append(("load-into", m.group(1), width, addr))
            continue
        m = re.match(r"^(\w+) = \(?(a|b)\)?$", part)
        if m and out and out[-1][0] == "load2":
            kind, width, addr = out.pop()
            out.append(("load2a", m.group(1), width, addr))
            continue
        if m and m.group(2) == "b" and out and out[-1][0] == "load2a":
            kind, reg_a, width, addr = out.pop()
            out.append(("load2-into", f"{reg_a},{m.group(1)}", width, addr))
            continue
        if re.match(r"^(?:sp|ea|x\d+) = (?:x\d+|sp|ea)(?: [+-] 0x[0-9a-f]+)?$", part):
            continue
        if re.match(r"^sp = ea [+-] 0x[0-9a-f]+$", part):
            continue
        out.append(("text", part))
    return out


def compact(line, self_addr=None):
    """One generated-C line to a short operation, or None to drop it."""
    s = line.strip()
    if not s or DROP.match(s) or DROP_UDF.search(s) or s in ("}", "{") or s.startswith("void f_"):
        return None
    if s.startswith(("uint64_t x0 = c->x", "uint64_t FPCR", "Flags F", "vreg VB", "/* hint */")) or \
            "sp_ = (uint64_t)(sp_ -" in s or s.startswith("sp_ = (uint64_t)(sp_ +") or \
            re.match(r"^uint64_t [a-z0-9_]+ = [a-z0-9_]+(, [a-z0-9_]+ = [a-z0-9_]+)*;?$", s):
        return None
    m = TAIL.search(s)
    if m:
        return f"tail f_{m.group(1)}"
    m = CALL.search(s)
    if m:
        # the call line also shuffles argument registers; record only the call and any constant arguments
        args = re.findall(r"c->x\[(\d+)\] = (?:\(uint\d+_t\)\()?(0x[0-9a-f]+|0)", s)
        argc = " " + " ".join(f"x{n}={v}" for n, v in args[:3]) if args else ""
        return f"call f_{m.group(1)}{argc}"
    if "rt_udf(" in s:
        return None
    ops = mem_ops(norm(s))
    if ops and all(op[0] != "text" for op in ops):
        got = []
        for op in ops:
            if op[0] == "load-into":
                if op[3].startswith("sp") and op[1] in ("x29", "x30"):
                    continue
                got.append(f"{op[1]} = {op[2]}[{op[3]}]")
            elif op[0] == "load2-into":
                if op[3].startswith("sp") and op[1] in ("x29", "x30"):
                    continue
                got.append(f"{op[1]} = {op[2]}[{op[3]}]")
            elif op[0] == "store":
                if op[2].startswith("sp") and op[3].strip() in ("x29", "x30"):
                    continue
                got.append(f"{op[1]}[{op[2]}] = {op[3]}")
        if got:
            return " | ".join(got)
        return None
    c = norm(s)
    if not c:
        return None
    c = re.sub(r"\((0x[0-9a-f]+|x\d+|sp)((?: [+-] 0x[0-9a-f]+)?)\)", r"\1\2", c)
    c = re.sub(r"\(0 \| (x\d+)\)", r"\1", c)
    c = re.sub(r"\((x\d+ [+-] 0x[0-9a-f]+)\)", r"\1", c)
    c = c.rstrip(";")
    # pure register shuffling carries no meaning: x8 = x0, x19 = 0x700227d000, sp = sp + 0x30
    if re.match(r"^x\d+ = (?:x\d+|sp)$", c):
        return None
    if re.match(r"^x\d+ = sp(?: [+-] 0x[0-9a-f]+)?$", c):
        return None
    if re.fullmatch(r"(?:x\d+ = x\d+;? ?)+(?:return;?)?", c):
        return None
    if re.fullmatch(r"x\d+ = x\d+;? return;?", c):
        return None
    if c in ("return", "return;", "nzcv = fnz_nz", "nzcv = nzcv"):
        return None
    if re.match(r"^sp = sp [+-] 0x[0-9a-f]+$", c):
        return None
    if re.match(r"^x\d+ = 0x700[0-9a-f]+$", c):
        return None
    m = re.match(r"^x\d+ = (0x[0-9a-f]+)$", c)
    if m and int(m.group(1), 16) > 0xffff:
        return None
    if re.fullmatch(r"(?:x\d+ = x\d+(?:, )?)+", c):
        return None
    if c in ("return;", "nzcv = fnz_nz", "nzcv = nzcv"):
        return None
    return c[:150]


def read_ir(gen, funcs, starts_by_file, max_ir):
    """One streaming pass: compact IR per function, capped to max_ir with the middle summarised.

    A function's body ends at the next function's first line, so the parser needs every function's start line in the
    file, not only the selected ones. With a subset (`--addrs`, a cross-window sample) the file otherwise runs on into
    the next function and the entry shows another function's tail.
    """
    want_by_file = defaultdict(dict)
    for f in funcs:
        want_by_file[f["file"]][f["line"]] = f["addr"]
    out = {}
    for path, want in want_by_file.items():
        starts = starts_by_file[path]
        cur, acc = None, None
        with open(f"{gen}/{path}", encoding="utf-8", errors="replace") as fh:
            for ln, line in enumerate(fh, 1):
                if ln in starts:
                    if cur is not None:
                        out[cur] = acc
                        cur, acc = None, None
                    if ln in want:
                        cur, acc = want[ln], []
                    continue
                if acc is None:
                    continue
                c = compact(line)
                if c:
                    acc.append(c)
        if cur is not None:
            out[cur] = acc
    # cap: keep the head and the tail, count what is dropped
    capped = {}
    for a, ops in out.items():
        if len(ops) <= max_ir:
            capped[a] = ops
        else:
            head = ops[: max(4, max_ir - 4)]
            tail = ops[-4:]
            capped[a] = head + [f"... {len(ops) - len(head) - 4} more ops ..."] + tail
    return capped


def role_of(rows_by, addr, depth=0):
    r = rows_by.get(addr)
    if not r:
        return ""
    if r.get("name"):
        return r["name"]
    if r["kind"] == "game":
        return r["role"][:48]
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    ap.add_argument("--out", default=ROOT + "/work/map/read")
    ap.add_argument("--batch-size", type=int, default=150)
    ap.add_argument("--max-ir", type=int, default=12)
    ap.add_argument("--only", default="main")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--addrs", default="", help="file of addresses to batch (a rerun of missing.txt)")
    ap.add_argument("--start", type=int, default=0, help="skip this many batches (resume)")
    ap.add_argument("--all", action="store_true", help="every function of the module, not only tag H")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(f"{a.index}/roles.jsonl", encoding="utf-8")]
    rows_by = {r["addr"]: r for r in rows}
    gen_funcs = {r["addr"]: r for r in (json.loads(l) for l in open(f"{a.index}/generated_functions.jsonl",
                                                                     encoding="utf-8"))}
    # reverse call map, so a function's callers can be shown with their roles
    callers = defaultdict(list)
    for r in rows:
        g = gen_funcs[r["addr"]]
        for c in g["calls"]:
            callers[c].append(r["addr"])
    # every function's first line per generated file, so a body ends where the next function begins
    starts_by_file = defaultdict(dict)
    for g in gen_funcs.values():
        starts_by_file[g["file"]][g["line"]] = g["addr"]

    todo = [r for r in rows if (a.all or r["tag"] == "H")
            and (a.only == "all" or r["module"] == a.only)]
    os.makedirs(a.out, exist_ok=True)
    # the stable target list for the whole pass: merge validates answers against it across reruns
    tpath = a.out + "/targets.txt"
    if not os.path.exists(tpath) and todo:
        open(tpath, "w", newline="\n").write("\n".join(sorted((r["addr"] for r in todo), key=lambda x: int(x, 16))) + "\n")
    # a window label for every window: the region notes' subsystem, else the window's own most common strings
    win = {}
    strc = defaultdict(Counter)
    for r in rows:
        key = (r["module"], int(r["addr"], 16) >> 18)
        if r["sub"] and not r["sub"].isdigit():
            win.setdefault(key, r["sub"])
        for s in r["strings"][:4]:
            s = s.strip()
            if 8 <= len(s) <= 70 and not s.startswith(("/", "\\", "%")):
                strc[key][s] += 1
    for key, c in strc.items():
        if key not in win and c:
            win[key] = "window strings: " + "; ".join(s for s, _ in c.most_common(3))
        elif key in win:
            win[key] = win[key] + " | strings: " + "; ".join(s for s, _ in c.most_common(2))

    todo.sort(key=lambda r: int(r["addr"], 16))
    if a.addrs:
        want = {x.strip().lower() for x in open(a.addrs, encoding="utf-8") if x.strip()}
        todo = [r for r in todo if r["addr"] in want]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} functions to read; {sum(r['lines'] for r in todo):,} generated lines")
    ir = read_ir(a.gen, [gen_funcs[r["addr"]] for r in todo], starts_by_file, a.max_ir)

    os.makedirs(a.out, exist_ok=True)
    batches = []
    for i in range(0, len(todo), a.batch_size):
        chunk = todo[i:i + a.batch_size]
        num = i // a.batch_size
        # fastball: `--all` builds dossiers for theming (not only for the 47k unread pass), so the title says what it is
        title = "Functions" if a.all else "Unread functions"
        lines = [f"# {title}, batch {num} ({len(chunk)} functions, game 1.0.20)",
                 "",
                 "Each entry: address, generated-C lines, direct callers, span in bytes, vtable slot, the 256 KB",
                 "window's subsystem, the function's own strings, the known role of each callee in brackets, then the",
                 "function's operations: `call f_X` (a direct call), `LD32[x0+0x8]` / `ST8[x8+0xa]` (memory),",
                 "`if ... goto L_x` (branch). Register names match the game's own; x0 is the first argument and the",
                 "return value. The strings line is the only place this function's literals appear: quote from there.",
                 ""]
        for r in chunk:
            g = gen_funcs[r["addr"]]
            cs = callers.get(r["addr"], [])
            cdesc = ", ".join(f"{c}{('=' + role_of(rows_by, c)) if role_of(rows_by, c) else ''}" for c in cs[:4])
            calls = []
            for c in g["calls"][:6]:
                nm = role_of(rows_by, c)
                calls.append(f"f_{c[2:]}" + (f"({nm})" if nm else ""))
            vt = f" vtable {r['vtable']} slot {r['slot']}" if r["vtable"] else ""
            label = win.get((r["module"], int(r["addr"], 16) >> 18), "") or "(no theme for this window)"
            lines.append(f"## {r['addr']}  l={r['lines']} span={r['span']}B callers={r['callers']}{vt} "
                         f"window=\"{label[:110]}\"")
            if cdesc:
                lines.append(f"callers: {cdesc}")
            if calls:
                lines.append("calls: " + ", ".join(calls))
            lit = [s.strip() for s in (r.get("strings") or [])
                   if 3 <= len(s.strip()) <= 60 and not s.strip().startswith(("/", "\\", "%"))][:8]
            if lit:
                lines.append("strings: " + ", ".join(json.dumps(s) for s in lit))
            for op in ir.get(r["addr"], []):
                lines.append("  " + op)
            lines.append("")
        path = f"{a.out}/batch-{num:03d}.md"
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        batches.append(dict(id=num, file=path, count=len(chunk), addrs=[r["addr"] for r in chunk]))
    json.dump(dict(only=a.only, batch_size=a.batch_size, total=len(todo), batches=batches),
              open(f"{a.out}/manifest.json", "w"), indent=1)
    sizes = [os.path.getsize(b["file"]) for b in batches]
    print(f"{len(batches)} batches written, {min(sizes)}..{max(sizes)} bytes each, mean {sum(sizes)//len(sizes)}")


if __name__ == "__main__":
    main()
