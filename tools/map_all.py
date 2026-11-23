"""Rebuild the whole function map in order, then check it. Stops at the first failing step.

    python -I tools/map_all.py [--skip-game]     # --skip-game: only the repo's own source (no work/gen needed)

Steps: map_source (hand-written code; needs libclang in work/pylib), then, with game code present, map_generated,
map_binary, map_strings, then map_docs and map_coverage. The game-derived indexes land in work/map/index/ and are
never committed. Needs: python -I -m pip install libclang --target work/pylib   (once).
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
steps = [("map_source.py", ["--out", ROOT + "/work/map/index"])]
if "--skip-game" not in sys.argv:
    steps += [("map_generated.py", []), ("map_binary.py", []), ("map_strings.py", [])]
steps += [("map_docs.py", []), ("map_coverage.py", [])]
for name, args in steps:
    print("==", name, flush=True)
    r = subprocess.run([sys.executable, "-I", ROOT + "/tools/" + name] + args)
    if r.returncode:
        sys.exit(f"{name} failed ({r.returncode})")
