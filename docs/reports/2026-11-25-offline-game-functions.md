# Calling one recompiled game function without the game (2026-11-25)

## In plain words

Checking what a piece of the game does has meant playing a 10-minute match and hoping the situation comes up. The
port turns the game's code into C, so one function can be compiled by itself into a small program, handed a made-up
game situation, and asked for its answer. This worked for the error judge's question "did a runner gain on this
fielder action?" (`0x7000d42f20`, 1.0.20). A full run takes 6 to 8 seconds.

## Run it

```
python -I tools/guestfn_test.py
```

From the repository root, with `work/gen_cheats` present (`--gen work/gen` takes another set of generated C). The
exit code is the number of failed checks. Only our own code is committed: `tools/guestfn_test.py` and
`tools/guestfn_errorjudge.c`. The extracted game code and the program stay in `work/scratch/guestfn/`.

## How it works

1. The script starts at the function and follows direct calls through the generated C: 9 functions, 505 lines. It
   stops if they use a runtime service the harness does not provide (an indirect call, a patch switch, a system call).
2. It compiles them with the flags `tools/build.py` uses for game code.
3. The harness builds the objects the code walks: the rules object, one fielder action, four runners and the two team
   objects. Guest addresses are host addresses, so they can live anywhere.
4. One fixed address is read, the pointer to the team objects at `0x7003aeb728`. The harness maps that one page.
   With it left unmapped the call faults at exactly that address, which the script checks on every run.

## Results

46 checks, 0 failed. 5,000,000 calls took 0.37 to 0.42 s (74 to 84 ns each, three runs, four runners per call).
Extract 4.2 to 6.7 s, compile 0.8 to 1.5 s, run about 0.5 s. The stack pointer and the saved registers x19 to x29
came back unchanged on every call.

Two broken controls, each a one-spot change to a copy of the extracted code, run once and removed:

| Change | Result |
|---|---|
| put-out test "got further than the base" changed to "got at least to it" | 1 of 46 failed: "put out, recorded at first (1): did not get past it", answered 1, wanted 0 |
| accepted runner states 0x10 and 0x14 narrowed to 0x10 | 1 of 46 failed: "flip state 0x10 -> 0x14", answered 0, wanted 1 |

## What the function does

Confirmed in the code, and by the checks:

- With bit 0 of `w2` set, only the first runner of the action (the batter) is judged, and only for first base. With
  it clear, the four runners are tried in order and the first who gained is reported.
- The base to gain is the one after the base held at the action. Positions count in half-bases: 1 first, 3 second,
  5 third, 7 home.
- A runner in the scored list has gained. A runner in the put-out list has gained only if his record shows him
  strictly past the base. Anyone else has gained if his state is 0x10 or 0x14 and his position has reached the base.
  Home counts only through the scored list.
- On the scored shortcut the "which runner" output is not written. With bit 0 set, that shortcut also answers yes
  whatever base the batter held.
- With exactly one action on the list and the byte at entry `+0x90` set, the function writes 0 into the batter's base.
- A put-out runner with no record of his own is judged by the fourth record.

The earlier static analysis held: the closure is 9 functions, with no indirect branches or thread-local storage and one
global. The judge calls the function from 11 places, and only one of them passes the output pointer.

## What the names rest on

- Scored list (`+0x1d0`): `f_7000d493a0` appends to it, adds a run and logs "Score: %d to %d".
- Put-out list (`+0x148`): `f_7000d45cb0` appends to it where it counts the out.
- Inferred, not confirmed: states 0x10 and 0x14 mean "safe on a base"; `+0x124` of the runner's state object is how
  far he has got; `+0xc` of a record is how far he had got when put out (the code that writes it points to this);
  entry `+0x6c` is the base held when the action happened. The meaning of byte `+0x90` is unknown.
- The runners are looked up in the object returned by the getter the skill calls `GetFieldingTeam()` (`0x7000d1cd98`).
  Why runners are found there is unexplained. The harness checks that the batting-side byte picks the object.

## Limits

- The made-up plays prove what the function answers for the inputs we built; the live comparison below covers only
  what one match produced.
- The fake objects hold only the fields this closure reads. Other values in a real match have no effect on these 9
  functions, but whoever fills the fields is not covered.
- It suits small closures. An indirect (virtual) call, an SDK call or many globals each need a stand-in, and a large
  closure soon needs most of the game's memory.
- Windows only (`VirtualAlloc` at the game's address). 1.0.20 only.
- The code tested is what is in `work/gen_cheats` at the time of the run.

## Compared with a live match

```
python -I tools/guestfn_capture.py on        # recorder into the generated C (default work/gen_cheats)
ninja -f work/<build>/build.ninja            # run a match with this build, then:
python -I tools/guestfn_capture.py off       # restore, and build again
python -I tools/guestfn_test.py --replay work/scratch/guestfn/live.bin
```

The recorder writes, for each call with new input or a new answer, the rules object, the batting-side byte, the figures
of every runner named in it, `w2`, the answer, the output and the batter's base afterwards (`tools/guestfn_record.h`).
The replay loads each record into the fake objects and compares answer, output and base.

One AI match with the trainer's wild throws and ground balls forced (2026-11-25): **40 recorded calls, 0 differ**.
5 answered yes and 35 no; 12 were throws, 7 the batter-only form, 9 had someone put out and 6 someone scored. The
control (`--broken`, which feeds every runner a state the code does not accept) gave 5 differences, all of the yes
calls.

So the fields named above are enough to reproduce this function's answers. It does not confirm what they mean in
baseball terms, and one match did not reach every branch: the rewrite of the batter's base never happened.
