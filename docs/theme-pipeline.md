# Theming pipeline: double read, machine check, judge, answer sheet

Assigning one aspect to every `main` function, with each accepted label backed by evidence the machine can check, and
a fixed answer sheet that every rule change has to survive. Everything under `work/theme/` is resumable: each step
writes files, and rerunning a step keeps finished work.

## Rules the pipeline enforces

- **Library code is never read.** `tools/theme_filter.py` drops functions the index calls library code and functions
  whose strings or source paths name nlohmann, ImGui, stb, mbedtls, zlib, ASTC and the like. Encryption and image
  decoding have no aspect of the game.
- **Generic machinery is `Shared engine code`**, not `Menus and UI`. Containers, list and tree helpers, string
  buffers, allocators, maths and hashing are engines, not screens. `Menus and UI` is for code that draws or drives a
  real screen. `Unclear` is only for functions the reader genuinely cannot place.
- **A callee alone is not evidence** unless that callee already has a label. Labels that rested only on calling an
  unlabelled function were right about half the time; they are rejected.
- **Only quoted text counts.** A string claim must put the game text inside double quotation marks; the machine
  matches keywords as whole words, so a stray "menu" in a sentence cannot prove a menu. `bat` no longer matches
  `battle`, `out` no longer matches `route`.
- **Split votes are restricted.** When a third read breaks a tie (including outvoting an `Unclear`), the winning
  evidence must be the function's own distinctive text or its class's text, not a bare callee.
- **A separate agent judges.** `tools/theme_judge.py` shows one accepted label and its evidence to a judge in its
  own agent, with the function body and no votes. The same model is allowed; what matters is that it cannot see the
  readers' agreement or the window theme. It answers `follows`, `does not follow` or `unsure`.
- **The answer sheet decides whether a change helped.** `tools/theme_sheet.py` holds ~200 functions with known
  verdicts: gold rows where the function's own string names the aspect, known-bad rows an earlier run accepted on a
  bare callee, library rows that must not be labelled, generic rows that must be `Shared engine code`, and noise rows
  used only to catch a rule that labels everything. Score it after any rule change.

## Files

| Path | What it is |
|---|---|
| `PROMPT.md` | The readers' instructions, copied from `tools/theme_prompt.md` |
| `targets.jsonl` | The functions chosen, with window theme and prior aspect |
| `library.jsonl` | Library functions the filter removed, with the reason |
| `batches/batch-NNN.md` | Dossiers: body, callers, callees with roles, class strings, window theme, own strings |
| `reads/{a,b,c}/out-NNN.jsonl` | The two independent reads, and the third for disagreements |
| `accepted.jsonl` | Labels whose two reads agree and whose evidence checks, with tier and strengths |
| `abstained.jsonl` | Everything not labelled, with the reason |
| `judge/judge-batch-NNN.md` | One label, its evidence and the body, for the judge agent |
| `judged.jsonl` | Accepted rows with the judge's verdict attached |
| `queue-c.jsonl` | Addresses the two reads disagree on |
| `sheet.jsonl` | The answer sheet and its verdicts |
| `state.json` | Counts from prep and adjudication |

## Steps

1. `python -I tools/theme_prep.py --window 0x7000ac0000 --limit 40`
2. Two readers, independently: read `PROMPT.md` and the dossier, write `reads/a/` and `reads/b/`. Neither sees the
   other's directory.
3. `python -I tools/theme_adjudicate.py`
4. A third reader only for `queue-c.jsonl`, then rerun step 3.
5. `python -I tools/theme_judge.py --prepare`, run the judge in its own agent, then `--merge`.
6. `python -I tools/theme_sheet.py --score` after every rule change.

## Why two reads and a judge

A single model read is inference, not measurement: the earlier body-reading audit found 6 right, 1 incomplete and 3
with a wrong detail out of 10. Two independent reads plus a mechanical evidence check turns "the model said so" into
"two readings agree and the quoted text is really there"; the judge adds one more pass over the body, without the
votes, so a plausible-sounding label still has to survive a cold reading. Rows that fail any step stay unlabelled.
