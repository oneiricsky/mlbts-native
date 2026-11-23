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

## Open question: why does the game make so many NaNs at match start?

In plain words: a NaN ("not a number") is what a calculation gives when it has no answer, such as 0 divided by 0 or
infinity minus infinity. A normal program makes a handful. At match start the game draws a 512x512 picture of the
field's edges (the msdfgen step) and makes about 67 million of them in one frame, roughly 256 per pixel. The port
handles each one correctly but slowly. The change on `research/float-fixup` makes each one cheaper (the step goes from
702 to 525 ms), but it never asks why they appear. If the game is feeding itself bad numbers, or the port turns good
numbers into bad ones, removing the cause would remove most of the step, which is far more than the fix-up can.

Answer (2026-11-22, one stadium): the NaNs are the game's own, not a port bug. Before the pass starts, 97 % of the
picture's pixels hold plain infinity ("inside" or "outside", no distance) and only 2.9 % (7,506) hold real distances,
and the picture's signs trace a clean field outline. msdfgen's error-correction pass (`f_7000030ec0`, with
`f_7000031e70`, `f_7000033530`) then visits every pixel and computes `(a - 0.5) / (a - b)`; with infinities that is
`inf - inf`, a NaN, which fails the "edge between these pixels" test, so the answer is always "nothing to fix". About 99.9 %
of the 70 million NaN results come from five functions in that pass; about a quarter are `inf - inf` births and the rest
are those NaNs carried on. In plain words: the game spends most of its match-start step proving that empty space has no
edges.

The fix is a code patch set `msdf_skip` (`tools/data/patches-1.0.20.txt`, setting `MLB_MSDF_SKIP`, default on, with a
settings-menu row "Shorter freeze at match start"): the pass skips a pixel whose three channels are all infinite. Six
runs, 35 s each, off and on alternated: the MSDF step 683, 706, 673 ms (mean 687) with the skip off, 166, 221, 182 ms
(mean 189) with it on; the finished field texture has the same checksum in all six (sum 147739026, 587113 non-zero of
1048576), and the owner saw the field in game and it looked right.

How sure we are (2026-11-23): for the two stadiums tested, the finished texture is byte for byte identical with the
skip off and on (all 1,048,576 bytes, same SHA-256), so the output is proven equal there. Dodger Stadium: six runs,
three off and three on. Baltimore (BAL home, BOS away): four runs of 40 s, off and on alternated, the step 723 and
727 ms off (mean 725) and 187 and 186 ms on (mean 187); SHA-256
5f450eca81b533dcc436c911e5fb081f35641ccc7170588480f6d55a3bc4e6a0 and byte sum 127082744 in all four. It is not proven
for every input: reading the guest code showed the pass marks a pixel only through two classifier calls
(`f_70000336bc`, `f_7000033530`); the divide-based range tests give NaN for an infinite pixel whatever its neighbours
hold, but a range test can pass for one and `f_70000336bc` then checks the real stadium outline, which cannot be worked
out offline. So more stadiums, times of day and weather still need the same byte compare. How to do it: the dev harness
dumps the picture (scenario key `dump = texture:fmt=0x25,size=512x512`; `tools/scenarios/bal-tor-field.txt` is the
Baltimore one); run the scenario once with `MLB_MSDF_SKIP=0` and once with `1`, each with its own `MLB_HARNESS_OUT`,
and compare the two `dumps` folders (`tools/harness.py compare`). Still to do: more stadiums, a whole-match run, the
1.0.15 address (needs the 1.0.15 exefs for `tools/addrmap.py`; it is not on this machine). The report is
`docs/reports/2026-11-23-msdf-skip.md`. The float fix-up (`research/float-fixup`) matters much less once the NaNs are
gone; measure it again before merging it.

The trace that found this (a diagnostic build kept out of commits): count NaN results by calling function from the host
return address (symbolized with `llvm-symbolizer`), split "born" from "carried on", dump the pass's input picture, read
the guest code with `tools/disasm.py`.

## Experiment and tooling notes

- Run a deliberately broken control before trusting a new metric (the known-yellow case proved the blown-pixel
  count could see the bug). Run each configuration fixed from frame 0; switching a setting mid-run misled us
  because head-show results are baked once.
- Run `ninja -f work/build/build.ninja` from the repo root, not from `work/build`. That builds with the build file as
  it is. After `tools/build.py` itself changes, or a source file is added, run `python -I tools/build.py --exefs
  work/build/game/exefs --portable` to write a new one. Seen 2026-11-23: `work/build/mlb.exe` had no dev harness,
  because its build file was a day older than the switch that adds it. `grep -c -a "harness: marker" <exe>` prints 1
  when the harness is in. Run shell scripts from the folder they live in. Never run two game instances at once; they
  share the screenshot folder.
- Seen once (2026-11-23): the first game run from a freshly copied exe folder took 37 s to reach the field picture and
  the next three took 22.5 s, with the MSDF step the same. Do not take timing from the first run of a new folder.
- In Python on Windows use `D:/` style paths. In shell heredocs backslashes get eaten, so build escape characters
  with `chr(92)`. Source files may have Windows line endings; check before a text replace.
- Before any `gh` or push command, check the repo, the remote and the real commit hash (a wrong-repo issue and a
  mistyped lease hash both happened). The auto-mode checker blocks force-pushes and deletes: say what the action
  does and wait for an explicit yes.
- When several sessions work at once, a game run takes the lock folder first: `mkdir D:/AI/Apps/mlbts-native/work/game.lock`
  (it fails if another session holds it) and removes it when the game has exited.
- A game run needs a live Windows audio output. With none (the monitor's speakers asleep), the log says `audout: no
  output device` and the game sits at the loading screen and never starts the match. Check that line first.
- A build made in a worktree (`.claude/worktrees/<name>`) is run with `MLB_EXEFS`, `MLB_ROMFS` and `MLB_PROFILE` set to
  `D:/AI/Apps/mlbts-native/work/build/game/exefs`, `.../game/romfs` and `.../profile`, and from `work/build`, because
  the shader translator (`totk_xlate.exe`, `.id`) and `SDL3.dll` sit next to the exe there. Build it from the
  worktree root with `ninja -f work/<dir>/build.ninja`. Bench settings take the full name (`MLB_MSDF_SKIP=0`).
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
- Every chat reply that reports a finding, a result or a decision contains a layman's explanation: what it means in
  everyday words, with no jargon (or the jargon explained the first time), and what it changes for the owner. Put it
  in the reply itself, not only in a report or a commit. A pure status line or a question needs none.
- Long runs go to a background agent. Agents follow the session's permission mode, and plan mode pauses them.
  Watch the 5-hour usage limit before starting long work.
- Do not launch long game runs unasked; short smoke runs are fine.
