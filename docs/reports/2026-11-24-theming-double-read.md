# Theming by double read: the pilot, in numbers

Date: 2026-11-24. Scope: one 200-function sample of `main`, three reads, an adjudicator and a hand audit. This is
the first measured run of the method the owner chose: two independent body reads; accept a label only when they
agree and the evidence is machine-checkable; a third read settles disagreements.

## What this is for

The wiki groups functions by the aspect of the game they serve, using one label per 256 KB window. That window label
is right for a single function about 37.5% of the time. The goal is a per-function answer at about 95% precision,
with the rest left unlabelled rather than guessed. The full map is 94,991 `main` functions.

## The pipeline

1. `tools/theme_prep.py` picks targets (a fixed stride over the address space, so a sample spans every region) and
   has `tools/map_read_prep.py --all` write dossiers: the normalised body, callers, callees with their known roles,
   the window theme, and the function's own strings.
2. Two readers, each in its own agent, read `tools/theme_prompt.md` and one dossier, and write one JSON line per
   function: aspect, confidence, evidence, basis.
3. `tools/theme_adjudicate.py` accepts an address when both readers name the same non-`Unclear` aspect and each row's
   evidence is grounded: a quoted string that really is one of the function's strings, or an address that really is
   one of its direct callees. A quoted string at most 20 `main` functions quote is a `rare string`; a callee whose
   own role or strings contain the aspect's vocabulary names the aspect. The two together give a tier: `strong`
   (both rows are rare-string or naming-callee), `medium`, or `weak` (only common strings or unlabelled callees).
4. Addresses the two readers disagree on go to a third read; a 2-of-3 majority wins if two of the winning rows are
   grounded. Anything else stays abstained with a reason.
5. `tools/theme_audit.py` draws a fixed sample of accepted rows for a person to judge, and scores the filled sheet.

## Bugs the pilot found, and the fixes

These are the reasons the first attempt could not have measured anything:

- **Dossiers ran past the end of the function.** The body reader ended a function at the next *selected* function's
  line, not the next function's line. With a cross-window sample the first entry carried 15,072 operations, tail and
  all, for a function of 224 bytes. Fixed in `map_read_prep.py` (the parser now knows every function's first line);
  the 200-function dossiers are 19,231–25,094 bytes for 40 functions each.
- **The dossier did not show the function's own strings.** Readers fetched them from the map index themselves. The
  strings are now a line in each entry, so both readers see the same evidence and the quote is checkable.
- **The adjudicator's callee check could never pass in a fresh run.** It required the cited callee's label to be
  already accepted, and a fresh run has no accepted labels. It now checks that the address is a real direct callee,
  and looks for the aspect's vocabulary in that callee's role and strings.
- **`Unclear` was outside the adjudicator's allowed set**, so every pair of Unclear answers was abstained as "aspect
  outside the list" (83 rows in one run) instead of "no decisive evidence".
- **Addresses written as `f_7000…` were not recognised**; the check parsed only `0x…`. Fifteen agreed rows that had
  been abstained were accepted once fixed.

## Results

Sample: 200 `main` functions drawn with a fixed stride from the whole address space, spread over 111 distinct 256 KB
windows. Three reads, three passes over the queue. Wall time about 40 minutes with up to eight reader agents at
once.

| Measure | Number |
|---|---|
| Addresses with two reads | 200 |
| Both readers named an aspect | 80 |
| …and named the **same** aspect | 61 of 80 = **76%** |
| One reader said Unclear | 35 |
| Both said Unclear | 85 |
| Accepted after the third read | **80 of 200 = 40%** |
| — tier strong / medium / weak | 29 / 1 / 50 |
| Abstained | 120 |
| …both readers found nothing | 85 |
| …three reads did not settle it | 26 |
| …agreed but evidence failed the check | 9 |
| Accepted labels that merely repeat the window's aspect | 23 of 80 = **29%** |

Accepted labels by aspect: Menus and UI 21, Online and Diamond Dynasty 20, Data and serialization 13, Graphics and
textures 6, Road to the Show 5, Franchise/league/roster 5, Audio 5, Stats and records 2, Presentation and animation
2, Gameplay: in-play 1.

The third read added 28 labels (52 accepted after the two reads, 80 after the third). It also left 26 addresses
unsettled: three readings with no majority, or a majority whose evidence did not ground.

## The hand audit

18 accepted rows were sampled — 8 strong, 10 weak — and judged against the dossier (the sheet is
`work/theme/audit-final-strong.md` and `-weak.md`):

| Tier | Rows | Right | Wrong | Unsure |
|---|---|---|---|---|
| strong | 8 | 7 | 0 | 1 |
| weak | 10 | 7 | 0 | 3 |
| **total** | **18** | **14** | **0** | **4** |

The four "unsure" are not obvious mistakes, and they are the interesting part:

- three are generic C++ or third-party code (`std::istream` teardown, vector reallocation, an `operator new` accessor
  clone). The prompt maps generic machinery to `Menus and UI`, so the label follows the rule, but it says nothing
  about the game. 29 of the 80 accepted rows mention a runtime or third-party name in their evidence, 53 are
  "boilerplate" in the map's own `kind`, and 8 are `library`.
- one is a claim the dossier does not support (a roster bitmask read as roster bookkeeping; the window theme was the
  only thing naming the roster).

"0 wrong in 18" is not a 95% proof: with 14 right and 0 wrong, the 95% lower bound is about 77%. The sample is also
judged by the same model family that wrote the labels, so it is a consistency check, not an independent referee. It
does say the accepted rows are not visibly broken and that the failure mode is abstention, not invention.

## What the numbers say for the plan

- The method does what it was chosen for: when both readers commit, they agree 76% of the time, and a third read
  recovers most of the disagreements. On this sample it labelled 40% of the code and abstained on 60%.
- The weak tier (50 of 80 accepted) is where the precision risk sits. Most of it is generic machinery wearing the
  `Menus and UI` label. Two fixes are worth doing before scaling: exclude functions whose map `kind` is `library`,
  or which are recognisably third-party (`std::__1`, OpenSSL, nlohmann, libwebp, Lua, Dear ImGui), from the targets;
  and require a naming callee (not just any callee) for a weak row to be accepted at all.
- Coverage will not approach "every function". That is the honest shape of this data: in this sample 85 of 200
  functions had no decisive evidence in either reading, and the ones that did were mostly vtable stubs, getters and
  container plumbing whose bodies name no aspect.
- Scale, from this run's rate: 40 functions per reader-agent in 5–10 minutes, eight at a time. Two passes over
  94,991 functions is roughly 70–100 hours of wall clock; the third read adds about a quarter of that. The earlier
  cost estimate (about $55 of reads) stands.

## Vtable class context (added the same day)

33,403 of the 94,991 `main` functions are one slot of one of 5,813 vtables. A bare getter or empty stub carries no
evidence of its own, but its class does. Dossiers now carry a `class:` line for every vtable method: the class's
slot count, the strings its sibling methods quote (`method strings`), strings one hop out from the siblings
(`near strings`, from their callees and callers), and up to three named sibling roles. The adjudicator checks class
evidence the same way it checks the rest and ranks it: a method string is strong (rank 1), a one-hop string is medium
(rank 2). The code is `tools/vtable_class.py`.

Experiment: the 40 functions from the pilot that both readers had called Unclear — 31 vtable methods and 9
non-vtable controls — were read again with the class line (same prompt otherwise, fresh readers):

| Group | Readers labelled | Agreed | Accepted after a third read |
|---|---|---|---|
| 31 vtable methods | A 14, B 13 | 11 | **11 (9 strong, 2 medium)** |
| 9 non-vtable controls | A 6, B 0 | 0 | 1 (weak, from operations) |

The gain is specific to the vtable group: the control group shows the readers did not simply get bolder. Of the 40,
19 still have no evidence at all — their classes quote nothing (field writes, `+0x` getters, empty stubs).

Hand audit of the 12 accepted: **10 right, 0 wrong, 2 unsure** (a fielding-versus-in-play boundary, and Home Run Derby
mapped to `Gameplay: batting` because the aspect list has no HRD). On decided rows that is 10/10.

What the class line can and cannot reach, over the whole map: 25,243 of the 55,394 vtable slots sit in a class that
quotes at least one string (17,509 have method strings, 22,123 one-hop strings); 4,151 classes quote nothing. Only 16
classes quote a source-file name, so the class *name* is rarely available — the label rests on the vocabulary of its
methods. In this sample the class line lifted coverage by 11 of 200 (5.5 points). The deeper version of the same
idea — resolving each class's registration data to name its fields, which is how the batch-4 reader labelled 22 stub
getters — is not automated yet.

## Suggested next step

1. Exclude `library`-kind and recognisably third-party functions from the targets; require a naming callee (or a
   class string) for a row to be accepted. Rerun this same 200 with the class line in every dossier to see the
   end-to-end coverage, and re-audit: the class evidence is the strongest new tier.
2. Then draw 1,000 functions (25 batches) for an audit with a usable confidence interval before committing to the
   full pass. The full run is a background job in chunks of a few hundred, resumable through `accepted.jsonl`.

## Reproducing

```
python -I tools/theme_prep.py --limit 200          # dossiers and addrs
# two readers per batch, then
python -I tools/theme_adjudicate.py
python -I tools/theme_stats.py
python -I tools/theme_audit.py --tier strong --sample 8
python -I tools/theme_audit.py --score work/theme/audit-final-strong.md
```

The state, reads and accepted rows are under `work/theme/` (ignored); the tools and the readers' prompt are in
`tools/`.
