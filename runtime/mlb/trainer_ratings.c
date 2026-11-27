// Trainer ratings (trainer_ratings.h). The hook reports each player of the match; the game's own values are copied
// before anything is written, so they can be put back. Only bytes the trainer has changed are ever restored, and a
// player whose record or table has moved is forgotten.
#include "trainer_ratings.h"

#include <stdio.h>
#include <string.h>

#include "host.h"
#include "platform/platform.h"

const TrRating tr_ratings[] = {
    {"Contact vs left", 4},  {"Contact vs right", 5}, {"Power vs left", 6},  {"Power vs right", 7},
    {"Plate vision", 11},    {"Speed", 15},           {"Stamina", 0x28},     {"Pitch 1 speed", 0x36},
    {"Pitch 2 speed", 0x37}, {"Pitch 3 speed", 0x38}, {"Pitch 4 speed", 0x39}, {"Pitch 5 speed", 0x3a},
    {"Pitch 1 movement", 0x3c}, {"Pitch 2 movement", 0x3d}, {"Pitch 3 movement", 0x3e},
    {"Pitch 4 movement", 0x3f}, {"Pitch 5 movement", 0x40},
};
const int tr_rating_count = sizeof tr_ratings / sizeof *tr_ratings;

typedef struct {
    int used;
    uint64_t record, table;
    char name[24];
    uint8_t own[TR_RATING_BYTES];     // the game's values, taken before the first write
    uint8_t changed[TR_RATING_BYTES]; // 1: the trainer wrote this byte
    uint8_t edit[TR_RATING_BYTES];    // a single value asked for, plus one; 0 none
} Player;

static PlatMutex g_lock = PLAT_MUTEX_INIT;
static Player g_players[TR_PLAYERS];
static int g_level[2][TR_GROUPS];   // [away or home][group]
static int g_dirty;   // a preset changed: trainer.txt wants writing

static int in_preset(int group, int off) {
    if (group == TR_BATTING) return off == 4 || off == 5 || off == 6 || off == 7 || off == 11;
    return off >= 0x36 && off <= 0x41;   // pitch speed and movement
}

static int group_of(int off) { return off < 0x28 ? TR_BATTING : TR_PITCHING; }

// The name at record +0x60 and the ratings table at *(record + 0x48).
static int read_player(uint64_t record, char *name, uint64_t *table) {
    if (!record || !mem_guest_readable(record, 0xb0)) return 0;
    const unsigned char *r = (const unsigned char *)(uintptr_t)record;
    int n = 0;
    while (n < 20 && r[0x60 + n] >= 32) n++;
    if (n < 2 || n >= 20 || r[0x60 + n]) return 0;
    for (int i = 0; i < n; i++)
        if (r[0x60 + i] == 127) return 0;
    memcpy(name, r + 0x60, (size_t)n + 1);
    memcpy(table, r + 0x48, 8);
    return *table && mem_guest_readable(*table, TR_RATING_BYTES);
}

void trainer_ratings_seen(int id, uint64_t record) {
    char name[24];
    uint64_t table;
    if (id < 0 || id >= TR_PLAYERS || !read_player(record, name, &table)) return;
    plat_mutex_lock(&g_lock);
    Player *p = &g_players[id];
    if (!p->used || p->record != record || p->table != table || strcmp(p->name, name)) {
        memset(p, 0, sizeof *p);
        p->used = 1, p->record = record, p->table = table;
        memcpy(p->name, name, sizeof p->name);
        memcpy(p->own, (const void *)(uintptr_t)table, TR_RATING_BYTES);
        rt_log("trainer: player %d %s", id, name);
    }
    plat_mutex_unlock(&g_lock);
}

void trainer_ratings_preset(int side, int group, int level) {
    if (side < 0 || side > 1 || group < 0 || group >= TR_GROUPS || level < 0 || level >= TR_LEVELS) return;
    plat_mutex_lock(&g_lock);
    g_level[side][group] = level;
    g_dirty = 1;
    if (level == TR_NORMAL)
        for (int id = 0; id < TR_PLAYERS; id++)
            for (int off = 0; off < TR_RATING_BYTES; off++)
                if (id / (TR_PLAYERS / 2) == side && group_of(off) == group) g_players[id].edit[off] = 0;
    rt_log("trainer: ratings: %s %s %s", side ? "home" : "away", group == TR_BATTING ? "batting" : "pitching",
           level == TR_NORMAL ? "normal" : level == TR_BEST ? "best" : "worst");
    plat_mutex_unlock(&g_lock);
}

void trainer_ratings_cycle(int side, int group) {
    trainer_ratings_preset(side, group, (trainer_ratings_level(side, group) + 1) % TR_LEVELS);
}

int trainer_ratings_level(int side, int group) {
    return side >= 0 && side <= 1 && group >= 0 && group < TR_GROUPS ? g_level[side][group] : TR_NORMAL;
}

void trainer_ratings_set(int id, int rating, int value) {
    if (id < 0 || id >= TR_PLAYERS || rating < 0 || rating >= tr_rating_count || value < 0 || value > TR_RATING_MAX)
        return;
    plat_mutex_lock(&g_lock);
    if (g_players[id].used) g_players[id].edit[tr_ratings[rating].off] = (uint8_t)(value + 1);
    plat_mutex_unlock(&g_lock);
}

int trainer_ratings_player(int id, char *name, int name_size) {
    if (id < 0 || id >= TR_PLAYERS) return 0;
    plat_mutex_lock(&g_lock);
    int used = g_players[id].used;
    if (used) snprintf(name, (size_t)name_size, "%s", g_players[id].name);
    plat_mutex_unlock(&g_lock);
    return used;
}

int trainer_ratings_value(int id, int rating) {
    if (id < 0 || id >= TR_PLAYERS || rating < 0 || rating >= tr_rating_count) return 0;
    int value = 0;
    plat_mutex_lock(&g_lock);
    const Player *p = &g_players[id];
    if (p->used && mem_guest_readable(p->table, TR_RATING_BYTES))
        value = *(const uint8_t *)(uintptr_t)(p->table + tr_ratings[rating].off);
    plat_mutex_unlock(&g_lock);
    return value;
}

static void apply_player(Player *p, int side, int allowed) {
    char name[24];
    uint64_t table;
    if (!read_player(p->record, name, &table) || table != p->table || strcmp(name, p->name)) {
        p->used = 0;   // gone or reused: nothing is written to it
        return;
    }
    uint8_t *t = (uint8_t *)(uintptr_t)table;
    for (int off = 0; off < TR_RATING_BYTES; off++) {
        int want = -1, group = group_of(off), level = g_level[side][group];
        if (allowed) {
            // a pitch he does not have (0) is left alone
            if (level != TR_NORMAL && in_preset(group, off) && (group == TR_BATTING || p->own[off]))
                want = level == TR_BEST ? TR_RATING_MAX : TR_RATING_MIN;
            if (p->edit[off]) want = p->edit[off] - 1;
        }
        if (want >= 0) {
            if (t[off] != want) t[off] = (uint8_t)want, p->changed[off] = 1;
        } else if (p->changed[off]) {
            t[off] = p->own[off], p->changed[off] = 0;
        }
    }
}

void trainer_ratings_apply(int allowed) {
    plat_mutex_lock(&g_lock);
    for (int id = 0; id < TR_PLAYERS; id++)
        if (g_players[id].used) apply_player(&g_players[id], id / (TR_PLAYERS / 2), allowed);
    plat_mutex_unlock(&g_lock);
}

void trainer_ratings_match_over(void) {
    plat_mutex_lock(&g_lock);
    memset(g_players, 0, sizeof g_players);
    plat_mutex_unlock(&g_lock);
}

void trainer_ratings_reset(void) {
    plat_mutex_lock(&g_lock);
    memset(g_players, 0, sizeof g_players);
    memset(g_level, 0, sizeof g_level);
    g_dirty = 0;
    plat_mutex_unlock(&g_lock);
}

int trainer_ratings_take_dirty(void) {
    plat_mutex_lock(&g_lock);
    int dirty = g_dirty;
    g_dirty = 0;
    plat_mutex_unlock(&g_lock);
    return dirty;
}

void trainer_ratings_load_line(const char *line) {
    int side, group, level;
    if (sscanf(line, "preset %d %d %d", &side, &group, &level) != 3 || side < 0 || side > 1 || group < 0 ||
        group >= TR_GROUPS || level < 0 || level >= TR_LEVELS)
        return;
    plat_mutex_lock(&g_lock);
    g_level[side][group] = level;
    plat_mutex_unlock(&g_lock);
}

void trainer_ratings_save(void *file) {
    plat_mutex_lock(&g_lock);
    for (int side = 0; side < 2; side++)
        for (int group = 0; group < TR_GROUPS; group++)
            if (g_level[side][group] != TR_NORMAL)
                fprintf((FILE *)file, "preset %d %d %d\n", side, group, g_level[side][group]);
    plat_mutex_unlock(&g_lock);
}
