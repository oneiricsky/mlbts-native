"""What a function's vtable class says about it.

A vtable is an array of method addresses; many functions of `main` are one slot of one (33,403 of 94,991 in the
index). A bare getter or an empty stub carries no evidence of its own, but its class does: the strings its other
methods quote, the methods' own roles, and the strings of the functions they call. This module builds that context
once per vtable, and answers the three questions the dossier and the adjudicator need:

  class_of(addr)      -> (vtable, slot, size) or None
  method_strings(vt)  -> strings quoted by the class's own methods, rarest first (the class's vocabulary)
  near_strings(vt)    -> strings quoted by the class's methods' callees and callers (a step further out)
  named_slots(vt)     -> (slot, addr, role) for methods whose role says something more than "virtual slot"

The filter is rarity across `main`: a string quoted by more than RING_RARE functions ("vector", "league_id") says
nothing about one class and is dropped. A class string is one hop of evidence, not proof: `theme_adjudicate.py` ranks
it below the function's own string, and the hand audit reports it separately.
"""
import json
from collections import Counter, defaultdict

RING_RARE = 40

BOILERPLATE = (
    "empty stub", "returns a constant", "forwards to operator delete", "tail-calls another function",
    "jumps through a function pointer", "calls through a table", "unreachable trap", "virtual slot",
    "reads +0x", "writes +0x", "reads a field", "writes a field", "deleting destructor",
)


class Index:
    def __init__(self, roles, gen, classes, string_count):
        self.roles = roles
        self.gen = gen
        self.classes = classes
        self.string_count = string_count
        self.callers = defaultdict(set)
        for addr, g in gen.items():
            for c in g.get("calls") or []:
                self.callers[c.lower()].add(addr)

    def class_of(self, addr):
        r = self.roles.get(addr.lower())
        if not r or not r.get("vtable"):
            return None
        return r["vtable"].lower(), r.get("slot"), r.get("vtable_size")

    def _rare(self, addrs):
        c = Counter()
        for f in addrs:
            for s in self.roles.get(f.lower(), {}).get("strings") or []:
                s = s.strip()
                if 4 <= len(s) <= 70 and self.string_count.get(s, 0) <= RING_RARE:
                    c[s] += 1
        return c

    def method_strings(self, vtable):
        return self._rare(self.classes.get(vtable.lower(), []))

    def near_strings(self, vtable):
        ring = set()
        for m in self.classes.get(vtable.lower(), []):
            ring |= self.callers.get(m.lower(), set())
            ring.update(x.lower() for x in (self.gen.get(m.lower(), {}).get("calls") or []))
        return self._rare(ring - set(self.classes.get(vtable.lower(), [])))

    def named_slots(self, vtable, limit=6):
        out = []
        for i, f in enumerate(self.classes.get(vtable.lower(), [])):
            r = self.roles.get(f) or {}
            role = " ".join(str(r.get("role") or r.get("name") or "").split())
            if len(role) < 12 or any(b in role for b in BOILERPLATE):
                continue
            out.append((i, f, role[:70]))
            if len(out) >= limit:
                break
        return out

    def members(self, vtable):
        return [f.lower() for f in self.classes.get(vtable.lower(), [])]


def load(index_dir):
    roles, gen, classes, count = {}, {}, {}, Counter()
    with open(f"{index_dir}/roles.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["module"] != "main":
                continue
            roles[r["addr"].lower()] = r
            for s in r.get("strings") or []:
                count[s.strip()] += 1
    with open(f"{index_dir}/generated_functions.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["module"] == "main":
                gen[r["addr"].lower()] = r
    with open(f"{index_dir}/vtables.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["module"] == "main":
                classes[r["vtable"].lower()] = [x.lower() for x in r["functions"]]
    return Index(roles, gen, classes, count)


def describe(ix, addr, limit=6):
    """The class block for one function's dossier entry, or "" when it is not a vtable method."""
    c = ix.class_of(addr)
    if not c:
        return ""
    vtable, slot, size = c
    parts = [f"vtable {vtable} slot {slot} of {size}"]
    ms = ix.method_strings(vtable)
    if ms:
        parts.append("method strings: " + "; ".join(f'"{s}"' for s, _ in ms.most_common(limit)))
    ns = ix.near_strings(vtable)
    if ns:
        parts.append("near strings: " + "; ".join(f'"{s}"' for s, _ in ns.most_common(limit)))
    named = ix.named_slots(vtable, 3)
    if named:
        parts.append("named methods: " + "; ".join(f"slot {i} {f} = {t}" for i, f, t in named))
    return "class: " + " | ".join(parts)
