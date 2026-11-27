# The in-game trainer

A panel over the running match that changes the situation and shows what the game is doing. Game version 1.0.20 only,
offline only, off by default.

## Turning it on and using it

F1 → Trainer → Trainer: On (or `MLB_TRAINER=1`, `--trainer 1`). Then, in a match:

| Action | Keys | Controller |
|---|---|---|
| Show or hide the panel | F2 | both stick clicks together |
| Save the situation to the chosen slot | F3 | button in the panel |
| Replay it | F4 | button in the panel |
| Slow motion on or off | F6 | the Speed row in the panel |
| Switch pages | Q / E | L / R |
| Move, press, close | arrows, Enter, Esc | D-pad, A, B |

While the panel is up the game gets an idle controller. F1 closes it. The four keys can be changed in the Trainer tab
(F2 to F7), as can the panel's corner and opacity. In a development build F7 also opens the dev panel; a trainer
key set to F7 takes it, and the dev panel is then opened from Settings > Dev. Each of the four ratings presets can also have a key (5 to 0,
Insert, Delete, Home, End, Page Up or Page Down; none by default) that steps it through Normal, Best and Worst.
So can each of the six guaranteed cheats: its key steps it through off, my side, their side and both.

| Page | What it does |
|---|---|
| Match | Balls, strikes, outs and both scores; speed (100, 75, 50, 25 %); jump to a later half-inning; three saved situations |
| Pitcher | The pitcher's energy, stamina and confidence as of the last pitch; my pitcher's and their pitcher's energy left to the game, held full or held tired (25 %), and a one-off refill (optional key). Energy is not edited in Season, Franchise or Road to the Show |
| Hitting | Read only: the last batted ball's speed, launch angle and direction (0 to centre field, beyond 45° foul) |
| Cheats | The six guaranteed cheats below, each off, for my side, their side or both |
| Ratings | Away batting, away pitching, home batting and home pitching at the game's values, all Best (99) or all Worst (10), whichever team your controller plays; below them one player's values as a scrolling list of sliders. Presets are remembered for later exhibitions; single values last one match. Not available in Season, Franchise or Road to the Show |

The Pitcher, Hitting, Ratings and Cheats pages need a build made with the trainer's patch sets. The normal build instructions pass the
patch file to the generator, so a fresh build has them; code generated before the sets were added must be generated
again (`recomp/gen.py ... --patches tools/data/patches-1.0.20.txt`).

## Guaranteed cheats

| Cheat | Goes by | What it does |
|---|---|---|
| Contact | who bats | A swing the game judged a miss puts the ball in play instead: a fair ball, 62 to 88 mph, -2 to 22 degrees, within 35 degrees of centre. Swings that already hit are left as they were |
| Home run | who bats | A swing that hits the ball (fouls included) sends it out: 110 to 114 mph, 27 to 31 degrees, within 25 degrees of centre. A miss stays a miss unless Contact is on too |
| Always miss | who bats | Every swing misses |
| Perfect aim | who pitches | The pitch goes where it was aimed: the miss the game adds to the aim point is cleared. Pitch movement is the game's |
| Strikes | who pitches | A pitch outside the zone that the batter takes is called a strike, so no ball is ever called |
| Wild throws | who fields | A throw by that side while a batted ball is in play is made a wild one, through the game's own decisions. The game makes the throw, the miss, the chase and the error itself |

With no side of your own (an AI match, or watching), mine is the away team and theirs the home team, and the panel says
Away and Home. Always miss shuts off Contact and Home run for the same side, and the other way round. The cheats are
off again when the match ends. They do nothing during Quick Manage. In Season, Franchise and Road to the Show nothing
happens until you confirm, as for any other change.

What they leave alone:

- A **check swing** is not a swing: the ball the game had worked out is never played, with or without a cheat.
- **Bunts** use a model of their own, which none of these touch.
- A forced ball is a ball like any other: a contact ball can be caught or thrown out.
- A forced **strike** changes the zone answer the umpire's call is made from. Whether a replay challenge (ABS) can
  overturn it was not tried.
- A **walk** that was already on its way (an intentional walk, a hit batter) is not tried either.
- **The game may take a wild throw back**, which is why about half were caught with the first answer alone (4 of 8
  plays in the match that counted). After the throw is marked wild, a second step (`f_7000389c00`, or a motion that is
  not the ordinary kind) can swap in a clean throw, marked in the throw plan. In one traced match that happened on 4 of
  13 wild throws and all 4 were 4-3 ground outs; none of the 8 it left wild ended in one. The trainer now holds the
  plan on the wild side too. Holding the mark the other way round changes nothing for the better (tried, one match).
- A wild throw is not always an error: on a fly ball already caught, or when no runner can gain, the play stands.
- The scoring is the game's: the trainer adds no error of its own.
- **Earlier ways, dropped.** Moving the throw's target 70 feet did not stop the catches. Taking the receiver off the ball
  let it get away with nobody going after it. Switching the loose ball to the live state got it chased and then ruled a
  foul ball, or left the play stuck. The traces are in the game-code skill's `known-functions.md`.
- The catcher's returns, pickoffs and throws between plays are left alone. A catcher's throw on a steal was not tried
  and may be left alone too.

**Inning jumps** go forwards only. The trainer sets the counter to one before the target with two outs, and the game
makes the next out and the change of sides itself, so it takes as long as that out takes.

**Season, Franchise and Road to the Show:** the match's result goes into your save, so the first change of a match
asks you to confirm.

## What else changes

- Changes are real: the scoreboard, the game's logic and any saved result see them.
- Saved situations are in `trainer.txt` in the profile folder. Loading one from an earlier inning restores the count
  and score but not the inning.
- With the trainer off no game memory is read or written. The patched call sites run their original call.

## How it works

`runtime/mlb/trainer_game.c` holds every address and checks each pointer and value before touching it;
`runtime/mlb/trainer.c` holds the rules; `runtime/gfx/ui/trainer_ui.cpp` draws the panel. Patch sets in
`tools/data/patches-1.0.20.txt` send game calls through `runtime/mlb/trainer_hooks.c`: `trainer_contact`,
`trainer_pitch`, `trainer_speed`, and for the cheats `trainer_swing`, `trainer_aim`, `trainer_call` and
`trainer_wild`. Addresses and
evidence are in the comments of those files and in the game-code skill's `known-functions.md`.

How each cheat gets in:

| Cheat | Where | What it does there |
|---|---|---|
| Contact, Home run | the contact model's callers | The model runs as usual. If another ball is wanted it runs a second time with the game's own "auto hit" block filled in, so the game builds the angles, speed, velocity, spin, hit type and direction itself. The block is put back afterwards |
| Always miss | the swing's hit-type answer inside the model | Answers "missed early" or "missed late", and the game handles the miss |
| Perfect aim | the pitch placement | Clears the miss and runs the game's step that adds it to the aim point again |
| Strikes | the pitch's end | Answers "in the zone" |
| Wild throws | a fielder's throw being set up | Answers yes to the game's "is this one wild" question (`f_700038a4c0`), then clears the "throw cleanly" byte of the plan it goes on with (`+0x32`, at the call of `f_7000378c64`). "In play" is read from the game's own log lines (`GAME_STATE_IN_PLAY: state = IN_PLAY`) |

An earlier try overwrote the finished batted ball (angles and speed only). It changed the scorebug's exit speed and not
the play, because the ball flies by the velocity the model had already written.

## How it was checked

All live runs were AI-against-AI matches on 1.0.20 with a hidden window, on 2026-11-24.

| Check | Result |
|---|---|
| `tools/trainer_test.c` (rules, checked memory access, panel colours and sizes) | 180 checks, 0 failed |
| Energy held full, then left alone, one match | read 98 to 99 % on every pitch while held, where it loses about 0.8 % a pitch; released, it fell from there (99, 98, 97 ... 94 %) |
| Your side | the controller setting read 1 playing the home team and 0 after Team Select moved to the away team; in an exhibition the trainer logged "your side: home" |
| Home pitching to Worst and back to Normal, one match | the scoreboard's fastball went 100 mph, then 82 and 83, then 98 and 100; all 52 players of both teams were found |
| Batting, both sides Best against both sides Worst, one match each | batted balls: 11 with a top speed of 96 mph and five at 81 or more, against 12 with a top speed of 78; those inside the foul lines averaged 89.5 mph (4 balls) against 67.5 (8). One run each and few balls, so a strong sign rather than a measurement |
| Single values | only in the host test; they write the same bytes as the presets |
| Quick Manage, fast forward to the next half inning, back to play (`tools/pad_drive.py`) | during Quick Manage the screen said "Bottom 1" while the data still said top 1; with the fix the trainer holds off and reads the bottom of the 1st after play resumes |
| Slow motion, two matches side by side over the same 18,600 frames | 17 pitches after the command at 100 %, 4 at 25 % (one run each) |
| `tools/menu_nav_test.cpp` (every controller button the panels use, held while a keyboard key arrives) | 44 cases, 0 failed; before the fix it aborted at "Y, then Down arrow" |
| Count and score writes, read back by the trainer | every read-back equal to the value written |
| A saved situation replayed | 5 of 5 in each of three runs |
| Inning jump to half-inning index 2 and 3 (`tools/trainer_live.py`) | right inning and batting side, 9 of 9 checks each; index 3 passed again on the finished build |
| Main menu, trainer on | it never read a match, so it can write nothing there |
| Batted-ball speed | logged 93.7 mph where the game's scoreboard showed "EXIT MPH: 94" |
| Panel text contrast over a white picture | lowest 7.26:1 (WCAG 2.2 AAA, 1.4.6) |
| Row and button height at 720 lines | 24 px (AA 2.5.8 target size; AAA's 44 px, 2.5.5, is not met: the panel would cover the play) |
| Trainer off, frame rate | uncapped, 3 minutes a run, runs alternated, each alone on the machine: 121.9 fps without the trainer (118.5, 124.8, 122.3) and 121.1 fps with it off (120.2, 120.7, 122.4). The 0.8 fps gap is inside the spread between runs. The build without the trainer is the main folder's, which may differ in other ways too |

### The guaranteed cheats

AI-against-AI matches on 1.0.20, hidden window, one cheat a run, 4 to 8 minutes each, on 2026-11-24
(`tools/trainer_cheats_live.py`). "First build" had extra diagnostic log lines and an inverted side mapping that only
matters for one-side settings; every run with one side used the final code.

| Check | Result |
|---|---|
| `tools/trainer_test.c` with the cheats' rules and memory access | 234 checks, 0 failed |
| `tools/menu_nav_test.cpp` | 44 cases, 0 failed |
| Contact | first build: the game's log judged 4 swings "Miss: 1"; all 4 became plays (lineout, single, two groundouts). Final code: the one miss of the run became a single |
| Home run (with Contact on), final code | 6 balls, all at 110 mph or more and 27 to 31 degrees; the game recorded "Solo Home Run" for all 6 and the score rose by 6; the scorebug showed an exit speed of 112 for the 111.9 mph ball |
| Home run, first build | of 8 balls, 5 were recorded as home runs, 2 were check swings (never played) and 1 was in the air when the run ended |
| Always miss | first build, both sides: 12 swings forced, no batted ball, the 4 finished at-bats were strikeouts. Final code, away only: 10 forced, all while the away team batted; the home team put 6 balls in play |
| Perfect aim | first build: 20 of 20 pitches ended on the aim point in the game's pitch data (up to 1.52 ft off before). On the 15 swings where the game logged where the ball crossed the plate, sideways it was within 0.008 zone units of the aim (median miss 0.53 to 0.75 in runs without the cheat); height matched for some batters and differed by up to 0.31 for others, in step with the aim height, which points to each batter's own zone size in my conversion (not confirmed). Final code: 21 pitches re-placed |
| Strikes | first build, both sides: 5 takes outside the zone called strikes, no ball counted, 2 strikeouts looking. Final code, away pitcher only: 2 forced while the away team pitched, no ball counted for that pitcher (6 for the other) |
| Trainer off, final code | all six patch sets reported off, no trainer log lines, 3 at-bats in 4 minutes, no FATAL line |
| Cheats page | one screenshot at 720 lines: five tabs and all rows fit |

### Wild throws

| Check (2026-11-25, AI matches, Contact on) | Result |
|---|---|
| `tools/trainer_test.c` | 246 checks, 0 failed |
| Ordinary swings, both sides, 8 minutes | 5 throws made wild; no error, no foul call after them, no fault |
| Ordinary swings, away fielding only, 10 minutes | 2 throws made wild, both while the home team batted; both plays were ground outs |
| Ground balls forced (diagnostic build, counts misses), 10 minutes | 9 throws made wild on 8 plays: error charged on 4, batter out on 4, no foul call |
| The same, an earlier diagnostic build, 7 minutes | 6 calls answered yes: errors charged on 3 plays |
| With the plan held wild too: ground balls forced (diagnostic build), 12 minutes | 12 throws on 10 plays, one of them swapped back by the game and held: error charged on all 10 plays (8 "Reached On Error", 2 fielder's choices), no foul call |
| With the plan held wild too: ordinary swings, 10 minutes | 4 throws made wild, none swapped back: one "Reached On Error"; the other plays were a double, a lineout and a flyout; no foul call after them, no fault |

Not checked for wild throws: the box score and the error column on screen, a person's own fielding and throwing, and a steal.

Not checked for the cheats: a person's own batting and pitching (all runs were AI against AI), the cheat keys on a real
keyboard, the panel's buttons with a mouse or pad, the confirmation in a real saved mode (host test only), bunts,
a ball-strike challenge, frame rate with cheats on, and game 1.0.15. A cheat is finished once the owner has tried it.

Not checked by any automated run: the ratings preset keys, F2, F3, F4, the stick clicks, F1 while the panel is up, mouse use, and the menu
after a finished match. In one hidden run the panel closed and the game's pause menu opened with nothing scripted to
press them; the likely cause is that a real controller on the PC also reaches a hidden game, which was not confirmed.
Launch angle and direction were not compared with a figure from the game.

## Known problems

- A play session (2026-11-24) ended with `Assertion failed: IsNamedKey(key)` after the pad's Y and a keyboard key
  met in the overlay. Fixed by no longer handing Y to Dear ImGui; the settings menu had the same fault.
- In the same session the Match page differed from the scoreboard after Quick Manage, fast forward, next half
  inning. Cause: while Quick Manage is open the game keeps the simulated innings to itself, and the match data
  catches up only when play resumes. The panel now says so and changes nothing until the scorebar returns.

## Not done, and why

Each of these was in the design. A control that looks like it works and does nothing would be worse than none, so
they are left out.

| Feature | What was found |
|---|---|
| Editing ratings in saved modes | Putting the game's values back has not been proven there, so it is blocked. |
| Editing stamina and confidence | Written values were replaced by the game's own at the next pitches (stamina 90 % read 70 %; confidence 90 read about 60). |
| The game's developer overrides | The switches the binary still has for pitch location and swing results are dead: the function that reads them (`f_70000bb414`) always answers no. |
| Match settings (stadium, weather, innings) | The settings block and its key numbering are known from the code; which keys do anything during a match was not tested. |
| Wind | The game has what looks like an override (`[main+0x227e6e0]`, flag `+0x28`, values `+0x64`); its effect was not tested. |
| Base runners | The game rebuilds the base array from the players on the field within about 3 seconds. |
| Game 1.0.15 | Its files are not on this machine. The trainer says it knows 1.0.20 only. |
