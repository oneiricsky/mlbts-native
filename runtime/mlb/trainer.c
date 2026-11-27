// Trainer rules (trainer.h). Requests are only recorded; trainer_tick, on the present thread, applies them.
// The inning jump is tools/scenario.py's method: writing the half-inning counter mid-play leaves the old team batting,
// so it writes (target - 1) with 2 outs and lets the game make the next out and the change of sides itself. One change
// of sides flips the batting side once, so a target whose parity differs from the batting side needs one natural
// change first.
#include "trainer.h"

#include <stdio.h>
#include <string.h>

#include "host.h"
#include "platform/platform.h"
#include "trainer_ratings.h"

#define SETTLE_NS 2500000000ull   // after a change of sides, before the next write (scenario.py)
#define GONE_NS 10000000000ull    // unreadable this long means the match is over; transitions blink for less
#define ALL ((1u << TR_FIELD_COUNT) - 1)
#define BIT(f) (1u << (f))

enum { J_IDLE, J_START, J_EXTRA_WAIT, J_EXTRA_SETTLE, J_MAIN_WAIT, J_MAIN_SETTLE };

static const char *const k_names[TR_FIELD_COUNT] = {"away", "home", "balls", "strikes", "outs", "half"};
static const char *const k_cheats[TR_CHEATS] = {"contact", "homer", "miss", "aim", "strike", "wild"};
static const char *const k_cheat_names[TR_CHEATS] = {"Always contact", "Always home run", "Batters miss",
                                                     "Perfect control", "Called strike", "Wild throws"};

static PlatMutex g_lock = PLAT_MUTEX_INIT;
static int g_managing;   // Quick Manage is open (set from the game's log, any thread)
static int g_live;       // a batted ball is in play (the same)
static int g_energy[2];   // [mine or theirs]: TR_ENERGY_*, remembered across matches and starts
static int g_scale_percent = 100;   // read by the frame-step hook without the lock
static char g_path[600];
static struct {
    int enabled, visible, slot, confirmed, needs_confirm;
    TrStatus status;
    TrCount now;
    uint64_t gone_since;
    int over;   // match_over has run for this gap: players seen since belong to the next match
    int used[TR_SLOTS];
    TrCount slots[TR_SLOTS];
    unsigned set_mask;   // requested writes
    TrCount set;
    unsigned check_mask;   // written last tick: to read back
    TrCount check;
    int save_slot, load_slot;   // -1 none
    int jump, target, from;
    uint64_t until;
    unsigned after_mask;   // written when the jump arrives
    TrCount after;
    char message[96];
    uint64_t pitcher_ptr;   // the state the last pitch was computed from; 0 before one
    int has_pitcher, has_hit;
    unsigned hits;
    int speed, slow;   // percent; 0 means unset (full, and 50)
    int ratings_blocked, user_side;
    uint64_t roles[2];   // the pitcher object last seen on the away and home side
    unsigned refill;     // bit per who
    int cheat[TR_CHEATS];   // sides, a bit per who
    uint32_t random;
    TrPitcher pitcher;
    TrHit hit;
} g = {.save_slot = -1, .load_slot = -1, .status = TR_NO_MATCH};

static void message(const char *text) {
    snprintf(g.message, sizeof g.message, "%s", text);
    if (*text) rt_log("trainer: %s", text);
}

// The factor is 1 unless the trainer is on and a match is being read: menus and loading run at full speed.
static void publish_speed(void) {
    int percent = g.enabled && g.status == TR_OK && g.speed ? g.speed : 100;
    __atomic_store_n(&g_scale_percent, percent, __ATOMIC_RELAXED);
}

// What has been asked for and not yet done.
static void drop_requests(void) {
    g.refill = 0;
    g.set_mask = g.check_mask = g.after_mask = 0;
    g.save_slot = g.load_slot = -1;
    g.jump = J_IDLE;
    g.needs_confirm = 0;
}

static void drop_pending(void) {
    g.set_mask = g.check_mask = g.after_mask = 0;
    g.save_slot = g.load_slot = -1;
    g.jump = J_IDLE;
    g.needs_confirm = 0;
}

static void cheats_clear(void) { memset(g.cheat, 0, sizeof g.cheat); }

// The match is over: the confirmation and what was seen go with it.
static void match_over(void) {
    drop_pending();
    g.confirmed = 0;
    g.pitcher_ptr = 0, g.has_pitcher = 0, g.has_hit = 0, g.hits = 0;
    g.speed = 0;
    g.roles[0] = g.roles[1] = 0;
    cheats_clear();
    trainer_ratings_match_over();
    __atomic_store_n(&g_managing, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&g_live, 0, __ATOMIC_RELAXED);
}

static int slot_ok(const TrCount *c) {
    for (int f = 0; f < TR_FIELD_COUNT; f++)
        if (!tr_write_range_ok((TrField)f, c->v[f])) return 0;
    return 1;
}

static void slots_read(void) {
    memset(g.used, 0, sizeof g.used);
    FILE *f = fopen(g_path, "rb");
    if (!f) return;
    char line[128];
    while (fgets(line, sizeof line, f)) {
        int n;
        TrCount c;
        trainer_ratings_load_line(line);
        int who, level;
        if (sscanf(line, "energy %d %d", &who, &level) == 2 && who >= 0 && who <= 1 && level >= 0 &&
            level < TR_ENERGY_LEVELS)
            g_energy[who] = level;
        if (sscanf(line, "slot %d %d %d %d %d %d %d", &n, &c.v[TR_AWAY_SCORE], &c.v[TR_HOME_SCORE], &c.v[TR_BALLS],
                   &c.v[TR_STRIKES], &c.v[TR_OUTS], &c.v[TR_HALF]) != 7 || n < 1 || n > TR_SLOTS || !slot_ok(&c))
            continue;
        g.slots[n - 1] = c, g.used[n - 1] = 1;
    }
    fclose(f);
}

static void slots_write(void) {
    FILE *f = fopen(g_path, "wb");
    if (!f) {
        message("Could not write trainer.txt; the slot lasts until the game closes.");
        return;
    }
    for (int n = 0; n < TR_SLOTS; n++) {
        const int *v = g.slots[n].v;
        if (g.used[n])
            fprintf(f, "slot %d %d %d %d %d %d %d\n", n + 1, v[TR_AWAY_SCORE], v[TR_HOME_SCORE], v[TR_BALLS],
                    v[TR_STRIKES], v[TR_OUTS], v[TR_HALF]);
    }
    trainer_ratings_save(f);
    for (int who = 0; who < 2; who++)
        if (g_energy[who]) fprintf(f, "energy %d %d\n", who, g_energy[who]);
    fclose(f);
}

void trainer_init(const char *profile_dir) {
    plat_mutex_lock(&g_lock);
    snprintf(g_path, sizeof g_path, "%s/trainer.txt", profile_dir);
    match_over();
    g.gone_since = 0;
    g.status = TR_NO_MATCH;
    g.message[0] = 0;
    trainer_ratings_reset();
    g_energy[0] = g_energy[1] = TR_ENERGY_NORMAL;
    slots_read();
    plat_mutex_unlock(&g_lock);
}

void trainer_set_enabled(int on) {
    plat_mutex_lock(&g_lock);
    g.enabled = on != 0;
    if (!g.enabled) {
        trainer_ratings_apply(0);   // the game's own values go back
        g.visible = 0;
        g.confirmed = 0;
        drop_pending();
        cheats_clear();
        g.speed = 0;
        g.status = TR_NO_MATCH;
    }
    publish_speed();
    plat_mutex_unlock(&g_lock);
}

// A request is dropped while the trainer is off.
#define REQUEST(body)                  \
    do {                               \
        plat_mutex_lock(&g_lock);      \
        if (g.enabled) {               \
            body;                      \
        }                              \
        plat_mutex_unlock(&g_lock);    \
    } while (0)

void trainer_set(TrField f, int value) {
    if (!tr_write_range_ok(f, value)) return;
    REQUEST(g.set.v[f] = value; g.set_mask |= BIT(f));
}

void trainer_slot_select(int slot) {
    if (slot >= 0 && slot < TR_SLOTS) REQUEST(g.slot = slot);
}

void trainer_slot_save(int slot) {
    if (slot >= 0 && slot < TR_SLOTS) REQUEST(g.save_slot = slot);
}

void trainer_slot_load(int slot) {
    if (slot >= 0 && slot < TR_SLOTS) REQUEST(g.load_slot = slot);
}

void trainer_jump(int half_index) {
    if (!tr_write_range_ok(TR_HALF, half_index)) return;
    REQUEST(g.target = half_index; g.after_mask = 0; g.jump = J_START);
}

void trainer_cancel(void) {
    REQUEST(g.jump = J_IDLE; g.after_mask = 0; message("Cancelled."));
}

void trainer_confirm(int yes) {
    REQUEST(if (g.needs_confirm) {
        g.needs_confirm = 0;
        if (yes) g.confirmed = 1;
        else {
            drop_pending();
            cheats_clear();
        }
    });
}

// What the Match page shows, for comparing with the game's scoreboard after a report that they differ.
static void log_count(const char *when) {
    const int *v = g.now.v;
    rt_log("trainer: %s: %s away %d home %d balls %d strikes %d outs %d half %d", when, tr_status_text(g.status),
           v[TR_AWAY_SCORE], v[TR_HOME_SCORE], v[TR_BALLS], v[TR_STRIKES], v[TR_OUTS], v[TR_HALF]);
}

void trainer_toggle(void) {
    REQUEST(g.visible = !g.visible; rt_log("trainer: panel %s", g.visible ? "up" : "down");
            if (g.visible) log_count("panel shows"));
}

// Where `part` ends in the line, or -1. A message may begin with blank lines.
static int after(const char *text, int n, const char *part) {
    int m = (int)strlen(part);
    for (int i = 0; i + m <= n; i++)
        if (!memcmp(text + i, part, (size_t)m)) return i + m;
    return -1;
}

// The in-play state logs IN_PITCH, POST_PITCH (a take), IN_PLAY (from contact) and PLAY_OVER.
static void play_log(const char *text, int n) {
    int at = after(text, n, "GAME_STATE_IN_PLAY: state = ");
    if (at >= 0)
        __atomic_store_n(&g_live, n - at >= 7 && !memcmp(text + at, "IN_PLAY", 7), __ATOMIC_RELAXED);
    else if (after(text, n, "FLOW STATE EXIT: GAME_STATE_IN_PLAY") >= 0)
        __atomic_store_n(&g_live, 0, __ATOMIC_RELAXED);
}

void trainer_game_log(const char *text, int n) {
    play_log(text, n);
    static const char pre[] = "uiEngine: Entering screen: [";
    enum { PRE = sizeof pre - 1 };
    if (n <= PRE || memcmp(text, pre, PRE)) return;
    for (int i = PRE; i + 2 < n; i++) {
        if (text[i] != '-' || text[i + 1] != '>') continue;
        const char *screen = text + i + 2;
        int left = n - i - 2;
        if (left > 18 && !memcmp(screen, "SportscastManager ", 18))
            __atomic_store_n(&g_managing, 1, __ATOMIC_RELAXED);
        else if (left > 9 && !memcmp(screen, "Scorebar ", 9))
            __atomic_store_n(&g_managing, 0, __ATOMIC_RELAXED);
        return;
    }
}

void trainer_menu_opened(void) {
    REQUEST(if (g.visible) rt_log("trainer: panel down (settings menu)"); g.visible = 0);
}

int trainer_visible(void) { return __atomic_load_n(&g.visible, __ATOMIC_RELAXED); }

static void write_fields(unsigned mask, const TrCount *c) {
    for (int f = 0; f < TR_FIELD_COUNT; f++) {
        if (!(mask & BIT(f))) continue;
        TrStatus s = tr_count_write((TrField)f, c->v[f]);
        if (s == TR_OK) g.check.v[f] = c->v[f], g.check_mask |= BIT(f);
        else rt_log("trainer: %s = %d not written: %s", k_names[f], c->v[f], tr_status_text(s));
    }
}

static void write_one(TrField f, int value) {
    TrCount c = {{0}};
    c.v[f] = value;
    write_fields(BIT(f), &c);
}

static void start_load(int slot) {
    if (!g.used[slot]) {
        message("That slot is empty.");
        return;
    }
    const TrCount *s = &g.slots[slot];
    unsigned rest = ALL & ~BIT(TR_HALF);
    g.jump = J_IDLE, g.after_mask = 0;
    message("");
    if (s->v[TR_HALF] > g.now.v[TR_HALF]) {
        for (int f = TR_AWAY_SCORE; f <= TR_HOME_SCORE; f++) g.set.v[f] = s->v[f], g.set_mask |= BIT(f);
        g.after = *s, g.after_mask = rest;
        g.target = s->v[TR_HALF], g.jump = J_START;
        return;
    }
    for (int f = 0; f < TR_FIELD_COUNT; f++)
        if (rest & BIT(f)) g.set.v[f] = s->v[f], g.set_mask |= BIT(f);
    if (s->v[TR_HALF] < g.now.v[TR_HALF]) message("Inning not restored: the game cannot go back.");
}

static void jump_arrived(void) {
    write_fields(g.after_mask, &g.after);
    g.after_mask = 0;
    g.jump = J_IDLE;
    message("");
}

static void jump_step(uint64_t now) {
    int cur = g.now.v[TR_HALF];
    switch (g.jump) {
    case J_START: {
        if (g.target < cur) {
            g.jump = J_IDLE, g.after_mask = 0;
            message("The game cannot go back an inning.");
            return;
        }
        if (g.target == cur) {
            jump_arrived();
            return;
        }
        message("Waiting for the next out.");
        int side = tr_batting_side();
        if (side >= 0 && g.target % 2 != side) {
            write_one(TR_OUTS, 2);
            g.from = cur, g.jump = J_EXTRA_WAIT;
            return;
        }
        goto main_start;
    }
    case J_EXTRA_SETTLE:
        if (now < g.until) return;
    /* fall through */
    main_start:
        if (g.target > cur) {
            write_one(TR_HALF, g.target - 1);
            write_one(TR_OUTS, 2);
            g.jump = J_MAIN_WAIT;
        } else {
            g.until = now, g.jump = J_MAIN_SETTLE;
        }
        return;
    case J_EXTRA_WAIT:
        if (cur != g.from) g.until = now + SETTLE_NS, g.jump = J_EXTRA_SETTLE;
        return;
    case J_MAIN_WAIT:
        if (cur >= g.target) g.until = now + SETTLE_NS, g.jump = J_MAIN_SETTLE;
        return;
    case J_MAIN_SETTLE:
        if (now >= g.until) jump_arrived();
        return;
    }
}

// 1 Season, 3 Franchise, 4 Road to the Show: the match's result goes into the save.
static int saved_mode(void) {
    int mode = tr_game_mode();
    return mode == 1 || mode == 3 || mode == 4;
}

// The held levels and single refills, written to each side's pitcher object.
static void energy_apply(void) {
    static const float level_value[TR_ENERGY_LEVELS] = {0, 255, 64};
    for (int side = 0; side < 2; side++) {
        if (!g.roles[side]) continue;
        int who = g.user_side < 0 ? side : side == g.user_side ? TR_MINE : TR_THEIRS;
        float want = g.refill & BIT(who) ? 255.0f : level_value[g_energy[who]], now;
        int id;
        if (!(g.refill & BIT(who)) && g_energy[who] == TR_ENERGY_NORMAL) continue;
        if (tr_energy_read(g.roles[side], &now, &id) == TR_OK && now != want) tr_energy_write(g.roles[side], want);
    }
}

static void tick_locked(uint64_t now) {
    TrCount c;
    TrStatus s = tr_count_read(&c);
    // Quick Manage: the data reads well but is frozen
    if (s == TR_OK && __atomic_load_n(&g_managing, __ATOMIC_RELAXED)) s = TR_MANAGING;
    if (s != g.status) rt_log("trainer: %s", tr_status_text(s));
    g.status = s;
    if (s == TR_MANAGING) {   // nothing is read from or written to the frozen data
        g.gone_since = 0;
        drop_requests();
        return;
    }
    if (s != TR_OK) {   // nothing is written; the requests wait out a transition, then go
        if (!g.gone_since) g.gone_since = now;
        else if (now - g.gone_since >= GONE_NS) match_over(), g.over = 1, g.message[0] = 0;
        return;
    }
    if (g.gone_since && !g.over && now - g.gone_since >= GONE_NS) match_over();
    g.gone_since = 0, g.over = 0;
    int new_half = c.v[TR_HALF] != g.now.v[TR_HALF];
    g.now = c;
    if (new_half) log_count("half-inning");
    for (int f = 0; f < TR_FIELD_COUNT; f++)
        if (g.check_mask & BIT(f))
            rt_log("trainer: %s = %d, read back %d", k_names[f], g.check.v[f], c.v[f]);
    g.check_mask = 0;
    if (g.save_slot >= 0) {
        if (slot_ok(&c)) {
            g.slots[g.save_slot] = c, g.used[g.save_slot] = 1;
            rt_log("trainer: slot %d saved", g.save_slot + 1);
            message("Saved.");
            slots_write();
        } else {
            message("Cannot save during a change of sides or batters.");
        }
        g.save_slot = -1;
    }
    g.has_pitcher = g.pitcher_ptr && tr_pitcher_read(g.pitcher_ptr, &g.pitcher) == TR_OK;
    g.ratings_blocked = saved_mode();
    int user = tr_user_side();
    if (user != g.user_side) rt_log("trainer: your side: %s", user < 0 ? "none" : user ? "home" : "away");
    g.user_side = user;
    trainer_ratings_apply(!g.ratings_blocked);
    if (trainer_ratings_take_dirty()) slots_write();
    if (!g.ratings_blocked) energy_apply();
    g.refill = 0;
    int cheating = 0;
    for (int k = 0; k < TR_CHEATS; k++) cheating |= g.cheat[k];
    if (!cheating && !g.set_mask && g.load_slot < 0 && g.jump == J_IDLE) return;
    if (!g.confirmed && saved_mode()) {
        g.needs_confirm = 1;
        return;
    }
    if (g.load_slot >= 0) {
        int slot = g.load_slot;
        g.load_slot = -1;
        start_load(slot);
    }
    if (g.set_mask) {
        write_fields(g.set_mask, &g.set);
        g.set_mask = 0;
    }
    if (g.jump != J_IDLE) jump_step(now);
}

static int speed_ok(int percent) { return percent == 100 || percent == 75 || percent == 50 || percent == 25; }

static void speed_locked(int percent) {
    g.speed = percent;
    if (percent != 100) g.slow = percent;
    publish_speed();
    rt_log("trainer: speed %d%%", percent);
}

void trainer_speed(int percent) {
    if (speed_ok(percent)) REQUEST(speed_locked(percent));
}

void trainer_slow_toggle(void) { REQUEST(speed_locked(g.speed && g.speed != 100 ? 100 : g.slow ? g.slow : 50)); }

float trainer_speed_scale(void) { return __atomic_load_n(&g_scale_percent, __ATOMIC_RELAXED) / 100.0f; }

void trainer_energy(int who, int level) {
    if (who < 0 || who > 1 || level < 0 || level >= TR_ENERGY_LEVELS) return;
    REQUEST(g_energy[who] = level; slots_write(); rt_log("trainer: energy: %s %s", who ? "theirs" : "mine",
            level == TR_ENERGY_NORMAL ? "normal" : level == TR_ENERGY_FULL ? "full" : "tired"));
}

int trainer_energy_level(int who) { return who >= 0 && who <= 1 ? g_energy[who] : TR_ENERGY_NORMAL; }

void trainer_energy_refill(int who) {
    if (who >= 0 && who <= 1) REQUEST(g.refill |= BIT(who); rt_log("trainer: energy: refill %s", who ? "theirs" : "mine"));
}

void trainer_on_role(uint64_t role) {
    plat_mutex_lock(&g_lock);
    float energy;
    int id;
    if (g.enabled && tr_energy_read(role, &energy, &id) == TR_OK) g.roles[id / 40] = role;
    plat_mutex_unlock(&g_lock);
}

void trainer_on_pitch(uint64_t state) {
    plat_mutex_lock(&g_lock);
    TrPitcher p;
    if (g.enabled) {
        g.pitcher_ptr = state;
        if (tr_pitcher_read(state, &p) == TR_OK) {
            rt_log("trainer: pitch stamina %.3f energy %.3f confidence %.1f", p.v[TR_STAMINA], p.v[TR_ENERGY],
                   p.v[TR_CONFIDENCE]);
            g.pitcher = p, g.has_pitcher = 1;
        }
    }
    plat_mutex_unlock(&g_lock);
}

void trainer_on_hit(uint64_t result) {
    plat_mutex_lock(&g_lock);
    TrHit h;
    if (g.enabled && tr_hit_read(result, &h) == TR_OK && h.speed > 0) {
        rt_log("trainer: contact direction %.1f launch %.1f speed %.1f", h.direction, h.launch, h.speed);
        g.hit = h, g.has_hit = 1, g.hits++;
    }
    plat_mutex_unlock(&g_lock);
}

static void cheat_locked(int cheat, int sides) {
    if (g.status != TR_OK) return;
    g.cheat[cheat] = sides;
    if (cheat == TR_CHEAT_MISS) g.cheat[TR_CHEAT_CONTACT] &= ~sides, g.cheat[TR_CHEAT_HOMER] &= ~sides;
    if (cheat == TR_CHEAT_CONTACT || cheat == TR_CHEAT_HOMER) g.cheat[TR_CHEAT_MISS] &= ~sides;
    static const char *const what[4] = {"off", "mine", "theirs", "both"};
    rt_log("trainer: cheat %s: %s", k_cheats[cheat], what[sides]);
}

void trainer_cheat(int cheat, int sides) {
    if (cheat >= 0 && cheat < TR_CHEATS && sides >= 0 && sides <= TR_SIDES_ALL) REQUEST(cheat_locked(cheat, sides));
}

void trainer_cheat_cycle(int cheat) {
    if (cheat >= 0 && cheat < TR_CHEATS) REQUEST(cheat_locked(cheat, (g.cheat[cheat] + 1) & TR_SIDES_ALL));
}

int trainer_cheat_sides(int cheat) {
    return cheat >= 0 && cheat < TR_CHEATS ? __atomic_load_n(&g.cheat[cheat], __ATOMIC_RELAXED) : 0;
}

const char *trainer_cheat_name(int cheat) { return cheat >= 0 && cheat < TR_CHEATS ? k_cheat_names[cheat] : ""; }

// Whether a cheat holds for the team that bats (pitching 0) or pitches (1) now. The batting team is read from the game
// at the call, so a change of sides needs no frame in between.
static int cheat_now(int cheat, int pitching) {
    if (!g.enabled || g.status != TR_OK || !g.cheat[cheat] || __atomic_load_n(&g_managing, __ATOMIC_RELAXED)) return 0;
    if (!g.confirmed && saved_mode()) return 0;
    int side = tr_batting_team();
    if (side < 0) return 0;
    side ^= pitching;
    int user = tr_user_side();
    int who = user < 0 ? side : side == user ? TR_MINE : TR_THEIRS;
    return (g.cheat[cheat] >> who) & 1;
}

static int cheat_asked(int cheat, int pitching) {
    plat_mutex_lock(&g_lock);
    int on = cheat_now(cheat, pitching);
    plat_mutex_unlock(&g_lock);
    return on;
}

int trainer_swing_misses(void) { return cheat_asked(TR_CHEAT_MISS, 0); }
int trainer_pitch_centered(void) { return cheat_asked(TR_CHEAT_AIM, 1); }
int trainer_strike_called(void) { return cheat_asked(TR_CHEAT_STRIKE, 1); }
int trainer_throw_wild(void) {
    return __atomic_load_n(&g_live, __ATOMIC_RELAXED) && cheat_asked(TR_CHEAT_WILD, 1);
}

static float between(float lo, float hi) {
    g.random = g.random ? g.random : 2463534242u;
    g.random ^= g.random << 13, g.random ^= g.random >> 17, g.random ^= g.random << 5;
    return lo + (hi - lo) * (float)(g.random >> 8) / 16777216.0f;
}

// A home run: toward the middle of the field, high and hard enough for any park. Contact after a miss: a fair ball
// from a grounder to a shallow fly, hit softly to fairly well.
int trainer_force_swing(int missed, TrForced *out) {
    plat_mutex_lock(&g_lock);
    int contact = cheat_now(TR_CHEAT_CONTACT, 0);
    int force = 0;
    if (cheat_now(TR_CHEAT_HOMER, 0) && (!missed || contact)) {
        float azimuth = between(-25, 25), launch = between(27, 31);
        *out = (TrForced){azimuth, launch, between(110, 114)};
        force = 1;
    } else if (missed && contact) {
        float azimuth = between(-35, 35), launch = between(-2, 22);
        *out = (TrForced){azimuth, launch, between(62, 88)};
        force = 1;
    }
    plat_mutex_unlock(&g_lock);
    return force;
}

void trainer_tick(uint64_t now_ns) {
    plat_mutex_lock(&g_lock);
    if (g.enabled) tick_locked(now_ns);
    publish_speed();
    plat_mutex_unlock(&g_lock);
}

void trainer_view(TrView *out) {
    plat_mutex_lock(&g_lock);
    *out = (TrView){.status = g.status, .now = g.now, .enabled = g.enabled, .visible = g.visible,
                    .jumping = g.jump != J_IDLE, .jump_target = g.target, .needs_confirm = g.needs_confirm,
                    .slot = g.slot, .has_pitcher = g.has_pitcher, .has_hit = g.has_hit,
                    .speed = g.speed ? g.speed : 100, .ratings_blocked = g.ratings_blocked, .user_side = g.user_side,
                    .hits = g.hits, .pitcher = g.pitcher, .hit = g.hit};
    memcpy(out->used, g.used, sizeof out->used);
    memcpy(out->slots, g.slots, sizeof out->slots);
    memcpy(out->message, g.message, sizeof out->message);
    plat_mutex_unlock(&g_lock);
}

static int fkey(const char *name) {
    return name && name[0] == 'F' && name[1] >= '2' && name[1] <= '7' && !name[2] ? 0x70 + name[1] - '1' : 0;
}

int trainer_keys(const char *show, const char *save, const char *load, const char *slow, int vk[4]) {
    int a = fkey(show), b = fkey(save), c = fkey(load), d = fkey(slow);
    if (a && b && c && d && a != b && a != c && a != d && b != c && b != d && c != d) {
        vk[0] = a, vk[1] = b, vk[2] = c, vk[3] = d;
        return 1;
    }
    vk[0] = 0x71, vk[1] = 0x72, vk[2] = 0x73, vk[3] = 0x75;   // F2, F3, F4, F6
    return 0;
}

int trainer_cheat_key(const char *name) {
    static const struct { const char *name; int vk; } keys[] = {
        {"5", '5'}, {"6", '6'}, {"7", '7'}, {"8", '8'}, {"9", '9'}, {"0", '0'}, {"Insert", 0x2d}, {"Delete", 0x2e},
        {"Home", 0x24}, {"End", 0x23}, {"PageUp", 0x21}, {"PageDown", 0x22},
    };
    for (size_t i = 0; name && i < sizeof keys / sizeof *keys; i++)
        if (!strcmp(name, keys[i].name)) return keys[i].vk;
    return 0;
}

int trainer_takes_key(int system_key, int auto_repeat) { return !system_key && !auto_repeat; }

int trainer_command(const char *cmd) {
    int who, held;
    if (sscanf(cmd, "energy %d %d", &who, &held) == 2) {
        if (who < 0 || who > 1 || held < 0 || held >= TR_ENERGY_LEVELS) return 0;
        trainer_energy(who, held);
        return 1;
    }
    int side, group, level;
    if (sscanf(cmd, "ratings %d %d %d", &side, &group, &level) == 3) {
        if (side < 0 || side > 1 || group < 0 || group >= TR_GROUPS || level < 0 || level >= TR_LEVELS) return 0;
        trainer_ratings_preset(side, group, level);
        return 1;
    }
    char word[16] = "", arg[16] = "";
    int n = 0, got = sscanf(cmd, "%15s %15s %d", word, arg, &n);
    if (got < 1) return 0;
    if (!strcmp(word, "cheat")) {
        for (int k = 0; got == 3 && k < TR_CHEATS; k++)
            if (!strcmp(arg, k_cheats[k]) && n >= 0 && n <= TR_SIDES_ALL) {
                trainer_cheat(k, n);
                return 1;
            }
        return 0;
    }
    if (!strcmp(word, "show") || !strcmp(word, "hide")) {
        if (trainer_visible() != (word[0] == 's')) trainer_toggle();
        return 1;
    }
    if (!strcmp(word, "confirm")) {
        trainer_confirm(1);
        return 1;
    }
    if (!strcmp(word, "cancel")) {
        trainer_cancel();
        return 1;
    }
    if (!strcmp(word, "set") && got == 3) {
        for (int f = 0; f < TR_FIELD_COUNT; f++)
            if (!strcmp(arg, k_names[f]) && tr_write_range_ok((TrField)f, n)) {
                trainer_set((TrField)f, n);
                return 1;
            }
        return 0;
    }
    int value;
    if (got < 2 || sscanf(arg, "%d", &value) != 1) return 0;
    if (!strcmp(word, "jump") && tr_write_range_ok(TR_HALF, value)) {
        trainer_jump(value);
        return 1;
    }
    if (!strcmp(word, "speed") && speed_ok(value)) {
        trainer_speed(value);
        return 1;
    }
    if (value < 1 || value > TR_SLOTS) return 0;
    if (!strcmp(word, "save")) {
        trainer_slot_save(value - 1);
        return 1;
    }
    if (!strcmp(word, "load")) {
        trainer_slot_load(value - 1);
        return 1;
    }
    return 0;
}
