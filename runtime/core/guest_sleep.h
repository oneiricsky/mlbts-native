// fastball: how a guest SleepThread waits on the host. tools/sleep_test.c checks it without the game.
#pragma once
#include "platform/platform.h"

// The OS timer ends a wait late by up to PLAT_WAIT_LATE_NS (Windows' high-resolution waitable timer: 0.3-0.5 ms; the
// SDK's 20 us polling sleeps, main thread and job workers, about 1.5 per frame each, took 460-515 us). Sleeps up to
// twice that spin on the clock instead (1 ms on Windows, 120 us on Linux); the virtual core is already given up.
#define GUEST_SPIN_NS (2 * PLAT_WAIT_LATE_NS)

// Spinning costs a host core for as long as it goes on. The SCREAM sound library's file stream thread (f_7001b42280,
// 1.0.20) looks at its queue and sleeps 100 us, about 9,000 times a second, menus included: 98% of a core. So a thread
// that asks for the same sleep of at least GUEST_POLL_MIN_NS more than GUEST_POLL_STREAK times in a row, running less
// than GUEST_POLL_GAP_NS between them, is idle polling and waits on the OS timer until it does some work again. Shorter
// sleeps and occasional ones (the SDK's 200 us sleeps on the job threads, about 1,000 in 90 s) stay on the clock.
#define GUEST_POLL_MIN_NS 100000u
#define GUEST_POLL_STREAK 16
#define GUEST_POLL_GAP_NS 50000u

typedef struct { uint64_t ns, resumed; uint32_t streak; } GuestSleep;   // one per guest thread, zero at its start

// The thread runs guest code again after a sleep (after it got a virtual core back: that wait is not its work).
static inline void guest_sleep_resumed(GuestSleep *s) { s->resumed = plat_now_ns(); }

static inline void guest_sleep_ns(GuestSleep *s, uint64_t ns) {
    if (ns != s->ns || plat_now_ns() - s->resumed >= GUEST_POLL_GAP_NS) s->streak = 0;
    else if (s->streak < GUEST_POLL_STREAK) s->streak++;
    s->ns = ns;
    if (ns <= GUEST_SPIN_NS && (ns < GUEST_POLL_MIN_NS || s->streak < GUEST_POLL_STREAK)) {
        uint64_t end = plat_now_ns() + ns;
        while (plat_now_ns() < end) plat_pause();
        return;
    }
    plat_wait_ns(ns);
}
