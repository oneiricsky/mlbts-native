#!/usr/bin/env python3
"""Turn one game run's log into one JSON summary, so runs can be compared without re-reading logs.

  python -I tools/perf_summary.py work/build/run_perf_C1.out [more logs] [--out summary.json]

Reads the game's own once-a-minute "frametime:" lines, the "hdtex: texture ..." swap lines and the first
"Options - Online: ..." game line. One object per log; with several logs the output is a list."""
import json
import re
import sys

FRAME = re.compile(r"frametime: 60 s: (\d+) frames in ([\d.]+) s, mean ([\d.]+) fps, 1% low ([\d.]+) fps, "
                   r"over 25 ms (\d+), 50 ms (\d+), 100 ms (\d+)")
SWAP = re.compile(r"hdtex: texture \S+ (\d+)x(\d+) .* is (\S+): image (\d+)x(\d+).*?([\d.]+) ms\s*$")
OPTIONS = re.compile(r"Options - Online: (\d), .*?RTTS: (\d), DD: (\d)")
WORST = re.compile(r"frametime:\s+worst frame (\d+): ([\d.]+) ms")
SLOW = re.compile(r"perf: slow frame (\d+): ([\d.]+) ms")
GPULINE = re.compile(r"perf: frame \d+: .*?vram (\d+) of (\d+) MiB.*?ram working set (\d+) MiB")
HDERR = re.compile(r"hdtex: .*(cannot open|cannot read|not handled|odd header|not a PS5|leaves no level|outside the file|cannot be sampled|creation failed)")


def window_row(m):
    frames, secs, mean, low, o25, o50, o100 = m.groups()
    return {"frames": int(frames), "seconds": float(secs), "mean_fps": float(mean), "low1_fps": float(low),
            "over25": int(o25), "over50": int(o50), "over100": int(o100)}


def pool(rows):
    if not rows:
        return None
    frames = sum(r["frames"] for r in rows)
    secs = sum(r["seconds"] for r in rows)
    mins = secs / 60.0
    return {"windows": len(rows), "mean_fps": round(frames / secs, 2) if secs else None,
            "mean_window_low1_fps": round(sum(r["low1_fps"] for r in rows) / len(rows), 2),
            "over25_per_min": round(sum(r["over25"] for r in rows) / mins, 2),
            "over50_per_min": round(sum(r["over50"] for r in rows) / mins, 2),
            "over100_per_min": round(sum(r["over100"] for r in rows) / mins, 2)}


def summarize(path):
    windows, swaps, errors, options = [], [], 0, None
    worst, slow, vram, ram = [], [], [], []
    with open(path, errors="replace") as f:
        for line in f:
            m = FRAME.search(line)
            if m:
                windows.append(window_row(m))
                continue
            m = WORST.search(line)
            if m:
                worst.append(float(m.group(2)))
                continue
            m = SLOW.search(line)
            if m:
                slow.append(float(m.group(2)))
                continue
            m = GPULINE.search(line)
            if m:
                vram.append(int(m.group(1)))
                ram.append(int(m.group(3)))
                continue
            m = SWAP.search(line)
            if m:
                swaps.append((m.group(3), float(m.group(6))))
                continue
            if HDERR.search(line):
                errors += 1
            elif options is None:
                m = OPTIONS.search(line)
                if m:
                    options = {"online": int(m.group(1)), "rtts": int(m.group(2)), "dd": int(m.group(3))}
    ms = [t for _, t in swaps]
    extra = {}
    if worst:
        extra["worst_frame_ms"] = max(worst)
    if slow:
        extra["slow_frames_logged"] = len(slow)
        extra["slowest_logged_ms"] = max(slow)
    if vram:
        extra["vram_max_mib"] = max(vram)
        extra["ram_working_set_max_mib"] = max(ram)
    res = {"log": path, "windows": windows,
            "all_windows": pool(windows),
            "windows_2_on": pool(windows[1:]),
            "first_window_frames": windows[0]["frames"] if windows else None,
            "hdtex": {"swaps_logged": len(swaps), "colour": sum("-COLOR" in p for p, _ in swaps),
                      "normal": sum("-NORMAL" in p for p, _ in swaps), "load_ms_total": round(sum(ms), 1),
                      "load_ms_max": max(ms) if ms else None, "errors": errors,
                      "note": "the game logs only the first 64 swaps"},
            "first_options_line": options if options else "unknown"}
    if extra:
        res["extra"] = extra
    return res


def main(argv):
    out, paths = None, []
    it = iter(argv)
    for a in it:
        if a == "--out":
            out = next(it, None)
        else:
            paths.append(a)
    if not paths or out == "":
        sys.exit(__doc__)
    res = [summarize(p) for p in paths]
    text = json.dumps(res[0] if len(res) == 1 else res, indent=1)
    if out:
        with open(out, "w") as f:
            f.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
