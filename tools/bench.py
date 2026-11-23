#!/usr/bin/env python3
"""Repeatable A/B comparison of game runs: upstream's method (docs/frame-rate.md, "Measuring").

  python -I tools/bench.py run --config off:MLB_HD_TEXTURES=off --config colour:MLB_HD_TEXTURES=hdtex_allc
  python -I tools/bench.py run --config A --config B:MLB_X=1 --runs 3 --seconds 400 --dry-run
  python -I tools/bench.py compare work/bench/2026-11-22          (a folder of run JSONs)
  python -I tools/bench.py compare off=a1.log off=a2.log colour=c1.log colour=c2.log

`run` starts the game once per run, alternating the configurations (A, B, A, B, ...), through tools/game.py in a slot
(work/runs/<slot>, default `bench`), with the sampler off and MLB_TRACE=perf, lets it play for --seconds, closes
it, and writes <out>/<label>-<n>.log and .json (the JSON is tools/perf_summary.py's summary plus the run's
settings). Each run is exclusive: it waits (--wait) until no game is live anywhere, and ordinary runs then wait
for it; a run that shared the machine anyway is marked contended. A slot's first run fills its caches and is
slower: let the slot run once before timing. `compare` prints, per label, the run count and the mean with its
spread (min to max) of each figure, and says when the runs are too few or the ranges overlap. The protocol is in
docs/dev-config.md, "Running a comparison"."""
import argparse
import datetime
import importlib.util
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_tool(name):
    # -I removes tools/ from sys.path, so sibling scripts load by path.
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


game = load_tool("game")   # tools/game.py: slots, turns, the game's process

# Settings that would change timing or take screenshots; a comparison run never inherits them.
DROPPED = ("MLB_SHOT", "MLB_DRAWLOG", "MLB_WATCH", "MLB_DISPATCH_DUMP", "MLB_STATEDUMP", "MLB_SAMPLER", "MLB_TRACE")


def load_summary():
    # -I removes the script's folder from sys.path, so load tools/perf_summary.py by path.
    spec = importlib.util.spec_from_file_location("perf_summary", os.path.join(HERE, "perf_summary.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_assign(text, what):
    key, sep, val = text.partition("=")
    if not sep or not key:
        sys.exit("%s must look like KEY=VALUE, got %r" % (what, text))
    return key, val


def parse_config(text):
    """LABEL or LABEL:KEY=VALUE[,KEY=VALUE...]"""
    label, _, rest = text.partition(":")
    if not label:
        sys.exit("a --config needs a label: %r" % text)
    env = dict(parse_assign(p, "a --config setting") for p in rest.split(",") if p)
    return label, env


def overlay(extra):
    """What a measurement run adds to the environment game.py builds: the settings that would change timing or take
    screenshots removed (None), the sampler off, MLB_TRACE=perf, then `extra`."""
    over = {k: None for k in DROPPED}
    over.update({"MLB_SAMPLER": "off", "MLB_TRACE": "perf"})
    over.update(extra)
    return over


def run_env(common, extra):
    env = {k: v for k, v in os.environ.items() if k not in DROPPED}
    env["MLB_SAMPLER"] = "off"
    env["MLB_TRACE"] = "perf"
    env.update(common)
    env.update(extra)
    return env


def schedule(configs, runs, counterbalance):
    order = []
    for n in range(1, runs + 1):
        row = list(configs)
        if counterbalance and n % 2 == 0:
            row.reverse()
        order += [(label, env, n) for label, env in row]
    return order


def cmd_run(a):
    configs = [parse_config(c) for c in a.config]
    if len(configs) < 1:
        sys.exit("give at least one --config")
    if len({label for label, _ in configs}) != len(configs):
        sys.exit("labels must be different")
    common = dict(parse_assign(e, "--env") for e in a.env)
    exe = os.path.abspath(a.exe)
    out = os.path.abspath(a.out or os.path.join(ROOT, "work", "bench", datetime.date.today().isoformat()))
    plan = schedule(configs, a.runs, a.counterbalance)
    print("exe: %s" % exe)
    print("slot: work/runs/%s (the game runs from tools/game.py's copy of the exe folder)" % a.slot)
    print("output: %s" % out)
    print("%d runs of %d s, each with the machine to itself, in this order: %s" %
          (len(plan), a.seconds, " ".join("%s-%d" % (l, n) for l, _, n in plan)))
    if a.dry_run:
        for label, env, n in plan:
            shown = run_env(common, env)
            keys = sorted(set(common) | set(env) | {"MLB_SAMPLER", "MLB_TRACE"})
            print("[dry-run] %s-%d: %s  (settings: %s)" % (label, n, exe, " ".join("%s=%s" % (k, shown[k]) for k in keys)))
        return
    if not os.path.isfile(exe):
        sys.exit("no game at %s (build it, or pass --exe / set MLB_BENCH_EXE)" % exe)
    try:
        game.prepare(a.slot, exe=exe)      # the slot is made once; its exe and the files beside it follow the build
    except game.GameError as e:
        sys.exit(str(e))
    os.makedirs(out, exist_ok=True)
    summary = load_summary()
    manifest = []
    for label, env, n in plan:
        stem = os.path.join(out, "%s-%d" % (label, n))
        over = overlay({**common, **env})
        print("== %s-%d: a turn with the machine to itself, then %s for %d s" % (label, n, os.path.basename(exe), a.seconds),
              flush=True)
        try:
            r = game.run(a.slot, env=over, mode="exclusive", wait=a.wait, timeout=a.seconds)
        except game.NoTurn as e:
            sys.exit("no turn for a timing run: %s" % e)
        shutil.copyfile(r["out"], stem + ".log")
        res = summary.summarize(stem + ".log")
        early = r["exit_code"] if r["ended"] == "by itself" and r["seconds"] < a.seconds else None
        res.update({"label": label, "run": n, "seconds": a.seconds, "started": r["started"],
                    "settings": {k: over.get(k) for k in sorted(set(common) | set(env) | {"MLB_SAMPLER", "MLB_TRACE"})},
                    "ended_early_with_code": early, "how_it_ended": r["ended"], "exit_code": r["exit_code"],
                    "first_run_of_slot": r["first_run_of_slot"], "contended": r["contended"], "shared_with": r["shared_with"],
                    "run_folder": r["run_dir"]})
        with open(stem + ".json", "w") as f:
            json.dump(res, f, indent=1)
            f.write("\n")
        manifest.append({"label": label, "run": n, "json": os.path.basename(stem) + ".json"})
        w = res["all_windows"]
        print("   %s: %s windows, mean %s fps, first window %s frames%s%s%s" %
              (os.path.basename(stem), len(res["windows"]), w["mean_fps"] if w else "n/a", res["first_window_frames"],
               "" if early is None else "  ENDED EARLY (exit code %s)" % early,
               "" if not r["contended"] else "  CONTENDED, with %s" % ", ".join(
                   o["slot"] or os.path.basename(o["image"]) for o in r["shared_with"]),
               "  (the slot's first run: its caches were still cold)" if r["first_run_of_slot"] else ""), flush=True)
        time.sleep(3)
    with open(os.path.join(out, "bench.json"), "w") as f:
        json.dump({"exe": exe, "seconds": a.seconds, "runs": manifest}, f, indent=1)
        f.write("\n")
    print("done. Compare with: python -I tools/bench.py compare %s" % out)


def load_runs(items):
    """[(label, summary dict)] from LABEL=path items, JSON files, logs, or folders of JSONs."""
    summary = None
    runs = []
    for item in items:
        if "=" in item and not os.path.exists(item):
            label, path = item.split("=", 1)
        else:
            label, path = None, item
        files = []
        if os.path.isdir(path):
            manifest = os.path.join(path, "bench.json")
            if os.path.isfile(manifest):
                with open(manifest) as fh:
                    files = [os.path.join(path, r["json"]) for r in json.load(fh)["runs"]]   # run order: the first label is the baseline
            else:
                files = sorted(os.path.join(path, f) for f in os.listdir(path) if f.endswith(".json"))
        else:
            files = [path]
        for f in files:
            if f.endswith(".json"):
                with open(f) as fh:
                    d = json.load(fh)
                if isinstance(d, list):
                    runs += [(label or x.get("label") or os.path.basename(f), x) for x in d]
                else:
                    runs.append((label or d.get("label") or os.path.splitext(os.path.basename(f))[0], d))
            else:
                if summary is None:
                    summary = load_summary()
                runs.append((label or os.path.splitext(os.path.basename(f))[0], summary.summarize(f)))
    return runs


def spread(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    mean = sum(vals) / len(vals)
    return mean, min(vals), max(vals)


def fmt(s, digits=1):
    if s is None:
        return "n/a"
    mean, lo, hi = s
    if lo == hi:
        return "%.*f" % (digits, mean)
    return "%.*f (%.*f-%.*f)" % (digits, mean, digits, lo, digits, hi)


def per_run(d):
    w = d["windows"]
    p2 = d.get("windows_2_on") or {}
    allw = d.get("all_windows") or {}
    h = d.get("hdtex") or {}
    return {
        "mean_fps_all": allw.get("mean_fps"),
        "over100_total": sum(x["over100"] for x in w) if w else None,
        "over50_total": sum(x["over50"] for x in w) if w else None,
        "first_window_frames": d.get("first_window_frames"),
        "mean_fps_2on": p2.get("mean_fps"),
        "low1_2on": p2.get("mean_window_low1_fps"),
        "over25_2on": p2.get("over25_per_min"),
        "over50_2on": p2.get("over50_per_min"),
        "over100_2on": p2.get("over100_per_min"),
        "swaps": h.get("swaps_logged"),
        "load_ms_total": h.get("load_ms_total"),
        "load_ms_max": h.get("load_ms_max"),
        "errors": h.get("errors"),
        "worst_frame_ms": (d.get("extra") or {}).get("worst_frame_ms"),
        "vram_max": (d.get("extra") or {}).get("vram_max_mib"),
        "ram_max": (d.get("extra") or {}).get("ram_working_set_max_mib"),
    }


def table(rows, header):
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    line = lambda r: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)).rstrip()
    return "\n".join([line(header), line(["-" * w for w in widths])] + [line(r) for r in rows])


def cmd_compare(a):
    runs = load_runs(a.inputs)
    if not runs:
        sys.exit("nothing to compare")
    labels = []
    groups = {}
    for label, d in runs:
        if label not in groups:
            labels.append(label)
            groups[label] = []
        groups[label].append(per_run(d))
    print("Runs per label: %s" % ", ".join("%s %d" % (l, len(groups[l])) for l in labels))
    if len({len(groups[l]) for l in labels}) > 1:
        print("WARNING: the labels have different run counts; the comparison is lopsided.")
    print("\nAll windows (the figures docs/reports/2026-11-22-hd-texture-performance.md uses; the first window holds loading and any boot stall):")
    head = ["label", "runs", "mean fps", "first window frames", "frames >50 ms", "frames >100 ms"]
    rows = []
    for l in labels:
        g = groups[l]
        rows.append([l, len(g), fmt(spread([r["mean_fps_all"] for r in g]), 2), fmt(spread([r["first_window_frames"] for r in g]), 0),
                     fmt(spread([r["over50_total"] for r in g]), 0), fmt(spread([r["over100_total"] for r in g]), 0)])
    print(table(rows, head))
    print("\nFrom the second minute on (per minute; mean with min-max over runs):")
    head = ["label", "runs", "mean fps", "1% low (mean of windows)", ">25 ms/min", ">50 ms/min", ">100 ms/min"]
    rows = []
    for l in labels:
        g = groups[l]
        rows.append([l, len(g), fmt(spread([r["mean_fps_2on"] for r in g]), 2), fmt(spread([r["low1_2on"] for r in g]), 1),
                     fmt(spread([r["over25_2on"] for r in g]), 1), fmt(spread([r["over50_2on"] for r in g]), 1),
                     fmt(spread([r["over100_2on"] for r in g]), 1)])
    print(table(rows, head))
    if any(r["swaps"] for l in labels for r in groups[l]):
        print("\nPS5 texture loads (the game logs only the first 64 swaps):")
        head = ["label", "runs", "swaps logged", "load ms total", "slowest load ms", "errors"]
        rows = []
        for l in labels:
            g = groups[l]
            rows.append([l, len(g), fmt(spread([r["swaps"] for r in g]), 0), fmt(spread([r["load_ms_total"] for r in g]), 1),
                         fmt(spread([r["load_ms_max"] for r in g]), 1), fmt(spread([r["errors"] for r in g]), 0)])
        print(table(rows, head))
    if any(r["worst_frame_ms"] is not None or r["vram_max"] is not None for l in labels for r in groups[l]):
        print()
        print("From the log's own worst-frame and MLB_TRACE=perf lines:")
        head = ["label", "runs", "worst frame ms", "vram max MiB", "ram working set max MiB"]
        rows = []
        for l in labels:
            g = groups[l]
            rows.append([l, len(g), fmt(spread([r["worst_frame_ms"] for r in g]), 0), fmt(spread([r["vram_max"] for r in g]), 0),
                         fmt(spread([r["ram_max"] for r in g]), 0)])
        print(table(rows, head))
    base = labels[0]
    if len(labels) > 1:
        print("\nVersus %s (a difference counts only if the min-max ranges do not overlap):" % base)
        checks = [("mean fps (from minute 2)", "mean_fps_2on", True), ("frames >100 ms per minute", "over100_2on", False),
                  ("frames >50 ms per minute", "over50_2on", False), ("1% low", "low1_2on", True)]
        for l in labels[1:]:
            few = min(len(groups[base]), len(groups[l]))
            for name, key, higher_better in checks:
                b = spread([r[key] for r in groups[base]])
                c = spread([r[key] for r in groups[l]])
                if b is None or c is None:
                    continue
                delta = c[0] - b[0]
                overlap = not (c[1] > b[2] or c[2] < b[1])
                if overlap:
                    verdict = "within noise (ranges overlap)"
                else:
                    good = (delta > 0) == higher_better
                    word = ("better" if good else "worse") if few >= 3 else ("looks better" if good else "looks worse")
                    verdict = "%s, ranges do not overlap%s" % (word, "" if few >= 3 else " (fewer than 3 runs)")
                print("  %s vs %s, %s: %+.2f  %s" % (l, base, name, delta, verdict))
            if few < 3:
                print("  %s vs %s: only %d run(s) per label, so even a clear gap is indicative, not settled. Three or more runs each is safer." % (l, base, few))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run labelled configurations, alternating them")
    r.add_argument("--config", action="append", default=[], metavar="LABEL[:KEY=VAL,...]", help="a configuration; give it twice or more for an A/B")
    r.add_argument("--env", action="append", default=[], metavar="KEY=VAL", help="a setting added to every configuration")
    r.add_argument("--seconds", type=int, default=400, help="how long each run plays (default 400)")
    r.add_argument("--runs", type=int, default=2, help="runs per configuration (default 2)")
    r.add_argument("--counterbalance", action="store_true", help="flip the order every second round (A B B A) to cancel drift")
    r.add_argument("--exe", default=os.environ.get("MLB_BENCH_EXE") or os.path.join(ROOT, "work", "build", "mlb.exe"),
                   help="the game (default work/build/mlb.exe, or MLB_BENCH_EXE)")
    r.add_argument("--out", help="output folder (default work/bench/<date>)")
    r.add_argument("--slot", default="bench", help="the tools/game.py slot the runs go through (default %(default)s)")
    r.add_argument("--wait", type=float, default=1800, help="seconds to wait for a turn with the machine to itself (default %(default)s)")
    r.add_argument("--dry-run", action="store_true", help="print the plan and settings; start nothing")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("compare", help="compare runs per label")
    c.add_argument("inputs", nargs="+", metavar="[LABEL=]PATH", help="a folder of run JSONs, JSON files, or game logs (give LABEL= for logs)")
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main(sys.argv[1:])
