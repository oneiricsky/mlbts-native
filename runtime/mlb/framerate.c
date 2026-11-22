// fastball: the frame rate limit above (or below) the game's 60 fps (MLB_FPS_LIMIT, the settings menu's Display tab).
// Replaces the frame_step_* stubs of gfx_stubs.c; TotK Recomp's frame_rate.c is the model for the host half (the
// present pacer holds frames to the limit, nvn_api_obj.c present_period).
//
// How MLB times its frames (1.0.20 main+0x58a9f0, 1.0.15 main+0x58a9d0; read 2026-11-16): the main loop calls this frame
// timer once a frame with the number of 60 Hz vsyncs a frame should last, an int the game keeps in its data (1.0.20
// main+0x22ad028, written as 60 / target fps from the table {1, 5, ..., 48, 60} at main+0x22ad02c: 1 for 60 fps). The
// timer sleeps until that many vsyncs have passed since the last frame (minus 1/1200 s), then sets the game's frame step
// (main+0x22c90c4, read back by main+0x58a9e0 into s_fDeltaTime, which some 200 sites of the game read):
//   - with the averaging flag set (main+0x22c9078, 1 as shipped), the step is the mean of the last 15 measured frame
//     times (the farthest from the mean dropped), at least the target (vsyncs / 60 s) and at most a ceiling;
//   - with it clear, the step is the whole vsyncs measured, at least the target.
// So MLB already steps its game by real time; the vsync count only sets its own sleep and the step's floor. With the
// count at 0 the timer does not sleep and the step is the mean measured frame time: the game runs at whatever rate the
// frames come, at its normal speed. The host pacer then holds frames to the limit. Nothing in the game's code changes.
//
// The averaging flag follows a byte the game's event handler sets (main+0xd514e0: event 0x220 sets it, so averaging
// off; 0x61, 0x11c and 0x213 clear it) and main+0xd4f6e0 copies before each timer call. With averaging off and a count
// of 0, a frame shorter than 1/60 s would step the game by 0 (the whole vsyncs measured): so in that state the game's
// own count goes back and the frame rate is the game's own 60 again, until averaging is back on.
//
// The switch to whole vsyncs reaches the host one frame late: the game copies the handler's byte into the flag
// (main+0xd4f6e0) right before it calls the timer, and the host sees the flag only at the next present. So one timer
// call runs with whole vsyncs and a count of 0, and a frame shorter than 1/60 s steps the game by exactly 0: a frame in
// which nothing moves, and inf or NaN wherever the game divides by its step (found 2026-11-18 while tracing GitHub #18,
// no ball in one RTTS batting cage mode above 60 fps; not reproduced, so not confirmed as its cause). The timer's carry (main+0x2cb6150: the frame time left over from the whole vsyncs, at most
// 1/60 s, read nowhere else) guards that frame: at every unlocked present the host sets it to 1/60 s, so whole vsyncs
// count at least 1 and the step is at least 1/60 s. With averaging on the carry changes nothing: the step is the
// average, and the sleep reads only a negative carry (a count above the vsyncs measured, never with a count of 0).
//
// The other callers of the timer (loading loops) pass 1 themselves and stay at 60.
//
// MLB_FPS_LIMIT=60 (default): nothing here runs; the game and the pacer behave as shipped. Any other limit, read live:
// the count is set to 0 at every present while averaging is on (the game sets its own value again on some screen
// changes; one frame at 60 follows), and the pacer holds frames to the limit. "display" is the monitor's refresh rate.
// At most 240 per second, as in TotK Recomp (the shortest step tested there); MLB's own shortest is not known.
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "gfx.h"
#include "host.h"
#include "ui/menu.h"

#define LIMIT_MIN_HZ 30
#define LIMIT_MAX_HZ 240

// The game's data, per version: the GOT slots of the vsync count and of the averaging flag (main+0x6cfc and the
// timer's own loads), so a wrong address shows as a slot that does not point into main's data.
// step: the timer's result, the game's frame step in seconds (MLB_TRACE=perf only). carry: the timer's leftover frame
// time (float seconds, the timer's own adrp x20 + 0x150). The two builds' timers are the same instructions with other
// addresses (compared 2026-11-16, the carry 2026-11-18).
static const struct { const char *build; uint64_t count_slot, avg_slot, step, carry; } k_addrs[] = {
    {"1.0.15", 0x700227d000ull, 0x7002283ba8ull, 0x70022c70c4ull, 0x7002cb4150ull},
    {"1.0.20", 0x700227e070ull, 0x7002284c18ull, 0x70022c90c4ull, 0x7002cb6150ull},
};

static volatile int32_t *g_count;       // the game's vsyncs per frame; NULL: unknown game build
static volatile const uint8_t *g_avg;   // the timer's averaging flag
static volatile const float *g_step;    // the game's frame step
static volatile float *g_carry;         // the timer's leftover frame time (seconds, at most 1/60)
static int32_t g_game_count = 1;        // the count the game last wrote (what goes back at the limit 60)
static int g_addrs_read;

static unsigned g_seen;
static int g_read, g_limit = 60;        // 0: the monitor's refresh rate
static int g_active;                    // this frame runs unlocked: count 0, the pacer at the limit

static void addrs_init(void) {
    g_addrs_read = 1;
    for (size_t i = 0; i < sizeof k_addrs / sizeof *k_addrs; i++) {
        if (strcmp(rt_game_build, k_addrs[i].build)) continue;
        uint64_t count = *(const uint64_t *)(uintptr_t)k_addrs[i].count_slot;
        uint64_t avg = *(const uint64_t *)(uintptr_t)k_addrs[i].avg_slot;
        int32_t v = *(const int32_t *)(uintptr_t)count;
        if (count < 0x7002000000ull || count >= 0x7004000000ull || avg < 0x7002000000ull || avg >= 0x7004000000ull ||
            v < 0 || v > 60) {
            rt_log("frame rate: game %s's frame timer data is not where expected (count %#llx = %d, flag %#llx); "
                   "the game's own 60 fps stays", rt_game_build, (unsigned long long)count, v, (unsigned long long)avg);
            return;
        }
        g_count = (volatile int32_t *)(uintptr_t)count;
        g_avg = (volatile const uint8_t *)(uintptr_t)avg;
        g_step = (volatile const float *)(uintptr_t)k_addrs[i].step;
        g_carry = (volatile float *)(uintptr_t)k_addrs[i].carry;
        return;
    }
    rt_log("frame rate: no frame timer known for game %s; the game's own 60 fps stays", rt_game_build);
}

static void limit_live(void) {
    unsigned v = cfg_version();
    if (g_read && v == g_seen) return;
    g_read = 1;
    g_seen = v;
    const char *e = cfg_value("FPS_LIMIT");
    int hz = 60;
    if (!strcmp(e, "display")) hz = 0;
    else {
        char *end;
        long n = strtol(e, &end, 10);
        if (!*end && n >= LIMIT_MIN_HZ && n <= LIMIT_MAX_HZ) hz = (int)n;
        else rt_log("frame rate: MLB_FPS_LIMIT=%s is not %d..%d or display; 60", e, LIMIT_MIN_HZ, LIMIT_MAX_HZ);
    }
    if (hz == g_limit) return;
    g_limit = hz;
    if (hz) rt_log("frame rate: limit %d fps%s", hz, hz == 60 ? " (the game's own)" : "");
    else rt_log("frame rate: limit at the monitor's refresh rate");
}

// The limit in frames per second: the setting, or the monitor's rate (60 while it is not known).
static double limit_hz(void) {
    double hz = g_limit ? g_limit : gfx_window_refresh_hz();
    if (hz < LIMIT_MIN_HZ) hz = 60;
    return hz > LIMIT_MAX_HZ ? LIMIT_MAX_HZ : hz;
}

int frame_step_realtime(void) { return g_active; }

// Under the menu's row (ui/menu.cpp): why the limit is not in effect now; NULL when it is.
const char *frame_rate_note(void) {
    double hz = limit_hz();
    if (g_active || (hz > 59.5 && hz < 60.5)) return NULL;
    if (g_addrs_read && !g_count) return "not available for this game version";
    return "the game holds 60 here";
}

uint64_t frame_step_cap_ns(void) { return (uint64_t)(1e9 / limit_hz() + 0.5); }

// MLB_TRACE=perf: every 600 presents, the game time its frame steps added up to against the wall time between the
// presents' display times. 1.00 is the game at its normal speed; above it the game runs fast. Long frames (loads) are
// left out of both sums: there the game's step stops at its ceiling.
static void speed_report(uint64_t display_ns) {
    static uint64_t last_ns, n;
    static double game_s, wall_s;
    float step = *g_step;
    if (last_ns && display_ns > last_ns) {
        double dt = (double)(display_ns - last_ns) / 1e9;
        if (dt < 0.1) game_s += step, wall_s += dt;
    }
    last_ns = display_ns;
    if (++n % 600 || wall_s <= 0) return;
    rt_log("perf: frame rate: game time %.2f s in %.2f s (%.3f), %.1f fps, %s", game_s, wall_s, game_s / wall_s,
           600 / wall_s, g_active ? "unlocked" : "the game's own pacing");
    game_s = wall_s = 0;
}

// Every present (nvnQueuePresentTexture, after this frame's pacing): decides the next frame. The game's frame timer
// runs at the start of the next frame and reads the count then.
void frame_step_present(uint64_t display_ns, int interval) {
    (void)interval;
    limit_live();
    if (!g_addrs_read) {
        if (g_limit == 60 && !(rt_trace & RT_TRACE_PERF)) return;   // the default: nothing to look up
        addrs_init();
    }
    if (!g_count) return;
    if (rt_trace & RT_TRACE_PERF) speed_report(display_ns);
    int32_t now = *g_count;
    if (now != 0) g_game_count = now;   // the host only ever writes 0 or the game's own value back
    double hz = limit_hz();
    int want = hz > 60.5 || hz < 59.5;
    int avg = *g_avg != 0;
    int active = want && avg;
    if (active != g_active) {
        if (want) rt_log("frame rate: %s", active ? "unlocked (the game steps by the measured frame time)"
                                                  : "the game's own 60 fps (it steps by whole vsyncs here)");
        g_active = active;
    }
    int32_t set = active ? 0 : g_game_count;
    if (now != set) *g_count = set;
    // The next timer call may already run with whole vsyncs (the flag is copied right before it): a full carry makes
    // its step at least 1/60 s, never 0. The timer's own bound: its 1/60 constant is this float (0x3c888889).
    if (active) *g_carry = 1.0f / 60.0f;
}
