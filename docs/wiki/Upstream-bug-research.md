A reading of four open issues in the upstream project, done on 2026-11-22 from the merged code (upstream 0.2.0 plus our changes) and from the logs two reporters attached. Nothing was run and the game was not started, so every cause below is a reading of code and logs.

| Rank | Issue | Problem | Cause | Confidence | Effort |
|---|---|---|---|---|---|
| 1 | 10: buttons switch to circle during play | By design: the face-button map flips by screen and some overlay screens are not on its lists | Two screens missing from the menu list | About 85 percent | Hours |
| 2 | 18: no ball in one batting-cage mode | Only seen above 60 fps | Unknown | About 25 percent for any one guess | Small to reproduce, medium to fix |
| 3 | 21 and 26: local multiplayer | Missing feature: all pads are merged into player 1 | By design | About 95 percent | 2 to 4 days |
| 4 | 14: crash in the middle of a game | The attached log shows no crash | Cannot tell | | Nothing to do without a better log |

## Confirm button swap

On a PS5 pad, cross confirms in menus, but during play the confirm button becomes circle, for example for dynamic challenges and to skip scenes. The maintainer said this is on purpose: gameplay controls need the by-place layout, so confirm is cross in menus and circle in game.

`hid.c` keeps one flag, `screen_play`. `hid_game_log` reads the game's own `uiEngine: Entering screen: [<movie>-><screen>]` lines and sets it from the movie name.

| Movie | Effect |
|---|---|
| on the short menu list | face buttons map by label (cross confirms) |
| on the short play HUD list | maps by place (circle is the game's confirm) |
| any other | changes nothing |

The scene-skip screen (`PresSkip`) and the dynamic-challenge popup are on neither list, so while the last classified movie was a play HUD movie, circle confirms. The attached log fits: `PresSkip` is entered at line 6083 and the only switches are "by position" at `Scorebar` and back "by label" at `PM_Main_Alternate`.

Fix: add `PresSkip` and the challenge screen's name to the menu list. The challenge screen's name is not known; one log that includes a dynamic challenge would give it. Risk: a screen that needs both a confirm and a gameplay button at once would lose one.

## Batting-cage ball

A reporter said one of two Road to the Show batting-cage modes does not show the ball coming in from the sides.

At the default limit of 60 nothing in `framerate.c` runs. At another limit it writes 0 into the game's vsync count at every present, so the game's step is the average of the last 15 frame times. It also fills the timer's carry with 1/60 s as a guard (upstream commit `0c6fe91`, not confirmed as the cause).

Three candidates, none confirmed:

| Candidate | Idea |
|---|---|
| Whole-vsync stepping | the side-feed mode steps by whole vsyncs and one frame still steps wrongly |
| Step arithmetic | the ball code divides by the step or compares it with a threshold, and a step near 1/144 s breaks it |
| Present mode | the monitor's present mode, not the step |

About 60 percent that the bug only exists with a limit other than 60. To settle it: the same mode and save at 60, 144 and 240, noting whether the ball shows, then the `frame rate:` log lines and an F12 capture.

## Local multiplayer

Two reporters with two controllers see both pads controlling player 1. That is the design:

| Code | Behaviour |
|---|---|
| `connected()` | true only for the first pad id |
| `pad_read` | ORs the buttons of every SDL pad and takes the stick pushed furthest |
| controller-support applet | answered with one player |
| the game's pad records | an array of up to 8 (7 were seen), so the game itself is built for several pads |

Not known: how the game starts a 2-player game (whether it asks for pad 2's style set, calls the controller applet with a player count, or has its own join screen). A default-off log of the ids it asks for would settle that.

Fix outline: give each SDL pad a slot, keep the keyboard on player 1, make the connected check, style set and state per id, answer the applet with the number of pads, route vibration by id. The failure modes (a second pad that steals the first's input) are visible in play, so the estimate is 2 to 4 days.

## Mid-game crash

The attached log is from build 0.1.4, game 1.0.20, 11 minutes of earlier playtime. It ends normally: seven window focus changes, then "window closed; exiting", the pipeline-cache save and the frame-time summary. There is no `FATAL` and no device fault.

About 80 percent that it is not the log of the crashing launch, because `mlb.log` is overwritten at every start. What would help is a log copied before relaunch that ends in a `FATAL:` line. The 5 to 6 hour memory-leak crash fixed in 0.2.0 does not fit an 11-minute reporter.

## Open questions

Whether the challenge screen uses the game's confirm button; the reporter's frame limit in issue 18; how the game starts a 2-player game; whether a virtual pad driver on the dev PC can serve as a second pad.
