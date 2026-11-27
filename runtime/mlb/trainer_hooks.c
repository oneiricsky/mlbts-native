// Trainer hooks, game 1.0.20. The generator replaced a call at each patch site with a call to a word of the patch page
// (patches-1.0.20.txt); dispatch finds the host function registered there. It runs on the game's own thread, calls the
// function the site would have called, and hands the pointers to the rules (trainer.c). No recompiler change.
#include "trainer_hooks.h"

#include <string.h>

#include "cpu.h"
#include "dispatch.h"
#include "host.h"
#include "trainer.h"
#include "trainer_ratings.h"

#define HOOK_CONTACT 0x800   // offsets into the patch page, as encoded in the patch file's bl words
#define HOOK_PITCH 0x810
#define HOOK_STEP 0x820
#define HOOK_SWING 0x830
#define HOOK_AIM 0x840
#define HOOK_CALL 0x850
#define HOOK_WILD 0x860
#define HOOK_KEEP 0x890
#define FN_CONTACT 0x7001679cdcull
#define FN_PITCH 0x70002e9dc4ull
#define FN_SWING 0x700167fe28ull            // the swing's hit type; s0 is its timing, 0 early edge to 1 late edge
#define FN_AIM 0x7000247214ull              // places the pitch: aim, miss and result in its first argument
#define FN_PLACE 0x7000249cc8ull            // the step of it that adds the miss to the aim
#define FN_ZONE 0x7001687dd8ull             // 1 when the pitch was in the strike zone
#define FN_WILD 0x700038a4c0ull              // as a fielder sets up a throw: 1 when it is to be a wild one
#define FN_PLAN 0x7000378c64ull              // takes a throw plan on; x3 is the plan
#define PLAN_CLEAN 0x32                      // bytes of it: 1 to throw cleanly after all,
#define PLAN_BAD 0x33                        // and its opposite, 1 for the bad throw
#define MISS_EARLY 0
#define MISS_LATE 16
#define FN_PLAYER 0x700181a6bcull           // (player table, id) -> player object, whose first word is the record
#define PLAYER_TABLE 0x700227dda0ull
#define FN_STEP 0x700058a9e0ull   // returns the frame step in seconds (s0)

enum { SET_CONTACT, SET_PITCH, SET_SPEED, SET_SWING, SET_AIM, SET_CALL, SET_WILD, SETS };
static const char *const k_sets[SETS] = {"trainer_contact", "trainer_pitch", "trainer_speed", "trainer_swing",
                                         "trainer_aim", "trainer_call", "trainer_wild"};
static int g_set[SETS] = {-1, -1, -1, -1, -1, -1, -1};   // patch set numbers
static int g_ready;

static void call_game(Cpu *c, uint64_t fn) {
    GuestFn f = rt_dispatch_lookup(fn);
    if (!f) rt_fatal("trainer: no game function at %#llx", (unsigned long long)fn);
    f(c);
}

// Every player of the match, by id, through the game's own lookup. On the game's thread, at a pitch; the registers are
// put back, so the caller sees only the pitch's calculation.
static void report_players(Cpu *c) {
    uint64_t table = 0;
    if (!mem_guest_readable(PLAYER_TABLE, 8)) return;
    memcpy(&table, (const void *)(uintptr_t)PLAYER_TABLE, 8);
    if (!table) return;
    Cpu saved = *c;
    for (int id = 0; id < TR_PLAYERS; id++) {
        c->x[0] = table;
        c->x[1] = (uint64_t)id;
        call_game(c, FN_PLAYER);
        uint64_t object = c->x[0], record = 0;
        if (object && mem_guest_readable(object, 8)) memcpy(&record, (const void *)(uintptr_t)object, 8);
        trainer_ratings_seen(id, record);
        *c = saved;
    }
}

// The contact model runs as the game calls it. When a cheat wants another ball, it runs a second time with the
// override block set, which makes the game build that ball itself (trainer_game.c).
static void hook_contact(Cpu *c) {
    uint64_t result = c->x[0], input = c->x[1];
    Cpu before = *c;
    call_game(c, FN_CONTACT);
    TrHit hit;
    TrForced forced;
    uint8_t saved[TR_OVERRIDE_BYTES];
    if (!tr_is_bunt(input) && tr_hit_read(result, &hit) == TR_OK && trainer_force_swing(hit.speed <= 0, &forced) &&
        tr_force_hit(input, &forced, saved) == TR_OK) {
        *c = before;
        call_game(c, FN_CONTACT);
        tr_force_hit_end(input, saved);
        rt_log("trainer: %s swing given azimuth %.1f launch %.1f speed %.1f", hit.speed <= 0 ? "missed" : "hit",
               forced.azimuth, forced.launch, forced.speed);
    }
    trainer_on_hit(result);
}

static void hook_swing(Cpu *c) {
    float timing;
    memcpy(&timing, &c->v[0], 4);
    call_game(c, FN_SWING);
    if (!trainer_swing_misses()) return;
    uint32_t type = (uint32_t)c->x[0];
    c->x[0] = timing > 0.5f ? MISS_LATE : MISS_EARLY;
    rt_log("trainer: swing forced to miss (the game had hit type %u)", type);
}

static void hook_aim(Cpu *c) {
    uint64_t placement = c->x[0], input = c->x[1];
    call_game(c, FN_AIM);
    float miss[3];
    if (!trainer_pitch_centered() || tr_pitch_center(placement, miss) != TR_OK) return;
    // the game places the pitch many times over, mostly with no miss to remove: 3130 of 3143 calls in one match
    if (miss[0] == 0 && miss[1] == 0 && miss[2] == 0) return;
    Cpu after = *c;
    c->x[0] = placement, c->x[1] = input;
    call_game(c, FN_PLACE);
    *c = after;
    rt_log("trainer: pitch placed on the aim point (the miss was %.3f %.3f %.3f)", miss[0], miss[1], miss[2]);
}

static void hook_pitch(Cpu *c) {
    uint64_t state = c->x[2], role = c->x[0];
    call_game(c, FN_PITCH);
    trainer_on_role(role);
    trainer_on_pitch(state);
    report_players(c);
}

// Slow motion: the game steps by the figure this getter returns (framerate.c), so a smaller figure is a slower game at
// the same frame rate.
static void hook_step(Cpu *c) {
    call_game(c, FN_STEP);
    float scale = trainer_speed_scale(), step;
    if (scale == 1.0f) return;
    memcpy(&step, &c->v[0], 4);
    step *= scale;
    memcpy(&c->v[0], &step, 4);
}

static void hook_call(Cpu *c) {
    call_game(c, FN_ZONE);
    if (!trainer_strike_called() || (c->x[0] & 1)) return;
    c->x[0] |= 1;
    rt_log("trainer: pitch out of the zone called a strike");
}

// The game's own question while a fielder sets up a throw. Answered yes, the game makes the wild throw itself: the
// miss, the fielder going after the ball and the error are all its own.
static void hook_wild(Cpu *c) {
    if (!trainer_throw_wild()) {
        call_game(c, FN_WILD);
        return;
    }
    c->x[0] = 1;
    rt_log("trainer: throw made wild");
}

// A wild throw stays one: the game may swap it for a clean throw after all, which the receiver catches.
static void hook_keep(Cpu *c) {
    uint64_t plan = c->x[3];
    if (trainer_throw_wild() && mem_guest_readable(plan + PLAN_CLEAN, 2)) {
        uint8_t *clean = (uint8_t *)(uintptr_t)(plan + PLAN_CLEAN);
        if (*clean) rt_log("trainer: wild throw kept wild");
        *clean = 0;
        *(uint8_t *)(uintptr_t)(plan + PLAN_BAD) = 1;
    }
    call_game(c, FN_PLAN);
}

void trainer_hooks_apply(void) {
    int missing = 0;
    for (int k = 0; k < SETS; k++) missing |= (g_set[k] = rt_patch_set(k_sets[k])) < 0;
    uint8_t *page = rt_patch_page();
    if (missing || !page || strcmp(rt_game_build, "1.0.20")) return;
    static const struct { int at; GuestFn fn; } hooks[] = {
        {HOOK_CONTACT, hook_contact}, {HOOK_PITCH, hook_pitch}, {HOOK_STEP, hook_step},
        {HOOK_SWING, hook_swing},     {HOOK_AIM, hook_aim},     {HOOK_CALL, hook_call},
        {HOOK_WILD, hook_wild},       {HOOK_KEEP, hook_keep},
    };
    for (size_t k = 0; k < sizeof hooks / sizeof *hooks; k++)
        rt_register_host((uint64_t)(uintptr_t)page + hooks[k].at, hooks[k].fn);
    g_ready = 1;
}

int trainer_hooks_available(void) { return g_ready; }

void trainer_hooks_switch(int on) {
    for (int k = 0; k < SETS; k++)   // a build with the sites but no host functions must never take them
        if (g_set[k] >= 0) rt_patch_switch(g_set[k], g_ready && on);
}
