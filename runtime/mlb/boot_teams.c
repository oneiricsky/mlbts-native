// fastball: boot_teams, the GameOnly boot's chosen matchup (the code patch set in the temp patch file).
//
// The boot patch calls the menu's game-entry builder with the away and home ids read from the patch page,
// before the match state is copied. Two things the builder does not bring over from the bundle:
//   - the presentation reads the match settings block for the uniforms and the scoreboard, so its home/away
//     bytes are written here;
//   - the match player table (the game manager at 0x700227dda0, table at +0x10, 80 records of 0x138) still
//     holds the bundle's placeholder players (all id 0xC722), so the 3D models, heads and jersey numbers stay
//     the default Toronto/Los Angeles players. Each chosen team's 40-man roster is copied into it from the
//     league team record (the block at +0x50 points at the 40 records) before the builder runs.
//
// The thread polls once a millisecond from boot until the table and the state are built (about 20 s), then
// exits; nothing runs during play. 1.0.20 addresses; the patch set only exists for that version.
#include "cfg.h"
#include "host.h"
#include "platform/platform.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define BT_MANAGER 0x700227dda0ull   // the match manager: +0x10 player table, +0x38 its count
#define BT_LEAGUE 0x700227e6c0ull    // the league object: +0x8 the 30 team records
#define BT_SETTINGS 0x7004651350ull  // the settings block pointer (the presentation's team bytes)
#define BT_REC 0x138                 // one player table record
#define BT_TEAM 0x550                // one league team record
#define BT_BLOCK 0x50                // its roster block: 40 player-record pointers

static int away_id, home_id;
static int fill_names_table;   // MLB_BOOT_TABLE=1: the experimental roster table fill (see the note below)

static uint64_t rd64(uint64_t a, int *ok) {
    uint64_t v = 0;
    *ok = plat_mem_read(a, &v, sizeof v);
    return v;
}

static void fill_block(void) {
    int ok;
    uint64_t s = rd64(BT_SETTINGS, &ok);
    if (!ok || !s) return;
    static const uint8_t home_at[] = {0x3f, 0x47, 0x59};
    static const uint8_t away_at[] = {0x40, 0x52, 0x54, 0x56};
    for (size_t i = 0; i < sizeof home_at; i++) {
        if (plat_mem_readable(s + home_at[i], 1) && *(volatile uint8_t *)(uintptr_t)(s + home_at[i]) != home_id)
            *(volatile uint8_t *)(uintptr_t)(s + home_at[i]) = (uint8_t)home_id;
    }
    for (size_t i = 0; i < sizeof away_at; i++) {
        if (plat_mem_readable(s + away_at[i], 1) && *(volatile uint8_t *)(uintptr_t)(s + away_at[i]) != away_id)
            *(volatile uint8_t *)(uintptr_t)(s + away_at[i]) = (uint8_t)away_id;
    }
}

static int fill_table(void) {
    int ok;
    uint64_t mg = rd64(BT_MANAGER, &ok);
    if (!ok || !mg) return 0;
    uint64_t tb = rd64(mg + 0x10, &ok);
    if (!ok || !tb) return 0;
    uint32_t count = 0;
    if (!plat_mem_read(mg + 0x38, &count, sizeof count) || count < 80) return 0;
    uint64_t lg = rd64(BT_LEAGUE, &ok);
    if (!ok || !lg) return 0;
    uint64_t lb = rd64(lg + 8, &ok);
    if (!ok || !lb) return 0;
    int copied = 0;
    for (int side = 0; side < 2; side++) {
        int tid = side ? home_id : away_id;
        uint64_t tr = lb + (uint64_t)tid * BT_TEAM;
        uint8_t team[BT_TEAM];
        if (!plat_mem_read(tr, team, sizeof team) || !team[0x1a]) continue;
        for (int j = 0; j < 40; j++) {
            uint64_t p = 0;
            if (!plat_mem_read(tr + BT_BLOCK + (uint64_t)j * 8, &p, sizeof p)) continue;
            if (p <= 0x100000000ull || p >= 0x4000000000ull) continue;   // empty slot
            uint8_t rec[BT_REC];
            if (!plat_mem_read(p, rec, sizeof rec)) continue;             // not loaded
            uint64_t dst = tb + ((uint64_t)side * 40 + (uint64_t)j) * BT_REC;
            if (!plat_mem_readable(dst, BT_REC)) continue;
            memcpy((void *)(uintptr_t)dst, rec, sizeof rec);
            copied++;
        }
    }
    return copied;
}

static void boot_teams_thread(void *arg) {
    (void)arg;
    int logged = 0;
    for (int i = 0; i < 20000; i++) {   // 20 s: the league table is up at about 14 s, the state at 15.5 s
        fill_block();
        if (fill_names_table) {
            int n = fill_table();
            if (n && !logged) {
                rt_log("boot_teams: filled %d player records for away %d home %d", n, away_id, home_id);
                logged = 1;
            }
        }
        // The game fills the player names and builds the presentation from the table after the state copy;
        // writing the records after that point erases the names (a blank scoreboard card). Stop when the
        // state's two team slots hold the chosen ids (they hold the default matchup's until the builder).
        int ok;
        uint64_t st = rd64(0x7002296d40ull, &ok);
        if (ok && st) {
            uint32_t a = 0, h = 0;
            if (plat_mem_read(st + 0xc, &a, sizeof a) && plat_mem_read(st + 0x55c, &h, sizeof h) &&
                a == (uint32_t)away_id && h == (uint32_t)home_id)
                break;
        }
        plat_sleep_ns(1000000);
    }
}

void boot_teams_apply(void) {
    if (!rt_patch_enabled(rt_patch_set("boot_teams"))) return;
    const char *a = cfg_get("MLB_BOOT_AWAY"), *h = cfg_get("MLB_BOOT_HOME");
    away_id = a && *a ? atoi(a) : 0;
    home_id = h && *h ? atoi(h) : 0;
    const char *t = cfg_get("MLB_BOOT_TABLE");
    fill_names_table = t && *t && strcmp(t, "0") != 0;
    if (!plat_thread_spawn(boot_teams_thread, NULL, "boot_teams", 0))
        rt_log("boot_teams: cannot start the thread");
}
