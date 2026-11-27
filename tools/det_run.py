#!/usr/bin/env python3
"""One determinism run: python -I tools/det_run.py <label> [--seconds 40] [KEY=VAL ...]
Takes work/game.lock, starts work/build/mlb_det.exe from work/build on a copy of the profile, stops it after the
seconds, releases the lock. Writes work/det/<label>.log and, with MLB_HARNESS_DET_TRACE unset, <label>.trace."""
import os, shutil, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.realpath(os.path.join(ROOT, "work"))
label, secs, extra = sys.argv[1], 40, {}
for a in sys.argv[2:]:
    if a.startswith("--seconds="): secs = float(a.split("=")[1])
    else: k, v = a.split("=", 1); extra[k] = v
out = os.path.join(W, "det"); os.makedirs(out, exist_ok=True)
if b"mlb" in subprocess.run(["tasklist"], capture_output=True).stdout.lower().replace(b"mlbts", b""):
    raise SystemExit("a game is running")
lock = os.path.join(W, "game.lock")
os.mkdir(lock)   # fails when held
try:
    b = os.path.join(W, "build")
    prof = os.path.join(b, "profile_det")
    env = dict(os.environ, MLB_EXEFS=b + "/game/exefs", MLB_ROMFS=b + "/game/romfs", MLB_PROFILE=prof,
               MLB_SAMPLER="off", MLB_LOG_TIME="1")
    env["MLB_HARNESS_DET_TRACE"] = os.path.join(out, label + ".trace")
    env.update(extra)
    with open(os.path.join(out, label + ".log"), "wb") as log:
        p = subprocess.Popen([os.path.join(b, "mlb_det.exe")], cwd=b, env=env, stdout=log, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < secs and p.poll() is None: time.sleep(0.5)
        if p.poll() is None:
            p.terminate()
            try: p.wait(10)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
    print(label, "exit", p.returncode, "ran", round(time.time() - t0, 1), "s")
finally:
    os.rmdir(lock)
