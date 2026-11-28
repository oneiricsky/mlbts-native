# Contributing to Fastball

Thank you for your interest in contributing to the native Windows port of **MLB The Show 26** (Nintendo Switch, version **1.0.20**; 1.0.15 is still supported).

## Scope

- **Supported versions:** Switch versions **1.0.20** (primary) and **1.0.15**. A change that touches game addresses
  must work on both (`tools/addrmap.py` finds a 1.0.15 address in 1.0.20). Do not target other versions.
- **Playable scope:** Offline play only (Exhibition, Road to the Show, Franchise, menus, and local saves). Online play and Diamond Dynasty are out of scope.
- **Current focus:** Graphics correctness (missing/wrong images, lighting) and performance.

## Repository and Asset Safety

Never commit or upload proprietary material:

- Do **not** commit copyrighted game files, extracted game assets, encryption keys (`prod.keys`, `title.keys`), or local build/dump artifacts.
- Keep all dumps, extracted files, reference checkouts, and build outputs inside git-ignored directories (`gamefiles/`, `work/`, `refs/`). Add `.gitignore` rules before generating large local datasets.
- Pass key paths to tools (`%APPDATA%/Ryujinx/system/prod.keys` and `title.keys`); never print, copy, or hardcode key values.
- Keep the project buildable and research reproducible without distributing original game files.

## Development Setup

See [README.md](README.md) and [docs/runtime-port.md](docs/runtime-port.md) for full setup instructions.

- **Python:** Always invoke Python with `-I` so user site-packages do not load:
  ```powershell
  .venv/Scripts/python -I tools/build.py
  ```
- **Close before building:** `work/build/mlb.exe` is locked while running, which will cause linking to fail.
- **Sanity checks:**
  - Filesystem overrides: `work/build/mlb.exe --probe-fs`
  - Shader translator smoke test: `.venv/Scripts/python -I tools/shader_smoke.py`

## Code Guidelines

- **Keep generic and game-specific code separate:**
  - `runtime/core/` holds generic host runtime code (nothing MLB-specific).
  - `runtime/mlb/` holds MLB-specific services, boot, input, settings, and logging.
  - `recomp/` is kept unmodified from TotK Recomp (`ae30a61`).
- **Mark upstream changes:** Any edits to vendored files (`runtime/core/`, `runtime/gfx/`) must include a `fastball` comment explaining the observed case (screen, texture, address, or SDK behavior) that required the change.
- **Performance first:** Never regress frame rate. Diagnostic code must cost nothing during normal play—gate it behind `F12` (or `F9` under RenderDoc), a `mlb.cfg` / `MLB_*` setting, or RenderDoc. Remove temporary slow test code before committing.
- **Fix root causes with evidence:** Trace issues using RenderDoc (`tools/renderdoc.cmd`), frame captures, `mlb.log`, or profiler dumps (`tools/prof_report.py`) rather than adding per-screen workarounds.
- **Document discoveries:** Record significant findings in code comments and `docs/` (tagging confirmed binary/machine facts `[C]` and hypotheses `[H]` where appropriate). Avoid unnecessary abstractions.

## Third-Party Code and Attribution

- Preserve original copyright and attribution headers in all copied or adapted files.
- If you add or adapt third-party code or dependencies, document the source, commit/version, license, and target files in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Bug Reports and Debugging

- `work/build/logs/mlb.log` is overwritten on every launch—copy it before restarting if it contains relevant evidence.
- Attach `mlb.log` to bug reports (`[lm 0]` lines are game logs; `[host]` lines are host runtime logs).
- Symbolize `FATAL:` crash addresses with `llvm-symbolizer`:
  ```powershell
  llvm-symbolizer --obj=work/build/mlb.exe --relative-address <addr>
  ```
- For graphics bugs, press **F12** (or **F9** under RenderDoc) to capture the frame's draw log and render targets.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) for commit titles:

- `feat:` — new feature or capability
- `fix:` — bug fix
- `perf:` — performance improvement
- `docs:` — documentation changes only
- `refactor:` — code restructuring without behavior changes
- `chore:` — build, tooling, or maintenance tasks

Example: `docs: add CONTRIBUTING.md` or `fix(gfx): resolve texture alias overwrite`.

In this fork (oneiricsky/mlbts-native), since 2026-11-27:

- The subject is one line, imperative and scoped: `fix(gfx): bind compute dispatches to the Switch-size level`.
- The body is three sentences at most, or nothing. Trailer lines do not count.
- The long explanation goes in `docs/reports/YYYY-MM-DD-slug.md`, committed in the same change.
- Issues and docs cite the date and subject, or the report's path, not this fork's commit hashes. Upstream hashes may
  stay, with the date and subject.

## Pull Requests and Branches

- Create a focused branch for your changes (e.g., `docs/contributing`, `fix/...`, `feat/...`).
- Verify an incremental build (`.venv/Scripts/python -I tools/build.py`) and smoke-test `work/build/mlb.exe` before submitting.
