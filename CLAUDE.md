# Rules for this fork (oneiricsky/mlbts-native)

These override AGENTS.md (upstream's) wherever they conflict. Upstream's AGENTS.md says to push to the upstream
repo, which does not apply here. Its rule to end commits with a Co-Authored-By line does apply (see below).

## Research branch

This is the owner's personal research fork of upstream (sam110411/fastball). It tracks upstream by merging each
release and keeps its own work in separate files where possible. The product is what we learn plus working tools,
not releases, so the gates are lighter: a PS5 colour-map default needs the fallback, the `MLB_HD_TEXTURES` settings
row, a check on about two dozen heads from both teams with the known-bad control, and one full match; the
full-content fingerprint check and the stale-face test wait until a wrong or stuck face appears. The main line is
making the PS5 faces solid, then the next visible category. General performance is upstream's strength; the current
research focus is the remaining stalls (the match-start CPU work, first-use costs). Loading-ahead work beyond the
head-file prefetch (a pack file, remembered players, mode detection) is deferred.

## Commits and remotes

- Subjects use Conventional Commit types like upstream (`feat`, `fix`, `perf`, `docs`, `refactor`, `chore`, with an
  optional scope such as `fix(gfx):`), and never a project prefix. Older commits here use area words
  (`readme:`, `tools:`); new ones follow the types.
- Author and committer are Sky Miles <14169181+oneiricsky@users.noreply.github.com>. Every commit is SSH-signed
  through 1Password, which must be unlocked; check with `git cat-file commit HEAD | grep gpgsig`.
- Since 2026-11-22 the owner allows a Co-Authored-By trailer for the model, as upstream does: end the message with
  the Co-Authored-By line the session gives. The model is never the author or committer (those stay Sky Miles),
  and no other AI identity appears in a commit. Earlier commits are not rewritten to add it. The owner's personal
  email never appears in a commit, a message or a network request.
- Every commit is SSH-signed with the 1Password key (see the parent CLAUDE.md for the setup); never pass
  `--no-gpg-sign`. If signing fails because 1Password is locked, stop and tell the user.
- Commit only. Push only when asked. Force-push only on an explicit request, with `--force-with-lease` pinned to
  the full remote tip, after saying that it rewrites published history.
- `origin` is oneiricsky/mlbts-native. Upstream is sam110411/fastball (renamed from mlbts-native). Pass
  `-R oneiricsky/mlbts-native` to `gh` and check `git remote -v` first.
- Game files and keys are never committed. `work/` is ignored.

## Working rules

- Check upstream before investing in a fix area. Fetch it into a temporary ref and search its log. Release 0.2.0
  had already fixed the per-pitch freeze we spent a long time on.
- Do not accept "inherent" for a hitch. Ask why the game does the work, and compare consecutive calls for
  redundant inputs. Code patch sets are a valid fix route (see below).
- Every experiment gets per-change numbers: a before and after with the run count, written down when it is run.
  The yellow-face fix has them (0 of 101 screenshots blown, against about 50 without the fix). The pitch-hitch
  work had none, which is partly why it was parked. Before calling a hitch inherent, list where the time goes as a
  share of the thread's busy time; that list would have pointed at the redundant lighting bake that 0.2.0 fixed.
- Diagnostics cost nothing in normal play: off by default, and never a `getenv` or `cfg` lookup in a per-draw or
  per-call path (cache it once). Keep diagnostics out of commits; stash them with a short note.
- The dev harness drifts by hundreds of frames between runs. Compare fixed-from-frame-0 configurations or
  matched game events, never frame numbers, and never judge a visual fix from two faces. The 60 fps cap hides
  per-frame cost, so measure uncapped for performance claims.
  Tools: `tools/perf_summary.py` turns a run log into JSON; `work/scratch/ycount.py` counts blown-yellow pixels.
- PS5 textures: `MLB_HD_TEXTURES=off` disables them. Colour maps stay opt-in until they pass verification on many
  heads. A compute dispatch binds PS5 images from the Switch-size level (`get_view`, `cur_texel`); a new PS5
  asset category needs its compute consumers checked first.
- `MLB_HD_TEXTURES` still needs a settings row in `cfg.c` (every setting there is also a command-line flag).

## Experiment and tooling notes

- Run a deliberately broken control before trusting a new metric (the known-yellow case proved the blown-pixel
  count could see the bug). Run each configuration fixed from frame 0; switching a setting mid-run misled us
  because head-show results are baked once.
- Run `ninja -f work/build/build.ninja` from the repo root, not from `work/build`. Run shell scripts from the
  folder they live in. Never run two game instances at once; they share the screenshot folder.
- In Python on Windows use `D:/` style paths. In shell heredocs backslashes get eaten, so build escape characters
  with `chr(92)`. Source files may have Windows line endings; check before a text replace.
- Before any `gh` or push command, check the repo, the remote and the real commit hash (a wrong-repo issue and a
  mistyped lease hash both happened). The auto-mode checker blocks force-pushes and deletes: say what the action
  does and wait for an explicit yes.
- The investigation plan lives outside the repo at `C:/Users/sky/.claude/plans/fuzzy-growing-kurzweil.md`.

## What upstream (Fastball 0.2.0) already has

Present in this tree once 0.2.0 is merged.

- Game-behaviour fixes are code patch sets: `tools/data/patches-<version>.txt` (format in `recomp/patches.py`),
  passed to `recomp/gen.py --patches` and by the setup. `docs/walkup-freeze.md` is the model: cause, call sites,
  measurements. Try a patch set before accepting a hitch as inherent.
- The runtime is built with a profile (`tools/data/runtime.profdata`, PGO; `--pgo off` skips it). Retrain it with
  `tools/pgo.py` after large replay changes, or performance numbers drift.
- Heavy-scene frame rate: the game waits for each frame's GPU signal. What was measured and ruled out is in
  `docs/frame-rate.md`. Read it before touching waits.
- Release standards (`docs/release.md`): one program (`Fastball.exe`), a portable folder with the game in `MLBTS\`,
  nothing in `%LOCALAPPDATA%`, and every `cfg.c` setting is also a command-line flag (`mlb.exe --help`).
- Upscalers: `MLB_DLSS` and `MLB_FSR` (FSR 3.1 and 4, `vk_ffx.c`), off by default, in the F1 Graphics menu;
  `tools/fetch_ffx.py` puts AMD's DLLs in `work/build`.
- Comments on vendored files carry the marker `fastball` (not `mlbts-native`) and say what MLB does and why.

## How upstream works — follow the same habits

- Profile before fixing. Sample the thread with tracing off and give each cost as a share of the thread's busy
  time ("13% of the replay's busy time"). Fix the biggest, then measure again.
- A commit message gives the cause, the change and the numbers: before and after, with the run count ("replay 3.22
  to 2.92 ms per frame, 149.6 to 155.8 fps, two runs each, same code").
- Say how sure you are. One upstream fix reads "found while tracing #18; not reproduced, so not confirmed as its
  cause".
- Find root causes by checking what the original platform really does. The 5 to 6 hour crash was a memory leak
  from the loader binding symbols differently from Horizon's rtld; the fix copies rtld's rule.
- A behaviour fix ships as one unit: the code, a settings row (on by default) with a menu toggle, and a short doc
  with Cause, the fix, what else changes, and How it was checked.
- Tie fixes to issue numbers and credit contributors. Release notes are plain language, with the "no game files"
  notice first.

## Contributing the way upstream does (CONTRIBUTING.md in 0.2.0)

- Scope: Switch versions 1.0.20 (primary) and 1.0.15. A change that touches game addresses must work on both;
  `tools/addrmap.py` finds a 1.0.15 address in 1.0.20. Offline play only; online play and Diamond Dynasty are out
  of scope. Current focus: graphics correctness and performance. Never regress frame rate.
- Build and check before committing: always run Python as `python -I` (so user site-packages do not load), close
  `mlb.exe` before building (it locks the file), build with `tools/build.py` (an incremental runtime build with
  `ninja -f work/build/build.ninja` also works here), then smoke-test `work/build/mlb.exe`. Sanity checks:
  `mlb.exe --probe-fs` and `tools/shader_smoke.py`.
- Keep generic and game-specific code apart: `runtime/core/` is generic host code with nothing MLB-specific,
  `runtime/mlb/` is MLB-specific, and `recomp/` stays unmodified from TotK Recomp.
- Edits to vendored files (`runtime/core/`, `runtime/gfx/`) carry a marker comment that explains the observed
  case: the screen, texture, address or SDK behaviour.
- Fix root causes with evidence from RenderDoc (`tools/renderdoc.cmd`), F12 frame captures (F9 under RenderDoc),
  `mlb.log` or profiler dumps (`tools/prof_report.py`), not per-screen workarounds. `mlb.log` is overwritten on every
  launch, so copy it before restarting if it holds evidence; `[lm 0]` lines are game logs and `[host]` lines are
  runtime logs. Symbolize `FATAL:` addresses with `llvm-symbolizer --obj=work/build/mlb.exe --relative-address`.
- Document discoveries in code comments and `docs/`, tagging confirmed binary or machine facts `[C]` and
  hypotheses `[H]`.
- Third-party code keeps its copyright headers, and each addition is recorded in `THIRD_PARTY_NOTICES.md` with
  source, version, license and target files.
- Branches are focused (`fix/...`, `feat/...`, `docs/...`); pull requests are checked by `.github/workflows/pr.yml`
  (content check, syntax compile). Upstream's contributors target the `dev` branch and releases go to `main`.
- A release is a version bump in `VERSION`, `docs/release-notes-<version>.md`, `tools/make_release.py`, then
  `gh release create` as described in `docs/release.md` ("Making a release").

## Working with the owner

- Short, plain language; follow the human-writing skill for prose. The owner is not a graphics programmer.
- Long runs go to a background agent. Agents follow the session's permission mode, and plan mode pauses them.
  Watch the 5-hour usage limit before starting long work.
- Do not launch long game runs unasked; short smoke runs are fine.
