"""Draw the theme-label progress charts for the wiki, and keep their numbers in one committed file.

    python -I tools/wiki_theming.py --refresh          # recompute tools/data/theming-pilot.json from work/theme*
    python -I tools/wiki_theming.py --out work/wiki    # write the two SVGs (content-named)

theming-<hash>.svg:        progress across the 200-function sample, the vtable experiment and the continuation.
theming-aspects-<hash>.svg: the accepted labels by aspect of the game, measured per function, beside the window-based
                           chart on the home page.

The numbers live in `tools/data/theming-pilot.json` so a checkout without `work/` can still rebuild the wiki. The two
hand audits are constants below because they are a person's verdicts, not something the reads can produce; each is
recorded on its sheet under `work/theme/` and `work/theme-vt/`.

Both charts use the dark card and palette from `tools/wiki_completeness.py`, so `tools/wiki_wcag_check.py` checks them
with the same rules.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
sys.path.insert(0, ROOT + "/tools")
from wiki_completeness import LEFT, BW, head, bar, legend

DATA = ROOT + "/tools/data/theming-pilot.json"

# verdicts of the two hand audits, each on a fixed sheet: 18 rows from the 200-function sample, 12 from the vtable
# experiment. "right" and "wrong" are decided rows; "unsure" are labels the dossier does not settle either way.
AUDIT = {
    "pilot": {"rows": 18, "right": 14, "wrong": 0, "unsure": 4},
    "vtable": {"rows": 12, "right": 10, "wrong": 0, "unsure": 2},
}


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_aspects(theme):
    A, B = {}, {}
    for folder, out in (("a", A), ("b", B)):
        for path in sorted(glob.glob(f"{theme}/reads/{folder}/out-*.jsonl")):
            for r in load_jsonl(path):
                out[r["addr"].lower()] = r.get("aspect", "")
    return A, B


def refresh():
    """Recompute the numbers from the run folders and write the committed JSON."""
    pilot, ev = ROOT + "/work/theme", ROOT + "/work/theme-vt"
    acc = load_jsonl(f"{pilot}/accepted.jsonl")
    ab = load_jsonl(f"{pilot}/abstained.jsonl")
    tiers = Counter(r.get("tier") for r in acc)
    reasons = Counter(r.get("reason") for r in ab)
    prior = {r["addr"]: r.get("prior_aspect", "") for r in load_jsonl(f"{pilot}/targets.jsonl")}
    A, B = _read_aspects(pilot)
    both = [a for a in A if a in B]
    agreed = sum(1 for a in both if A[a] == B[a] != "Unclear")
    n = int(json.load(open(f"{pilot}/batches/manifest.json"))["total"])

    roles = {}
    for line in open(f"{ROOT}/work/map/index/roles.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["module"] == "main":
            roles[r["addr"].lower()] = r
    eacc = {r["addr"]: r for r in load_jsonl(f"{ev}/accepted.jsonl")}
    eab = [r for r in load_jsonl(f"{ev}/abstained.jsonl")]
    eset = [a.lower() for a in json.load(open(f"{ev}/batches/manifest.json"))["batches"][0]["addrs"]]
    vt = [a for a in eset if roles[a].get("vtable")]
    ctl = [a for a in eset if not roles[a].get("vtable")]

    def group(addrs):
        tiers = Counter(eacc[a]["tier"] for a in addrs if a in eacc)
        reasons = Counter(r["reason"] for r in eab if r["addr"] in addrs)
        return {"functions": len(addrs), "accepted": dict(tiers),
                "no_evidence": reasons.get("both reads found no decisive evidence", 0),
                "not_settled": sum(v for k, v in reasons.items() if k != "both reads found no decisive evidence")}

    d = {
        "sample": n,
        "agreement": {"both_labelled": sum(1 for a in both if A[a] != "Unclear" and B[a] != "Unclear"), "agreed": agreed},
        "accepted": {k: tiers.get(k, 0) for k in ("strong", "medium", "weak")},
        "abstained": {"no_evidence": reasons.get("both reads found no decisive evidence", 0),
                      "not_settled": sum(v for k, v in reasons.items()
                                         if k != "both reads found no decisive evidence")},
        "window_prior_match": sum(1 for r in acc if prior.get(r["addr"]) == r["aspect"]),
        "vtable_round": group(vt),
        "control_round": group(ctl),
        "audit": AUDIT,
        "class_evidence": {"slots": 55394, "method_strings": 17509, "near_strings": 22123,
                           "either": 25243, "classes": 5813, "classes_without_strings": 4151},
        "aspects": dict(Counter(r["aspect"] for r in acc)),
        "vtable_aspects": dict(Counter(r["aspect"] for r in eacc.values())),
    }
    # The published continuation is reviewed separately from refreshing the two historical pilot runs.
    with open(DATA, encoding="utf-8") as f:
        d["continuation"] = json.load(f)["continuation"]
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(d, open(DATA, "w", encoding="utf-8", newline="\n"), indent=1)
    print(f"wrote {DATA}")
    return d


def svg_progress(d):
    accepted, abstained = d["accepted"], d["abstained"]
    a_total = sum(accepted.values())
    w, top, rowh = 1000, 148, 46
    h = top + rowh * 4 + 78
    out = head(w, h, "Where the theme labels stand",
               ["One label per function from two independent body reads; a third read settles disagreements.",
                f"{d['sample']} functions drawn across main: {a_total} labelled, {d['sample'] - a_total} not."],
               "Theme labels accepted across the pilot, vtable experiment and continuation")
    parts = [(accepted["strong"], "c"), (accepted["medium"], "i"), (accepted["weak"], "h"),
             (abstained["no_evidence"], "n"), (abstained["not_settled"], "q")]
    y = 84
    out.append(f'<text x="{LEFT - 12}" y="{y + 15}" font-size="11" class="f1" text-anchor="end">'
               f'{d["sample"]}-function sample</text>')
    out += bar(LEFT, y, BW, 22, parts)
    cx, total = LEFT, sum(n for n, _ in parts) or 1
    for n, _ in parts:
        sw = BW * n / total
        if n and sw >= 34:
            out.append(f'<text x="{cx + sw / 2:.1f}" y="{y + 15}" font-size="10" class="onbar" '
                       f'text-anchor="middle">{n}</text>')
        cx += sw
    out += legend(y + 44, [("c", f"strong {accepted['strong']}"), ("i", f"medium {accepted['medium']}"),
                           ("h", f"weak {accepted['weak']}"), ("n", f"no evidence {abstained['no_evidence']}"),
                           ("q", f"not settled {abstained['not_settled']}")])
    v = d["vtable_round"]
    y = top + rowh
    out.append(f'<text x="{LEFT - 12}" y="{y + 15}" font-size="11" class="f1" text-anchor="end">'
               f'vtable stubs, no evidence ({v["functions"]})</text>')
    vparts = [(v["accepted"].get("strong", 0), "c"), (v["accepted"].get("medium", 0), "i"),
              (v["no_evidence"], "n"), (v["not_settled"], "q")]
    out += bar(LEFT, y, BW, 22, vparts)
    cx = LEFT
    for n, _ in vparts:
        sw = BW * n / (sum(x for x, _ in vparts) or 1)
        if n and sw >= 30:
            out.append(f'<text x="{cx + sw / 2:.1f}" y="{y + 15}" font-size="10" class="onbar" '
                       f'text-anchor="middle">{n}</text>')
        cx += sw
    out.append(f'<text x="{LEFT + BW + 10}" y="{y + 15}" font-size="10" class="f2">'
               f'from class: {sum(v["accepted"].values())} labelled</text>')
    c = d["control_round"]
    y = top + rowh * 2
    out.append(f'<text x="{LEFT - 12}" y="{y + 15}" font-size="11" class="f1" text-anchor="end">'
               f'controls, no vtable ({c["functions"]})</text>')
    out += bar(LEFT, y, BW, 22, [(sum(c["accepted"].values()), "h"), (c["no_evidence"], "n"),
                                 (c["not_settled"], "q")])
    out.append(f'<text x="{LEFT + BW + 10}" y="{y + 15}" font-size="10" class="f2">'
               f'{sum(c["accepted"].values())} labelled (weak)</text>')
    continuation = d["continuation"]
    accepted = continuation["accepted"]
    y = top + rowh * 3
    out.append(f'<text x="{LEFT - 12}" y="{y + 15}" font-size="11" class="f1" text-anchor="end">'
               f'continuation ({continuation["functions"]})</text>')
    out += bar(LEFT, y, BW, 22, [(accepted.get("strong", 0), "c"), (accepted.get("medium", 0), "i"),
                               (accepted.get("weak", 0), "h"), (continuation["abstained"], "n")])
    out.append(f'<text x="{LEFT + BW + 10}" y="{y + 15}" font-size="10" class="f2">'
               f'{sum(accepted.values())} labelled</text>')
    ag, both = d["agreement"]["agreed"], d["agreement"]["both_labelled"]
    au = d["audit"]
    rows = au["pilot"]["rows"] + au["vtable"]["rows"]
    right = au["pilot"]["right"] + au["vtable"]["right"]
    unsure = au["pilot"]["unsure"] + au["vtable"]["unsure"]
    out.append(f'<text x="{LEFT}" y="{h - 34}" font-size="11" class="f2">'
               f'Both readers named an aspect on {both} of {d["sample"]} and agreed on {ag} '
               f'({100.0 * ag / (both or 1):.0f}%). {d["window_prior_match"]} of the {a_total} labels just repeat the '
               f'window theme.</text>')
    out.append(f'<text x="{LEFT}" y="{h - 17}" font-size="11" class="f2">'
               f'Hand audit: {rows} labels checked, {right} right, 0 wrong, {unsure} unsure.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def svg_aspects(d):
    counts = Counter(d["aspects"])
    counts.update(d["vtable_aspects"])
    counts.update(d["continuation"]["aspects"])
    items = sorted(counts.items(), key=lambda kv: -kv[1])
    total = sum(n for _, n in items) or 1
    w, top, rowh = 1000, 128, 32
    h = top + rowh * len(items) + 34
    out = head(w, h, "Aspects measured per function",
               [f"{total} accepted labels across the pilot, vtable experiment and continuation.",
                "Each label applies to one function and is backed by evidence from its body or class."],
               "Accepted theme labels by aspect of the game, measured per function")
    for pct in (0, 25, 50, 75, 100):
        x = LEFT + BW * pct / 100
        out.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{h - 26}"/>')
        out.append(f'<text x="{x:.1f}" y="{top - 14}" font-size="9" class="f2" text-anchor="middle">{pct}%</text>')
    for i, (name, n) in enumerate(items):
        y = top + i * rowh
        shade = BW * n / total
        out.append(f'<text x="{LEFT - 12}" y="{y + 12}" font-size="11" class="f1" text-anchor="end">{name}</text>')
        out.append(f'<rect x="{LEFT}" y="{y}" width="{BW}" height="15" rx="3" class="track"/>')
        out.append(f'<rect x="{LEFT}" y="{y}" width="{shade:.1f}" height="15" rx="3" class="bar"/>')
        label = f"{100.0 * n / total:.0f}%"
        if shade >= 42:
            out.append(f'<text x="{LEFT + shade - 7:.1f}" y="{y + 12}" font-size="10" class="onbar" '
                       f'text-anchor="end">{label}</text>')
        else:
            out.append(f'<text x="{LEFT + shade + 7:.1f}" y="{y + 12}" font-size="10" class="f2">{label}</text>')
        out.append(f'<text x="{LEFT + BW + 10}" y="{y + 12}" font-size="10" class="f2">{n}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write(out, data=DATA):
    os.makedirs(out, exist_ok=True)
    d = json.load(open(data, encoding="utf-8"))
    names = {}
    for kind, body in (("theming", svg_progress(d)), ("theming-aspects", svg_aspects(d))):
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]
        name = f"{kind}-{digest}.svg"
        open(f"{out}/{name}", "w", encoding="utf-8", newline="\n").write(body)
        names[kind] = name
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ROOT + "/work/wiki")
    ap.add_argument("--refresh", action="store_true", help="recompute the numbers from work/theme and work/theme-vt")
    a = ap.parse_args()
    d = refresh() if a.refresh else json.load(open(DATA, encoding="utf-8"))
    if a.refresh and not os.path.exists(f"{a.out}/."):
        return 0
    print(json.dumps(d, indent=1))
    if os.path.exists(a.out):
        print("wrote " + ", ".join(write(a.out, DATA).values()))


if __name__ == "__main__":
    main()
