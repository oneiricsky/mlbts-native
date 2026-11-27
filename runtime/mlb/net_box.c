// fastball (MLB_NO_NETWORK_ERROR, patch set no_net_box): drop only the "Network Error" boxes from the game's message
// box queue. f_7000aa6ea8 calls f_7000889978 every frame a box waits; that opens the next queued box, whatever it
// says. Removing the call kept every box from opening, and the game waits for the answer of its own ones: seen
// 2026-11-26 as a hang on Road to the Show's "Tools and Attributes" confirm, with "Network Error", "Auto-Saving" and
// "You still have tokens remaining." waiting in the queue; the hang ended when the call ran again [C]. The patch site
// now calls the function here, which takes the network error entries off the queue and then makes the game's call.
//
// The queue (manager object, 1.0.20) [C]: 16 entries of 0x7e8 bytes from offset 0, each with its title at +0x20;
// bytes at +0x7e90: last queued, last shown, box active, blocked.
#include <stdint.h>
#include <string.h>

#define NB_SLOTS 16
#define NB_ENTRY 0x7e8
#define NB_TITLE 0x20
#define NB_STATE 0x7e90

// The entries dropped. Nothing is touched while a box is up or the queue is blocked: the game opens nothing then.
int net_box_drop(uint8_t *queue) {
    uint8_t *s = queue + NB_STATE;   // [0] queued, [1] shown, [2] active, [3] blocked
    int dropped = 0;
    while (!s[2] && !s[3] && s[1] != s[0]) {
        int next = (s[1] + 1) % NB_SLOTS;
        if (memcmp(queue + (size_t)next * NB_ENTRY + NB_TITLE, "Network Error", sizeof "Network Error")) break;
        s[1] = (uint8_t)next;
        dropped++;
    }
    return dropped;
}

#ifndef NET_BOX_TEST
#include "host.h"

#define NB_HOOK 0x8a0   // patch page offset, as encoded in the patch file's bl word
#define NB_SHOW 0x7000889978ull

static void show_hook(Cpu *c) {
    uint64_t queue = c->x[0];
    if (queue && mem_guest_readable(queue, NB_STATE + 4) && net_box_drop((uint8_t *)(uintptr_t)queue))
        rt_log("net box: a Network Error box was taken off the queue");
    rt_call(c, NB_SHOW, 1, queue);
}

// boot.c: after rt_patches_init, before hostfn_seal. With the set off the site runs the game's own call.
void net_box_apply(void) {
    uint8_t *page = rt_patch_page();
    if (page && rt_patch_set("no_net_box") >= 0 && !strcmp(rt_game_build, "1.0.20"))
        rt_register_host((uint64_t)(uintptr_t)page + NB_HOOK, show_hook);
}
#endif
