"""Index every function in the hand-written source tree.

    python -I tools/map_source.py [--out docs/map/index]

C/C++ come from libclang (a real parse, with the flags tools/build.py uses), Python from `ast`, C# and GLSL from
regexes (vendored or shader code, lower fidelity, flagged in the `parser` column). libclang is read from
work/pylib (`python -I -m pip install libclang --target work/pylib`). Output: source_functions.jsonl (one function
per line: area, file, line, end, name, kind, signature, calls, parser) and source_summary.json.
"""
import argparse, ast, json, os, re, subprocess, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/work/pylib")

C_FLAGS = ["-std=gnu11", "-D_CRT_SECURE_NO_WARNINGS", "-DMLB_DEV_HARNESS", "-DNDEBUG",
           "-I" + ROOT + "/runtime/mlb", "-I" + ROOT + "/runtime/core", "-I" + ROOT + "/runtime/gfx",
           "-I" + ROOT + "/runtime/third_party/imgui", "-I" + ROOT + "/runtime/third_party/ffx/api/include",
           "-I" + ROOT + "/runtime/third_party/ffx/upscalers/include",
           "-I" + ROOT + "/work/gen", "-I" + ROOT + "/work/deps/include", "-I" + ROOT + "/work/deps/include/vma"]
CXX_FLAGS = ["-x", "c++", "-std=c++17"] + C_FLAGS[1:]


def area_of(rel):
    if rel.startswith("runtime/third_party/"):
        return "runtime/third_party"
    if rel.startswith("tools/vendor/"):
        return "tools/vendor"
    p = rel.split("/")
    if p[0] in ("runtime", "tools") and len(p) > 2:
        return p[0] + "/" + p[1]
    return p[0]


def list_files():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard"], capture_output=True,
                         text=True, check=True).stdout.split("\n")
    return sorted(f for f in out if f and not f.startswith(".claude/") and os.path.isfile(ROOT + "/" + f))


def c_functions(rel, cindex, idx):
    ext = rel.rsplit(".", 1)[-1]
    args = CXX_FLAGS if ext in ("cpp", "cc", "hpp") else C_FLAGS
    if ext == "h" and not rel.startswith("runtime/third_party"):
        args = ["-x", "c"] + C_FLAGS
    elif ext == "h":
        args = ["-x", "c++-header"] + CXX_FLAGS[2:]
    tu = idx.parse(ROOT + "/" + rel, args=args, options=cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES * 0)
    errs = sum(1 for d in tu.diagnostics if d.severity >= 3)
    K = cindex.CursorKind
    defs = {}

    def calls_in(cur):
        seen = []
        for n in cur.walk_preorder():
            if n.kind == K.CALL_EXPR and n.spelling and n.spelling not in seen:
                seen.append(n.spelling)
            elif n.kind == K.DECL_REF_EXPR and n.referenced is not None and \
                    n.referenced.kind == K.FUNCTION_DECL and n.spelling not in seen:
                seen.append(n.spelling)
        return seen

    def visit(cur):
        for ch in cur.get_children():
            f = ch.location.file
            if ch.kind in (K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.FUNCTION_TEMPLATE) \
                    and ch.is_definition():
                if f is not None:
                    p = os.path.abspath(f.name).replace("\\", "/")
                    if p.startswith(ROOT + "/"):
                        r = p[len(ROOT) + 1:]
                        key = (r, ch.location.line, ch.spelling)
                        if key not in defs:
                            sc = ch.storage_class.name if ch.kind == K.FUNCTION_DECL else ""
                            defs[key] = dict(file=r, line=ch.location.line, end=ch.extent.end.line,
                                             name=ch.spelling, kind=ch.kind.name.lower(),
                                             signature=ch.type.spelling, storage=sc.lower(),
                                             calls=calls_in(ch), parser="libclang")
            elif ch.kind in (K.NAMESPACE, K.UNEXPOSED_DECL, K.CLASS_DECL, K.STRUCT_DECL, K.CLASS_TEMPLATE) and \
                    (ch.kind in (K.NAMESPACE, K.UNEXPOSED_DECL) or ch.is_definition()):
                visit(ch)

    visit(tu.cursor)
    return list(defs.values()), errs


def py_functions(rel):
    try:
        tree = ast.parse(open(ROOT + "/" + rel, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        return [], 1
    out = []

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls = []
                for n in ast.walk(ch):
                    if isinstance(n, ast.Call):
                        nm = n.func.id if isinstance(n.func, ast.Name) else \
                            n.func.attr if isinstance(n.func, ast.Attribute) else None
                        if nm and nm not in calls:
                            calls.append(nm)
                doc = (ast.get_docstring(ch) or "").split("\n")[0]
                out.append(dict(file=rel, line=ch.lineno, end=ch.end_lineno, name=prefix + ch.name,
                                kind="function" if not prefix else "method", signature=doc,
                                storage="", calls=calls, parser="ast"))
                walk(ch, prefix + ch.name + ".")
            elif isinstance(ch, ast.ClassDef):
                walk(ch, prefix + ch.name + ".")
            else:
                walk(ch, prefix)

    walk(tree, "")
    return out, 0


CS_RE = re.compile(r"^[ \t]*(?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|async|"
                   r"unsafe|extern|partial|new|readonly)\s+)*[\w<>\[\],.?\s]+?\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^;{}]*)\)"
                   r"\s*(?:where [^{;]*)?(?:\{|=>)", re.M)
CS_KW = {"if", "while", "for", "foreach", "switch", "using", "lock", "catch", "return", "fixed", "nameof", "typeof",
         "sizeof", "new", "else", "when"}
GLSL_RE = re.compile(r"^[ \t]*(?:(?:const|highp|mediump|lowp|inline)\s+)*[A-Za-z_][\w]*(?:\s*\[\s*\d*\s*\])?\s+"
                     r"([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*\{", re.M)


C_DEF = re.compile(r"^(?!\s*(?:typedef|#|return|else|if|for|while|switch))[A-Za-z_][\w\s\*\(\)]*?\b(\w+)\s*"
                   r"\([^;{}]*\)\s*\{", re.M)
C_KEYWORDS = {"if", "for", "while", "switch", "sizeof", "return", "defined", "do", "else"}
ATTR = re.compile(r"__attribute__\s*\(\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)\)")


def strip_c(txt):
    """Blank out comments, strings and __attribute__ lists, keeping line numbers."""
    keep_lines = lambda m: "\n" * m.group(0).count("\n")
    txt = re.sub(r"/\*.*?\*/", keep_lines, txt, flags=re.S)
    txt = re.sub(r"//[^\n]*", "", txt)
    txt = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', txt)
    return ATTR.sub(keep_lines, txt)


def inactive_branch_functions(rel, have):
    """Functions the libclang parse did not see (typically under an #if/#ifdef that is off for this build)."""
    txt = strip_c(open(ROOT + "/" + rel, encoding="utf-8", errors="replace").read())
    out = []
    for m in C_DEF.finditer(txt):
        nm = m.group(1)
        if nm in C_KEYWORDS or nm in have:
            continue
        ln = txt.count("\n", 0, m.start(1)) + 1
        end = txt.count("\n", 0, m.end())
        out.append(dict(file=rel, line=ln, end=ln, name=nm, kind="function",
                        signature=" ".join(m.group(0).split())[:120], storage="", calls=[],
                        parser="regex-inactive-branch"))
    return out


def regex_functions(rel, rx, banned):
    txt = open(ROOT + "/" + rel, encoding="utf-8", errors="replace").read()
    out = []
    for m in rx.finditer(txt):
        if m.group(1) in banned:
            continue
        ln = txt.count("\n", 0, m.start(1)) + 1
        out.append(dict(file=rel, line=ln, end=ln, name=m.group(1), kind="function",
                        signature="(" + " ".join(m.group(2).split()) + ")", storage="", calls=[],
                        parser="regex"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ROOT + "/docs/map/index")
    a = ap.parse_args()
    from clang import cindex
    idx = cindex.Index.create()
    files = list_files()
    funcs, parse_errs, skipped = [], {}, []
    for rel in files:
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if ext in ("c", "cpp", "cc", "h", "hpp"):
            if rel.startswith("tools/vendor/") and ext in ("h", "hpp"):
                pass
            fs, e = c_functions(rel, cindex, idx)
            if e:
                parse_errs[rel] = e
            if ext in ("c", "cpp", "cc"):
                have = {f["name"].split("::")[-1] for f in fs}
                fs = fs + inactive_branch_functions(rel, have)
        elif ext == "py":
            fs, e = py_functions(rel)
        elif ext == "cs":
            fs, e = regex_functions(rel, CS_RE, CS_KW), 0
        elif ext in ("glsl", "vert", "frag", "comp"):
            fs, e = regex_functions(rel, GLSL_RE, {"if", "for", "while", "switch"}), 0
        else:
            continue
        funcs.extend(fs)
    seen, uniq = set(), []
    tracked = set(files)
    for f in funcs:
        k = (f["file"], f["line"], f["name"])
        if k not in seen and f["file"] in tracked:
            seen.add(k)
            f["area"] = area_of(f["file"])
            uniq.append(f)
    uniq.sort(key=lambda f: (f["file"], f["line"]))
    os.makedirs(a.out, exist_ok=True)
    with open(a.out + "/source_functions.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for f in uniq:
            fh.write(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + "\n")
    by_area = Counter(f["area"] for f in uniq)
    by_parser = Counter((f["area"], f["parser"]) for f in uniq)
    summ = dict(total=len(uniq), by_area=dict(sorted(by_area.items())),
                by_area_parser={f"{k[0]}|{k[1]}": v for k, v in sorted(by_parser.items())},
                files_with_parse_errors=parse_errs)
    json.dump(summ, open(a.out + "/source_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1)[:3000])


if __name__ == "__main__":
    main()
