"""Check the function map against independent counts. Exit status 1 if anything is unmapped.

    python -I tools/map_coverage.py [--index work/map/index] [--docs docs/map]

Checks (each is a second way of counting, not a re-read of the index):
  python    every `def` line (regex) is in the index, per file; counts must match exactly
  c/c++     every function definition found by a column-0 regex scan of runtime/ and tools/ .c/.cpp files is in the
            libclang index (name + file); index-only names (macros, static inline in headers) are listed as extras
  c#/glsl   regex-only tier (vendored Ryujinx C#, shaders): index count vs a second, looser regex; flagged "unverified"
  generated function count in each generated chunk set equals manifest function_count, no duplicate addresses
  binary    each direct `bl` target in the original .text is an indexed function (binary_check.json)
  docs      every indexed source function appears in docs/map/source/*.md (by file and name)
Writes docs/map/coverage.md.
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import map_source as ms
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.M)
CS_LOOSE = re.compile(r"^\s+(?:public|private|protected|internal|static|override|virtual|unsafe)[^;=\n(]*\(", re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--docs", default=ROOT + "/docs/map")
    a = ap.parse_args()
    src = [json.loads(l) for l in open(a.index + "/source_functions.jsonl", encoding="utf-8")]
    by_file = defaultdict(list)
    for f in src:
        by_file[f["file"]].append(f)
    lines, bad = [], 0

    def row(name, ok, detail):
        nonlocal bad
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
        if not ok:
            bad += 1

    py_files = [f for f in by_file if f.endswith(".py")]
    import subprocess
    tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard"], capture_output=True,
                             text=True).stdout.split("\n")
    tracked = [t for t in tracked if t and not t.startswith(".claude/") and os.path.isfile(ROOT + "/" + t)]
    py_all = [t for t in tracked if t.endswith(".py")]
    import io, tokenize
    miss, tot_py, idx_py = [], 0, 0
    for t in py_all:
        toks = list(tokenize.generate_tokens(io.StringIO(
            open(ROOT + "/" + t, encoding="utf-8", errors="replace").read()).readline))
        n = sum(1 for k, tk in enumerate(toks[:-1]) if tk.type == tokenize.NAME and tk.string == "def" and
                toks[k + 1].type == tokenize.NAME)
        i = len(by_file.get(t, []))
        tot_py += n
        idx_py += i
        if n != i:
            miss.append((t, n, i))
    row("python defs", not miss, f"{idx_py} indexed vs {tot_py} counted in {len(py_all)} files; mismatches: {miss[:5]}")

    c_all = [t for t in tracked if t.rsplit(".", 1)[-1] in ("c", "cpp") and not t.startswith("tools/vendor")]
    missing, found_total, extras = [], 0, 0
    for t in c_all:
        txt = ms.strip_c(open(ROOT + "/" + t, encoding="utf-8", errors="replace").read())
        names = {m.group(1) for m in ms.C_DEF.finditer(txt) if m.group(1) not in ms.C_KEYWORDS}
        idxn = {f["name"].split("::")[-1] for f in by_file.get(t, [])}
        found_total += len(names)
        missing += [(t, n) for n in sorted(names - idxn)]
        extras += len(idxn - names)
    inactive = sum(1 for f in src if f["parser"] == "regex-inactive-branch")
    row("c/c++ definitions", not missing,
        f"{found_total} regex-found definitions in {len(c_all)} files, {len(missing)} missing from index "
        f"({inactive} of the indexed ones sit in preprocessor branches libclang skipped and come from the regex) "
        f"{missing[:8]}; index-only (macro/inline) names: {extras}")

    cs = [t for t in tracked if t.endswith(".cs")]
    n_idx = sum(len(by_file.get(t, [])) for t in cs)
    n_loose = sum(len(CS_LOOSE.findall(open(ROOT + "/" + t, encoding="utf-8", errors="replace").read())) for t in cs)
    row("c# (vendored, regex tier)", n_idx >= n_loose * 0.9,
        f"{n_idx} indexed vs {n_loose} by a looser regex; NOT parser-verified (vendored Ryujinx)")

    g = json.load(open(a.index + "/generated_summary.json"))
    for mod in ("main", "sdk"):
        m = g[mod]
        ok = m["indexed"] == m["manifest_function_count"] == m["unique_addresses"]
        row(f"generated {mod}", ok, f"{m['indexed']} indexed, manifest says {m['manifest_function_count']}, "
            f"{m['duplicates']} duplicate addresses")
    row("generated callees", g["callee_addresses_not_defined"] == 0,
        f"{g['callee_addresses_not_defined']} direct callee addresses with no definition")
    b = json.load(open(a.index + "/binary_check.json"))
    for mod in ("main", "sdk"):
        m = b[mod]
        row(f"binary {mod} (original .text)", m["bl_targets_not_indexed"] == 0 and m["named_symbols_not_indexed"] == 0,
            f"{m['distinct_bl_targets_in_text']} distinct bl targets scanned from machine code, "
            f"{m['bl_targets_not_indexed']} not indexed; {m['named_function_symbols']} named symbols, "
            f"{m['named_symbols_not_indexed']} not indexed")

    undoc = []
    srcdir = a.docs + "/source"
    doc_text = {}
    for fn in os.listdir(srcdir) if os.path.isdir(srcdir) else []:
        doc_text[fn] = open(srcdir + "/" + fn, encoding="utf-8").read()
    alldocs = "\n".join(doc_text.values())
    for f in src:
        if f"`{f['name']}`" not in alldocs or f"`{f['file']}`" not in alldocs:
            undoc.append((f["file"], f["name"]))
    row("docs list every source function", not undoc and bool(doc_text),
        f"{len(src) - len(undoc)} of {len(src)} appear in docs/map/source/; missing {undoc[:5]}")

    out = ["# Map coverage", "", "Generated by `tools/map_coverage.py`; rerun it after any change to the map.", "",
           "| Check | Result | Detail |", "|---|---|---|"] + lines + ["", f"Failed checks: {bad}"]
    os.makedirs(a.docs, exist_ok=True)
    open(a.docs + "/coverage.md", "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print("\n".join(out))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
