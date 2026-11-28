# Report: four open bugs in upstream (sam110411/fastball)

Status: research only. Nothing was run. The game was not started and nothing was built. The code read is the merged
tree of 2026-11-22 (upstream 0.2.0 plus our changes). The issue threads were read with `gh` on 2026-11-22, and the two
`mlb.log` files attached to issues 10 and 14 were downloaded as text and read; both come from a 0.1.4 build.

## Summary

| Rank | Issue | What it is | Cause (confidence) | Effort | Fix generic enough for upstream |
| --- | --- | --- | --- | --- | --- |
| 1 | #10 buttons switch to circle during play | By design: the face-button map flips by screen, and some overlay screens are not on its lists | High (about 85%) | Small, hours | Yes, and the maintainer said he would look |
| 2 | #18 no ball in one batting cage mode | Unknown; only seen above 60 fps; the 0.2.0 step guard is unconfirmed | Low (about 25% for any one guess) | Small to reproduce, medium to fix | Yes |
| 3 | #21 and #26 local multiplayer | Missing feature: all pads are merged into player 1 | Certain (about 95%) | Large, 2 to 4 days | Yes |
| 4 | #14 crash in the middle of a game | The attached log shows no crash | Cannot tell | Nothing to do without a better log | Nothing to fix yet |

Ranked by value to a solo owner against effort. Issue 10 is the cheapest and the clearest. Issue 18 matters most if you
play Road to the Show above 60 fps. Issue 21 and 26 is the biggest win if you own two controllers and the biggest job.

## Issue 10: buttons switch to circle during play

**What the reporter saw.** On a PS5 pad, cross confirms in menus, but during play the confirm button becomes circle,
for example in dynamic challenges and to skip scenes, "as if I was playing on a Nintendo Switch controller". The same
issue also reports missing last-name audio and asks whether textures such as Petco Park's backdrop can be improved.
The maintainer answered on 2026-11-16 that this is on purpose: gameplay controls (throw to first, pick pitches, swing
types) need the by-place layout, so confirm is cross in menus and circle in game, and that he will look at making
confirm work in game too.

**What the code does.** `runtime/mlb/hid.c` keeps one flag, `screen_play`. `hid_game_log` (hid.c:182) reads the game's
own `uiEngine: Entering screen: [<movie>-><screen>]` lines and sets the flag from the movie name. A short list of menu
movies sets it to 0, which maps face buttons by label (cross confirms); a short list of play HUD movies sets it to 1,
which maps by place (circle is Switch A, the game's confirm). Any other movie changes nothing. The lists:
- menus: TitleLoadingScreen, PM_Main_Alternate, Pause_Menu, Selection Box 2, SubMenu Selection Box 2, Dialog, Keyboard,
  CareerDecision, LaunchGame, Topbar, Background, and any movie starting with `ol_`;
- play: Scorebar, TM_ScoreBar, PitchSelect_Bars, PitchHistory, PitchMeter_Feedback, SwingAnalysis, Fielding_Assets,
  Fielding_Assistance, Bullet_Time_Assets, Lead_Runner.

`hid_face_position` (hid.c:208) returns that flag and `face_bits` (hid.c:223) applies it.

**Most likely cause (about 85%).** The scene-skip screen (`PresSkip`) and the dynamic-challenge popup are on neither
list. They appear while the last classified movie was a play HUD movie, so the map stays by place and circle confirms.
The attached log fits: `PresSkip` is entered at line 6083, and the only switches are "by position" at `Scorebar`
(line 6134) and back "by label" at `PM_Main_Alternate` (line 6179). The log ends before any dynamic challenge, so the
challenge screen's name is not known.

**What would settle it.** One log from a Road to the Show game that includes a dynamic challenge and a skippable scene
after play has started. The lines `Entering screen: [...]` around those two moments give the names to add.

**Repro on your PC.** Any exhibition game with a PlayStation or Xbox pad: skip the pre-game scene and watch the
`hid: face buttons by ...` log line. The challenge popup needs a Road to the Show save; whether you have one here is
not known.

**Fix and effort.** Add `PresSkip` and the challenge screen's name to the `menus` list in `hid_game_log`, so confirm is
by label while they are up; the play HUD movies are entered again when play resumes, which flips the map back. A few
lines and an hour of checking with a pad. Risk: a screen that needs both a confirm and a gameplay button at once would
lose one of them.

**Upstream.** Generic and welcome; the maintainer already said he would investigate.

Two side notes from the same thread: the missing last-name audio is a separate bug (the reporter attached a log), and
the Petco Park backdrop question is relevant to the PS5 texture work as a candidate category for later.

## Issue 18: no ball in one batting cage mode above 60 fps

**What the reporter saw.** On 2026-11-18, "AbrahamHuitron" reported that one of the two batting cage modes in Road to
the Show practice does not show the ball coming in from the sides; the mode where balls fall from above works. The
title says "above 60hz refresh rate". No comments, no log, no settings were given.

**What the code does.** The frame limiter is `runtime/mlb/framerate.c`, explained in `docs/frame-rate.md`. At the
default limit of 60 nothing in it runs (`frame_step_present`, framerate.c:151). At any other limit it writes 0 into the
game's vsync count at every present while the game is in its averaging mode, so the game's time step is the average of
the last 15 measured frame times, and it fills the timer's carry with 1/60 s as a guard (framerate.c:171-175). In the
game's whole-vsync mode it hands the game's own count back and the game runs at 60. Upstream commit `0c6fe91` (2026-11-18, "Frame rate: never a zero game step when the game switches to whole vsyncs (#18)") added the
carry guard while tracing this issue; its comment says it was not reproduced and not confirmed as the cause.

**Most likely cause.** Not known. Three candidates, none confirmed:
1. The side-feed cage mode uses the game's whole-vsync stepping, and one frame still steps wrongly. The carry guard
   should have fixed this; the issue is still open, but nobody reported back after 0.2.0.
2. The mode's ball code divides by the time step or compares it with a threshold, and a step near 1/144 s breaks it.
   With averaging on, the step has a floor of vsyncs/60, which is 0 when the count is 0, so steps below 1/60 s
   reach the game.
3. The cause is not the step at all but the present mode on a high-refresh monitor.
Confidence in any single one is about 25%. About 60% that the bug only exists with a limit other than 60: the
reporter's limit is not stated, and a monitor above 60 Hz with the default limit of 60 does not run this code.

**What would settle it.** Same practice mode, same save, limit 60 against 144 against 240, with a note of whether the
ball shows. If it shows only at 60, it is the step. Then: the `frame rate:` log lines (does the mode switch to "the game's
own 60 fps (it steps by whole vsyncs here)"?), `MLB_TRACE=perf` for the speed ratio, and an F12 capture to see whether
the ball is drawn off screen or not drawn at all.

**Repro on your PC.** Needs a Road to the Show save that reaches batting practice. A limit above the monitor's rate
only takes effect with Presentation set to Fast VSync or Off; the monitor's rate is not known here.

**Fix and effort.** Reproduction is small. A workaround is also small: hold 60 on that screen the way the code
already does for whole-vsync mode. A root-cause fix is unknown until the step is shown to be the cause.

**Upstream.** Generic.

## Issues 21 and 26: local multiplayer

**What the reporters saw.** Issue 21 (JUANKY577, 2026-11-19): the game only supports one player offline; a second pad is
not used. A comment (DSeverinoX, 2026-11-20): two PS4 pads both work as Player 1 at the same time. Issue 26
(DSeverinoX, 2026-11-22): two original DualShocks, the game only recognises Player 1 and both pads control it.

**What the code does.** This is the design, not a detection fault.
- The header comment (hid.c:5) says the console is docked, so the controller is one full-key pad as player 1 (NpadId
  No1).
- `connected()` (hid.c:604) answers true only for `ID_NO1`; every other id reads as disconnected.
- `pad_read` (hid.c:473-490) ORs the buttons of every SDL pad and takes the stick pushed furthest; `poll` (hid.c:542)
  adds the keyboard. One merged state serves player 1.
- `ov_controller_support` (hid.c:763) answers the game's controller applet with one player, No1.
- `ov_supported_ids` (hid.c:622) only logs whether No1 is listed; what ids the game lists is not logged.
- Vibration handles are per id but `pad_rumble` (hid.c:498) drives every pad.
- The game's own pad records are an array of up to 8 (`PAD_MAX`; 7 were seen; `repeat_pace`, hid.c:665-711), so the
  game itself is built for several pads.

**Cause.** Certain (about 95%): all pads are one player by design, so both reporters see exactly this.

**What is not known.** How the game starts a 2-player game: whether it asks `GetNpadStyleSet` for No2, calls the
controller applet with a player count, or has its own join screen. The log has a `2P Game` flag but nothing about ids.

**What would settle it.** A default-off log of the ids passed to `SetSupportedNpadIdType`, the ids asked through
`GetNpadStyleSet` and `GetNpadState`, and the applet's arguments, during an attempted 2-player exhibition.

**Fix outline.** Give each SDL pad a slot (first pad No1, second No2, and so on); keep the keyboard on No1; make
`connected()`, the style set and the state per id; answer the applet with the number of pads; route vibration by id;
keep the settings-menu pad read on No1. The face-button map and button icons are global, which is acceptable.

**Repro on your PC.** Needs two controllers. Your PATH shows a Nefarius virtual pad driver, which might supply a second
pad; that it works with SDL is untested. The 2-player mode is in Exhibition.

**Effort.** Large, about 2 to 4 days, mostly because the game's join flow is unknown and the failure modes (a second pad
that steals the first's input) are visible in play. **Upstream.** Generic, and two open issues ask for it.

## Issue 14: crash in the middle of a game

**What the reporter saw.** On 2026-11-16, "Manuel15160410" reported crashes in the middle of a session in Road to the
Show and Franchise. The maintainer asked for `mlb.log`; the reporter attached one.

**What the log shows.** Build 0.1.4+54af845, game 1.0.20, 11 minutes of earlier playtime, 11,968 lines. The last
lines are a normal exit: seven `window lost/gained the focus` events between 19:46:45 and 19:47:59, then `window
closed; exiting`, the pipeline-cache save and the frame-time summary. There is no `FATAL`, no device fault, no abort.
The last game output is an ordinary play (`Best Play State Changed`). Worst frames: 622 ms at frames 2 and 3 (start-up),
350 ms at frame 2279, nothing alarming. One game line, `ERROR: eg elbowGuard_jordan needs 2 dgrps! (has 0)`, looks
like a game asset warning and has no sign of causing a stop.

**Most likely cause.** Not determinable from this log (80% that it is not the log of the crashing launch). The repo's
CONTRIBUTING says `mlb.log` is overwritten at every launch, so a reporter who restarts the game before copying it
sends the next session's log. Two other possibilities: the game froze and the reporter closed the window (the focus
changes suggest alt-tabbing), or a crash without a logged fatal line. The 5 to 6 hour memory-leak crash fixed in 0.2.0
(issue 17) does not fit: this reporter had 11 minutes of total playtime.

**What would settle it.** A log copied before relaunch that ends in a `FATAL:` line (symbolise with `llvm-symbolizer`),
the Windows Event Viewer entry, and how long into the session it happened. 0.2.0's crash reports after a graphics
driver error say more than 0.1.4's.

**Repro on your PC.** None; there is nothing to reproduce. **Effort.** Nothing to do until a better log exists.
**Upstream.** Nothing to fix yet.

## Not verified

- Nothing here was run, so every cause is a reading of code and logs.
- Issue 10: the dynamic challenge screen's name; whether those screens use the game's confirm button; whether adding
  the names flips the map back correctly when play resumes.
- Issue 18: the reporter's frame limit and monitor, the mode's frame logic, and whether the 0.2.0 step guard changed
  anything.
- Issues 21 and 26: how the game decides to start a 2-player game and which ids it asks for.
- Issue 14: whether the attached log is from the crashing launch.
- The two attached logs come from a 0.1.4 build; line numbers and behaviour may differ in 0.2.0.
- That a Nefarius virtual pad can serve as a second pad for testing.
