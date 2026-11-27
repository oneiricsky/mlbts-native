// fastball (hid.c nne_log): the presses the port makes once the main menu is back after a failed login, and when the
// black screen over them ends. Times are on hid.c's running-game clock. tools/nne_plan_test.c checks it without the game.
#pragma once
#include <stdint.h>

#define NNE_DELAY_NS 300000000ull
#define NNE_HOLD_NS 100000000ull
#define NNE_GAP_NS 1000000000ull
#define NNE_TAIL_NS 700000000ull

// A span with from == to == 0 is not pressed. hold_end is always set: with the box patched out there is often no
// press at all, and the black screen must not wait for its 12 s limit.
typedef struct { uint64_t a_from, a_to, down_from, down_to, hold_end; } NnePlan;

static inline NnePlan nne_plan(uint64_t clock, int press_a, int press_down) {
    NnePlan p = {0};
    if (press_a) {
        p.a_from = clock + NNE_DELAY_NS;
        p.a_to = p.a_from + NNE_HOLD_NS;
        p.hold_end = p.a_to + NNE_TAIL_NS;
    }
    if (press_down) {
        p.down_from = clock + NNE_GAP_NS;
        p.down_to = p.down_from + NNE_HOLD_NS;
        p.hold_end = p.down_to + NNE_TAIL_NS;
    }
    if (!p.hold_end) p.hold_end = clock + NNE_TAIL_NS;
    return p;
}
