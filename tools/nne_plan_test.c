// Checks runtime/mlb/nne_plan.h (the presses and the end of the black screen after a failed login) without the game.
//   clang -I runtime/mlb tools/nne_plan_test.c -o work/scratch/nne_plan_test.exe && work/scratch/nne_plan_test.exe
#include <stdio.h>

#include "nne_plan.h"

static int failed;

static void check(const char *what, int ok) {
    printf("%s: %s\n", ok ? "ok" : "FAIL", what);
    failed |= !ok;
}

int main(void) {
    const uint64_t c = 5000000000ull;
    NnePlan p = nne_plan(c, 0, 0);   // a tile press with the box patched out
    check("no press is scheduled", !p.a_from && !p.a_to && !p.down_from && !p.down_to);
    check("with no press the black screen still ends after the tail", p.hold_end == c + NNE_TAIL_NS);

    p = nne_plan(c, 1, 0);
    check("A is held 0.3 s later", p.a_from == c + NNE_DELAY_NS && p.a_to == p.a_from + NNE_HOLD_NS);
    check("black ends after A and the tail", p.hold_end == p.a_to + NNE_TAIL_NS);

    p = nne_plan(c, 0, 1);
    check("Down is held 1 s later", p.down_from == c + NNE_GAP_NS && p.down_to == p.down_from + NNE_HOLD_NS);
    check("black ends after Down and the tail", p.hold_end == p.down_to + NNE_TAIL_NS && !p.a_to);

    p = nne_plan(c, 1, 1);
    check("with both, black ends after the later one", p.hold_end == p.down_to + NNE_TAIL_NS);
    return failed;
}
