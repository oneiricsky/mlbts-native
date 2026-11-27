# Float NaN fix-up at match start

Status: a code change on `research/float-fixup`, on by default, `MLB_FP_FIXUP=0` turns it off. The match-start frame's
MSDF step drops from 702 ms to 525 ms (six runs each) and the worst frame in a run from 1291 to 1094 ms (four runs
each). Frame rate in play is unchanged (within noise); see "How it was checked".

## Cause

The match-start frame (1.4 to 1.6 s of the game's own CPU work, `docs/reports/2026-11-22-load-stall-investigation.md`
section 3) holds an msdfgen distance-field run of 512x512 texels, 0.7 to 0.97 s of it. The sampler puts 42 % of the
samples under it inside `sfix_s` (29 %) and `sfix_d` (13 %).

`sfix_s` and `sfix_d` are not float-to-integer helpers (those are `toint_s` and `toint_d`). They are the cold side of
every scalar floating-point operation, `FN(sfix)` in `runtime/core/simd_fp.h`. Each operation runs on the host first
(`FN(op)`: `vsubss`, `vmulsd` and so on), then tests the result and calls `sfix` when:

- FPCR.RMode is not round-to-nearest (directed rounding), or
- the result is a NaN, or
- the result is exactly plus or minus the smallest normal number. Under FPCR.FZ the host and the ARM chip disagree on
  such a result (x86 decides "tiny" after rounding, ARM before it), so `sfix` reruns the operation.

What `sfix` computes with FPCR.RMode, FZ and DN clear: for a NaN result of ADD, SUB, MUL, DIV and MADD, the ARM choice
(`FN(nanv)`): the first signalling NaN operand made quiet, else the first quiet NaN operand, else the default NaN. ARM's
default NaN is positive (`0x7FC00000`); x86 produces the negative one (`0xFFC00000`) for an invalid operation such as
inf - inf or 0 / 0, so the host result cannot be used as it is. A result of exactly the smallest normal comes back
unchanged. Other operations (FMUL-extended, FRECPS, FRSQRTS, FSQRT, FABD, FNMUL) go to `FN(redo)` and `FN(fix)`.

`sfix` is entered 67.1 million times in the one frame, about 256 times per texel, against zero for the smallest-normal
case. I counted with a diagnostic build (not committed): the counters sit in `sfix`, and the totals at the end of the
MSDF step are below. All 67.1 million are NaN results; none is a directed rounding mode.

| operation | NaN from NaN operand | NaN from operands that are not NaN |
| --- | --- | --- |
| float SUB | 20.3 M | 17.4 M |
| float ADD | 8.7 M | 0 |
| double MUL | 11.6 M | 0 |
| double DIV | 5.8 M | 0.03 M |
| double MADD | 2.9 M | 0 |
| float FRECPS | 0 | 0.46 M |
| the rest | under 0.01 M | under 0.01 M |

So the game's msdfgen code works largely on NaN and infinity: samples such as `0 - NaN`, `inf - inf`, `0 / 0`,
`NaN / NaN` and `inf / inf` fill the counters, and FRECPS with an infinite estimate (a reciprocal of zero). Why the game
feeds it such values is not known. Each NaN result is the right ARM answer, so the port must produce it; but if the
distance field of a degenerate shape is thrown away, or the shape could be skipped, that would remove the step, which
is far more than this change can.

Why each call costs so much: `sfix` is `preserve_all` (so the generated code does not spill its vector registers around
every operation), and its vector NaN pass (`FN(nanv)`) uses all sixteen. The compiled function stores and reloads
15 YMM registers on every call. In a standalone loop it costs 4.0 to 4.8 ns per call (the same operation with an
ordinary result costs 0.46 ns).

FPCR in the generated code: the `main` module never writes FPCR (no `c->fpcr =` in `work/gen/main`); the sdk module
does in five places (the C library's save and restore of the floating-point environment, `f_7004d46cb8`,
`f_700519cabc`, `f_700519cb28`), and the runtime starts each thread with FPCR 0. So it is 0 in practice, but not provably
constant: a guest call could set it. The change therefore keeps reading it (the generated code loads it at function
entry and after calls, `recomp/fpcr.py`) and runs the old code for every other value.

## Sites

- `runtime/core/simd_fp.h`: `FN(sfix)` renamed `FN(sfix_full)` (unchanged); new `FN(nanbits)`, a new lean `FN(sfix)`,
  and `FN(cold)`, which `FN(op)` now calls where it called `sfix`.
- `runtime/core/simd.h`: `rt_fp_fix_lim` and `FPCR_FIXCLEAN(c)`.
- `runtime/mlb/main.c`, `runtime/mlb/cfg.c`: the setting `MLB_FP_FIXUP` (default 1), read once at start.
- Generated code is not touched: it includes `simd.h`, so `work/gen` was not regenerated, only recompiled. The lifter
  (`recomp/`) is unchanged.

## The change

`FN(cold)`, inline at each of the roughly 147,000 scalar FP operation sites, for ADD, SUB, MUL and DIV when FPCR.RMode, FZ
and DN are all clear and `MLB_FP_FIXUP` is on:

1. result not a NaN (the smallest-normal case): keep the host result, as `sfix` did;
2. NaN result, neither operand a NaN (invalid operation): the default NaN, `0x7FC00000` or `0x7FF8000000000000`;
3. NaN result, exactly one operand a NaN: keep the host result, which is that operand made quiet, what ARM gives;
4. both operands NaN: call the lean `sfix`.

Only compares and jumps are inline, no integer register, so the registers around a site are not disturbed. MADD, the
both-NaN case and any other operation call the lean `FN(sfix)`, which for ADD, SUB, MUL, DIV and MADD picks the NaN in
integer registers (`FN(nanbits)`, the selection of `FN(nanv)` for one lane) and saves a few integer registers instead of
sixteen vector ones; everything else goes on to `sfix_full`. With FPCR not clear, or `MLB_FP_FIXUP=0`, a call goes
straight to `sfix_full`: the old behaviour.

Standalone cost per operation with a NaN result, old to new (ns, the loop is independent iterations, one core):

| operation | old | new |
| --- | --- | --- |
| float SUB | 4.8 | 1.6 |
| float ADD | 4.5 | 1.2 |
| double MUL | 4.3 | 1.3 |
| double DIV | 4.9 | 1.8 |
| double MADD | 5.8 | 4.4 |
| any, ordinary result | 0.46 to 0.91 | the same |

The vector path (`FN(vop)`, `FN(vfix)`, `FN(nanv)`) is unchanged; the MSDF code is scalar.

## What else changes

- The executable grows from 132.7 MB to 148.0 MB (code 122.6 MB to 137.9 MB, 12 %): each site gets about 100 bytes of
  cold code (147,000 sites). The hot path of an operation is the same instructions as before. The game objects take a little longer to
  compile.
- It relies on the host giving, for one NaN operand and no other, that operand made quiet. Intel's manual says
  so for SSE (I did not check AMD's); the test below shows it on the 12th Gen i5-12400F here, and it was not run on an AMD
  chip.
- The vector, MADD, FRECPS and conversion paths still call the old functions and cost what they did.
- `MLB_FP_FIXUP=0` is not exactly the old speed: nothing inline, but the call goes to `sfix_full` after one extra
  compare.

## How it was checked

Bit-exactness, a standalone program (`op_s`, `op_d` and the vector `vop_s`, `vop_d` of the old header, from `git
archive HEAD`, and of the new one, compiled with the same flags as the generated code and compared bit for bit): all 15
operation kinds, all 16 combinations of FPCR.RMode, FZ and DN, random bit patterns and edge classes (quiet and signalling
NaN of both signs with random payloads, inf, +-0, subnormals, the smallest normal and its neighbours, the largest
normals, operand sets whose exact result is the smallest normal for ADD, SUB, MUL, DIV and MADD). Three runs, different
seeds, `MLB_FP_FIXUP` on, on, off: 690 million evaluations for single precision and 690 million for double (scalar ones,
plus 4-lane and 2-lane vector ones counted once each), 0 differences. About a quarter of the cases give a NaN result and a
twentieth give exactly the smallest normal. Controls, each a copy of the new header with one rule broken: the signalling-NaN rule for the second operand left out of
the lean function, 70,600 differences in 30 million evaluations; the inf * 0 rule of MADD left out, 120 in 30 million;
the invalid-operation answer in the inline step replaced by the host's result, 1,667 in 15 million. So the test sees
these bugs, including the rare one.

`tools/check_content.py --all`: no findings.

MSDF step (the game's own "MSDF took" line), `work/build` harness settings, `MLB_LOG_TIME=1`, one game at a time,
alternated, run stopped 3 s after the line:

| build | runs | MSDF step ms, mean (min to max) |
| --- | --- | --- |
| HEAD (`mlb_old.exe`) | 6 | 702 (675 to 712) |
| this change, `MLB_FP_FIXUP=0` | 6 | 716 (684 to 758) |
| this change, `MLB_FP_FIXUP=1` | 6 | 525 (502 to 558) |

The ranges do not overlap: 25 % less for the step, 177 ms. The grass step (157 ms) did not move. A sampler run of an
earlier build of this change (same behaviour, setting on) puts `sfix_s` and `sfix_d` at 9 % and 6 % of the step's
samples, from 29 % and 13 % (these are the calls that remain: MADD, two NaN operands, FRECPS).

Whole-run comparison, `tools/bench.py compare` on four runs of 400 s each, alternated (old, new, new, old, ...; the
60 fps cap is on, so mean fps cannot show a gain), `MLB_LOG_TIME=1`, one game at a time:

| figure | old (4 runs) | new (4 runs) |
| --- | --- | --- |
| MSDF step ms, from the game's own line | 692, 737, 682, 754 | 527, 527, 495, 522 |
| worst frame ms | 1291 (1251 to 1341) | 1094 (1078 to 1102) |
| mean fps from minute 2 | 59.87 (59.86 to 59.88) | 59.82 (59.67 to 59.91) |
| frames over 25 ms per minute | 26.4 (22.2 to 33.8) | 23.9 (18.0 to 32.4) |
| frames over 50 ms per minute | 1.1 (1.0 to 1.2) | 0.9 (0.0 to 1.8) |
| frames over 100 ms per minute | 0.2 | 0.1 (0.0 to 0.2) |
| RAM working set max, MiB | 3767 | 3770 |

The match-start frame is shorter: the step by about 190 ms and the worst frame by about 200 ms, and the ranges do not
overlap. Every other figure is within noise, including mean fps and the slow frames after the first minute, so the
other 147,000 sites show no gain or loss in play. Memory use did not change. Not checked: whether the 12 % larger
executable matters on a slower disk or a machine with less cache; this machine is one i5-12400F.

## Considered and not taken

- A branchless integer NaN select in the lean `sfix` only (no inline step): 4.4 ns instead of 4.8, which is 10 % of the
  gain. Kept for MADD and the both-NaN case.
- Removing the smallest-normal test from the hot path. It does nothing with FPCR.FZ clear (the cold code returns the host
  result), but with FZ set it is the only guard against the tininess difference, and FPCR is not provably zero. Dropping
  it would save one compare per operation, at the price of a guarantee. Not done.
- Treating FPCR as a constant in the lifter. It is not one (see Cause); a constant would also hide a guest `fesetround`.
- A hand-written assembly stub with its own register convention for the call: the call would cost 1 to 2 ns and each site
  would stay small, but the stub has to follow the Windows x64 unwind rules by hand. Not tried.
- Vectors (`FN(nanv)` for 4-lane operations): not in this code's profile.
- Skipping the whole distance-field run, or feeding it valid data: a game-behaviour patch, not the port's lowering. The
  67 million NaN results point at it.
