// Dev harness determinism (research fork): a fixed random stream and fixed guest clocks, so the same scenario plays
// out the same run after run. Compiled only with MLB_DEV_HARNESS; without it every call is an empty macro.
//
//   MLB_HARNESS_SEED=<n>        every host random source (GetInfo 11, csrng, uuids) reads one stream seeded with n
//   MLB_HARNESS_FIXED_CLOCK=1   guest tick = base + 1/60 s per presented frame + a small step per read; wall clock fixed
//   MLB_HARNESS_EPOCH=<s>       the fixed wall clock at boot, posix seconds (default 2026-06-15 19:05:00 UTC)
//   MLB_HARNESS_DET_TRACE=<f>   per presented frame: hashes of main's data/bss in 64 KiB chunks, written to <f>
//   MLB_HARNESS_DET_LOG=1       logs every random request
#pragma once

#ifdef MLB_DEV_HARNESS

#include <stddef.h>
#include <stdint.h>

extern int hd_clock_on;                  // 1 with MLB_HARNESS_FIXED_CLOCK=1
uint64_t hd_ticks(void);                 // the fixed 19.2 MHz guest counter (main.c rt_ticks)
int64_t hd_time(void);                   // posix seconds: the fixed epoch plus the fixed tick, or time(NULL)
int hd_random(void *out, size_t n);      // 1 when it filled out from the seeded stream (platform plat_random)
void hd_frame(uint64_t frame);           // once per presented frame (gfx_stubs.c mlb_capture_tick)

#define HD_TICKS_FIXED() (hd_clock_on)
#else

#define HD_TICKS_FIXED() 0
#define hd_ticks() 0
#define hd_time() ((int64_t)time(NULL))
#define hd_random(o, n) 0
#define hd_frame(f) ((void)0)

#endif
