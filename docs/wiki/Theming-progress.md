The home page's aspect chart groups a function by the theme of its 256 KB window. Read against a function's own body, that window label is right about 37.5% of the time — it describes an area, not a function. This page follows the attempt to label functions one by one, with evidence and abstention, and records how far it has got.

![Theme labels accepted]({{theming.svg}})

The method is two independent reads of the same dossier, a machine check of the evidence each one quotes, and a third read when they disagree. A label is accepted only when the two readers name the same aspect **and** each one's evidence checks out. Everything else is left unlabelled with a reason. The reader instructions and the checking rules are in `tools/theme_prompt.md` and `tools/theme_adjudicate.py` in the repo; the numbers below come from `tools/data/theming-pilot.json`.

## What counts as evidence

| Basis | Machine check | Strength |
|---|---|---|
| the function's own string | the quoted text really is one of the function's strings; at most 20 `main` functions quote it | strong (`rare string`) |
| a direct callee | the address really is called by the function, and that callee's role names the aspect | strong |
| a sibling method's string (vtable methods) | the quoted text really is quoted inside the class | strong (`class method string`) |
| a string one hop out from the class | quoted by a sibling's callee or caller | medium (`class near string`) |
| a common string, or a callee with no role | the string exists, or the call is real, but neither names the aspect | weak |

The window theme is never accepted as evidence. A label that only repeats the window is exactly what this work is meant to replace.

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
seeing the earlier votes. Later batches prioritized functions with specific strings in their own body or in their
vtable siblings.

| Selection | Reviewed | Accepted | Abstained |
|---|---:|---:|---:|
| Functions spaced across `main` | 24 | 1 | 23 |
| Functions with rare strings | 78 | 36 | 42 |
| Small vtable methods with class evidence | 94 | 38 | 56 |
| Total | 196 | 75 | 121 |

Of the 75 accepted labels, 72 have strong evidence and three have medium evidence.

## Accepted labels by aspect

![Aspects measured per function]({{theming-aspects.svg}})

The chart includes 167 distinct accepted labels across the original sample (80), the vtable and control experiment
(12), and the continuation (75).

## The hand audit

An agreement is not proof, so a sample of accepted labels was judged by hand against the same dossier the readers saw:

| Sample | Rows | Right | Wrong | Unsure |
|---|---|---|---|---|
| the 200-function run | 18 | 14 | 0 | 4 |
| the vtable experiment (below) | 12 | 10 | 0 | 2 |

The six "unsure" are not obvious mistakes; they are the places the data cannot decide. Three are generic C++ or third-party code (`std::istream` teardown, a vector reallocation, an `operator new` accessor clone): the rules map generic machinery to `Menus and UI`, so the label follows the rule but says nothing about the game. One is a claim the dossier does not support. Two are boundary calls — fielding versus in-play, and Home Run Derby mapped to batting because the aspect list has no bucket for it.

"0 wrong in 30" is not a 95% proof: with 24 right and 0 wrong the 95% lower bound is about 76%, and the audit is done by the same model family that wrote the labels. It says the accepted rows are not visibly broken and that the failure mode is abstention, not invention.

## Giving vtable methods their class

33,403 of the 94,991 `main` functions are one slot of one of 5,813 vtables, and many are bare getters or empty stubs: the body says nothing, so both readers say Unclear. The class does say something. The dossier now carries a `class:` line — the strings its sibling methods quote, the strings one hop out from them, and the roles of named siblings — and the adjudicator accepts a class string as evidence.

Tested on the 40 functions from the sample that both readers had called Unclear: 31 vtable methods and 9 non-vtable controls, read again with the class line.

| Group | Labelled by A | by B | Agreed | Accepted |
|---|---|---|---|---|
| 31 vtable stubs | 14 | 13 | 11 | **11** (9 strong, 2 medium) |
| 9 controls | 6 | 0 | 0 | 1 (weak, from operations) |

The controls matter: they show the gain comes from the class line, not from readers getting bolder. Of the 40, 19 still have no evidence — their classes quote nothing at all. Over the whole map, 25,243 of 55,394 vtable slots sit in a class that quotes something specific (17,509 of them in their own methods); 4,151 classes quote nothing.

## What is left

- **Classes that quote nothing.** A stub whose class is all field writes and `+0x` getters has no vocabulary to read. The way past it is the registration data: the game builds each class's field table from immediates, and resolving those gives field names (`m_nRightWristBandStyle`, `m_nQualityStarts`). One reader did that by hand for 22 getters; automating it is the next real piece of work.
- **The weak tier.** 49 of the 80 accepted labels rest on a bare callee. They are the precision risk, and an audit should decide whether to keep them or abstain.
- **Scale.** Two reads over all 94,991 functions is roughly 70–100 hours of wall clock at eight readers; a third read adds about a quarter. The pipeline is resumable, so the full pass is a background job in chunks.
