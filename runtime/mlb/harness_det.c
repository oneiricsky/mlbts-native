// Dev harness determinism: see harness_det.h. Our own implementation.
#ifdef MLB_DEV_HARNESS

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gfx.h"
#include "harness_det.h"
#include "host.h"
#include "nvn_api.h"
#include "platform/platform.h"

#define TICK_HZ 19200000ull
#define FRAME_TICKS (TICK_HZ / 60)      // one presented frame is 1/60 s of guest time
#define READ_TICKS 96ull                // 5 us per tick read, so a loop that polls the clock moves on
#define BASE_TICKS (10 * TICK_HZ)       // the steady clock starts at 10 s, as a console some seconds after boot
#define CHUNK 0x10000u

int hd_clock_on;
static int seed_on, log_on;
static uint64_t seed, epoch = 1781550300;   // 2026-06-15 19:05:00 UTC
static const char *trace_path;

static _Atomic uint64_t frame_now, reads_in_frame, last_tick, rnd_ctr;

__attribute__((constructor)) static void hd_env(void) {
    const char *s = getenv("MLB_HARNESS_SEED"), *c = getenv("MLB_HARNESS_FIXED_CLOCK"), *e = getenv("MLB_HARNESS_EPOCH");
    if (s && *s) { seed = strtoull(s, NULL, 0); seed_on = 1; }
    hd_clock_on = c && *c && strcmp(c, "0");
    if (e && *e) epoch = strtoull(e, NULL, 0);
    trace_path = getenv("MLB_HARNESS_DET_TRACE");
    if (trace_path && !*trace_path) trace_path = NULL;
    log_on = getenv("MLB_HARNESS_DET_LOG") != NULL;
}

uint64_t hd_ticks(void) {
    uint64_t f = atomic_load_explicit(&frame_now, memory_order_relaxed);
    uint64_t n = atomic_fetch_add_explicit(&reads_in_frame, 1, memory_order_relaxed);
    uint64_t v = BASE_TICKS + f * FRAME_TICKS + n * READ_TICKS, last = atomic_load_explicit(&last_tick, memory_order_relaxed);
    do {   // never backwards, and every read is newer than the one before
        if (v <= last) v = last + 1;
    } while (!atomic_compare_exchange_weak_explicit(&last_tick, &last, v, memory_order_relaxed, memory_order_relaxed));
    return v;
}

int64_t hd_time(void) {
    if (!hd_clock_on) return (int64_t)time(NULL);
    return (int64_t)epoch + (int64_t)((hd_ticks() - BASE_TICKS) / TICK_HZ);
}

static uint64_t splitmix(uint64_t x) {
    x += 0x9E3779B97F4A7C15ull;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBull;
    return x ^ (x >> 31);
}

int hd_random(void *out, size_t n) {
    if (!seed_on) return 0;
    uint64_t k = atomic_fetch_add_explicit(&rnd_ctr, 1, memory_order_relaxed);
    uint8_t *p = out;
    for (size_t i = 0; i < n; i += 8) {
        uint64_t w = splitmix(seed * 0x2545F4914F6CDD1Dull + k * 0x100000001B3ull + i);
        memcpy(p + i, &w, n - i < 8 ? n - i : 8);
    }
    if (log_on) rt_log("harness det: random request %llu: %zu bytes", (unsigned long long)k, n);
    return 1;
}

static uint64_t hash_chunk(const uint8_t *p, size_t n) {
    uint64_t h = 0xCBF29CE484222325ull;
    for (size_t i = 0; i + 8 <= n; i += 8) {
        uint64_t w;
        memcpy(&w, p + i, 8);
        h = (h ^ w) * 0x100000001B3ull;
        h ^= h >> 29;
    }
    return h;
}

// Trace file: "HDT1", u32 chunk, u64 base, u64 size; then per frame {u64 frame, tick, nvn_calls, nvn_distinct, u32 n,
// u32 pad, u64 hash[n]}. The hashes run over main's writable data and bss while the game's threads keep running.
static FILE *tf;
static int tf_failed;

static void trace_frame(uint64_t frame) {
    const RtLoaded *m = ldr_count() ? ldr_module(0) : NULL;
    if (!m || tf_failed) return;
    uint64_t lo = m->base + m->data_off, hi = m->base + m->size;
    if (!tf) {
        tf = fopen(trace_path, "wb");
        if (!tf) { tf_failed = 1; rt_log("harness det: cannot write %s", trace_path); return; }
        uint32_t chunk = CHUNK;
        fwrite("HDT1", 1, 4, tf);
        fwrite(&chunk, 4, 1, tf);
        fwrite(&lo, 8, 1, tf);
        uint64_t sz = hi - lo;
        fwrite(&sz, 8, 1, tf);
        rt_log("harness det: trace %s: main+%#llx..+%#llx in %u-byte chunks", trace_path, (unsigned long long)m->data_off,
               (unsigned long long)m->size, CHUNK);
    }
    uint32_t n = (uint32_t)((hi - lo + CHUNK - 1) / CHUNK);
    uint64_t *h = malloc(n * 8);
    static const uint8_t zero[CHUNK];
    for (uint32_t i = 0; i < n; i++) {
        uint64_t a = lo + (uint64_t)i * CHUNK, len = hi - a < CHUNK ? hi - a : CHUNK;
        h[i] = hash_chunk(plat_mem_readable(a, len) ? (const uint8_t *)(uintptr_t)a : zero, len);
    }
    uint64_t rec[4] = {frame, atomic_load(&last_tick), __atomic_load_n(&gfx_counters.nvn_calls, __ATOMIC_RELAXED),
                       __atomic_load_n(&gfx_counters.nvn_distinct, __ATOMIC_RELAXED)};
    uint32_t hd[2] = {n, 0};
    fwrite(rec, 8, 4, tf);
    fwrite(hd, 4, 2, tf);
    fwrite(h, 8, n, tf);
    fflush(tf);
    free(h);
}

void hd_frame(uint64_t frame) {
    atomic_store_explicit(&frame_now, frame, memory_order_relaxed);
    atomic_store_explicit(&reads_in_frame, 0, memory_order_relaxed);
    if (trace_path) trace_frame(frame);
}

#endif
