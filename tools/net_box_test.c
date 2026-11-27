// Checks runtime/mlb/net_box.c's queue filter without the game.
//   clang -DNET_BOX_TEST tools/net_box_test.c -o work/net_box_test.exe && work/net_box_test.exe
#include <stdio.h>
#include <string.h>

#include "../runtime/mlb/net_box.c"

static uint8_t q[NB_STATE + 4];
static int failed;

static void check(const char *what, int ok) {
    printf("%s: %s\n", ok ? "ok" : "FAIL", what);
    failed |= !ok;
}

static void queue(int shown, const char *const *titles, int n) {
    memset(q, 0, sizeof q);
    q[NB_STATE + 1] = (uint8_t)shown;
    q[NB_STATE] = (uint8_t)((shown + n) % NB_SLOTS);
    for (int i = 0; i < n; i++)
        strcpy((char *)q + (size_t)((shown + 1 + i) % NB_SLOTS) * NB_ENTRY + NB_TITLE, titles[i]);
}

int main(void) {
    const char *seen[] = {"Network Error", "Auto-Saving", ""};   // the queue of the hang: the last box has no title
    queue(0, seen, 3);
    check("the leading network error is dropped", net_box_drop(q) == 1 && q[NB_STATE + 1] == 1);
    check("the next box stays queued", q[NB_STATE] == 3);
    check("a second call drops nothing", net_box_drop(q) == 0 && q[NB_STATE + 1] == 1);

    const char *two[] = {"Network Error", "Network Error"};
    queue(15, two, 2);
    check("two in a row across the ring's end", net_box_drop(q) == 2 && q[NB_STATE + 1] == q[NB_STATE]);

    const char *other[] = {"Network Errors"};
    queue(0, other, 1);
    check("a longer title is another box", net_box_drop(q) == 0);

    queue(0, seen, 3);
    q[NB_STATE + 2] = 1;
    check("nothing moves while a box is up", net_box_drop(q) == 0 && q[NB_STATE + 1] == 0);
    queue(0, seen, 3);
    q[NB_STATE + 3] = 1;
    check("nothing moves while the queue is blocked", net_box_drop(q) == 0 && q[NB_STATE + 1] == 0);
    queue(4, seen, 0);
    check("an empty queue stays", net_box_drop(q) == 0 && q[NB_STATE + 1] == 4);
    return failed;
}
