"""Recognise third-party library code so the readers never spend time on it.

    python -I tools/theme_filter.py [--index work/map/index]

A function is library code when the index already says so (`kind: library`), when its strings carry a library's own
name or source path, or when its role text names a bundled library. The theming pipeline drops these before making
dossiers: an encryption routine or an image decoder has no aspect of the game, and reading it costs the same as
reading a game function.

The signals are deliberately narrow. A file name like `processor_input.cpp` is not enough on its own; the marker has
to be a library directory or a known library name.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")

# library names, as they appear in a string the function quotes
LIBRARY_WORDS = [
    "nlohmann", "stb_image", "stb_truetype", "stb_vorbis", "imgui", "implot", "mbedtls", "openssl",
    "libpng", "libjpeg", "jpeg-decoder", "freetype", "harfbuzz", "zlib", "miniz", "deflate", "inflate",
    "boost::", "fmt::format", "std::__1", "crypto++", "botan", "tinyxml", "pugixml", "rapidjson",
    "yaml-cpp", "lz4", "zstd", "brotli", "opusfile", "vorbisfile", "sdl_", "vulkan", "spirv",
    "bc7enc", "astcenc", "ispc", "xatlas", "meshoptimizer", "recast", "detour", "lua 5.", "lua_",
]

# marker directories in a source path a function quotes
LIBRARY_PATHS = [
    "third_party/", "thirdparty/", "3rdparty/", "external/", "vendor/", "nlohmann/", "stb_", "imgui/",
    "mbedtls/", "openssl/", "zlib/", "libpng/", "jpeg/", "freetype/", "extern/", "deps/",
]

# role phrases the read pass already wrote for bundled libraries
ROLE_MARKERS = [
    "nlohmann", "bundled json library", "json library", "dear imgui", "imgui", "stb_image",
    "texture decoding: astc", "astc codec", "third-party", "third party", "sdl", "mbedtls",
    "openssl", "zlib", "crypto", "encryption", "decoder for", "codec library", "lua",
]


def _text_of(row):
    parts = [str(row.get("role") or ""), str(row.get("basis") or "")]
    parts += [str(s) for s in (row.get("strings") or [])]
    return " | ".join(parts)


def is_library(row):
    """(True, reason) when the row is third-party library code."""
    if row.get("kind") == "library":
        return True, "index kind library"
    text = _text_of(row).lower()
    for w in LIBRARY_WORDS:
        if w in text:
            return True, f"library name {w!r}"
    for p in LIBRARY_PATHS:
        if p in text:
            return True, f"library path {p!r}"
    for r in ROLE_MARKERS:
        if r in text:
            return True, f"role says {r!r}"
    return False, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=ROOT + "/work/map/index")
    ap.add_argument("--out", default=ROOT + "/work/theme/library.jsonl")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(f"{a.index}/roles.jsonl", encoding="utf-8")]
    picked = []
    for r in rows:
        if r["module"] != "main":
            continue
        lib, why = is_library(r)
        if lib:
            picked.append({"addr": r["addr"], "reason": why, "role": (r.get("role") or "")[:120]})
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in picked:
            f.write(json.dumps(r) + "\n")
    print(f"{len(picked):,} library functions of {sum(1 for r in rows if r['module'] == 'main'):,} main functions")
    from collections import Counter
    for why, n in Counter(p["reason"].split(" ", 1)[0] for p in picked).most_common():
        print(f"  {n:>6} by {why}")


if __name__ == "__main__":
    main()
