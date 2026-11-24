// fastball: the game-modes menu without the "you are currently disconnected" panel (MLB_HIDE_OFFLINE_BANNER).
//
// The main menu's data object (class "GameModesMain", vtable 0x70021bd438 in 1.0.20) has the fields HAS_ANNOUNCEMENTS,
// ANNOUNCMENT_NUMBER, SHOW_DYNAMIC_PANELS and STUBS_CAP. Its function in slot 8 (f_7000c0dc6c, 1.0.20) hands the
// field values to the menu script; for SHOW_DYNAMIC_PANELS it gives obj[+0x129] && obj[+0x128] [C, read 2026-11-24].
// Both bytes are set by the function in slot 6 (f_7000c0da4c) from the online state: offline both are 0, so the menu
// script draws its "offline" tile, a 1740x636 picture of a Wi-Fi symbol and the text "YOU ARE CURRENTLY DISCONNECTED!"
// in a focus frame (FRONTEND.TEX dynamictile_home_offline). Setting the bytes for good made the game think it was
// online (a "NETWORK ERROR" box); setting them only while slot 8 runs gives the menu script a true SHOW_DYNAMIC_PANELS
// and leaves every other reader of the bytes alone. The panels list is then empty, so no tile is drawn.
#include <stdint.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"

static const struct { const char *build; uint64_t slot, fn; } k_builds[] = {
    {"1.0.20", 0x70021bd438ull + 8 * 8, 0x7000c0dc6cull},
};
static uint64_t g_prev;

static void get_hook(Cpu *c) {
    uint64_t obj = c->x[0];
    int ok = obj && mem_guest_readable(obj + 0x128, 2);
    uint8_t *p = (uint8_t *)(uintptr_t)obj, was128 = 0, was129 = 0;
    if (ok) {
        was128 = p[0x128], was129 = p[0x129];
        p[0x128] = p[0x129] = 1;
    }
    uint64_t r = rt_call(c, g_prev, 4, c->x[0], c->x[1], c->x[2], c->x[3]);
    if (ok) p[0x128] = was128, p[0x129] = was129;
    c->x[0] = r;
}

static int poke64(uint64_t addr, uint64_t val) {
    uint64_t page = addr & ~0xfffull, end = (addr + 8 + 0xfff) & ~0xfffull, stop = 0;
    int prot = plat_mem_state(page, end, &stop);
    if (prot < PLAT_PROT_READ || stop < end) return 0;
    if (prot != PLAT_PROT_RW && !plat_mem_protect(page, end - page, PLAT_PROT_RW)) return 0;
    memcpy((void *)(uintptr_t)addr, &val, 8);
    if (prot != PLAT_PROT_RW) plat_mem_protect(page, end - page, prot);
    return 1;
}

void menu_offline_apply(void) {
    if (!cfg_bool("MLB_HIDE_OFFLINE_BANNER")) return;
    int b = -1;
    for (int i = 0; i < (int)(sizeof k_builds / sizeof *k_builds); i++)
        if (!strcmp(rt_game_build, k_builds[i].build)) b = i;
    if (b < 0) {
        rt_log("menu offline: no addresses for game %s; the offline panel stays", rt_game_build);
        return;
    }
    uint64_t have = mem_guest_readable(k_builds[b].slot, 8) ? *(const uint64_t *)(uintptr_t)k_builds[b].slot : 0;
    if (have != k_builds[b].fn) {
        rt_log("menu offline: slot %#llx holds %#llx, not %#llx; the offline panel stays",
               (unsigned long long)k_builds[b].slot, (unsigned long long)have, (unsigned long long)k_builds[b].fn);
        return;
    }
    g_prev = have;
    if (!poke64(k_builds[b].slot, hostfn_register("<menu offline>", get_hook))) {
        rt_log("menu offline: could not write slot %#llx; the offline panel stays", (unsigned long long)k_builds[b].slot);
        return;
    }
    rt_log("menu offline: the main menu shows no offline panel");
}
