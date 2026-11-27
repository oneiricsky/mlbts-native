# A host core spent on the sound file thread's naps

## Cause

[C] The SCREAM sound library's file stream thread (`f_7001b42280`, 1.0.20) loops: lock its queue, serve a request if
there is one, unlock, `SleepThread(100 us)`. On the Switch the sleeping thread costs nothing. The port ran every sleep
up to 1 ms by spinning on the clock (`kernel.c`), because the Windows timer ends a wait up to 0.5 ms late and the
SDK's short polling sleeps took 460-515 us on it. So this loop held one host core at 97-99%, menus included.

In one 90 s run (boot, then a pitch in a match) that thread made 801,235 sleeps of 100 us. All other sleeps from
100 us to 1 ms together were about 1,000 (nearly all 200 us, the SDK's sleep on the job threads and the main thread),
plus 4 of 400 us.

## The fix

`runtime/core/guest_sleep.h`. A thread that asks for the same sleep of 100 us or more over 16 times in a row, running
less than 50 us between them, is idle polling: it waits on the OS timer instead. Once it runs longer than 50 us, or
asks for another duration, its sleeps are on the clock again. Sleeps under 100 us and occasional ones are as before.

Moving every sleep from 100 us up to the timer was rejected: it also made the 500 us and 1 ms cases 0.5 ms later in
the harness, and it would delay the SDK's 200 us sleeps.

It is a change in the port, not in game code, so there is no patch set, address or setting.

## What else changes

- An idle poller's 100 us sleep now ends after about 0.54 ms (median), so the sound thread can notice a new file
  request up to about 0.5 ms later than before (1.1 ms at the 99th percentile in the harness).
- Any other thread that polls the same way gets the same treatment, 1 ms sleeps included (about 1.5 ms then).
- On Linux the same rule applies, with that system's much finer timer. Not run on Linux.

## How it was checked

`tools/sleep_test.c` runs the real header without the game (build line at its top). Windows 11, i5-12400F (12 logical
processors):

| Loop | CPU before | CPU after | Median sleep after |
|---|---|---|---|
| 100 us idle poll | 98.6-100% | 1.4-2.1% | 541 us |
| 20 us idle poll | spins | spins | 20 us |
| 100, 200, 400 us with 200 us of work between | spins | spins | 100, 200, 400 us |

In game (`tools/scenarios/opening.txt`, hidden window, `TOTK_AUDIO=paced`, `MLB_FPS_LIMIT=240`, old and new builds of
the same source alternated, old = the streak limit set out of reach):

| | Old | New |
|---|---|---|
| Sound file thread, % of one core | 97-99 (six runs) | 6.7 (one 10 s sample, 125 of 138 samples in the timer wait) |
| Whole game, % of one core, pairs 1-3 (150 s runs) | 337, 338, 334 | 246, 243, 242 |
| Boot to the field picture, seconds | 21.4-22.6, mean 21.8 (six runs) | 21.2-21.5, mean 21.4 (six runs) |
| Frame rate, mean of the 60 s windows after the first | 122.8 (7 windows) | 123.2 (9 windows) |

The frame rate did not change measurably: single windows ranged from 115 to 133 fps in both builds. Left out of that
row: the windows near 60 fps late in the session (old run 11 from its third window, then runs 12 and 13, one of each
build), most likely because the display had gone to sleep; that was not checked. The runs logged no underrun, sound
stream or file-seek error.

Not checked: sound by ear on a real audio device, the season simulation's speed, a whole match, version 1.0.15 and
Linux.

## Seen on the way

A second thread of the running game was also at about 97% of a core: its samples were in `nvnSyncWait`, called from
`f_70005a1330`, a wait on the GPU. It is a separate path and is unchanged.
