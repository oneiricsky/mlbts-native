#!/usr/bin/env python3
"""Developer harness runner: unattended, repeatable game runs from a scenario file.

  python -I tools/harness.py run   tools/scenarios/x.scn [--env KEY=VAL ...] [--exe PATH] [--slot NAME]
  python -I tools/harness.py ab    x.scn --a MLB_MSDF_SKIP=0 --b MLB_MSDF_SKIP=1 [--runs 2]
  python -I tools/harness.py smoke
  python -I tools/harness.py compare <run folder A> <run folder B>
  python -I tools/harness.py restore <backup> --confirm <backup>

Every run goes through tools/game.py in a slot (work/runs/<slot>, default `harness`): its own copy of the exe, its own
log and a copy of the saves, refreshed from the real profile at each run, which is so never written. `ab` compares
dumps, not times, so it runs shared with other games (--mode exclusive for a machine to itself); it waits for its turn
(--wait). --real-profile is the old way: the game runs on the real profile itself from the exe's folder, after its
save, save-tx and playtime.txt were copied to work/harness/backups/<timestamp> (the newest 10 are kept; only folders
this tool made are ever deleted), and only when no other game is live; `restore` puts a backup back.

A scenario is `key = value` lines (name, home, away, seed, fixed_clock, stop_after_s, stop_at_marker, dump (repeatable),
markers, framelog). The runner gives it to the game as MLB_HARNESS=<file>, dumps go to MLB_HARNESS_OUT=<run>/dumps in
game.py's run folder, and the game stops itself at stop_after_s. Each run leaves, in work/harness/<date>/<name>-<n>/:
scenario.scn and summary.json (and diff/ when something differs); summary.json names game.py's run folder, which holds
game.out, mlb.log, result.json and dumps/. These hold game data and are never committed.

Exit status: 0 fine, 1 a difference or a failed check, 2 the run could not happen (no audio device, no turn, bad input).
Tests: python -I -m unittest discover -s tools -p test_harness.py"""
import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN = os.environ.get("MLB_HARNESS_MAIN") or "D:/AI/Apps/mlbts-native"   # the main checkout holds the built game
STALL_MS = 3000          # a single frame longer than this counts as a stall
MIN_FPS = 30.0           # a smoke run slower than this is not sane
SCENARIO_KEYS = {"name", "home", "away", "seed", "fixed_clock", "stop_after_s", "stop_at_marker", "dump", "markers", "framelog"}
SMOKE_SCENARIO = """name = smoke
home = 0
away = 1
seed = 1
fixed_clock = 1
stop_after_s = %s
dump = texture:fmt=0x25,size=512x512
"""


class HarnessError(Exception):
    pass


class ScenarioError(HarnessError):
    pass


def load_tool(name):
    # -I removes tools/ from sys.path, so sibling scripts load by path.
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


game = load_tool("game")   # tools/game.py: slots, turns, the game's process
bench = load_tool("bench")


# ---- scenario ----------------------------------------------------------------------------------------------------

def parse_scenario(text):
    s = {"dump": [], "extra": {}}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not sep or not key:
            raise ScenarioError("scenario line %d is not 'key = value': %r" % (n, raw))
        try:
            if key in ("home", "away"):
                s[key] = int(val)
                if not 0 <= s[key] <= 29:
                    raise ScenarioError("scenario line %d: %s must be 0..29, got %s" % (n, key, val))
            elif key in ("seed",):
                s[key] = int(val, 0)
            elif key == "fixed_clock":
                if val not in ("0", "1"):
                    raise ScenarioError("scenario line %d: fixed_clock must be 0 or 1, got %s" % (n, val))
                s[key] = int(val)
            elif key == "stop_after_s":
                s[key] = float(val)
                if s[key] <= 0:
                    raise ScenarioError("scenario line %d: stop_after_s must be above 0" % n)
            elif key == "dump":
                if not val:
                    raise ScenarioError("scenario line %d: dump needs a value such as texture:fmt=0x25,size=512x512" % n)
                s["dump"].append(val)
            elif key in SCENARIO_KEYS:
                s[key] = val
            else:
                s["extra"][key] = val
        except ValueError:
            raise ScenarioError("scenario line %d: bad value for %s: %r" % (n, key, val))
    return s


def load_scenario(path):
    try:
        with open(path, encoding="utf-8") as f:
            s = parse_scenario(f.read())
    except OSError as e:
        raise ScenarioError("cannot read scenario %s: %s" % (path, e))
    s.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    return s


# ---- log reading ---------------------------------------------------------------------------------------------------
def parse_markers(log):
    return [(m.group(1), int(m.group(2)), float(m.group(3))) for m in game.MARKER_LINE.finditer(log)]


audio_state = game.audio_state


def marker_fps(markers):
    if len(markers) < 2:
        return None
    (_, f0, t0), (_, f1, t1) = markers[0], markers[-1]
    return (f1 - f0) / (t1 - t0) if t1 > t0 else None


# ---- dump comparison -----------------------------------------------------------------------------------------------

def list_files(d):
    out = {}
    for base, _, names in os.walk(d):
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, d).replace("\\", "/")] = p
    return out


def compare_dumps(dir_a, dir_b):
    """Byte-for-byte comparison of two dump folders. [] means every file is identical."""
    import numpy as np
    fa, fb = list_files(dir_a), list_files(dir_b)
    diffs = []
    for name in sorted(set(fa) | set(fb)):
        if name not in fb:
            diffs.append({"file": name, "kind": "missing in B"})
        elif name not in fa:
            diffs.append({"file": name, "kind": "missing in A"})
        else:
            a = np.fromfile(fa[name], dtype=np.uint8)
            b = np.fromfile(fb[name], dtype=np.uint8)
            if a.size != b.size:
                diffs.append({"file": name, "kind": "size", "size_a": int(a.size), "size_b": int(b.size)})
            elif not np.array_equal(a, b):
                diffs.append({"file": name, "kind": "content", "bytes_differ": int((a != b).sum()), "size": int(a.size)})
    return diffs


def load_pixels(path):
    """(array h x w x c uint8, how) for an image file, or raw bytes shaped by a WxH in the file name."""
    import numpy as np
    if os.path.splitext(path)[1].lower() in (".png", ".bmp", ".tga", ".jpg", ".jpeg", ".tif", ".tiff"):
        from PIL import Image
        a = np.asarray(Image.open(path))
        return (a[:, :, None] if a.ndim == 2 else a), "image"
    raw = np.fromfile(path, dtype=np.uint8)
    m = re.findall(r"(\d+)x(\d+)", os.path.basename(path))
    if m:
        w, h = int(m[-1][0]), int(m[-1][1])
        if w * h and raw.size % (w * h) == 0 and 1 <= raw.size // (w * h) <= 4:
            return raw.reshape(h, w, raw.size // (w * h)), "raw"
    w = 1024
    pad = (-raw.size) % w
    return np.concatenate([raw, np.zeros(pad, np.uint8)]).reshape(-1, w, 1), "strip"


def write_diff_image(path_a, path_b, out_png):
    """White where a pixel differs in any channel, black elsewhere. Returns the count of differing pixels."""
    import numpy as np
    from PIL import Image
    a, _ = load_pixels(path_a)
    b, _ = load_pixels(path_b)
    if a.shape != b.shape:
        h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        c = min(a.shape[2], b.shape[2])
        a, b = a[:h, :w, :c], b[:h, :w, :c]
    mask = (a != b).any(axis=2)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    Image.fromarray((mask * 255).astype(np.uint8), "L").save(out_png)
    return int(mask.sum())


def read_head(path, n=1 << 20):
    with open(path, "rb") as f:
        return f.read(n)


def describe_diff(d):
    if d["kind"] == "content":
        return "%s: %d bytes differ%s" % (d["file"], d["bytes_differ"], " of %d" % d["size"] if "size" in d else "")
    if d["kind"] == "size":
        return "%s: different size (%d against %d bytes)" % (d["file"], d["size_a"], d["size_b"])
    return "%s: %s" % (d["file"], d["kind"])


def ab_verdict(label_a, label_b, diffs_ab, diffs_repeat, marker_mismatch, times_a, times_b, repeats_checked=True):
    lines = []
    if diffs_repeat:
        lines.append("INCONCLUSIVE: the same setting gave different dumps on a repeat, so the output is not repeatable "
                     "and an A/B difference proves nothing yet. Fix the run-to-run noise first (seed, clock).")
        lines += ["  repeat: " + describe_diff(d) for d in diffs_repeat]
    if diffs_ab or marker_mismatch:
        lines.append("DIFFERENT: %s and %s do not give the same result." % (label_a, label_b))
        lines += ["  " + describe_diff(d) for d in diffs_ab]
        if marker_mismatch:
            lines.append("  markers seen on only one side: %s" % ", ".join(marker_mismatch))
    elif not diffs_repeat:
        lines.append("IDENTICAL: every dump is the same byte for byte between %s and %s, and the same markers appeared." %
                     (label_a, label_b))
        if not repeats_checked:
            lines.append("  (one run each, so repeatability was not checked; use --runs 2 or more)")
    both = [m for m in times_a if m in times_b]
    if both:
        lines.append("Marker times in seconds (timing may differ without it being a fault):")
        for m in both:
            lines.append("  %-14s %s %.2f   %s %.2f   change %+.2f s" % (m, label_a, times_a[m], label_b, times_b[m], times_b[m] - times_a[m]))
    return "\n".join(lines)


# ---- one run -------------------------------------------------------------------------------------------------------

PROFILE_ITEMS = ("save", "save-tx", "playtime.txt")     # the owner's progress; caches, screenshots and logs are not copied
BACKUP_MARK = ".harness-backup"                         # only folders holding this file are ever pruned
KEEP_BACKUPS = 10


def real_profile():
    return os.environ.get("MLB_HARNESS_PROFILE") or MAIN + "/work/build/profile"


def backups_root():
    return os.environ.get("MLB_HARNESS_BACKUPS") or os.path.join(MAIN, "work", "harness", "backups")


def copy_items(src, dst):
    for it in PROFILE_ITEMS:
        s = os.path.join(src, it)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst, it), dirs_exist_ok=True)
        elif os.path.isfile(s):
            shutil.copy2(s, dst)


def prune_backups(root, keep=KEEP_BACKUPS):
    mine = sorted(n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n, BACKUP_MARK)))
    for n in mine[:-keep]:
        shutil.rmtree(os.path.join(root, n))


def backup_profile(profile, tag=""):
    """Copy save, save-tx and playtime.txt to <backups>/<timestamp>; keep the newest 10 this tool made."""
    root = backups_root()
    os.makedirs(root, exist_ok=True)
    base = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + tag
    d, n = os.path.join(root, base), 1
    while os.path.exists(d):
        n += 1
        d = os.path.join(root, "%s-%d" % (base, n))
    os.makedirs(d)
    copy_items(profile, d)
    with open(os.path.join(d, BACKUP_MARK), "w") as f:
        f.write("made by tools/harness.py from %s\n" % profile)
    prune_backups(root)
    return d


def restore_profile(backup, profile):
    """Make save, save-tx and playtime.txt in `profile` match `backup` (files only; the caller made a safety backup)."""
    for it in PROFILE_ITEMS:
        src, dst = os.path.join(backup, it), os.path.join(profile, it)
        if os.path.isdir(src):
            keep = {os.path.relpath(os.path.join(b, f), src) for b, _, fs in os.walk(src) for f in fs}
            for b, _, fs in os.walk(dst):
                for f in fs:
                    if os.path.relpath(os.path.join(b, f), dst) not in keep:
                        os.remove(os.path.join(b, f))
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif os.path.isfile(src):
            shutil.copy2(src, profile)


def run_env(scn_path, dumps_dir, extra, profile):
    """The whole environment of a --real-profile run: measured without diagnostics, the game from its own folder on
    the real profile."""
    common = {
        "MLB_EXEFS": MAIN + "/work/build/game/exefs",
        "MLB_ROMFS": MAIN + "/work/build/game/romfs",
        "MLB_PROFILE": profile,
        "MLB_HARNESS": os.path.abspath(scn_path),
        "MLB_HARNESS_OUT": os.path.abspath(dumps_dir),
    }
    return bench.run_env(common, extra)


def launch_args(exe):
    return [sys.executable, "-I", exe] if exe.lower().endswith(".py") else [exe]


def default_exe():
    return os.environ.get("MLB_BENCH_EXE") or os.path.join(MAIN, "work", "build", "mlb.exe")


def next_run_dir(out, name):
    os.makedirs(out, exist_ok=True)
    n = 1
    while True:
        d = os.path.join(out, "%s-%d" % (name, n))
        try:
            os.mkdir(d)
            return d
        except FileExistsError:
            n += 1


def harness_env(extra):
    """What a slot run adds to the environment (the rest is game.py's): no setting that would change the picture or
    take screenshots, the sampler off and MLB_TRACE=perf, then the caller's settings. None removes a variable."""
    over = bench.overlay({})
    over.update(extra)
    return over


def run_one(scn_path, scn, extra_env, exe, folder, grace, slot="harness", real=False, mode="shared", wait=1800):
    """Run the game once, filling `folder`. Game-level trouble is recorded in the result, not raised.
    Default: through tools/game.py in the slot, on a copy of the real saves. real=True: the old way, on the real
    profile itself after a backup, alone on the machine (_run_real)."""
    os.makedirs(folder, exist_ok=True)
    with open(scn_path, "rb") as src, open(os.path.join(folder, "scenario.scn"), "wb") as dst:
        dst.write(src.read())
    limit = scn.get("stop_after_s", 60) + grace
    res = {"profile": None, "backup": None, "name": scn["name"], "scenario": os.path.abspath(scn_path), "exe": os.path.abspath(exe),
           "env": {k: extra_env[k] for k in sorted(extra_env)}, "started": datetime.datetime.now().isoformat(timespec="seconds")}
    if real:
        code, hung, log_path, dumps = _run_real(scn_path, extra_env, exe, folder, limit, res, wait)
        with open(log_path, encoding="utf-8", errors="replace") as f:
            log = f.read()
        markers, audio, fatal = parse_markers(log), audio_state(log), "FATAL:" in log
        perf = load_tool("perf_summary").summarize(log_path)
        res.update({"audio": audio, "fatal": fatal, "markers": markers, "dumps_dir": dumps,
                    "dumps": {n: os.path.getsize(p) for n, p in sorted(list_files(dumps).items())}})
        how = "killed"
    else:
        game.prepare(slot, exe=exe)          # the slot is made once; its exe follows the build
        try:
            r = game.run(slot, env=harness_env(extra_env), scenario=scn_path, mode=mode, wait=wait, timeout=limit,
                         real_profile=real_profile())
        except game.NoTurn as e:
            raise HarnessError("no turn for a run in slot %s: %s" % (slot, e))
        with open(r["out"], encoding="utf-8", errors="replace") as f:   # what the game printed: the same lines as mlb.log
            text = f.read()
        res.update({"profile": os.path.join(game.slot_path(slot), "profile"), "slot_run": r["run_dir"], "log": r["log"],
                    "dumps_dir": os.path.join(r["run_dir"], "dumps"), "dumps": r.get("dumps", {}), "out": r["out"],
                    "exit_code": r["exit_code"], "seconds": r["seconds"], "audio": audio_state(text),
                    "markers": parse_markers(text), "fatal": "FATAL:" in text,
                    "window_title": r["window_title"], "contended": r["contended"],
                    "first_run_of_slot": r["first_run_of_slot"]})
        code, hung, how = r["exit_code"], r["ended"] != "by itself", r["ended"]
        perf = load_tool("perf_summary").summarize(r["out"])
    res.update({"marker_fps": marker_fps(res["markers"]), "perf": perf, "hung": hung})
    res["worst_frame_ms"] = (perf.get("extra") or {}).get("worst_frame_ms")
    if hung:
        res["exit"] = "did not stop by itself within %d s; %s" % (limit, "closed on request" if how == "after a close request" else "killed")
    elif code != 0 or res["fatal"]:
        res["exit"] = "crashed (exit code %s%s)" % (code, ", FATAL line in the log" if res["fatal"] else "")
    else:
        res["exit"] = "stopped by itself"
    with open(os.path.join(folder, "summary.json"), "w") as f:
        json.dump(res, f, indent=1)
        f.write("\n")
    return res


def _run_real(scn_path, extra_env, exe, folder, limit, res, wait):
    """The old way, behind --real-profile: the game runs on the real profile itself from its own folder, after its
    saves were backed up, and only when no other game is live. Returns (exit code, whether it had to be killed, the
    log, the dumps folder)."""
    profile = real_profile()
    dumps, log_path = os.path.join(folder, "dumps"), os.path.join(folder, "game.log")
    os.makedirs(dumps, exist_ok=True)
    with game.admission("exclusive", wait=wait) as turn:
        if not turn.ok:
            raise HarnessError("no turn for a run on the real profile: %s" % turn.why)
        res["backup"] = backup_profile(profile)
        nm = os.path.basename(res["backup"])
        print("profile: REAL %s; save backup %s (undo with: restore %s --confirm %s)" % (profile, res["backup"], nm, nm), flush=True)
        res["profile"] = profile
        env = run_env(scn_path, dumps, extra_env, profile)
        t0 = time.time()
        proc = None
        try:
            with open(log_path, "wb") as log:
                proc = subprocess.Popen(launch_args(exe), cwd=os.path.dirname(os.path.abspath(exe)), env=env,
                                        stdout=log, stderr=subprocess.STDOUT)
                while proc.poll() is None and time.time() - t0 < limit:
                    time.sleep(0.25)
                hung = proc.poll() is None
                if hung:
                    proc.kill()
                    proc.wait()
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
    res.update({"exit_code": proc.returncode, "seconds": round(time.time() - t0, 1)})
    return proc.returncode, hung, log_path, dumps


NO_AUDIO = ("no audio output device: the game's log says 'audout: no output device', so it sits at the loading screen and "
            "never reaches the match. Wake the speakers or plug in an output and run again.")


def run_problem(res):
    """A plain sentence when the run itself went wrong, else None."""
    if res["audio"] == "none":
        return NO_AUDIO
    if res["hung"] or res["exit"].startswith("crashed"):
        return "the game %s. See %s." % (res["exit"], "game.log")
    return None


def summary_line(res, folder):
    fps = res.get("marker_fps")
    return "%s: %s in %s s, %d marker(s)%s, %d dump file(s). Folder: %s" % (
        res["name"], res["exit"], res["seconds"], len(res["markers"]),
        "" if fps is None else ", %.1f fps between first and last marker" % fps, len(res["dumps"]), folder)


# ---- commands -------------------------------------------------------------------------------------------------------

def parse_assign(text):
    k, sep, v = text.partition("=")
    if not sep or not k:
        raise HarnessError("%r must look like KEY=VALUE" % text)
    return k, v


def out_root(a):
    return os.path.abspath(a.out or os.path.join(ROOT, "work", "harness", datetime.date.today().isoformat()))


def cmd_run(a):
    scn = load_scenario(a.scenario)
    extra = dict(parse_assign(e) for e in a.env)
    folder = next_run_dir(out_root(a), scn["name"])
    res = run_one(a.scenario, scn, extra, a.exe, folder, a.grace, slot=a.slot, real=a.real_profile, mode=a.mode, wait=a.wait)
    print(summary_line(res, folder))
    problem = run_problem(res)
    if problem:
        print("FAIL: " + problem)
        return 2 if res["audio"] == "none" else 1
    return 0


def mean_times(results):
    acc = {}
    for r in results:
        for name, _, t in r["markers"]:
            acc.setdefault(name, []).append(t)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def cmd_ab(a):
    scn = load_scenario(a.scenario)
    sides = {"a": dict(parse_assign(e) for e in a.a), "b": dict(parse_assign(e) for e in a.b)}
    common = dict(parse_assign(e) for e in a.env)
    folder = next_run_dir(out_root(a), scn["name"] + "-ab")
    label = {k: " ".join("%s=%s" % kv for kv in v.items()) or "(default)" for k, v in sides.items()}
    print("A = %s\nB = %s\n%d run(s) each, alternating, folder %s" % (label["a"], label["b"], a.runs, folder), flush=True)
    results = {"a": [], "b": []}
    for n in range(1, a.runs + 1):
        for side in ("a", "b"):
            tag = "%s-%d" % (side, n)
            print("== %s %s" % (tag, label[side]), flush=True)
            sub = os.path.join(folder, tag)
            os.makedirs(sub)
            res = run_one(a.scenario, scn, {**common, **sides[side]}, a.exe, sub, a.grace, slot=a.slot, real=a.real_profile,
                      mode=a.mode, wait=a.wait)
            print("   " + summary_line(res, sub), flush=True)
            problem = run_problem(res)
            if problem:
                print("FAIL: " + problem)
                return 2 if res["audio"] == "none" else 1
            results[side].append(res)
    dumps = lambda side, n: results[side][n - 1]["dumps_dir"]   # slot runs keep their dumps in game.py's run folder
    diffs_ab = compare_dumps(dumps("a", 1), dumps("b", 1))
    repeat = []
    for side in ("a", "b"):
        for n in range(2, a.runs + 1):
            repeat += [dict(d, file="%s-%d vs %s-1: %s" % (side, n, side, d["file"])) for d in compare_dumps(dumps(side, 1), dumps(side, n))]
    names = lambda side: {m[0] for m in results[side][0]["markers"]}
    mismatch = sorted(names("a") ^ names("b"))
    for d in diffs_ab:
        if d["kind"] == "content":
            png = os.path.join(folder, "diff", d["file"].replace("/", "_") + ".png")
            d["differing_pixels"] = write_diff_image(os.path.join(dumps("a", 1), d["file"]), os.path.join(dumps("b", 1), d["file"]), png)
    text = ab_verdict(label["a"], label["b"], diffs_ab, repeat, mismatch, mean_times(results["a"]), mean_times(results["b"]),
                      repeats_checked=a.runs > 1)
    if diffs_ab and any(d["kind"] == "content" for d in diffs_ab):
        text += "\nDiff images (white = differing pixel) are in %s" % os.path.join(folder, "diff")
    text += "\nLogs and dumps of every run are kept in %s" % folder
    print("\n" + text)
    with open(os.path.join(folder, "verdict.txt"), "w") as f:
        f.write(text + "\n")
    return 1 if (diffs_ab or mismatch or repeat) else 0


def folder_view(path):
    """(the dumps folder, the summary) of a run folder: an old one with its own dumps/, or a slot run whose dumps are
    in game.py's run folder."""
    summary = os.path.join(path, "summary.json")
    res = None
    if os.path.isfile(summary):
        with open(summary) as f:
            res = json.load(f)
    dumps = (res or {}).get("dumps_dir") or os.path.join(path, "dumps")
    return (dumps if os.path.isdir(dumps) else path), res


def cmd_compare(a):
    da, ra = folder_view(a.a)
    db, rb = folder_view(a.b)
    diffs = compare_dumps(da, db)
    ma = {m[0] for m in (ra or {"markers": []})["markers"]}
    mb = {m[0] for m in (rb or {"markers": []})["markers"]}
    for d in diffs:
        if d["kind"] == "content":
            png = os.path.join(os.path.abspath(a.b), "diff_vs_" + os.path.basename(os.path.abspath(a.a)), d["file"].replace("/", "_") + ".png")
            d["differing_pixels"] = write_diff_image(os.path.join(da, d["file"]), os.path.join(db, d["file"]), png)
    ta = mean_times([ra]) if ra else {}
    tb = mean_times([rb]) if rb else {}
    text = ab_verdict(os.path.basename(os.path.abspath(a.a)), os.path.basename(os.path.abspath(a.b)), diffs, [], sorted(ma ^ mb), ta, tb)
    print(text)
    return 1 if (diffs or ma ^ mb) else 0


def cmd_restore(a):
    src = a.backup if os.path.isdir(a.backup) else os.path.join(backups_root(), a.backup)
    name = os.path.basename(os.path.normpath(src))
    if not os.path.isfile(os.path.join(src, BACKUP_MARK)):
        raise HarnessError("%s is not a backup made by this tool (no %s file); nothing was changed." % (src, BACKUP_MARK))
    profile = real_profile()
    have = [it for it in PROFILE_ITEMS if os.path.exists(os.path.join(src, it))]
    if a.confirm != name:
        print("This would put %s from %s back into %s, replacing what is there (a safety backup of the current state is made first)." %
              (", ".join(have), src, profile))
        print("To do it, run again with: --confirm %s" % name)
        return 1
    with game.admission("exclusive", wait=a.wait) as turn:
        if not turn.ok:
            raise HarnessError("a game is running, so the saves are not restored: %s" % turn.why)
        safety = backup_profile(profile, "-pre-restore")
        restore_profile(src, profile)
    print("restored %s from %s; the state before the restore is saved in %s" % (", ".join(have), src, safety))
    return 0


def cmd_smoke(a):
    folder = next_run_dir(out_root(a), "smoke")
    scn_path = os.path.join(folder, "smoke-scenario.scn")
    with open(scn_path, "w") as f:
        f.write(SMOKE_SCENARIO % a.seconds)
    scn = load_scenario(scn_path)
    res = run_one(scn_path, scn, {}, a.exe, folder, a.grace, slot=a.slot, real=a.real_profile, mode=a.mode, wait=a.wait)
    print(summary_line(res, folder))
    fails = []
    if res["audio"] == "none":
        fails.append(NO_AUDIO)
    elif res["audio"] == "unknown":
        fails.append("the log has no 'audout:' line, so the game never reached its audio start-up; see game.log")
    if res["hung"]:
        fails.append("the game did not stop by itself (%s)" % res["exit"])
    elif res["exit"].startswith("crashed"):
        fails.append("the game crashed: %s" % res["exit"])
    if not res["markers"] and res["audio"] == "ok":
        fails.append("no harness marker line in the log: this build has no harness hooks, or the match never started")
    worst = res.get("worst_frame_ms")
    if worst is not None and worst > STALL_MS:
        fails.append("a stall: one frame took %.0f ms (limit %d ms)" % (worst, STALL_MS))
    fps = res.get("marker_fps")
    if fps is None:
        fps = ((res["perf"] or {}).get("all_windows") or {}).get("mean_fps")
    if fps is not None and fps < MIN_FPS:
        fails.append("the frame rate is too low: %.1f fps (needs %.0f or more)" % (fps, MIN_FPS))
    elif fps is None and res["audio"] == "ok" and not res["hung"] and not res["exit"].startswith("crashed"):
        fails.append("no frame rate could be worked out (needs two marker lines or one perf line)")
    texture = [n for n, size in res["dumps"].items() if size > 0]
    if texture and all(not any(read_head(os.path.join(res["dumps_dir"], n))) for n in texture):
        fails.append("the dumped texture is all zeros")
    if not texture and res["audio"] == "ok" and not res["hung"]:
        fails.append("the field texture was not written (no non-empty file in dumps/)")
    if fails:
        print("\nSMOKE FAIL:")
        for f in fails:
            print("  FAIL: " + f)
        print("Log kept in %s" % res["log"])
        return 2 if res["audio"] == "none" else 1
    print("\nSMOKE PASS: audio ok, no crash, no stall (worst frame %s ms), %s fps, field texture written." %
          ("n/a" if worst is None else "%.0f" % worst, "n/a" if fps is None else "%.1f" % fps))
    return 0


def add_run_options(p, grace_default=240):
    p.add_argument("--exe", default=default_exe(), help="the game (default work/build/mlb.exe in the main checkout, or MLB_BENCH_EXE)")
    p.add_argument("--out", help="output folder (default work/harness/<date>)")
    p.add_argument("--slot", default="harness", help="the tools/game.py slot the runs go through (default %(default)s)")
    p.add_argument("--mode", choices=("shared", "exclusive"), default="shared",
                   help="shared: run beside other games (default; this tool compares dumps, not times); exclusive: only with no game live")
    p.add_argument("--wait", type=float, default=1800, help="seconds to wait for a turn (default %(default)s)")
    p.add_argument("--real-profile", action="store_true",
                   help="the old way: run on the real profile itself from the exe's folder, saves backed up first, only with no game live")
    p.add_argument("--grace", type=float, default=grace_default,
                   help="seconds allowed beyond stop_after_s before the game is asked to close (default %(default)s)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one run of a scenario")
    r.add_argument("scenario")
    r.add_argument("--env", action="append", default=[], metavar="KEY=VAL")
    add_run_options(r)
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("ab", help="the same scenario twice with one setting changed; compare every dump byte for byte")
    b.add_argument("scenario")
    b.add_argument("--a", action="append", required=True, metavar="KEY=VAL", help="setting for side A (repeatable)")
    b.add_argument("--b", action="append", required=True, metavar="KEY=VAL", help="setting for side B (repeatable)")
    b.add_argument("--env", action="append", default=[], metavar="KEY=VAL", help="a setting for both sides")
    b.add_argument("--runs", type=int, default=2, help="runs per side, alternating A B A B (default 2; 2 also checks repeatability)")
    add_run_options(b)
    b.set_defaults(fn=cmd_ab)
    s = sub.add_parser("smoke", help="boot, short AI match, no crash, no stall, sane frame rate, field texture written")
    s.add_argument("--seconds", type=int, default=100, help="stop_after_s of the smoke scenario (default 100)")
    add_run_options(s)
    s.set_defaults(fn=cmd_smoke)
    q = sub.add_parser("restore", help="put the save files back from a backup this tool made")
    q.add_argument("backup", help="a backup folder name (under work/harness/backups) or a path")
    q.add_argument("--confirm", help="the backup's folder name, to confirm")
    q.add_argument("--wait", type=float, default=1800, help="seconds to wait until no game is live")
    q.set_defaults(fn=cmd_restore)
    c = sub.add_parser("compare", help="compare the dumps and markers of two run folders")
    c.add_argument("a")
    c.add_argument("b")
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except HarnessError as e:
        print("ERROR: %s" % e)
        return 2
    except KeyboardInterrupt:
        print("interrupted; the game was stopped")
        return 2


if __name__ == "__main__":
    sys.exit(main())
