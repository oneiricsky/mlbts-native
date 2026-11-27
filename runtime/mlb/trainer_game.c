// Trainer game access, game 1.0.20. Evidence: tools/scenario.py (live writes) and the mlbts-game-code skill's
// known-functions.md:
//   count object O = *(*(main+0x227e6b8)): u32 +0x8 away, +0xc home, +0x10 balls, +0x14 strikes, +0x18 outs,
//     +0x20 half-inning index
//   batting side   = byte [[*(main+0x3aeb728) + 0x20] + 0x124]
//   game mode      = byte [*(main+0x4651350) + 0x3e + 19]   (settings key 19; the key numbering is inferred)
// Every pointer step is checked: the objects come and go with the match.
#include "trainer_game.h"

#include <math.h>
#include <string.h>

#include "host.h"

static int within(float v, float lo, float hi) { return isfinite(v) && v >= lo && v <= hi; }

static const int k_off[TR_FIELD_COUNT] = {0x8, 0xc, 0x10, 0x14, 0x18, 0x20};
// The game holds 4 balls, 3 strikes and 3 outs for a moment at transitions, so reading allows one more than writing.
static const int k_read_max[TR_FIELD_COUNT] = {99, 99, 4, 3, 3, 199};
static const int k_write_max[TR_FIELD_COUNT] = {99, 99, 3, 2, 2, 199};

static int g_known;
static uint64_t g_count_slot, g_teams_slot, g_settings_slot;

TrStatus tr_game_init(const char *build) {
    g_known = build && !strcmp(build, "1.0.20");
    g_count_slot = 0x700227e6b8ull;
    g_teams_slot = 0x7003aeb728ull;
    g_settings_slot = 0x7004651350ull;
    return g_known ? TR_OK : TR_WRONG_VERSION;
}

void tr_game_set_slots(uint64_t count_slot, uint64_t teams_slot, uint64_t settings_slot) {
    g_count_slot = count_slot, g_teams_slot = teams_slot, g_settings_slot = settings_slot;
}

// The pointer stored at a, or 0 when a is null or unreadable.
static uint64_t ptr_at(uint64_t a) {
    uint64_t v = 0;
    if (a && mem_guest_readable(a, 8)) memcpy(&v, (const void *)(uintptr_t)a, 8);
    return v;
}

static uint64_t count_object(void) {
    uint64_t o = ptr_at(ptr_at(g_count_slot));
    return o && mem_guest_readable(o, 0x24) ? o : 0;
}

static TrStatus read_at(uint64_t o, TrCount *out) {
    for (int f = 0; f < TR_FIELD_COUNT; f++) {
        uint32_t v;
        memcpy(&v, (const void *)(uintptr_t)(o + k_off[f]), 4);
        if (v > (uint32_t)k_read_max[f]) return TR_UNEXPECTED;
        out->v[f] = (int)v;
    }
    return TR_OK;
}

TrStatus tr_count_read(TrCount *out) {
    memset(out, 0, sizeof *out);
    if (!g_known) return TR_WRONG_VERSION;
    uint64_t o = count_object();
    return o ? read_at(o, out) : TR_NO_MATCH;
}

int tr_write_range_ok(TrField f, int value) {
    return (unsigned)f < TR_FIELD_COUNT && value >= 0 && value <= k_write_max[f];
}

TrStatus tr_count_write(TrField f, int value) {
    if (!g_known) return TR_WRONG_VERSION;
    if (!tr_write_range_ok(f, value)) return TR_OUT_OF_RANGE;
    uint64_t o = count_object();
    if (!o) return TR_NO_MATCH;
    TrCount now;
    TrStatus s = read_at(o, &now);
    if (s != TR_OK) return s;
    uint32_t v = (uint32_t)value;
    memcpy((void *)(uintptr_t)(o + k_off[f]), &v, 4);
    return TR_OK;
}

int tr_batting_side(void) {
    if (!g_known) return -1;
    uint64_t b = ptr_at(ptr_at(g_teams_slot) ? ptr_at(g_teams_slot) + 0x20 : 0);
    if (!b || !mem_guest_readable(b + 0x124, 1)) return -1;
    uint8_t side = *(const uint8_t *)(uintptr_t)(b + 0x124);
    return side <= 1 ? side : -1;
}

// The byte is 1 in the top of an inning and 0 in the bottom (tools/scenario.py expected_side, trainer_live.py).
int tr_batting_team(void) {
    int side = tr_batting_side();
    return side < 0 ? -1 : !side;
}

// Seen live 2026-11-24: 1 while playing the home team, 0 after Team Select moved the controller to the away team.
int tr_user_side(void) {
    if (!g_known) return -1;
    uint64_t s = ptr_at(g_settings_slot);
    if (!s || !mem_guest_readable(s + 0x3e + 15, 1)) return -1;
    uint8_t side = *(const uint8_t *)(uintptr_t)(s + 0x3e + 15);
    return side <= 1 ? side : -1;
}

// The real energy (2026-11-24): the pitcher object holds an energy object at +0x10 (its first word the table below),
// a float 0..255 at +0x18 and the pitcher's id at +0x1c. The byte in the player record and the fatigue calculation's
// copy are both refreshed from it; writing the float refills the pitcher (the next request was 255 - 3).
#define ENERGY_TABLE 0x70022b6bf8ull
TrStatus tr_energy_read(uint64_t role, float *energy, int *id) {
    if (!g_known) return TR_WRONG_VERSION;
    if (!role || !mem_guest_readable(role + 0x10, 0x10)) return TR_NO_MATCH;
    uint64_t table;
    memcpy(&table, (const void *)(uintptr_t)(role + 0x10), 8);
    memcpy(energy, (const void *)(uintptr_t)(role + 0x18), 4);
    memcpy(id, (const void *)(uintptr_t)(role + 0x1c), 4);
    if (table != ENERGY_TABLE || !within(*energy, 0, 255.5f) || *id < 0 || *id >= 80) return TR_UNEXPECTED;
    return TR_OK;
}

TrStatus tr_energy_write(uint64_t role, float energy) {
    float now;
    int id;
    if (!within(energy, 0, 255)) return TR_OUT_OF_RANGE;
    TrStatus s = tr_energy_read(role, &now, &id);
    if (s != TR_OK) return s;
    memcpy((void *)(uintptr_t)(role + 0x18), &energy, 4);
    return TR_OK;
}

int tr_game_mode(void) {
    if (!g_known) return -1;
    uint64_t s = ptr_at(g_settings_slot);
    if (!s || !mem_guest_readable(s + 0x3e + 19, 1)) return -1;
    return *(const uint8_t *)(uintptr_t)(s + 0x3e + 19);
}

// Offsets read from the printf arguments of f_70002e9dc4 and the contact model, ranges seen live on 2026-11-24.
static const int k_pitch_off[TR_PITCH_COUNT] = {0x20, 0xf4, 0xf8};
static const float k_pitch_read_max[TR_PITCH_COUNT] = {1.001f, 1.001f, 150.0f};
#define HIT_OFF 0x40   // three floats: launch angle (radians), direction (radians), speed (mph)
#define DEG 57.29578f

TrStatus tr_pitcher_read(uint64_t state, TrPitcher *out) {
    memset(out, 0, sizeof *out);
    if (!g_known) return TR_WRONG_VERSION;
    if (!state || !mem_guest_readable(state, 0x100)) return TR_NO_MATCH;
    for (int f = 0; f < TR_PITCH_COUNT; f++) {
        memcpy(&out->v[f], (const void *)(uintptr_t)(state + k_pitch_off[f]), 4);
        if (!within(out->v[f], 0, k_pitch_read_max[f])) return TR_UNEXPECTED;
    }
    return TR_OK;
}

TrStatus tr_hit_read(uint64_t result, TrHit *out) {
    memset(out, 0, sizeof *out);
    if (!g_known) return TR_WRONG_VERSION;
    if (!result || !mem_guest_readable(result + HIT_OFF, 12)) return TR_NO_MATCH;
    float f[3];
    memcpy(f, (const void *)(uintptr_t)(result + HIT_OFF), sizeof f);
    if (!within(f[0], -3.16f, 3.16f) || !within(f[1], -1.59f, 1.59f) || !within(f[2], 0, 200)) return TR_UNEXPECTED;
    out->launch = f[0] * DEG, out->direction = f[1] * DEG, out->speed = f[2];
    return TR_OK;
}

// The contact model (f_700167bb7c) takes its own "auto hit" path when the u32 at +0x28 of the block at input+0x18 is
// set: f_700167823c then makes the whole result (angles, speed, velocity, spin, hit type, direction) from the floats
// at +0x30 azimuth (degrees), +0x34 launch (degrees), +0x38 speed (mph); spin at +0x4c..+0x54, worked out when zero.
// The game's scripted situations fill the same block. input+0x140 holds the bunt flags at +0x4d and +0x4e: when
// either is set the call goes to the bunt model instead (f_7001679cdc).
#define OVERRIDE_FLAG 0x28
#define OVERRIDE_DATA 0x30
static uint64_t override_block(uint64_t input) {
    if (!input || !mem_guest_readable(input + 0x18, 8)) return 0;
    uint64_t b = ptr_at(input + 0x18);
    return b && mem_guest_readable(b + OVERRIDE_FLAG, TR_OVERRIDE_BYTES) ? b : 0;
}

TrStatus tr_force_hit(uint64_t input, const TrForced *f, uint8_t saved[TR_OVERRIDE_BYTES]) {
    if (!g_known) return TR_WRONG_VERSION;
    if (!within(f->azimuth, -180, 180) || !within(f->launch, -89, 89) || !within(f->speed, 1, 130))
        return TR_OUT_OF_RANGE;
    uint64_t b = override_block(input);
    if (!b) return TR_NO_MATCH;
    uint32_t flag;
    memcpy(&flag, (const void *)(uintptr_t)(b + OVERRIDE_FLAG), 4);
    if (flag > 1) return TR_UNEXPECTED;
    uint8_t *at = (uint8_t *)(uintptr_t)(b + OVERRIDE_FLAG);
    memcpy(saved, at, TR_OVERRIDE_BYTES);
    memset(at, 0, TR_OVERRIDE_BYTES);
    flag = 1;
    memcpy(at, &flag, 4);
    memcpy(at + (OVERRIDE_DATA - OVERRIDE_FLAG), f, sizeof *f);
    return TR_OK;
}

void tr_force_hit_end(uint64_t input, const uint8_t saved[TR_OVERRIDE_BYTES]) {
    uint64_t b = override_block(input);
    if (b) memcpy((void *)(uintptr_t)(b + OVERRIDE_FLAG), saved, TR_OVERRIDE_BYTES);
}

int tr_is_bunt(uint64_t input) {
    if (!g_known || !input || !mem_guest_readable(input + 0x140, 8)) return 0;
    uint64_t b = ptr_at(input + 0x140);
    if (!b || !mem_guest_readable(b + 0x4d, 2)) return 0;
    const uint8_t *flags = (const uint8_t *)(uintptr_t)(b + 0x4d);
    return flags[0] || flags[1];
}

// f_7000247214 leaves the aim point at +0x38 and the miss added to it at +0x100..+0x108 ("pitchstoreaccuracy x y").
#define MISS_OFF 0x100
TrStatus tr_pitch_center(uint64_t placement, float miss[3]) {
    if (!g_known) return TR_WRONG_VERSION;
    if (!placement || !mem_guest_readable(placement + MISS_OFF, 12)) return TR_NO_MATCH;
    memcpy(miss, (const void *)(uintptr_t)(placement + MISS_OFF), 12);
    for (int k = 0; k < 3; k++)
        if (!within(miss[k], -50, 50)) return TR_UNEXPECTED;
    memset((void *)(uintptr_t)(placement + MISS_OFF), 0, 12);
    return TR_OK;
}

const char *tr_status_text(TrStatus s) {
    switch (s) {
    case TR_OK: return "Ready.";
    case TR_WRONG_VERSION: return "The trainer knows game version 1.0.20 only.";
    case TR_NO_MATCH: return "No match is running.";
    case TR_UNEXPECTED: return "The match data does not look as expected; nothing is changed.";
    case TR_MANAGING: return "Quick Manage is open. Return to play first.";
    default: return "That value is out of range.";
    }
}
