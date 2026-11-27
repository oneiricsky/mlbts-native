// Checks runtime/core/guest_sleep.h without the game: how late each sleep ends and what a polling loop costs.
//   clang -O2 -march=x86-64-v3 -D_CRT_SECURE_NO_WARNINGS -I runtime/core -I runtime/mlb tools/sleep_test.c
//     runtime/core/platform/win32.c -ffunction-sections -fuse-ld=lld -Wl,/OPT:REF -o work/sleep_test.exe
//     <LLVM>/lib/clang/<n>/lib/windows/clang_rt.builtins-x86_64.lib
//     -lbcrypt -luser32 -ladvapi32 -lwinmm -lpsapi -lshell32 -lole32
//   work/sleep_test.exe
// Timing checks: run it on a machine with a free core.
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>

#include "guest_sleep.h"

#define N 4000

static int failed;

static void check(const char *what, int ok) {
    printf("%s: %s\n", ok ? "ok" : "FAIL", what);
    failed |= !ok;
}

static int by_value(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return x < y ? -1 : x > y;
}

static uint64_t cpu_ns(void) {
    FILETIME c, e, k, u;
    GetThreadTimes(GetCurrentThread(), &c, &e, &k, &u);
    return (((uint64_t)k.dwHighDateTime << 32 | k.dwLowDateTime) +
            ((uint64_t)u.dwHighDateTime << 32 | u.dwLowDateTime)) * 100;
}

static void busy(uint64_t ns) {
    uint64_t end = plat_now_ns() + ns;
    while (plat_now_ns() < end) plat_pause();
}

typedef struct { double cpu, med, p99; int early; } Run;

// A loop of sleeps of ns each with work_ns of work before each one; cpu is the whole loop's, the times the sleeps'.
static Run run(const char *what, uint64_t ns, uint64_t work_ns) {
    static uint64_t took[N];
    GuestSleep s = {0};
    Run r = {0};
    uint64_t t0 = plat_now_ns(), c0 = cpu_ns(), now = t0;
    int n = 0;
    while (n < N && now - t0 < 3000000000ull) {
        if (work_ns) busy(work_ns);
        uint64_t before = plat_now_ns();
        guest_sleep_ns(&s, ns);
        now = plat_now_ns();
        guest_sleep_resumed(&s);
        took[n] = now - before;
        r.early += took[n] < ns;
        n++;
    }
    r.cpu = 100.0 * (cpu_ns() - c0) / (now - t0);
    double per_s = n * 1e9 / (now - t0);
    qsort(took, n, sizeof *took, by_value);
    r.med = took[n / 2] / 1e3;
    r.p99 = took[n * 99 / 100] / 1e3;
    printf("%-22s %7.1f us: %5d times, cpu %5.1f%%, took median %7.1f us p99 %7.1f us, %6.0f per s, early %d\n", what,
           ns / 1e3, n, r.cpu, r.med, r.p99, per_s, r.early);
    return r;
}

// How many back-to-back sleeps of ns stay on the clock after a pause with work.
static int exact_after_work(uint64_t ns) {
    GuestSleep s = {0};
    for (int i = 0; i < 100; i++) {
        guest_sleep_ns(&s, ns);
        guest_sleep_resumed(&s);
    }
    busy(200000);
    int n = 0;
    for (; n < 100; n++) {
        uint64_t before = plat_now_ns();
        guest_sleep_ns(&s, ns);
        if (plat_now_ns() - before > ns + 150000) break;
        guest_sleep_resumed(&s);
    }
    return n;
}

int main(void) {
    plat_timer_1ms();
    Run poll = run("idle poll", 100000, 0), sdk = run("idle poll", 20000, 0);
    Run w100 = run("work between", 100000, 200000), w200 = run("work between", 200000, 200000);
    Run w400 = run("work between", 400000, 200000);
    Run idle1ms = run("idle poll", 1000000, 0), frame = run("idle poll", 16000000, 0);
    int n = exact_after_work(100000);
    printf("after work, %d sleeps of 100 us in a row stayed on the clock\n", n);
    check("a 100 us idle poll loop (the sound file thread) uses under 20% of a core", poll.cpu < 20.0);
    check("a 100 us idle poll still ends within 1 ms (median)", poll.med < 1000.0);
    check("a 20 us idle poll stays exact (median under 25 us)", sdk.med < 25.0);
    check("a 100 us sleep between work stays exact (median under 130 us)", w100.med < 130.0);
    check("a 200 us sleep between work stays exact (median under 230 us)", w200.med < 230.0);
    check("a 400 us sleep between work stays exact (median under 430 us)", w400.med < 430.0);
    check("work ends the back-off: the next sleeps are exact again", n >= 8);
    check("no sleep ends early", !poll.early && !sdk.early && !w100.early && !w200.early && !w400.early &&
                                     !idle1ms.early && !frame.early);
    return failed;
}
