# Reading every function body

The wiki's coverage chart draws two bars per region: the evidence behind each role (C, I or H) and the share of bodies that were read.

The first reading pass covered only the 47,308 `main` functions that had no string, symbol or simple shape. Every other function kept a role inferred from a name or from the shape of its code, and the `sdk` module was not read at all. This pass reads the rest, 87,352 functions, so that every bar reaches 100%.

| Module | functions | read before | to read |
|---|---|---|---|
| `main` | 94,991 | 47,708 | 47,283 |
| `sdk` | 40,069 | 0 | 40,069 |
| total | 135,060 | 47,708 | 87,352 |

## Read roles

A read role is written by an agent from the function's own normalized body (`tools/map_read_prep.py` produces the
dossiers), the known roles of its callers and callees, its window's subsystem and its own strings. The overlay keeps
one row per function: `role`, `tag` and `evidence`.

- `tag` is `C` when the role rests on a name that is in the dossier (a string, an import or symbol name, a vtable
  class name), `I` when it rests on the code itself (operations, call graph, vtable slot, empty body), and `H` only
  when the dossier says nothing usable about the function.
- A read role is a lead, not a verified fact. The earlier audit found 6 right, 1 incomplete and 3 with a wrong
  specific detail out of 10. Open the body before relying on a detail.
- The merge machine-checks every quoted fragment against the function's dossier (`--check-quotes`), so an invented
  string is reported instead of trusted.

## Running a wave

`main` and `sdk` are separate runs, each with its own target list and batch numbering:

```
python -I tools/map_read_prep.py --out work/map/read-all --only main --unread --batch-size 200
python -I tools/map_read_prep.py --out work/map/read-sdk  --only sdk  --unread --batch-size 200
```

`--unread` takes every function with no entry in the overlay, writes the whole remaining set to `targets.txt`, and numbers the batches from it. A later `--start N --limit M` slice continues where an earlier one stopped and never rewrites an existing dossier.

Each batch is one Markdown dossier of 200 entries. One reader agent reads a dossier completely and writes `out-<prefix>-<n>.jsonl`, one JSON object per entry:

```
{"addr":"0x7000051e60","role":"copies a 0x80-byte block from x1 to the object at x0; memcpy-shaped helper","tag":"I","evidence":"x3 = x2 + 0x40; x4 = 0x80; LD64/ST64 at sp+0x10; 268 lines"}
```

Then:

```
python -I tools/map_read_merge.py --read work/map/read work/map/read-all work/map/read-sdk --check-quotes
python -I tools/map_roles.py            # applies the overlay: roles.jsonl carries read=true and the read role
python -I tools/wiki_completeness.py    # the chart, and the read count per region
```

The merge rejects a line with bad JSON, an address outside its run's target list, or an empty role/evidence
(exit code 1). Quote mismatches are reported with their addresses (exit 0): they are re-read, not trusted.

## Wave checks

- Every `## ` heading in the dossier appears exactly once in the answer file, in order (the merge's counts and the
  wave's own check).
- `--check-quotes` finds no invented text in the new rows.
- Spot-check about five rows per wave against `work/gen/<module>/*.c` at the file:line `tools/map_find.py fn` prints,
  the way the earlier read reports were checked (`docs/map/bodies/`).
- The chart's `bodies read` count rises by the wave's size and the C/I/H split matches what the readers answered.

## Known lines

Many functions already have a symbol, an import name or a string-derived role in the index, but that evidence is not in the body. Without the `known:` line a reader sees an anonymous destructor loop where the index says `_fini`; with it the role can say what the function is.

The heading also carries `trap=N` (unreachable trap sites the recompiler drops from the ops) and `indirect=N` (calls through a function pointer), so a stub is not mistaken for an empty function.
