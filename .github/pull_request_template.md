## Summary

<!-- Describe what this PR changes and why. Link any related issue. -->

## Root Cause & Evidence

<!-- For bug fixes or graphics/audio/runtime changes:
- What did you observe? (screen, texture/guest address, RenderDoc capture, `mlb.log` / `[lm 0]` lines, crash symbolization)
- Why is this a root-cause fix rather than a per-screen workaround? -->

## Verification

<!-- Check what you actually ran after your final edit and note the results (e.g., fps impact, pass/fail counts). -->

- [ ] Built cleanly with `.venv/Scripts/python -I tools/build.py`
- [ ] Smoke-tested `work/build/mlb.exe` (no fps regression observed)
- [ ] Ran `work/build/mlb.exe --probe-fs` (if touching `fs_host.c` or file I/O)
- [ ] Ran `.venv/Scripts/python -I tools/shader_smoke.py` (if touching shaders or `tools/xlate`)

## Checklist

- [ ] PR title uses Conventional Commits (`feat:`, `fix:`, `perf:`, `docs:`, `refactor:`, `chore:`)
- [ ] Works on Switch versions **1.0.20** and **1.0.15**, offline scope only
- [ ] No copyrighted game files, extracted assets, keys, or `work/` / `gamefiles/` artifacts included
- [ ] `runtime/core/` remains generic (MLB-specific code stays in `runtime/mlb/`)
- [ ] Changes to vendored files (`runtime/core/`, `runtime/gfx/`) are marked `fastball` with a comment explaining the observed case
- [ ] `THIRD_PARTY_NOTICES.md` updated (if any third-party code or dependency was added/adapted)
- [ ] No always-on slow diagnostics (gated behind F12/F9, `mlb.cfg` / `MLB_*`, or RenderDoc)
