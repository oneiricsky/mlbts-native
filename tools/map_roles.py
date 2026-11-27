"""Give every recompiled function a classified identity: an import name, a symbol, a structural shape, or a
subsystem. This is the complete function map behind the wiki's Function pages.

    python -I tools/map_roles.py [--gen work/gen] [--exefs work/build/game/exefs] [--index work/map/index]

Reads the index (tools/map_all.py) plus the original modules for import names, the generated C for shape, and
the region notes for the 256 KB window's subsystem. Writes work/map/index/roles.jsonl and roles_summary.json.
Derived from game code: stays under work/, never committed.

Fields per function: module addr span lines callers ncallees dispatch udf shape kind role basis tag
name vtable slot vtable_size strings apis target off sub.
  kind   library | sdk | import | symbol | game | boilerplate | unknown
  tag    C (string, symbol, import) | I (inferred via shape of code or call graph) | H (inferred via neighbours)
"""
import argparse, json, os, re, struct, subprocess, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from nsoinfo import Nso  # noqa: E402

BASES = {"main": 0x7000000000, "sdk": 0x7004c00000}
ENDS = {"main": 0x7001c22800, "sdk": 0x700524e230}
CXXFILT = "C:/Program Files/LLVM/bin/llvm-cxxfilt.exe"

RE_THUNK_BASE = re.compile(r"x16 = \(uint64_t\)\((0x[0-9a-f]+)ull\);")
RE_THUNK_OFF = re.compile(r"ea = x16 \+ (0x[0-9a-f]+)ull")
RE_TAIL = re.compile(r"musttail\)\) return f_([0-9a-f]+)\(c\);")
RE_LD = re.compile(r"\bLD(?:64|32|U16|U8|S8|16|8)\(")
RE_ST = re.compile(r"\bST(?:64|32|16|8)\(")
RE_FIELD = re.compile(r"x0 \+ (0x[0-9a-f]+)ull")
RE_CONST = re.compile(r"x0 = \(uint64_t\)\((0x[0-9a-f]+|0)ull \| (0x[0-9a-f]+|0)ull\);")
RE_CONST1 = re.compile(r"x0 = \((?:uint64_t|uint32_t)\)\((0x[0-9a-f]+|0)ull\);")
CALL = re.compile(r"\bf_([0-9a-f]+)\(c\)")

LIBS = [
    (("nlohmann", "to_chars.hpp"), "nlohmann JSON"),
    (("imgui", "ImGui"), "Dear ImGui"),
    (("openssl", "OpenSSL", "libssl", "SSL_CTX", "EVP_"), "OpenSSL"),
    (("libcurl", "curl_easy", "CURLcode", "curl_multi"), "libcurl"),
    (("lua_", "Lua 5.", "luaL_"), "Lua"),
    (("opus_", "OpusEncoder", "OPUS_OK"), "Opus"),
    (("webp", "VP8L", "VP8StatusCode"), "libwebp"),
    (("tinyexr", "EXRHeader", "ParseEXR", "SaveEXR"), "tinyexr"),
    (("stb_image", "stbi_", "STB_IMAGE"), "stb_image"),
    (("astc-codec", "astc"), "ASTC codec"),
    (("msdfgen", "MSDF", "edge coloring"), "msdfgen"),
    (("Bink", "bink"), "Bink video"),
    (("gattaca", "wws_", "Scream", "SCREAM"), "SCREAM audio"),
    (("inflate", "deflate", "zlib"), "zlib"),
    (("fvad", "FVAD", "webrtc"), "libfvad"),
    (("mxml", "mini-XML"), "mini-XML"),
]
SHAPE_NAMES = {
    "empty": "empty stub (returns immediately)",
    "trap": "unreachable trap stub",
    "const": "returns a constant",
    "getter": "reads a field and returns it",
    "setter": "writes a field",
    "tailcall": "tail-calls another function",
    "thunk": "jumps through a function pointer",
    "dispatch": "calls through a table (virtual dispatch)",
    "unknown": "unclassified",
}


def load_index(idx):
    def rows(n):
        return [json.loads(l) for l in open(f"{idx}/{n}.jsonl", encoding="utf-8")]
    return rows("generated_functions"), {r["addr"]: r["strings"] for r in rows("function_strings")}, \
        {r["addr"]: r["demangled"] for r in rows("binary_names")}, rows("vtables")


def import_slots(exefs, mod):
    """GOT/import slot (module offset) -> imported symbol name, from the module's relocations."""
    n = Nso(f"{exefs}/{mod}")
    n.parse_dynamic()
    img, tags = n.image, n.dyn
    slots = {}

    def rela(off, size):
        for i in range(size // 24):
            r_off, r_info, _ = struct.unpack_from("<QQq", img, off + i * 24)
            if (r_info & 0xFFFFFFFF) in (1025, 1026) and (r_info >> 32):
                slots[r_off] = n.syms[r_info >> 32]["name"]
    if 7 in tags:
        rela(tags[7], tags.get(8, 0))
    if 23 in tags:
        rela(tags[23], tags.get(2, 0))
    return slots


def scan_bodies(gen, mod, funcs):
    """One streaming pass over the module's generated C: shape features per function and a thunk's import slot."""
    by_file = defaultdict(list)
    for f in funcs:
        by_file[f["file"]].append(f)
    feats = {}
    for path, fl in by_file.items():
        want = {f["line"]: f["addr"] for f in fl}
        cur, acc = None, None
        with open(f"{gen}/{path}", encoding="utf-8", errors="replace") as fh:
            for ln, line in enumerate(fh, 1):
                if ln in want:
                    if cur is not None:
                        feats[cur] = acc
                    cur = want[ln]
                    acc = dict(tail=None, ld=0, st=0, fields=[], const=None, dispatch=0, udf=0, thunk=None,
                               calls=0, meaningful=False)
                    continue
                if acc is None:
                    continue
                s = line
                m = RE_TAIL.search(s)
                if m:
                    acc["tail"] = "0x" + m.group(1)
                if "rt_dispatch(" in s:
                    acc["dispatch"] += s.count("rt_dispatch(")
                if "rt_udf(" in s:
                    acc["udf"] += s.count("rt_udf(")
                if RE_LD.search(s):
                    acc["ld"] += 1
                if RE_ST.search(s):
                    acc["st"] += 1
                for fm in RE_FIELD.finditer(s):
                    if fm.group(1) not in acc["fields"] and len(acc["fields"]) < 6:
                        acc["fields"].append(fm.group(1))
                m = RE_CONST.search(s)
                if m:
                    a, b = m.group(1), m.group(2)
                    acc["const"] = (0 if a == "0" else int(a, 16)) | (0 if b == "0" else int(b, 16))
                else:
                    m = RE_CONST1.search(s)
                    if m:
                        acc["const"] = 0 if m.group(1) == "0" else int(m.group(1), 16)
                m = RE_THUNK_BASE.search(s)
                if m:
                    acc["_tbase"] = int(m.group(1), 16)
                if "_tbase" in acc:
                    m2 = RE_THUNK_OFF.search(s)
                    if m2:
                        acc["thunk"] = (acc["_tbase"], int(m2.group(1), 16))
                if "f_" in s:
                    acc["calls"] += len(CALL.findall(s))
                st = s.strip()
                if st and not st.startswith(("FN_ENTER", "void f_", "return;", "}")):
                    acc["meaningful"] = True
            if cur is not None:
                feats[cur] = acc
    return feats


def shape_of(ft, lines):
    if lines <= 6 and ft["udf"] and not ft["tail"] and not ft["dispatch"] and not ft["calls"] and not ft["ld"] and not ft["st"]:
        return "trap"
    if not ft["meaningful"]:
        return "empty"
    if lines <= 16 and ft["dispatch"] and ft["ld"] and not ft["calls"] and not ft["tail"]:
        return "thunk"
    if ft["dispatch"] and ft["tail"]:
        return "dispatch"
    if ft["tail"] and ft["calls"] <= 1 and not ft["ld"] and not ft["st"]:
        return "tailcall"
    if lines <= 8 and ft["const"] is not None and not ft["tail"] and not ft["calls"] and not ft["ld"] and not ft["st"] \
            and not ft["dispatch"]:
        return "const"
    if lines <= 10 and ft["ld"] and not ft["st"] and not ft["calls"] and not ft["tail"]:
        return "getter"
    if lines <= 10 and ft["st"] and not ft["ld"] and not ft["calls"] and not ft["tail"]:
        return "setter"
    return "unknown"


def pick_string(st):
    """The most informative string in a body: a readable phrase beats a punctuation or path fragment."""
    def score(s):
        s = s.strip()
        if not s:
            return -20
        v = 0
        if " " in s:
            v += 3
        v += min(2, len(re.findall(r"[a-z]{3,}", s)))
        if 10 <= len(s) <= 60:
            v += 2
        if s[0] in "/\\%" or s.startswith(("_", "..")):
            v -= 4
        if len(set(s)) <= 4 or any(x in s for x in ("====", "----", "!=", "&&", "||", ".hpp", ".cpp")):
            v -= 6
        return v
    return max(st, key=lambda s: (score(s), len(s.strip())))


def short_api(name):
    n = re.sub(r"<.*", "", name.split("(")[0]).strip()
    parts = [p for p in n.split("::") if p]
    if n.startswith(("nn::", "std::")):
        return "::".join(parts[:3])
    return "::".join(parts[-2:]) if len(parts) > 2 else n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default=ROOT + "/work/gen")
    ap.add_argument("--exefs", default=ROOT + "/work/build/game/exefs")
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    a = ap.parse_args()
    gen_funcs, strings, names, vtables = load_index(a.index)

    vtmap = defaultdict(list)
    for v in vtables:
        for i, fn in enumerate(v["functions"]):
            vtmap[fn].append((v["vtable"], i, v["size"]))

    slots = {m: import_slots(a.exefs, m) for m in ("main", "sdk")}
    feats = {}
    for mod in ("main", "sdk"):
        feats.update(scan_bodies(a.gen, mod, [f for f in gen_funcs if f["module"] == mod]))

    span = {}
    for mod, end in ENDS.items():
        addrs = sorted(int(f["addr"], 16) for f in gen_funcs if f["module"] == mod)
        for x, y in zip(addrs, addrs[1:] + [end]):
            span[hex(x)] = y - x

    ident, ident_kind = {}, {}
    for f in gen_funcs:
        ad = f["addr"]
        ft = feats.get(ad) or {}
        if ad in names:
            ident[ad] = names[ad]
            ident_kind[ad] = "sdk" if f["module"] == "sdk" else "symbol"
        elif ft.get("thunk"):
            base, off = ft["thunk"]
            imp = slots[f["module"]].get(base - BASES[f["module"]] + off)
            if imp:
                ident[ad] = imp
                ident_kind[ad] = "import"

    # import names arrive mangled from the relocation symbol; make them readable once
    bysym = defaultdict(list)
    for ad, v in ident.items():
        if ident_kind[ad] == "import":
            bysym[v].append(ad)
    imp_names = sorted(bysym)
    raw_of = {}
    if imp_names and os.path.exists(CXXFILT):
        out = subprocess.run([CXXFILT], input="\n".join(imp_names) + "\n", capture_output=True, text=True).stdout
        for raw, dem in zip(imp_names, out.splitlines()):
            for ad in bysym[raw]:
                raw_of[ad] = raw
                if dem:
                    ident[ad] = dem

    def resolve(ad, depth=0):
        seen = set()
        while ad and ad not in seen and depth < 8:
            seen.add(ad)
            if ad in ident:
                return ident[ad]
            ad = (feats.get(ad) or {}).get("tail")
            depth += 1
        return None

    rows = []
    for f in gen_funcs:
        ad = f["addr"]
        ft = feats.get(ad) or {}
        st = strings.get(ad, [])
        vt = vtmap.get(ad)
        row = dict(module=f["module"], addr=ad, span=span.get(ad, 0), lines=f["lines"], file=f["file"], line=f["line"],
                   callers=f["callers"], ncallees=len(f["calls"]), dispatch=f["dispatch"], udf=f["udf"],
                   vtable=vt[0][0] if vt else None, slot=vt[0][1] if vt else None,
                   vtable_size=vt[0][2] if vt else None, strings=st[:6], shape=shape_of(ft, f["lines"]),
                   off=(ft.get("fields") or [None])[0], target=ft.get("tail"), apis=[])
        lib = next((lname for keys, lname in LIBS
                    if any(any(k.lower() in s.lower() for k in keys) for s in st)), None)
        if ad in ident:
            nm = ident[ad]
            kind = ident_kind[ad]
            row.update(kind=kind, role=short_api(nm), basis="import symbol" if kind == "import" else "exported symbol",
                       tag="C", name=short_api(nm))
            if kind == "import":
                row["raw"] = raw_of.get(ad, nm)
        elif lib:
            row.update(kind="library", role=f"{lib} code", basis="strings name the library", tag="C", name=lib)
        elif st:
            best = pick_string(st)
            row.update(kind="game", role=f'uses "{best[:70]}"', basis="string in the body", tag="C")
        else:
            sh = row["shape"]
            row.update(kind="boilerplate", role=SHAPE_NAMES.get(sh, "unclassified"), basis="code shape",
                       tag="I" if sh != "unknown" else "H")
        rows.append(row)

    byaddr = {r["addr"]: r for r in rows}
    gen_by = {g["addr"]: g for g in gen_funcs}
    # reverse call map: who calls whom (a caller's role explains an anonymous helper)
    callers_of = defaultdict(list)
    for g in gen_funcs:
        for c in g["calls"]:
            callers_of[c].append(g["addr"])
    for r in rows:
        apis = []
        for c in gen_by[r["addr"]]["calls"]:
            n = byaddr.get(c, {}).get("name")
            if n and n not in apis:
                apis.append(n)
        r["apis"] = apis[:5]
        tgt = resolve(r["target"]) if r.get("target") else None
        if r["shape"] == "tailcall" and tgt:
            r["role"] = f"forwards to {short_api(tgt)}"
            r["basis"] = "tail-call target"
            r["tag"] = "I"
            r["name"] = short_api(tgt)
        elif r["shape"] == "getter" and r.get("off"):
            r["role"] = f"reads +{r['off']} and returns it"
        elif r["shape"] == "setter" and r.get("off"):
            r["role"] = f"writes +{r['off']}"
        if r["kind"] == "boilerplate" and r["apis"]:
            r["basis"] = "code shape; calls " + ", ".join(r["apis"][:3])
            if r["shape"] == "unknown":
                r["role"] = "helper: calls " + ", ".join(r["apis"][:3])
        if r["kind"] == "boilerplate" and r["shape"] == "thunk":
            r["role"] = "jumps through a function pointer"
    # last resort for a function with no name, string or shape: say where it sits in the call graph
    for r in rows:
        if r["kind"] != "boilerplate" or r["shape"] != "unknown" or r["apis"]:
            continue
        cs = callers_of.get(r["addr"], [])
        known = [byaddr[c]["role"] for c in cs if byaddr.get(c, {}).get("name")]
        if known:
            r["role"] = f"helper of {known[0]}"
            r["basis"] = "only named caller"
            r["tag"] = "I"
        elif cs:
            r["role"] = f"helper, {len(cs)} anonymous caller(s)"
            r["basis"] = "call graph only"
            r["tag"] = "H"
        elif r["vtable"]:
            r["role"] = f"virtual slot {r['slot']} of table {r['vtable']}"
            r["basis"] = "vtable slot"
            r["tag"] = "I"
        else:
            r["role"] = "no caller and no string (table or exported use)"
            r["basis"] = "no evidence"
            r["tag"] = "H"

    subs = {}
    region_dir = ROOT + "/docs/map/regions"
    for name in sorted(os.listdir(region_dir)):
        if name.endswith(".md"):
            for line in open(f"{region_dir}/{name}", encoding="utf-8"):
                m = re.match(r"\|\s*(0x[0-9a-f]{9,})\s*\|\s*([^|]+?)\s*\|", line)
                if m:
                    subs.setdefault(int(m.group(1), 16), m.group(2))
    for r in rows:
        r["sub"] = subs.get(int(r["addr"], 16) & ~0x3FFFF, "")

    # body-read overlay (tools/map_read_*.py): a role read from the function's own code wins over the shape guess
    overlay_path = a.index + "/roles_read.jsonl"
    read = 0
    if os.path.exists(overlay_path):
        ov = {}
        for line in open(overlay_path, encoding="utf-8"):
            o = json.loads(line)
            ov[o["addr"]] = o
        for r in rows:
            o = ov.get(r["addr"])
            if o:
                r.update(role=o["role"], tag=o["tag"], basis=f"body read (batch {o['batch']})", read=True)
                read += 1

    with open(a.index + "/roles.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = dict(functions=len(rows),
                   by_module=dict(Counter(r["module"] for r in rows)),
                   by_kind=dict(Counter(r["kind"] for r in rows)),
                   by_tag=dict(Counter(r["tag"] for r in rows)),
                   boilerplate_shapes=dict(Counter(r["shape"] for r in rows if r["kind"] == "boilerplate")),
                   named=sum(1 for r in rows if r.get("name")),
                   with_strings=sum(1 for r in rows if r["strings"]),
                   in_vtable=sum(1 for r in rows if r["vtable"]),
                   read_from_bodies=read,
                   windows=len({(r["module"], int(r["addr"], 16) >> 18) for r in rows}))
    json.dump(summary, open(a.index + "/roles_summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
