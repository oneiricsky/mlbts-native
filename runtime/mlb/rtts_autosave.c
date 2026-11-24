// fastball: Road to the Show upgrades bought in the hub are saved when the player leaves the screen they were bought
// on (MLB_RTTS_AUTOSAVE, on by default). The game writes a career save after a played game and on a few game events,
// but not after hub purchases: a perk or attribute upgrade bought in the hub was lost when the player quit before
// the next game without saving by hand (seen 2026-11-20: an attribute upgrade, game closed, tokens and rating back as
// before).
//
// What the game does [C, 1.0.15 addresses; 1.0.20 in the table below; read 2026-11-20]:
//   f_7000de6728 (no arguments) is the career autosave the game runs after a played game: it checks that a career is
//   being played and the conditions the game checks there, takes the career save and queues it for the save worker,
//   which commits the file. The game also calls it from a few game events, never from the hub menus.
//   Every hub purchase or refund is a menu script command reached through a function pointer in main's data: perk
//   levels, perk upgrade parts and their removal (8), attribute upgrades and their commit (3). Each sets the player's
//   tokens through f_70004408e4, which stores them as a u16 at +0x12c0 of the record that f_700045c704(&record)
//   returns. A trigger upgrade goes through f_7000bd1da0 (1.0.20 f_7000bd3140), whose cost can be 0.
//   f_70004c779c (slot 0x700217d580, three arguments, no result) runs once each time a full screen is entered
//   ("uiEngine: Entering screen" [TitleLoadingScreen->...]) and for a few overlay layers (seen: Online Icons), not
//   for the sub-menus inside the Perks and Tools screens.
//
// How: a perk command, or an attribute command that changed the tokens, marks a save as wanted. The save runs at the
// next screen change, after the screen's own function: normally when the player leaves the Perks, Tools or pitch
// upgrade screen, once for any number of purchases. An overlay layer entering while the player is still in those
// menus would save there; not seen. Should the screen change while a command is still running, the save runs as soon
// as that command returns; not seen in any run either. (Saving right after each purchase was tried first; once
// the menu stopped taking input after the third purchase in a row, cause not found; in that run every save was
// followed by the menu re-entering its selection box.) The screen slot is shared with tutorials.c: whatever it holds
// at boot (the game's function or tutorials.c's host function) is called.
//
// Not while a new player is made. Making a player runs the same commands (the position's confirm, the first tokens
// spent on the TokenAllocation screen, the same screen as the hub's Tools), and the game's autosave then saved the
// half-made player as a career, before the name was typed. When the game closed or stopped before its own next save,
// that save was what was left: a career with the default name "Joe Random" that opened straight in the hub instead of
// the rest of creation (seen 2026-11-23, a player's report and test runs; a creation that runs on to the game's next
// save was not followed).
// Making a player starts at the BpCreation screen and ends when the Road to the Show home (RttSHomeMain) opens, and
// in between this module saves nothing, so the game saves when it would without it. services.c hands every game log
// line to rtts_autosave_game_log, which follows those two screens.
#include <stdint.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"

#define NBUY 11   // 0-7 perk commands, 8-10 attribute commands
static const struct {
    const char *build;
    uint64_t autosave, get_record, screen_slot, screen_fn;
    uint64_t slot[NBUY], fn[NBUY];
} k_builds[] = {
    {"1.0.15", 0x7000de6728ull, 0x700045c704ull, 0x700217d580ull, 0x70004c779cull,
     {0x70021b8ef0ull, 0x70021b8f08ull, 0x70021b8f20ull, 0x70021b8f38ull, 0x70021b8fc8ull, 0x70021b8fe0ull,
      0x70021b8ff8ull, 0x70021b9010ull, 0x70021b7ba8ull, 0x70021b7de0ull, 0x70021b7fb8ull},
     {0x7000bd06acull, 0x7000bd085cull, 0x7000bd09f8ull, 0x7000bd0bc4ull, 0x7000bd1da0ull, 0x7000bd2004ull,
      0x7000bd2240ull, 0x7000bd23a4ull, 0x7000bbf5d0ull, 0x7000bc0368ull, 0x7000bc4d7cull}},
    {"1.0.20", 0x7000de7c28ull, 0x700045c724ull, 0x700217e580ull, 0x70004c77bcull,
     {0x70021b9f58ull, 0x70021b9f70ull, 0x70021b9f88ull, 0x70021b9fa0ull, 0x70021ba030ull, 0x70021ba048ull,
      0x70021ba060ull, 0x70021ba078ull, 0x70021b8c10ull, 0x70021b8e48ull, 0x70021b9020ull},
     {0x7000bd1a4cull, 0x7000bd1bfcull, 0x7000bd1d98ull, 0x7000bd1f64ull, 0x7000bd3140ull, 0x7000bd33a4ull,
      0x7000bd35e0ull, 0x7000bd3744ull, 0x7000bc0970ull, 0x7000bc1708ull, 0x7000bc611cull}},
};
static const char *const k_names[NBUY] = {
    "<rtts autosave 0>", "<rtts autosave 1>", "<rtts autosave 2>", "<rtts autosave 3>",
    "<rtts autosave 4>", "<rtts autosave 5>", "<rtts autosave 6>", "<rtts autosave 7>",
    "<rtts autosave 8>", "<rtts autosave 9>", "<rtts autosave 10>"};
#define TOKENS 0x12c0u

static int g_build = -1;
static uint64_t g_hook[NBUY], g_screen_hook, g_screen_prev;
static uint64_t g_record;   // f_700045c704's out argument (guest addresses are host addresses in this port)
// All with __atomic: the commands and the screen function are thought to run on the same UI thread [H], not shown.
// g_making is set on the thread that logs the screen's line, which in every run logged it before that screen's
// commands and screen function ran.
static int g_pending;          // a save is wanted
static int g_in_cmd;           // wrapped commands running
static int g_screen_in_cmd;    // the screen changed while one ran
static int g_making;           // a new player is being made (BpCreation entered, the home screen not yet)
static int g_installed;        // every slot holds its hook

static uint64_t rd64(uint64_t a) { return a && mem_guest_readable(a, 8) ? *(const uint64_t *)(uintptr_t)a : 0; }

// The player's tokens, or -1 when there is no Road to the Show player.
static int tokens(Cpu *c) {
    g_record = 0;
    if (!(rt_call(c, k_builds[g_build].get_record, 1, (uint64_t)(uintptr_t)&g_record) & 1)) return -1;
    if (!g_record || !mem_guest_readable(g_record + TOKENS, 2)) return -1;
    return *(const uint16_t *)(uintptr_t)(g_record + TOKENS);
}

// The game's career autosave, with every register as it was before.
static void autosave(Cpu *c, const char *when) {
    uint64_t x[31];
    __uint128_t v[32];
    memcpy(x, c->x, sizeof x);
    memcpy(v, c->v, sizeof v);
    rt_log("rtts autosave: %s; running the game's career autosave (it makes its own checks)", when);
    rt_call(c, k_builds[g_build].autosave, 0);
    memcpy(c->x, x, sizeof x);
    memcpy(c->v, v, sizeof v);
}

// A purchase or refund command: run it, then note that a save is wanted.
static void buy_hook(Cpu *c) {
    int i = 0;
    while (i < NBUY && g_hook[i] != c->pc) i++;
    if (i == NBUY) rt_fatal("rtts autosave: entered at %#llx, not one of its slots", (unsigned long long)c->pc);
    // Reading the tokens calls into the game: the command gets every register as its caller left it, and its caller
    // gets them as the command left them.
    uint64_t x[31];
    __uint128_t v[32];
    memcpy(x, c->x, sizeof x);
    memcpy(v, c->v, sizeof v);
    int before = i >= 8 ? tokens(c) : 0;
    memcpy(c->x, x, sizeof x);
    memcpy(c->v, v, sizeof v);
    __atomic_add_fetch(&g_in_cmd, 1, __ATOMIC_ACQ_REL);
    rt_call(c, k_builds[g_build].fn[i], 8, x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7]);
    int still = __atomic_sub_fetch(&g_in_cmd, 1, __ATOMIC_ACQ_REL);
    memcpy(x, c->x, sizeof x);
    memcpy(v, c->v, sizeof v);
    int after = i >= 8 ? tokens(c) : 0;
    if (!__atomic_load_n(&g_making, __ATOMIC_ACQUIRE) && (i < 8 || (before >= 0 && after >= 0 && after != before))) {
        if (!__atomic_exchange_n(&g_pending, 1, __ATOMIC_ACQ_REL))
            rt_log("rtts autosave: an upgrade command ran; the career is saved when this screen is left");
    }
    if (!still && __atomic_exchange_n(&g_screen_in_cmd, 0, __ATOMIC_ACQ_REL)) {
        if (__atomic_exchange_n(&g_pending, 0, __ATOMIC_ACQ_REL)) autosave(c, "the screen changed during that command");
    }
    memcpy(c->x, x, sizeof x);
    memcpy(c->v, v, sizeof v);
}

// A screen change: run what the slot held (three arguments, no result), then save if an upgrade is waiting.
static void screen_hook(Cpu *c) {
    uint64_t r = rt_call(c, g_screen_prev, 8, c->x[0], c->x[1], c->x[2], c->x[3], c->x[4], c->x[5], c->x[6], c->x[7]);
    if (__atomic_load_n(&g_in_cmd, __ATOMIC_ACQUIRE))
        __atomic_store_n(&g_screen_in_cmd, 1, __ATOMIC_RELEASE);   // buy_hook saves once the command has returned
    else if (__atomic_exchange_n(&g_pending, 0, __ATOMIC_ACQ_REL)) autosave(c, "screen left after an upgrade command");
    c->x[0] = r;
}

// services.c: every log line of the game. "uiEngine: Entering screen: [TitleLoadingScreen->BpCreation (4)]" starts
// making a new player, "...->RttSHomeMain (19)" (the Road to the Show home) ends it.
void rtts_autosave_game_log(const char *text, int n) {
    static const char pre[] = "uiEngine: Entering screen: [";
    enum { PRE = sizeof pre - 1 };
    if (!__atomic_load_n(&g_installed, __ATOMIC_ACQUIRE) || n <= PRE || memcmp(text, pre, PRE)) return;
    const char *s = text + PRE, *end = text + n;
    while (s + 1 < end && !(s[0] == '-' && s[1] == '>')) s++;
    if (s + 1 >= end) return;
    s += 2;
    int k = 0;
    while (s + k < end && s[k] != ' ' && s[k] != ']') k++;
    int making;
    if (k == 10 && !memcmp(s, "BpCreation", 10)) making = 1;
    else if (k == 12 && !memcmp(s, "RttSHomeMain", 12)) making = 0;
    else return;
    if (making) __atomic_store_n(&g_pending, 0, __ATOMIC_RELEASE);
    if (__atomic_exchange_n(&g_making, making, __ATOMIC_ACQ_REL) != making)
        rt_log(making ? "rtts autosave: a new player is being made; no autosave until Road to the Show's home opens"
                      : "rtts autosave: Road to the Show's home opened; upgrades are saved again");
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

// boot.c: after the modules are loaded and after tutorials_apply, before hostfn_seal.
void rtts_autosave_apply(void) {
    if (!cfg_bool("MLB_RTTS_AUTOSAVE")) return;
    for (int b = 0; b < (int)(sizeof k_builds / sizeof *k_builds); b++)
        if (!strcmp(rt_game_build, k_builds[b].build)) g_build = b;
    if (g_build < 0) {
        rt_log("rtts autosave: no addresses for game %s; upgrades are saved as the game does it", rt_game_build);
        return;
    }
    for (int i = 0; i < NBUY; i++) {
        uint64_t want = k_builds[g_build].fn[i], have = rd64(k_builds[g_build].slot[i]);
        if (have != want) {
            rt_log("rtts autosave: slot %#llx holds %#llx, not %#llx; upgrades are saved as the game does it",
                   (unsigned long long)k_builds[g_build].slot[i], (unsigned long long)have, (unsigned long long)want);
            return;
        }
    }
    // The screen slot holds the game's function, or tutorials.c's host function when that is on.
    g_screen_prev = rd64(k_builds[g_build].screen_slot);
    if (g_screen_prev != k_builds[g_build].screen_fn && !hostfn_name(g_screen_prev)) {
        rt_log("rtts autosave: slot %#llx holds %#llx; upgrades are saved as the game does it",
               (unsigned long long)k_builds[g_build].screen_slot, (unsigned long long)g_screen_prev);
        return;
    }
    g_screen_hook = hostfn_register("<rtts autosave screen>", screen_hook);
    if (!poke64(k_builds[g_build].screen_slot, g_screen_hook)) {
        rt_log("rtts autosave: could not write slot %#llx; upgrades are saved as the game does it",
               (unsigned long long)k_builds[g_build].screen_slot);
        return;
    }
    for (int i = 0; i < NBUY; i++) {
        g_hook[i] = hostfn_register(k_names[i], buy_hook);
        if (!poke64(k_builds[g_build].slot[i], g_hook[i])) {
            for (int j = 0; j < i; j++) poke64(k_builds[g_build].slot[j], k_builds[g_build].fn[j]);
            poke64(k_builds[g_build].screen_slot, g_screen_prev);
            rt_log("rtts autosave: could not write slot %#llx; upgrades are saved as the game does it",
                   (unsigned long long)k_builds[g_build].slot[i]);
            return;
        }
    }
    __atomic_store_n(&g_installed, 1, __ATOMIC_RELEASE);
    rt_log("rtts autosave: upgrades bought in Road to the Show are saved when their screen is left");
}
