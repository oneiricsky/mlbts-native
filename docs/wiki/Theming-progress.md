The home page's aspect chart groups a function by the theme of its 256 KB window. Read against a function's own body, that window label is right about 37.5% of the time, because it describes an area of the code. This page follows the attempt to label functions one by one, with evidence and abstention, and records how far it has got.

![Theme labels accepted]({{theming.svg}})

The method is two independent reads of the same dossier, a machine check of the evidence each one quotes, and a third read when they disagree. A label is accepted only when the two readers name the same aspect **and** each one's evidence checks out. Everything else is left unlabelled with a reason. The reader instructions and the checking rules are in `tools/theme_prompt.md` and `tools/theme_adjudicate.py` in the repo; the numbers below come from `tools/data/theming-pilot.json`.

## What counts as evidence

| Basis | Machine check | Strength |
|---|---|---|
| the function's own string | the quoted text is one of the function's strings; at most 20 `main` functions quote it | strong (`rare string`) |
| a direct callee | the function calls that address, and that callee's role names the aspect | strong |
| a sibling method's string (vtable methods) | the quoted text appears inside the class | strong (`class method string`) |
| a string one hop out from the class | quoted by a sibling's callee or caller | medium (`class near string`) |
| a common string, or a callee with no role | the string exists, or the call is real, but neither names the aspect | weak |

The window theme is never accepted as evidence. This work is meant to replace labels that only repeat the window.

## The 200-function sample

200 functions drawn with a fixed stride across `main` (111 distinct windows), in five batches; two readers per batch, and a third read on the disagreements.

| Measure | Result |
|---|---|
| Both readers named an aspect | 80 of 200 |
| …and named the same one | 61 of 80 = 76% |
| Labels accepted | **80 of 200 = 40%** (29 strong, 2 medium, 49 weak) |
| No decisive evidence in either read | 85 |
| Three reads did not settle it | 35 |
| Accepted labels that just repeat the window theme | 23 of 80 = 29% |

## Continuation batches

Two Terra readers independently reviewed each function. A third reader saw the dossiers for disagreements without
seeing the earlier votes. Later batches prioritized functions with specific strings in their own body, their vtable
siblings, or the functions they call.

| Selection | Reviewed | Accepted | Abstained |
|---|---:|---:|---:|
| Functions spaced across `main` | 24 | 1 | 23 |
| Functions with rare strings | 366 | 158 | 208 |
| Small vtable methods with class evidence | 158 | 64 | 94 |
| Functions with direct-call evidence | 64 | 11 | 53 |
| Total | 612 | 234 | 378 |

Of the 234 accepted labels, 229 have strong evidence and five have medium evidence.

## Accepted labels by aspect

![Aspects measured per function]({{theming-aspects.svg}})

The chart includes 326 distinct accepted labels across the original sample (80), the vtable and control experiment
(12), and the continuation (234).

## The hand audit

An agreement is not proof, so a sample of accepted labels was judged by hand against the same dossier the readers saw:

| Sample | Rows | Right | Wrong | Unsure |
|---|---|---|---|---|
| the 200-function run | 18 | 14 | 0 | 4 |
| the vtable experiment (below) | 12 | 10 | 0 | 2 |

None of the six "unsure" rows is an obvious mistake. The data cannot decide them. Three are generic C++ or third-party code (`std::istream` teardown, a vector reallocation, an `operator new` accessor clone): the rules map generic machinery to `Menus and UI`, so the label follows the rule but says nothing about the game. One is a claim the dossier does not support. Two are boundary calls: fielding versus in-play, and Home Run Derby mapped to batting because the aspect list has no bucket for it.

"0 wrong in 30" is not a 95% proof: with 24 right and 0 wrong the 95% lower bound is about 76%, and the audit is done by the same model family that wrote the labels. It says the accepted rows are not visibly broken, and that when the method fails it abstains. The audit saw no invented labels.

## Giving vtable methods their class

33,403 of the 94,991 `main` functions are one slot of one of 5,813 vtables, and many are bare getters or empty stubs: the body says nothing, so both readers say Unclear. The class often does. The dossier now carries a `class:` line (the strings its sibling methods quote, the strings one hop out from them, and the roles of named siblings), and the adjudicator accepts a class string as evidence.

Tested on the 40 functions from the sample that both readers had called Unclear: 31 vtable methods and 9 non-vtable controls, read again with the class line.

| Group | Labelled by A | by B | Agreed | Accepted |
|---|---|---|---|---|
| 31 vtable stubs | 14 | 13 | 11 | **11** (9 strong, 2 medium) |
| 9 controls | 6 | 0 | 0 | 1 (weak, from operations) |

The controls show that the gain comes from the class line, not from readers getting bolder. Of the 40, 19 still have no evidence, because their classes quote nothing at all. Over the whole map, 25,243 of 55,394 vtable slots sit in a class that quotes something specific (17,509 of them in their own methods); 4,151 classes quote nothing.

## Labels from tracing

These functions were identified while the in-game trainer was built: by reading their recompiled code, and for many by
watching or changing them in a running match. They did not go through the double read, so they are not in the
agreement or audit numbers on this page. One session assigned the aspects and no second reader checked them. The
aspect chart includes them. They are kept in `tools/data/theme-findings.jsonl`, and `tools/theme_prep.py` does not
select them for reading again.

`live` means seen or changed in a running game; `code` means read from the recompiled code only.

| Function | Aspect | Basis | What it does |
|---|---|---|---|
| `0x7000247214` | Gameplay: pitching | live | places the pitch: aim, miss and break offset; changing its miss moved pitches |
| `0x7000249cc8` | Gameplay: pitching | live | adds the miss and break offset to the aim point of a pitch |
| `0x7000249e38` | Gameplay: pitching | code | sets the pitch's miss from the aim, for computer and analog pitching |
| `0x700024b6a8` | Gameplay: pitching | code | sets the break offset used when the pitch is placed |
| `0x70002e9dc4` | Gameplay: pitching | live | pitcher fatigue update: reads stamina, energy and confidence each pitch |
| `0x70002ed9a4` | Gameplay: pitching | live | stores the pitcher's energy into the player record |
| `0x7001687dd8` | Gameplay: pitching | live | answers whether a pitch was a strike by location; answering yes called balls strikes |
| `0x700167823c` | Gameplay: batting | live | builds the batted ball from an override block of azimuth, launch and speed |
| `0x7001679cdc` | Gameplay: batting | live | runs the bat-on-ball result: bunt model or contact model into one result struct |
| `0x7001679d18` | Gameplay: batting | code | bunt model, chosen by the swing's bunt flags |
| `0x700167bb7c` | Gameplay: batting | live | contact model: launch angle, direction and exit speed of a batted ball |
| `0x700167fe28` | Gameplay: batting | live | the swing's hit type from its timing; forcing a miss type made batters miss |
| `0x7001680870` | Gameplay: batting | code | handles the miss hit types of the contact model |
| `0x70000b5cf8` | Gameplay: fielding | code | per-fielder forced-error flag read by the throwing-error decision |
| `0x700017df20` | Gameplay: fielding | code | error roll: fielding or throwing error chance scaled by the error sliders |
| `0x700018949c` | Gameplay: fielding | code | decides a throwing error, by the forced flag or the error roll |
| `0x70001a5cb0` | Gameplay: fielding | live | picks a fielder's throwing or catching motion for a request |
| `0x7000378c64` | Gameplay: fielding | live | takes on a fielder's throw plan; its clean-throw byte undoes a wild throw |
| `0x7000389c00` | Gameplay: fielding | live | decides during throw setup whether a clean throw replaces the planned one |
| `0x7000389da4` | Gameplay: fielding | live | sets up a fielder's throw |
| `0x700038a4c0` | Gameplay: fielding | live | answers whether a throw is to be wild; answering yes produced wild throws |
| `0x70013fad18` | Gameplay: fielding | live | receiver's catch motion re-aims a ball in flight at the glove |
| `0x7001665d60` | Gameplay: fielding | code | re-times or drops a fielder's scheduled catch of the ball |
| `0x700166b0b8` | Gameplay: fielding | live | schedules a fielder getting the ball, with the time until it arrives |
| `0x7000d1cd98` | Gameplay: in-play | code | gives the team that is fielding |
| `0x7000d413bc` | Gameplay: in-play | live | rules handler that counts a ball |
| `0x7000d467c8` | Gameplay: in-play | code | rules handler beside the ball and strike counters, apparently a foul strike |
| `0x7000d493a0` | Gameplay: in-play | code | appends to the scored list, adds a run and logs the score |
| `0x7000d4c210` | Gameplay: in-play | live | rules handler that counts a strike or resets the count |
| `0x7001657330` | Gameplay: in-play | code | gives the ball's flight path object |
| `0x700165ca58` | Gameplay: in-play | code | builds the ball's flight path from a launch record |
| `0x7001665090` | Gameplay: in-play | live | switches the ball to the live state and clears its receiver |
| `0x70016671a0` | Gameplay: in-play | live | releases the ball for pitches and throws and sets the ball's state |
| `0x7001668ba0` | Gameplay: in-play | live | rebuilds the ball's path from a launch record and makes it live |
| `0x700166b264` | Gameplay: in-play | code | deflection: sends the ball on from a new launch record |
| `0x700166b51c` | Gameplay: in-play | live | re-aims a ball in flight at a new point |
| `0x700166f6d0` | Gameplay: in-play | live | raises the pitch-result event with ball or strike |
| `0x7001673894` | Gameplay: in-play | live | ends a pitch: takes the strike-zone answer and decides ball or strike |
| `0x70001dd438` | Stats and records | code | official scorer's play-event handler: error and play-record bits |
| `0x70001e4500` | Stats and records | live | scores the finished play, for example as reached on error |
| `0x7000d41660` | Stats and records | live | appends to the play's list of fielder actions used to judge errors |
| `0x7000d4256c` | Stats and records | live | charges an error to a fielder |
| `0x7000d42f20` | Stats and records | code | asks whether a runner gained from a listed fielder action |
| `0x7000d43ce0` | Stats and records | code | end-of-play error judge over the fielder actions |
| `0x7000d45cb0` | Stats and records | code | appends to the put-out list where an out is counted |
| `0x700181a6bc` | Franchise, league and roster | live | looks a player object up by id in the match's player table |
| `0x700183bb94` | Franchise, league and roster | code | reads one of a player's rating bytes |
| `0x7001868fd4` | Franchise, league and roster | live | reads a player rating as a fraction for play code |

## What is left

- Classes that quote nothing. A stub whose class is all field writes and `+0x` getters has no vocabulary to read. The way past it is the registration data: the game builds each class's field table from immediates, and resolving those gives field names (`m_nRightWristBandStyle`, `m_nQualityStarts`). One reader did that by hand for 22 getters; automating it is the next piece of work.
- The weak tier. 49 of the 80 accepted labels rest on a bare callee. They are the precision risk, and an audit should decide whether to keep them or abstain.
- Scale. Two reads over all 94,991 functions is roughly 70–100 hours of wall clock at eight readers; a third read adds about a quarter. The pipeline is resumable, so the full pass is a background job in chunks.
