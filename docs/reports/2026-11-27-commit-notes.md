# Notes from the rewritten commits (2026-11-27)

The explanations from the commit messages that the 2026-11-27 history rewrite replaced, oldest first, so they stay
on `main`. The owner's commit hashes in them are replaced by dates and subjects; the one upstream hash is kept. The text is otherwise as written then, and
later work may have changed what it describes. See `docs/reports/2026-11-27-commit-convention-and-history-rewrite.md`.

Counts: 155 old commits, 44 without a body, 111 with one, all 111 below; the other 44 subjects are listed at the end. Their bodies held 8,598 words (co-author
lines not counted); adding dates and subjects for 5 hashes (4 replaced, 1 upstream hash kept) added 59, so the bodies here hold 8,657.
Check with `python -I tools/check_commit_notes.py backup/pre-squash-20261127`.

## 2026-11-21 build pipelines on background workers, prebuild recorded ones at boot

~~~text
rt_boot never called vk_pipeline_async_enable or vk_pipeline_prewarm (TotK's boot did), so every new
pipeline compiled on the replay thread: frames of 0.5 to 3.5 s, no fast-linked libraries, no
pipeline-keys.bin. Enable both before the guest starts, except under MLB_SHOT; MLB_PIPE_SYNC=1 keeps the
old synchronous builds.
~~~

## 2026-11-21 split the replay in the wait-burst lines; MLB_DISPATCH_DUMP off by default

~~~text
The game's GPU-wait bursts (each batter walk-up of 1.0.20: about 55 waits) now
log where the replay of each waited submission went: before the submit (present
drain, texture bookkeeping, the submit lock), recording with its command count
and how many re-submitted the same first buffer, the upload flush, the mirror
prologue, the queue submit and the tail. Measured with it: recording dominates
(about 1.5 ms for ~4,800 commands, ~0.3 us per command; everything else together
is ~0.05 ms), and the per-pitch submissions are re-recorded every time (0 of 55
the same first buffer), so caching a re-submitted buffer would not cut the
per-pitch hitch.

MLB_DISPATCH_DUMP (the lighting-probe dispatch dump) was on by default through a
hardcoded hash list: 2,655 watch: lines in a 100 s run, buffer scans on the
replay thread. It now defaults to off like MLB_WATCH.
~~~

## 2026-11-21 skip the boot intro movies behind MLB_SKIP_INTRO (F1 Game tab)

~~~text
The fs layer answers both intro movies (the 62 MB MLB_INTRO.BIK with its 94 s
of narration, and the 5 MB SonyStudio_INTRO.BIK) as not found when the knob is
on, and the boot flow goes from the SIE text card through the loading screen
straight to the title. The game's own movie loader tolerates a missing
candidate: it probes NSW/AND/PS4 paths with fallthrough. SCE_PRESENTS.TEX must
stay: it is the loading screen's background, and without it that screen is a
white square.
~~~

## 2026-11-21 docs: the game's dev-config options and the dev harness

~~~text
The retail binary still carries the engine's dev-config system: at boot it
reads BOOT/CONFIG_MAIN_USER.TXT or BOOT/CONFIG_MAIN.TXT and matches bare
lines as boolean options by a 32-bit hash. The hash is reversed and the
option names recovered by brute force against every constant the retail code
queries (319 sites, 109 hashes, 27 named). GameOnly + AIvAI boot straight
into an AI-vs-AI exhibition, which doubles as an input-free test harness.
~~~

## 2026-11-21 PS5 face textures in place of the Switch ones at upload (MLB_HD_TEXTURES), Ohtani first

~~~text
The game creates head textures at their Switch size and copies the file's storage into them, so a bigger converted
file reads as noise. The port now recognises a texture at upload by a hash of the first 16 KiB of its storage
(tools/make_hd_index.py makes the index from the Switch files) and puts an image made from the PS5 file in its place.
Ohtani's colour and normal maps render at 1024x512; a 2048x1024 colour map comes out yellow, so the index caps the
size (docs/ps5-textures.md has the PS5 file layout and the limits).
~~~

## 2026-11-22 Merge upstream Fastball 0.2.0 into the fork

~~~text
Merges sam110411/fastball main (b9c607e (2026-11-22, "Update game performance status to 100+ fps"), release 0.2.0) into our main. Conflicts:
- README.md: our fork section stays on top, upstream's new README goes in the collapsed block.
- runtime/mlb/cfg.c: our SKIP_INTRO row and upstream's six new rows are all kept.
- fs_host.c, vk_sync.c, vk_texture.c, vk_exec_draw.c: our code stays, comment markers use
  upstream's new "fastball" name. In vk_exec_draw.c upstream's comment replaces ours, and our
  one-line handling of MLB_DISPATCH_DUMP=off stays, because upstream's loop would read "off"
  as a hex hash.
~~~

## 2026-11-22 chore: use the fastball marker in the comments our edits added

~~~text
Upstream renamed the comment marker in vendored files from mlbts-native to fastball. Our own
commits had added comments with the old marker; only the marker text changes, in comments.
~~~

## 2026-11-22 feat(tools): make_hd_index --check validates an index, with unit tests

~~~text
`--check <index.txt>` verifies every line: the PS5 file exists under the index's root,
the TX12PS5 header parses, the format code is BC1 (13) or BC7 (22), the level sizes
sum to the data size and fit in the file, the index's width, height, levels and drop
agree with the header, and the Switch and PS5 folder names match. One line per problem,
a summary count, exit 1 if anything is wrong. tools/test_hd_index.py runs 19 tests on
synthetic files (no dump needed); a local test checks the real indexes when the dump
is present. Both real indexes (2,370 and 7,116 lines) check clean.
~~~

## 2026-11-22 ci: fork-checks runs the content check, the syntax compile and the index tests on push

~~~text
A new workflow beside upstream's pr.yml (which stays untouched): runs on push, pull
request and manual dispatch with read-only permissions. Only compared with pr.yml;
Actions cannot run locally.
~~~

## 2026-11-22 feat(tools): perf_summary reads the worst-frame and perf lines too

~~~text
Adds an "extra" key when the log has them: the worst frame, the slow
frames and the vram and ram peaks that MLB_TRACE=perf writes. The
existing keys are unchanged.
~~~

## 2026-11-22 feat(tools): bench.py runs and compares A/B game runs

~~~text
`run` alternates labelled configurations, one game at a time, with the
sampler off and MLB_TRACE=perf, and writes each run's log and JSON.
`compare` prints per-label means with min-max spread, the first window
apart, and says when the runs are too few or the ranges overlap.
docs/dev-config.md gets the protocol. Checked against the six baseline
logs of the performance report; `run` has not been tried against the game.
~~~

## 2026-11-22 feat(log): MLB_LOG_TIME=1 stamps every log line with the time since the first line

~~~text
The game's log lines carry no time, so a slow frame could only be placed within about
20 s of the wall clock by counting frames. With MLB_LOG_TIME=1 every line starts with
"[ 12.345] " (seconds since the first log line) and the first line logs the local
wall-clock time once, so a log can be lined up with anything outside the game.
Off by default; read once from the environment because the log runs before the
settings are parsed. Syntax-checked with clang only; not built or run yet.
~~~

## 2026-11-22 docs: note in the reports what 0.2.0 changed

~~~text
The hitch report gets a section on upstream's walk-up patch (the per-pitch freeze is
fixed; post-merge frames over 100 ms per minute 3.2 to 0.2 with textures off, 4.4 to
0.6 with normal and colour maps; the lineup-card and 1.3 s load stalls remain) and a
status line saying the per-pitch conclusion was wrong. The performance report notes
that its numbers predate the merge.
~~~

## 2026-11-22 docs: research on upstream issues 18, 21, 26, 10 and 14

~~~text
Reads the four open bugs against the merged tree: the face-button map that
flips by screen (10), the limiter's step guard (18), one merged pad as player 1
(21, 26) and a crash log that shows a normal exit (14). Ranked by value and
effort, with what each needs to be settled.
~~~

## 2026-11-22 perf(hdtex): read a head's PS5 file in the background when the game opens its Switch file

~~~text
The PS5 dump is on a hard disk: a cold read of a head's file takes about 15 ms (0.25 ms warm), and hd_apply did
it on the replay thread at the texture's first upload, so a batch of new heads was a 200 to 670 ms frame (the
lineup card had one of 724 ms, 687 ms of it texture upload). The game opens each head's Switch files a median of
23 s (at least 1.7 s) before that upload, so the open now queues the PS5 file of the same name to one background
thread, which runs the loader and keeps the file in the system cache. Setting MLB_HD_PREFETCH, default on.

Cold runs (each run's files were hard links to heads nobody had read), prefetch off vs on, two to three runs each:
demand loads of the first 64 swaps 670 to 881 ms in total (max 28 ms) vs 26 and 29 ms (max 0.7 ms); frames with
50 ms or more of texture upload: 2 to 4 per run vs none. docs/reports/2026-11-22-load-stall-investigation.md.
~~~

## 2026-11-22 docs: report on the load stalls in the merged build

~~~text
Four stalls, one of them from this fork: the lineup card is gone with 0.2.0 (64 ms), PS5 cold reads are fixed on
this branch, the 1.4 to 1.6 s match-start frame is the game's own grass and distance-field CPU work, and a few
140 to 250 ms frames at match start are not traced further.
~~~

## 2026-11-23 docs: report on the match-start msdf skip

~~~text
Cause (97 % of the distance picture is infinite, so the clean-up pass makes
about 67 million NaNs), the patch, timings (687 to 189 ms mean, six runs) and
what is not yet proven (one stadium).
~~~

## 2026-11-23 docs: add the dev harness plan to dev-config

~~~text
Records the design settled with the owner: purpose, scenario file fields,
team ids, match-setup offsets, recording, baselines and build order.
Open items are marked.
~~~

## 2026-11-23 feat(harness): dev harness API and scenario file format

~~~text
harness.h documents the scenario keys and the small public API other
sessions code against. Compiled only with MLB_DEV_HARNESS.
~~~

## 2026-11-23 docs: CLAUDE.md records the msdf_skip result, game-run lock and audio rule

~~~text
The open-question section now holds the cause of the match-start NaNs, the
skip patch and its numbers, and the byte-identical field texture on one
stadium, with what is not proven. Tooling notes add the game-run lock folder
for parallel sessions, the live audio output a run needs, and how to run a
worktree build.
~~~

## 2026-11-23 docs: README lists the match-start skip and the dev harness

~~~text
Two rows in the "What this fork is for" table: the msdf_skip patch with its
measured effect (match-start step about 0.7 s to about 0.2 s, finished
field picture byte for byte the same on one stadium) and the dev harness,
marked as in progress.
~~~

## 2026-11-23 feat(tools): harness runner for scenario-driven game runs

~~~text
tools/harness.py: run, ab (byte-for-byte dump compare with diff image and
repeatability check), smoke and compare, under the game.lock folder lock with
a stray mlb*.exe check and audio-device detection. tools/test_harness.py
tests it against a fake game script (29 tests, about 55 s).
~~~

## 2026-11-23 feat(harness): scenario file, team override, markers, texture dump, clean stop

~~~text
Dev builds only (tools/build.py defines MLB_DEV_HARNESS, release toolchain
builds do not). MLB_HARNESS=<scenario> sets teams in every copy of the
match settings, logs markers, dumps matching WriteTexels data with a
sha256 to MLB_HARNESS_OUT and stops the game cleanly.
~~~

## 2026-11-23 feat(tools): harness backs up saves before each run, adds restore

~~~text
Runs use the real profile. Before each run, save, save-tx and playtime.txt are
copied to work/harness/backups/<timestamp> (newest 10 kept; only folders the
tool marked are pruned). `restore <backup> --confirm <name>` puts them back
after a safety backup. --copy-profile runs on a throwaway copy instead.
Tests: 34 pass.
~~~

## 2026-11-23 fix(harness): match the texture's size, not the written region's

~~~text
A 512x512 region written into the 1024x1024 texture had the field
picture's format and size, so the dump took it first. The field picture
is the 512x512 texture itself.
~~~

## 2026-11-23 feat(harness): log the profile path at boot

~~~text
State overrides can end up in the saves, so the log names the profile a
harness run used.
~~~

## 2026-11-23 feat(gfx): MLB_RUN_LABEL shows a run's name in the window title

~~~text
Several test sessions now run the game at once, each in its own slot,
and every window had the same title. MLB_RUN_LABEL=<name> (environment,
or RUN_LABEL in mlb.cfg) puts "[name]" at the end of the title bar, cut
at 80 characters.

Checked on the dev build with two 20 s runs in an isolated slot while
another game was running: the OS reported "MLB The Show 26 (fastball)
[label-test]" with the label set and "MLB The Show 26 (fastball)" in a
control run without it. Both stopped by themselves (exit code 0, 21.1 s).
~~~

## 2026-11-23 docs: msdf skip leaves the field picture the same in Baltimore too

~~~text
Second stadium for the match-start freeze fix, measured with the dev
harness dump. Four runs of 40 s, off and on alternated, one game on the
machine: the finished 512x512 field picture is identical in all four
(1,048,576 bytes, SHA-256 5f450eca...3bc4e6a0, byte sum 127082744, 0 bytes
differ off against on and on the repeats). The MSDF step is 725 ms with the
skip off and 187 ms with it on (two runs each). Until now the skip-off
picture of this stadium was not measured.

CLAUDE.md also records two things seen today: a bare ninja build keeps an
old build file (work/build/mlb.exe had no dev harness until tools/build.py
wrote a new one), and the first run from a freshly copied game folder took
37 s to reach the field picture against 22.5 s for the next three.
~~~

## 2026-11-23 feat(tools): game.py runs the game in isolated slots

~~~text
Until now a game run took the folder lock work/game.lock, because
games shared one exe folder, one log and one profile, so only one
could run at a time. tools/game.py gives every session a slot of its
own, work/runs/<id>/: a copy of the exe and of the files it needs
beside it, a copy of the saves, and a log of its own. The marker
work/game.state/<id>.lock is the slot's permit, and MLB_RUN_LABEL
puts "[id]" at the end of the game's window title.

Commands: create, update, run (shared: up to three games at once;
exclusive: a timing run, which ordinary runs then wait for), status,
stop, release, clean. The real profile is only read: each run copies
its saves into the slot, and MLB_PROFILE cannot be pointed back at
it. Live games are counted from the process list with ctypes: every
process under work/runs/ and every mlb*.exe, whoever started it.
result.json says whether the run was the slot's first (the first run
after a fresh copy of the exe folder is the slow one) and which other
games were live during it.

Checked with tools/test_game.py: 65 tests, no real game. The fake
game is a copy of python.exe carrying the slot exe's name, so the
tests go through the real process list. Three fake games ran side by
side and the fourth waited for a place; a detached run's watcher
wrote result.json and ended with its game; no process was left
behind. Read-only against the real folders, `status` counted another
session's game (mlb_scenario_search.exe) with its window title.
~~~

## 2026-11-23 test(tools): real check of game.py; close asks only the game's own window

~~~text
tools/test_game_real.py runs the real game through game.py and prints
numbers (16 checks, about 52 s of game time). With work/build/mlb.exe
from (2026-11-23, "feat(gfx): MLB_RUN_LABEL shows a run's name in the window title"), while another session's game was live:

1. One 20 s run in a fresh slot: exit code 0 by itself in 20.7 s, the
   boot marker in the log, audio ok, window title "MLB The Show 26
   (fastball) [real-1]" read from the operating system.
2. Two such runs at once: both live 0.7 s after they were asked for,
   both exit code 0 by themselves (20.9 s and 20.8 s), audio ok, two
   logs (55133 and 55421 bytes), two profiles, each window titled with
   its own label, each run saw the other as live.
3. While those two and the other session's game ran (3 of 3 places): a
   third slot asking for an exclusive turn without waiting exits with
   status 2, and a third shared run without waiting is refused with
   status 2 ("3 of 3 places used").
4. stop asked 0.6 s after launch, before the game's window exists: the
   game ended 5.2 s after launch by the close request, exit code 0.
The real profile had the same 14 files with the same hashes after.

Found by the first run of step 4, measured on the real game: 0.92 s
after launch the process has a hidden window of the graphics driver,
class temp_d3d_window_..., titled "Temp Window". The tool asked that
one to close and took it as done; the game's own window appeared at
6.35 s and was never asked, so stop killed the game after the grace
period. Asked at 8.97 s, the game ended 0.4 s later with exit code 0.
Now the game's window is a visible top-level window with a title: only
those are asked and listed, and the request is repeated every half
second until the game ends. The test fake's window is visible but
placed far off every screen, so nothing shows on the desktop.

tools/test_game.py: 66 tests.
~~~

## 2026-11-23 refactor(tools): harness and bench run through game.py slots

~~~text
tools/harness.py and tools/bench.py started the game themselves and
took care that only one ran: the folder lock work/game.lock in the
harness, a look for a process named mlb.exe in bench. Both now run
through tools/game.py in a slot (work/runs/harness and work/runs/bench
by default), so several games can run at once and nothing waits on a
lock.

harness.py: a run copies the real saves into the slot's profile, so
the real profile is never written; the lock code is gone. summary.json
names game.py's run folder, which holds game.out, game.log, result.json
and the dumps; `compare` reads old run folders with their own dumps/
too. `ab` compares dumps, not times, so it runs shared (--mode
exclusive and --wait are there when wanted). --real-profile keeps the
old way: on the real profile itself from the exe's folder, after the
backup, only when no game is live. The scenario key `framelog` is
known. No turn within the wait is an error of the harness (exit 2).

bench.py: every run takes an exclusive turn through game.py, so slot
games count too, and runs from the slot; a run that shared the machine
anyway is marked contended, and the slot's first run is marked as the
cold one.

Checked: python -I -m unittest discover -s tools -p test_harness.py,
35 tests. `bench.py run --dry-run` prints the slot and the plan.
~~~

## 2026-11-23 feat(mlb): MLB_LOG names the log file, so games from one folder keep their own

~~~text
The game always wrote its log to <exe folder>/logs/mlb.log. Several
games started from one exe folder wrote that one file over each other:
on 2026-11-23 three ran at once from work/runs/scenario-search.

Setting LOG (MLB_LOG in the environment or on the command line, --log)
names another file. An absolute path is used as given, a relative one
against the exe's folder, like the default; its folder is made when it
is missing. Without the setting nothing changes: the log still goes to
logs/mlb.log beside the exe. It is read once in log_open, after the
settings are loaded; nothing per call.

Checked: runtime/mlb/main.c and runtime/mlb/cfg.c compile syntax-only
with the build file's flags, with and without -DMLB_DEV_HARNESS, and
with the llvm-mingw clang of work/toolchain without it: exit 0 and no
warnings each time. The game itself is checked in the next commit,
where tools/game.py gives every run its own log file.
~~~

## 2026-11-23 feat(tools): every run gets its own log file; a busy slot refuses a second run

~~~text
tools/game.py gives every run MLB_LOG=<run folder>/mlb.log, so the game
writes its log there itself and runs of one slot no longer share
<slot>/logs/mlb.log. An exe without that setting still writes the log
beside itself: then it is copied into the run folder and result.json
says so (log_source). A slot whose game is live refuses a second run
with exit status 2 before anything is written into the slot, because
its exe folder and its profile are shared.

Checked with the rebuilt work/build/mlb.exe (tools/test_game_real.py,
21 of 21 checks in 72 s, the other session's game live):
1. One 20 s run: the game wrote <run folder>/mlb.log itself, 1750
   lines, first line "[host] version: Fastball 0.2.0, game MLB The
   Show 26 1.0.20"; the slot's logs/mlb.log was not written.
2. Control, the same exe started without MLB_LOG: the log is
   logs/mlb.log beside the exe, 400 lines, the same first line.
3. Two games from one exe folder at once, started by hand past the
   guard, each with its own MLB_LOG and profile copy: exit codes 0 and
   0; logs of 494 and 546 lines; each holds its own game's stop line
   ("marker stop frame 42 t 8.004" and "frame 233 t 14.000") and none
   of the other's.
Unit tests: 69 (tools/test_game.py); harness tests: 35. No process,
slot or marker left behind.
~~~

## 2026-11-23 docs: run slots replace the one-game lock

~~~text
docs/dev-config.md gets the section "Run slots": what a slot is, the
three rules (own slot, marker file, window label), the commands, shared
against exclusive turns, that the real saves are copied and the real
profile never written, and what MLB_LOG does (every run its own log
file; without it the log beside the exe is shared by every game started
from that folder). It also says that a slot's first run is the slow one
(37.1 s to the field picture after a fresh copy of the exe folder,
22.5 s for the next three), so timing needs a slot that has run once.

The text that still described the one-game lock is corrected:
bench.py no longer refuses while mlb.exe runs, it takes an exclusive
turn through game.py, and it runs from a slot.
~~~

## 2026-11-23 feat(tools): scenario.py puts a running game into a chosen match situation

~~~text
Reads a scenario file (teams, inning and half, outs, balls and strikes, both
scores) and applies it to a running 1.0.20 game by writing the count object
and the match settings, then prints one line per field with the value read
back and watches the match play on. The half-inning is set by writing the
previous half with 2 outs and letting the game make the transition itself,
because writing the half-inning mid-play leaves the old team batting.

Five scenarios, each on a fresh game in its own slot, all PASS: opening (top
1st), mid-game (top 4th), bal-bos-6th (other teams, bottom 6th), late-game
(bottom 9th, away 4 home 3, 1 out, 3-2) and extra-innings (top 10th, tied).
Every field read back equal to the file, and the game kept playing for 45 s
afterwards (log entries kept growing, its own play-by-play showed the same
inning, half and outs).

Not applied yet: runners on base and who is batting or pitching. The
scoreboard's base array is rebuilt from the real runner objects within about
3 s; those objects are not found. Offsets are for game 1.0.20 only.
~~~

## 2026-11-23 feat(audio): TOTK_AUDIO=paced, a silent fake device for unattended runs

~~~text
With no playback device the game's audio buffers counted as played the
instant they were queued, and a test run on a PC with no audio output sat at
the loading screen and never started the match. TOTK_AUDIO=paced never opens
the real device: a small thread advances the played counter at 48000 frames
a second and signals the buffer events, like hardware would. Default
behaviour is unchanged.

Checked: with the real output missing and then present, a run with
TOTK_AUDIO=paced logged "a fake device plays the ring out in real time",
reached the match in about 35 s and played on, with no sound on the speakers.
~~~

## 2026-11-23 feat(tools): scenario.py runs several scenarios in one game and makes runners

~~~text
Takes several scenario files and applies them in order to one running game
(the half-inning counter only moves forward, so the files go in increasing
inning order), with a short play-on check between them and a 60 s one after
the last. Runners are created by the game itself: a 3-0 count is forced until
the walks put the wanted runners on base (none, first, first and second, or
bases loaded). The team setting is described as stadium and uniforms only:
the players do not change.

One packed run (one game): opening (Baltimore/Boston numbers), mid-game with a
runner on first and late-game with first and second PASS, every field read
back equal. bal-bos-6th FAIL (bases loaded not reached in 120 s: only first
and second) and extra-innings FAIL (the transition to the top of the 10th was
not seen in 150 s and the game logged no plays for 60 s).
~~~

## 2026-11-23 feat(tools): unattended scenario runs: faster walks and MLB_HARNESS_PRESS

~~~text
Two changes that took the packed scenario run from 3 of 5 to 5 of 5 passing in
one game launch (silent, with TOTK_AUDIO=paced):

- MLB_HARNESS_PRESS=<period ms>[,A|B|X|Y|PLUS] holds a button for 120 ms every
  period in the controller poll, so cutscenes and prompts that wait for a
  button no longer stall an AI-vs-AI match nobody is watching. Off by default.
- apply_runners writes the 3-0 count only when the game has moved off it, and
  checks every 0.3 s: a runner on first now takes about 7 s (was 78 s) and the
  walk loop gets 240 s.

Packed run, one game: opening, mid-game (runner on first), bal-bos-6th (bases
loaded), late-game (first and second, bottom 9th, 4-3, 1 out, 3-2) and
extra-innings (top 10th, tied) all PASS, every field read back equal, and the
game played on for 60 s after the last one.

Not done: the team setting changes only the stadium and uniforms (the game's
own screenshots show Baltimore's park with Blue Jays against Dodgers players
and scoreboard); runners on first and third; who bats and pitches.
~~~

## 2026-11-23 docs: function-level codebase map with generators and a coverage check

~~~text
Indexes 11,308 source functions (libclang for C/C++, ast for Python, regex for vendored C# and GLSL) and all 135,060 recompiled game functions (main 94,991, sdk 40,069, matching each manifest). The original .text is scanned independently: all 45,361 + 9,790 direct bl targets are indexed. map_coverage.py exits 1 on any gap. The per-function binary index is derived from game code and stays under work/.
~~~

## 2026-11-23 docs: mlbts-game-code skill, region notes for the game binary, and map lookup tools

~~~text
A project skill that carries the game-code knowledge between sessions: port architecture, address map of main and sdk, about 100 named game addresses including the 12-state game flow, a tracing playbook, and solved/open problems. Region notes A-F (docs/map/regions) cover every 256 KB window of main and the sdk groups, written from the local index with claims tagged confirmed/inferred/guess. New tools: map_strings (strings per function, vtables), map_find (lookup), map_all (rebuild), map_skill_check (cited addresses exist). Per-function game indexes stay under work/ and are not committed.
~~~

## 2026-11-23 docs: skill states its index-level status and adds how to read a game function body

~~~text
Records the one function body read in full (the BATTER_UP handler) with what it confirmed, a shell filter that makes lifted C readable, and the reading conventions (this, global tables, virtual calls, patch switches). The skill now says plainly that it is an index-level map.
~~~

## 2026-11-23 docs: wiki sources and a build script that turns the skill and region notes into wiki pages

~~~text
Hand-written findings pages (walk-up freeze, match-start freeze, load stalls, frame rate, PS5 textures, upstream bugs, dev harness) live in docs/wiki. tools/wiki_build.py writes work/wiki from them plus the mlbts-game-code skill and docs/map/regions, converts links to wiki page names and fails on a broken link. The skill now says how the wiki is built and that it is the source for the game-code pages.
~~~

## 2026-11-23 Revert "docs: group the wiki's region pages under one collapsible category with an index page"

~~~text
This reverts commit (2026-11-23, "docs: group the wiki's region pages under one collapsible category with an index page").
~~~

## 2026-11-23 docs: put tabular wiki content in tables, with one-to-three-word column headers

~~~text
Function roles, patch sites, run results, field layouts, boot steps, option lists, team ids, clue types and rules were bullets or prose. Table headers are now one to three words (31 renamed), and tools/wiki_build.py fails if a generated page has a longer header or an empty one.
~~~

## 2026-11-23 docs: plain-writing pass over the wiki sources

~~~text
Removed boldface from the skill and region A, dropped "quietly" and renamed the "Graphics glue" heading to "Graphics functions". The map index and coverage were rebuilt (all checks pass).
~~~

## 2026-11-23 docs: read and check the game-state handler bodies, add a Game state machine page

~~~text
Four agents read the bodies of the 12 game-state classes; four Haiku checkers re-checked 20 claims per report against the generated C, and the disputed ones were verified by hand (two of the checkers' corrections were wrong and are not applied). Slots 5, 6 and 7 are enter, exit and update in every state (inferred; nothing calls them directly). Sub-state tables for BATTER_UP, IN_PLAY, PRE_PLAY and GAME_OVER are decoded from the game's own tables. The skill and wiki now carry the verified findings and list what is still open.
~~~

## 2026-11-24 docs(map): map every function and read the class and field schema

~~~text
Map all 135,060 functions of main and sdk, read the 47,308 bodies that had no
symbol, string or simple shape, and read the class and field schema out of the
game's saves. The wiki function pages are generated from the same index.
~~~

## 2026-11-24 docs(map): point the PXP handler row at its function entry

~~~text
0x7000e37a20 is a strncpy call inside DoPickoffResultPXP (0x7000e37630),
not a function entry. The skill check also stops flagging the string
address in the strdump.py example. Check now reads 155 addresses, 0 bad.
~~~

## 2026-11-24 docs(map): decode the saves, edit one and clean the wiki

~~~text
Solve the save container (the hash covers the compressed payload, the display
name does not), decode the five u16 field descriptor and the value-size model,
add tools/save_edit.py (edit a field by name, recompress, rehash), prove an
edited save loads in the game, and record where the values land in engine
state. Then fold the long wiki tables into address bands and remove the
AI-writing tells from the prose.
~~~

## 2026-11-24 feat(fs): MLB_ROMFS_OVERRIDE reads a changed game file for one run

~~~text
A RomFS file that also exists at the same relative path under the folder named
by MLB_ROMFS_OVERRIDE is read from there, so a test run can use a changed
default (the match options in FRONTEND/STATS/GAMEDATA.BIN: teams, stadium,
weather) without touching the installed game data. Off unless set.

Checked: a copy of GAMEDATA.BIN with home 0, away 1, stadium 0, 55 degrees gave
Oriole Park and Baltimore/Boston uniforms from the first pitch. The players,
cards and scorebug stayed Blue Jays against Dodgers.
~~~

## 2026-11-24 feat(hid): MLB_HARNESS_PAD lets another process hold buttons for test runs

~~~text
With MLB_HARNESS_PAD=1 the controller poll ORs in a 64-bit word whose address
the game logs at start (bit n = Switch button n). A test tool can then press
any sequence of buttons without keyboard focus: it walked the post-game menu
(right x5, A, A to confirm) and the game started a new match in the same
process. Off by default.
~~~

## 2026-11-24 feat(gfx): run label in the title bar and a hidden window for test runs

~~~text
MLB_RUN_LABEL=<name> shows "[name]" in the title bar so games running side by
side can be told apart. TOTK_HIDDEN_WINDOW=1 hides the window after it is made:
the game, its memory and MLB_SHOT captures run as usual (a full match and a
restart of the match ran with the window hidden). Both off by default.
~~~

## 2026-11-24 feat(tools): scenario.py keeps the real batting side in step; known-functions notes

~~~text
The game's real batting side is the byte [[main+0x3aeb728]+0x20]+0x124; it flips
only at natural half-inning transitions. Jumping the half-inning counter by an
even amount left the wrong team batting (mid-game and bal-bos-6th had the
home team batting in a top half). The tool now takes one extra natural
transition first when the parity would not fit and reads the side back as a
field. It also retries when the count object is briefly unreadable.
known-functions.md records the team accessors, the count object layout and
what the team setting does.
~~~

## 2026-11-24 docs: how to run the game headless (hidden window, fake audio, pad, screenshots)

~~~text
One table of the test-run settings that need no window, no sound hardware and
no keyboard focus, with the rule that each run gets its own slot and is stopped
by process id. Checked on a full match, the post-game menu and a second match
in one process.
~~~

## 2026-11-24 feat(harness): exhibition.py starts a match between chosen teams through the real menus

~~~text
Cause: lineups and scorebug stay TOR/LAD because rosters are built from the match settings block when the menus
go on after team select (and the untouched default pick keeps preloaded rosters); writes into a loaded match change
only stadium and uniforms. The tool presses the menu buttons, moves the cursor once, overwrites the block after the
confirm, and checks it at the first batter. Cold-start check BAL at BOS: scorebug, Taylor Ward, Garrett Crochet,
Fenway. Control (late write): Ohtani in a Red Sox uniform, TOR/LAD scorebug. One cold run passed; ids 5-24 and 26,
28, 29 are inferred from division order.
~~~

## 2026-11-24 feat(menu): hide the "you are currently disconnected" panel on the main menu

~~~text
Offline, the game-modes menu draws a 1740x636 panel (FRONTEND.TEX
dynamictile_home_offline) in a focus frame because SHOW_DYNAMIC_PANELS is false.
The getter (f_7000c0dc6c, vtable 0x70021bd438 slot 8, 1.0.20) computes it as
obj[+0x129] && obj[+0x128], both 0 offline. A host function sets both to 1 only
while the getter runs, so the menu script lists the (empty) server tiles and
draws neither picture nor frame. Setting the bytes for good gave a NETWORK ERROR
box; a transparent picture left the frame.

MLB_HIDE_OFFLINE_BANNER (default on) with a Game-tab toggle. 1.0.20 only; 1.0.15
logs that the panel stays. Headless menu at frame 6000, off against on: panel
luminance std 56.1 to 5.9, yellow pixels 1896 to 0, frame-edge pixels 2151 to 0,
mode-button strip identical. Check: tools/menu_offline_check.py. Notes in
docs/menu-offline-panel.md.
~~~

## 2026-11-24 chore(harness): check in the in-progress harness and test-tool work

~~~text
runtime/mlb/harness.c and harness.h hold the keyed option setter and the exhibition flow as they stand; tools/harness_parse_test.c and tools/scenarios/buffer-test.txt are the new test helpers. Committed as found and not built; this is a catch-up commit, not a finished change.
~~~

## 2026-11-24 docs(readme): fork features: save format, function map, headless, exhibition

~~~text
The feature table gains the decoded save container and schema with the field
editor, the function map and its wiki, the headless run settings, and
tools/exhibition.py picking the teams of a match. The dev-harness row no longer
needs a live audio output and separates what works from what is being built.

Every Behavior cell is one sentence, and the filler adjectives are gone (no
"real" menus, no "own" dump). A short research section links the wiki and
docs/map/README.md.
~~~

## 2026-11-24 docs(wiki): the team ids are read at game entry and their records copied

~~~text
The dev-harness page left open which function turns the two team bytes
into rosters. It is f_7000bab324: the game-entry handler reads option 2
(away) and then option 1 (home), resolves both ids through the league
team table (f_700181ad34, stride 0x550) and calls f_700066f324 ->
f_700066f390. The builder copies each picked 0x550-byte team record into
the match's two team slots with f_700185d058 (twice), and f_700066f770
then builds the side's 0x138-byte player entries from the player list in
the copied record. The ids select a team record; no roster row receives
the number.

Evidence: in the BOS-at-BAL cold run's first-call trace, team select is
at 45.759 s and the four first calls land together at 61.426 s (x0 = 1,
the away pick, at f_700066f324; the away record and match slot pointers
at f_700066f390 and f_700185d058); GAME ENTERED at 88.886 s. The
generated C shows the reads and the copy sizes. Known-game-functions
gains five rows and dev-config records the answer to its open item. The
wiki rebuilds to 61 pages with no broken links.
~~~

## 2026-11-24 docs(skill): record the settings block, pitcher state and contact result

~~~text
Read from the generated code while scoping a trainer; none of the new
addresses has been written in a live game.
~~~

## 2026-11-24 docs: design for the in-game trainer

~~~text
Memory edits plus switchable call-site hooks, in four stages; not built.
~~~

## 2026-11-24 docs: build plan for trainer stage 1

~~~text
Panel, F1 tab, match count, inning jumps and saved situations, in five tasks.
~~~

## 2026-11-24 feat(wiki): coverage chart on the home page

~~~text
tools/wiki_completeness.py draws the function map's coverage as an SVG from work/map/index/roles.jsonl: one bar per region split by the evidence behind each role (C, I, H), a second bar for the share of bodies read, and the sdk module. tools/wiki_build.py regenerates it with the pages, and the home page embeds it.
~~~

## 2026-11-24 feat(wiki): aspect chart with coverage, and charts that follow the colour scheme

~~~text
tools/wiki_completeness.py now draws two charts: the regional evidence/read coverage and a second one grouping functions by the aspect of the game their window theme names. The aspect bars are shaded to each group's share of the themed functions, and a strip above them shows how much of the map the themes cover (35,990 of 135,060). Both charts use CSS variables with a prefers-color-scheme rule, so they render light or dark to match the reader, and the home page embeds both.
~~~

## 2026-11-24 fix(wiki): theme-specific chart images for GitHub's dark mode

~~~text
GitHub's prefers-color-scheme follows the OS, not the GitHub theme, so a single image clashed on a dark page with a light OS. The generator now writes light and dark copies of each chart and the home page links them with the #gh-light-mode-only and #gh-dark-mode-only fragments, which GitHub switches on its own theme.
~~~

## 2026-11-24 docs(wiki): say where the aspect labels come from, not what the chart looks like

~~~text
The aspect subtitle and the home text now give the labels' provenance: each 256 KB window's theme from the region pages, not anything read in the function. The lines that only restated the bars and the strip are gone.
~~~

## 2026-11-24 feat(wiki): dark-card charts with a WCAG check

~~~text
GitHub wikis ignore the theme-only image fragments, so the page showed both variants. The charts are now a single dark card that reads on either page and declares color-scheme: dark so a browser does not auto-invert it. tools/wiki_wcag_check.py asserts the palette's contrast ratios (1.4.3 and 1.4.11), the accessible name bits (role, aria-label, title, desc) and the alt text on the home page.
~~~

## 2026-11-24 docs(wiki): punctuation in the chart captions

~~~text
Sentences start with a capital, the two subtitle lines are separate sentences rather than a semicolon join, the per-region figures use middots, and the sector labels read 'bodies read' and 'No theme yet'.
~~~

## 2026-11-24 fix(wiki): name the charts by content so GitHub's image cache cannot serve a stale one

~~~text
GitHub serves wiki images from a cache keyed by URL, so a rewritten completeness.svg kept showing the old bytes. The generator now writes completeness-<hash>.svg and aspects-<hash>.svg, the home page carries {{completeness.svg}} and {{aspects.svg}} placeholders, and wiki_build fills them in after the charts are drawn.
~~~

## 2026-11-24 feat(tools): double-read theme pipeline with evidence tiers and an audit

~~~text
Assigning one aspect of the game to a function needs two readings that agree and evidence a script can check, not one model's guess. This adds that pipeline and the first measured run of it.

theme_prep.py picks targets (fixed stride over the address space, so a sample spans every region) and builds dossiers through map_read_prep.py --all; theme_prompt.md is the readers' only instruction; theme_adjudicate.py accepts an address only when both readers name the same non-Unclear aspect and each quotes one of the function's own strings or names one of its direct callees, grades the pair strong/medium/weak and sends disagreements to a third read; theme_audit.py draws a fixed sample for a person to judge and scores it; theme_stats.py prints the run's numbers.

The pilot found and fixed three things that would have made any number meaningless. map_read_prep.py ended a function at the next *selected* function, so a 224-byte body carried 15,072 operations from the rest of the file with a cross-window sample; the parser now knows every function's start line. The dossier did not show the function's own strings, so readers had to fetch them from the map index; they are now a line in each entry. The adjudicator required the cited callee's label to be already accepted, which a fresh run never has, and did not parse f_ prefixed addresses.

200 functions, three reads: the readers agree on 61 of the 80 addresses where both named an aspect (76%); 80 of 200 are accepted (29 strong, 1 medium, 50 weak), 120 abstained (85 no decisive evidence, 26 unsettled by three reads, 9 evidence failed), and only 29% of accepted labels merely repeat the window's aspect. A hand audit of 18 accepted rows found 14 right, 0 wrong and 4 unsure (three generic library routines, one claim the dossier does not support). Report: docs/reports/2026-11-24-theming-double-read.md.
~~~

## 2026-11-24 feat(tools): give every vtable method its class as evidence

~~~text
The pilot left 85 of 200 functions with no label; 31 of them are vtable methods whose body is a getter, an empty stub or a field write, and nothing in the function itself says which system it serves. Its class does: the strings its sibling methods quote ("is_marketplace_sell", "RTTSMG_CATMITT", "lg_TeamSettings"), the strings one hop out, and the roles of its named siblings.

map_read_prep now writes a `class:` line for every method (and loads vtable_class.py, which had to be put on sys.path because -I drops the script directory). theme_adjudicate checks class evidence against the same class sets and ranks it: a sibling method's string or a naming sibling is strong, a one-hop string is medium. theme_prep gained --only (a deliberate address list, for an experiment on addresses an earlier run abstained on) and --reuse (rebuild the dossiers for the same targets). The prompt gained the `class` basis; its JSON example no longer uses a real string from a test batch.

Experiment: the 40 functions both earlier readers had called Unclear (31 vtable methods, 9 non-vtable controls) were read again with the class line. Vtable group: A labelled 14, B 13, 11 agreed, 11 accepted after a third read (9 strong, 2 medium). Controls: A 6, B 0, 0 agreed, 1 accepted (weak, from operations) — the gain is specific to the vtable methods, not readers getting bolder. Hand audit of the 12 accepted: 10 right, 0 wrong, 2 unsure (fielding/in-play boundary; Home Run Derby mapped to batting). Whole map: 25,243 of 55,394 vtable slots sit in a class that quotes something; 4,151 classes quote nothing. Report: docs/reports/2026-11-24-theming-double-read.md.
~~~

## 2026-11-24 docs(wiki): a theming progress page and its two charts

~~~text
The wiki could show how complete the map is and how functions group by their window's theme, but not how far the per-function labels had got. This adds that: a page, a chart on the home page, and the numbers kept in tools/data/theming-pilot.json so a checkout without work/ can still rebuild the wiki.

tools/wiki_theming.py draws two dark-card charts with the palette and helpers wiki_completeness.py already uses. The progress chart stacks the 200-function sample by evidence strength (29 strong, 2 medium, 49 weak), no evidence (85) and not settled (35), then repeats it for the 31 vtable stubs that had no evidence (11 labelled once their class was in the dossier) and for the 9 controls (1 labelled, weak) — the controls are what separates class evidence from bolder reads. The aspects chart shows the 80 accepted labels by aspect, which is a different measurement from the window-based chart beside it on the home page.

The page records the evidence rules, the 76% agreement, the 29% of labels that merely repeat the window theme, and the two hand audits (18 rows 14/0/4 and 12 rows 10/0/2) with what the unsure ones mean. wiki_build now replaces chart placeholders in every page, not only Home, and the WCAG check covers theming-*.svg and the two new palette segments (no evidence, not settled).
~~~

## 2026-11-25 docs(wiki): state the tag meanings as a table, word for word

~~~text
C is a string, symbol or import; I is inferred via the shape of the code or the call graph; H is inferred via neighbours. The pages and the chart legend said it in three different ways, and two of them called H a guess.

One TAG_TABLE in tools/map_functions_doc.py now feeds Function map and Function census; Home carries the same table; the coverage chart's legend and subtitle use the same words, so the picture and the text agree.
~~~

## 2026-11-25 docs(wiki): the tag legend as its own section

~~~text
Home had the tag table wedged between the coverage chart and the sentence about its lower bar. It is now a "Tag legend" section with the line that says what the letters are for, placed after the two map charts that use them.
~~~

## 2026-11-25 docs(wiki): put the tag table back under the coverage chart

~~~text
It stays where it was: right after the coverage chart, before the sentence about its lower bar. No heading, no new page, no further moves.
~~~

## 2026-11-25 docs(wiki): a real table of contents on the home page

~~~text
The home page listed nine pages under "How it is built and measured", which left 35 pages reachable only through the sidebar or another page. The table now lists every page, grouped exactly as the sidebar groups it, from the same section lists in wiki_build.py so the two cannot drift apart. The 17 read-role detail pages, which the sidebar deliberately leaves out, get their own row; a generated check inside the build confirms that every page it writes appears in the table.
~~~

## 2026-11-25 docs(wiki): name the function registers by address range

~~~text
The sidebar and the home table of contents listed Functions A to F and Functions SDK by letter. A reader looking for an address had to remember which letter holds it. The labels are now the ranges the pages cover, taken from the same REGIONS table that draws the pages (0x7000000000-0x70005fffff for A, and so on), and the SDK page's prose now uses the same inclusive last address as its label.

The sidebar writer also gained encoding="utf-8": it was using the machine's code page, which turned a non-ASCII dash into a byte the link check could not read back.
~~~

## 2026-11-25 docs(wiki): address labels for the region notes too

~~~text
The Game binary regions entries said Region A to F. They now show the range they cover, from the same REGIONS table, so both the region notes and the function registers are found by address. The two sections necessarily show the same six ranges; the section heading says which page set a link opens.
~~~

## 2026-11-25 docs(wiki): new sidebar order, address ranges as numbered lists

~~~text
Port and game flow first, then the function map and regions, findings last. The address-range entries under Function map and Game binary regions are ordered lists, so a range reads as one of a sequence rather than a loose bullet. The home table of contents follows the same section list, so it reorders with the sidebar.
~~~

## 2026-11-25 docs(wiki): keep the chart's note with the chart

~~~text
"The lower bar counts the bodies that were read" had the tag table in front of it, so it read as a caption for the table. The sentence now sits directly under the coverage chart it describes; the table follows it. The table itself has not moved.
~~~

## 2026-11-25 docs(wiki): home page in the layout the owner wrote

~~~text
Specs block, tag legend at the top with a rule under it, then the coverage and aspect charts, the theme-label section and the table of contents. The caption under the coverage chart sits with the chart. Chart names and the contents table stay as placeholders in the source; the build substitutes the content-hashed names and the generated table.
~~~

## 2026-11-25 docs(wiki): the prose research pages as tables

~~~text
The body and region pages were walls of prose: one paragraph per step, with addresses, strings and tags buried in sentences. Every one is now table-first, with a row per function or per state and the evidence in its own column: the ten body pages (AI layer, audio, batter-up, fielding, frontend, intro states, lighting, modes, play/game over, pre-play/in-play), the six region notes A to F, and the game state machine page.

Fidelity was checked mechanically for each page before and after (work/scratch/table_check.py, run again over all 17 at the end): every 0x address and every double-quoted string in the original is present in the table version, and the [C]/[I]/[H] tags are kept (counts rise where a tag that covered a list is repeated per row). No facts were dropped to make the tables fit; chains of events sit in a What it does cell.

wiki_build passes: 62 pages, no broken links, no table header over three words (three headers were shortened: Why open, Evidence, Not mapped), WCAG check passes.
~~~

## 2026-11-25 docs(wiki): the tag legend on every page that uses tags

~~~text
42 pages carry [C]/[I]/[H] (or a Tag column) and only the two map pages explained them. wiki_build now inserts a one-line legend after the generated banner (or at the top of a hand-written page) on every tagged page that has no legend of its own: "Tags: C string, symbol or import; I inferred via shape of code or call graph; H inferred via neighbours."

26 pages take that line. 16 already explain the tags in their own words and keep them, because in those pages C means "the body shows it" rather than only a string or symbol; overwriting the line would quietly change what their rows claim.
~~~

## 2026-11-25 docs(wiki): drop the chart captions the charts already carry

~~~text
The two map charts have their own subtitles inside the image, so the home page does not repeat them: "The lower bar counts the bodies that were read" and the paragraph about how the aspect labels are grouped are gone.
~~~

## 2026-11-26 feat(theme): filter library code, restore the judge and tighten the evidence rules

~~~text
Adds the shared-engine filter and the pipeline doc, judges only unjudged
rows and keeps earlier verdicts.
~~~

## 2026-11-26 feat(wiki): read every function body and format the wiki

~~~text
Body reading now covers every function; the wiki formats code and labels
its address ranges, and the reading method is published.
~~~

## 2026-11-26 feat(menu): clean up the offline main menu

~~~text
Hides the offline panel, scrolls to the mode tiles, holds a black window
while the menu settles and removes the network error box. Adds the layout
editor, the dev control channel and the menu checks.
~~~

## 2026-11-26 feat: add the trainer, dev panel and the other research work

~~~text
The in-game trainer and its cheats, the dev panel, the shorter match-start
freeze, the scalar NaN fix-up, the repeatable-run harness and traced
wiki themes. Conflicts between them kept both sides.
~~~

## 2026-11-26 fix(menu): drop only the network error box from the message queue

~~~text
Removing the call at main+0xaa6f0c kept every queued box from opening, so
the game hung waiting for the answer to its own ones. The site now calls
net_box.c, which takes "Network Error" entries off the queue first.

tools/net_box_test.c: 8 checks pass. In game, one run: the error box was
dropped at the menu, later boxes opened and the upgrade screen went on.
~~~

## 2026-11-26 feat: add a mods folder with the starting-tokens mod

~~~text
The mod writes a RomFS override that sets a new Road to the Show player's
tokens. The README gets a table of the mods. One run with 60000: the
screen showed it and spending worked.
~~~

## 2026-11-27 chore(tools): time the season sim in a running game

~~~text
Franchise simming was reported slow. Measured on a live game: 45 games a
simulated day, at most 3 per drawn frame (f_700075d8d0), 7 to 11 ms each,
about 420 ms a day; the bullpen search f_7001875aa0 is 37 % of the main
thread's samples while simming.

live_sample.py samples an already running game for prof_report.py;
season_sim_watch.py times the sim from the game's memory.
~~~

## 2026-11-27 fix(kernel): stop an idle sleep poll from spinning a host core

~~~text
The SCREAM file stream thread (f_7001b42280) checks its queue and sleeps
100 us in a loop. Every sleep up to 1 ms spun on the clock, so the thread
held a host core, menus included: 801,235 such sleeps in 90 s.

A thread that asks for the same sleep of 100 us or more over 16 times in a
row, running under 50 us between them, now waits on the OS timer until it
does some work. Occasional and shorter sleeps stay on the clock.

Sound thread: 97-99 % of a core (six runs) to 6.7 % (one 10 s sample).
Whole game over three alternated pairs: 337, 338, 334 % to 246, 243, 242 %.
Frame rate unchanged within noise (122.8 fps over 7 windows, 123.2 over 9).
An idle poll's 100 us sleep now takes about 0.54 ms.
~~~

## 2026-11-27 feat(boot): start the GameOnly boot with a chosen matchup

~~~text
With the code patch set boot_teams on (MLB_BOOT_TEAMS=1, off by default),
MLB_BOOT_AWAY and MLB_BOOT_HOME give the team ids: boot.c puts them in the
patch page, and boot_teams.c writes the settings block's team bytes during
boot. MLB_BOOT_TABLE=1 also copies the rosters into the match player table
(experimental). 1.0.20 only.

The patch set itself is not in tools/data/patches-1.0.20.txt; without it in
the generated code this does nothing. Compile-checked only, not run.
~~~

## 2026-11-27 chore(tools): tidy the wiki sidebar, code formatting and chart subtitles

~~~text
The sidebar gets a Read roles section grouped by region, bullet lists for
the address ranges and sorted links, and lists the Menu page in place of
Main-menu-offline-panel. More tokens are shown as code (signed offsets,
register brackets, CamelCase names, printf formats), and touching code spans
are merged. The Read roles index explains the 3,500-row page limit, and both
coverage charts have shorter subtitles.

tools/wiki_build.py wrote 74 pages with no missing pages or broken links.
~~~

## 2026-11-27 docs(readme): fold the tables into toggles

~~~text
Each of the five tables is inside its own collapsed details block, so the
page is shorter to read. The table text is unchanged.
~~~

## 2026-11-27 docs(readme): plainer wording in the fork section

~~~text
Also drop the research/msdf-skip branch name, since the fix is on main.
~~~

## 2026-11-27 docs: recount the boot options and add the tool that lists them

~~~text
The dev-config doc counted 109 option hashes with 27 named, from three
query functions. The 1.0.20 code has two option tables read by four
functions, 132 distinct hashes, and 32 names: 25 documented ones that
hash correctly plus 7 words from the executable. AlwaysDelayService does
not hash to its listed value and is unnamed again.

Checked with tools/config_options.py --names --check (exit 0).
~~~

## 2026-11-27 feat(gfx): use every PS5 head texture, colour maps on by default

~~~text
The index left out 41 normal-map entries whose Switch textures share a hash
of their first 16 KiB, and all colour maps. Those textures are now told
apart by a hash of the whole storage, or, for four pairs of heads with the
same Switch colour map, by which head file the game opened. Heads with no
PS5 file are compared too, so none is given another's face. Colour maps are
indexed unless --no-color is given, and MLB_HD_TEXTURES has a settings row
and a menu toggle.

Colour maps: 2,409 heads (none in the default index before). Normal maps:
2,411 heads (2,370 before). 13 heads are on one side only.

Checked: 26 tool tests; every Switch head texture through the runtime
lookup and loader, 0 failures; a build with the compute fix off blows out
Ohtani's face (11 flagged shots), the shipped one does not (0); one played
match to the post-game menu, 53 heads, 110 swaps, no errors. Not confirmed:
two dozen faces looked at. Open: stadiums turned black now and then in that
match, cause unknown.
~~~

## 2026-11-27 docs: name CloudSaveUrl and add the joined-word option search

~~~text
The option hash is 28 bits wide, not 32, so the chance-match figure for
the word search was 16 times too low (0.4, not 0.03). config_guess.py
joins words from each option's own code: 8 hits against 0 on the
random-letter control, of which only CloudSaveUrl is borne out by the
code that reads it. 33 of 132 options are now named.

Checked with config_options.py --names --check (exit 0) and
config_guess.py with and without --control.
~~~

## 2026-11-27 docs: record what some unnamed boot options do

~~~text
config_effects.py walks both sides of the branch after each option
lookup (197 of 246 unnamed sites). The table lists the options whose
effect is visible, among them two crash tests, the save compression
step and a start selector in the game-UI task; the [C] rows were checked
in the disassembly, none was tried in game.
~~~

## 2026-11-27 docs(wiki): rewrite wiki prose in a plainer style

~~~text
Ran the human-writing pass over every hand-written wiki source: dashes
replaced, empty table cells no longer hold a dash, staged closers and
sentences that only announced the tables removed. All 35 Markdown sources
pass its checker with numbers, links and code unchanged; the 74-page build
has no broken links. Generated per-function rows are left as they are.
~~~

## 2026-11-27 docs(wiki): say the match-start skip and prefetch are in main

~~~text
The wiki still called msdf_skip, the float fix-up and the head prefetch
research-branch work. msdf_skip and MLB_FP_FIXUP reached main in (2026-11-26, "feat: add the trainer, dev panel and the other research work")
(2026-11-26), the prefetch in (2026-11-22, "perf(hdtex): read a head's PS5 file in the background when the game opens its Switch file"). The fix-up was not remeasured on
main, and msdf_skip has no 1.0.15 site.
~~~

## 2026-11-27 fix(hid): end the black screen when there is no press to make

~~~text
The end of the black hold was scheduled only along with an A or Down press.
With no_net_box on (the default) a press on a network tile needs neither, so
the screen stayed black and the controller ignored until the 12 s limit.
It now ends 0.7 s after the menu is back.

In game, Diamond Dynasty press, one run each: black 12.0-12.8 s before,
between 2.1 and 2.8 s after.
~~~

## 2026-11-27 fix(tools): measure save names and strings in bytes

~~~text
rename and set-field checked the number of characters, so non-ASCII text could
overflow its field and shift the rest of SAVEINFO or the archive.
~~~

## 2026-11-27 fix(harness): make the dev panel's frame log and texture dump record

~~~text
Both buttons were stubs although harness.c implements them, and the panel said
"recording" while nothing was written. The texture field now takes a dump form,
and the frame log creates its folder.

In game (MLB_DEVPANEL_TEST), one run: a 3242-line frame log was written.
~~~

## 2026-11-27 fix(menu): give F7 to the trainer when it has the key

~~~text
In dev builds the dev panel took F7 first, so a trainer key set to F7 never
fired. Checked with window messages in tools/menu_hotkey_test.cpp, not by
hand in game.
~~~

## 2026-11-27 feat(tools): raise C/I/H tags to superscript in the built wiki

~~~text
A tag that annotates a claim is wrapped in <sup> at build time, so the
sources stay plain. Tag columns, legends, tags used as words and code are
left alone; wiki_sup_test.py covers 14 cases. 1,903 tags raised on the
first build.
~~~

## 2026-11-27 docs(wiki): break up dense blocks, shorten headings, drop correction logs

~~~text
61 prose blocks over 400 characters became short paragraphs, lists and
tables (0 left). Headings are now at most five words without parentheses;
dates and addresses moved to the line below. The "Corrections to earlier
pages" table and similar notes about earlier reports and agent briefs are
folded into the claims they concern. wiki_dense_check.py checks both rules.
~~~

## 2026-11-27 fix(tools): keep the wiki's italic banner and legend lines italic

~~~text
codeify took the opening underscore of "_Generated by ..." and "_Tags: ..."
for the start of a symbol and wrapped the word in code, so pages showed
stray underscores. Lines that open with a broken italic: 71 before, 0 after.
~~~

## 2026-11-27 fix(tools): repair the syntax error in the wiki text test

~~~text
The previous commit added the italic-line cases with a broken f-string, so
the test did not run. 17 of 17 cases pass; the rebuilt wiki has 0 lines
with a broken italic opener.
~~~

## 2026-11-27 fix(tools): format every state-style name in the built wiki

~~~text
Only all-caps names whose first part had four or more characters were
wrapped as code, so PRE_PLAY and IN_PLAY sat bare beside BATTER_UP in the
same column. Bare names in the built pages: 1,109 before, 0 after (quoted
game strings are left as they are). 21 of 21 text cases pass.
~~~

## Subjects of the commits that had no body

- 2026-11-21 readme: say what the fork is for, move the upstream readme into a toggle
- 2026-11-21 docs: fastload A/B showed no measurable change; mark unverified rows
- 2026-11-21 hd textures: normal maps only, a PS5 colour map makes the face yellow
- 2026-11-21 make_hd_index: --all-heads, header-only PS5 reads, skip entries whose Switch textures share a hash
- 2026-11-22 hdtex: read only the kept levels of a PS5 file (a cold read of the whole file took 31 ms, now 12)
- 2026-11-22 docs: PS5 textures: all-heads index, what is known about the yellow colour maps, load cost
- 2026-11-22 docs: PS5 textures: what the yellow colour-map experiments showed
- 2026-11-22 docs: reports: yellow PS5 colour maps, frame dips and hitches, PS5 normal maps for all heads
- 2026-11-22 docs: reports: yellow colour maps: result of the one-main-pass-exposed runs
- 2026-11-22 docs: PS5 colour maps: fixed-from-frame-0 runs show every kind of reader breaks on the 1024x512 level, no shader fix
- 2026-11-22 hd textures: compute passes read a PS5 image from the Switch-size level, which fixes the yellow face with PS5 colour maps
- 2026-11-22 docs: reports: yellow colour maps: the cause (compute skin-tone fetch) and the fix
- 2026-11-22 docs: reports: hd texture performance: off vs normals vs normals+colour, six 400 s runs
- 2026-11-22 readme: PS5 textures: colour maps (opt-in), measurements, how to turn it off
- 2026-11-22 tools: perf_summary.py turns a run's log into one JSON summary
- 2026-11-22 readme: PS5 textures bullet and a feature table for the fork section
- 2026-11-22 CLAUDE.md: rules for this fork, what upstream already has, how upstream works
- 2026-11-22 docs: use a placeholder for the PS5 dump path in the examples
- 2026-11-22 CLAUDE.md: allow a Co-Authored-By trailer for the model, as upstream does
- 2026-11-22 docs: how to check a PS5 texture index and what each message means
- 2026-11-22 Merge branch 'tools/index-check'
- 2026-11-22 Merge branch 'tools/bench'
- 2026-11-22 Merge branch 'tools/log-time'
- 2026-11-22 Merge branch 'docs/housekeeping'
- 2026-11-22 Merge branch 'docs/bug-research'
- 2026-11-22 Merge branch 'research/load-stall'
- 2026-11-22 docs: CLAUDE.md gets the research-branch section and the signing note
- 2026-11-23 chore: ignore .claude/worktrees
- 2026-11-23 test(harness): BAL scenario that dumps the field picture
- 2026-11-23 docs: skill records the exact steps to publish the wiki
- 2026-11-23 docs: group the wiki's region pages under one collapsible category with an index page
- 2026-11-23 docs: skill gives the right patch site counts (walkup_light 6, walkup_leaders 1)
- 2026-11-24 docs(harness): three cold-start exhibition runs and the field that picks the players
- 2026-11-24 docs(harness): the keyed option setter that writes the home and away team bytes
- 2026-11-24 docs(wiki): how to choose the teams of a run, and what is still open
- 2026-11-25 fix(tools): report third-read decisions after an abstention
- 2026-11-25 docs(wiki): show function theming continuation results
- 2026-11-25 docs(wiki): publish four more function theming batches
- 2026-11-25 docs(wiki): report 252 accepted function themes
- 2026-11-25 docs(wiki): report 315 accepted function themes
- 2026-11-25 docs(wiki): report 326 accepted function themes
- 2026-11-27 docs(readme): list the idle sound thread fix
- 2026-11-27 docs(readme): put Mods before What this fork is for
- 2026-11-27 docs: note what is known about the black stadiums
