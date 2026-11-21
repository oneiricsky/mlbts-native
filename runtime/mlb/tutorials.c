// fastball: finished tutorials stay finished (MLB_KEEP_TUTORIALS, on by default). The game remembers which tutorials
// the player has finished only in its online profile, so offline every tutorial (the Road to the Show home tour, the
// Legacy and Outlook tours, the Perks and Tools tips, Franchise and March to October tips) came back on every launch.
// This keeps the list in <profile>/tutorials-seen.txt, one name per line, and gives it back to the game.
//
// What the game does [C, 1.0.15 addresses; 1.0.20 in the table below; read 2026-11-19, seen in game on both]:
//   P = *(*(*0x7003abda98 + 0x198) + 0x318) (f_70008dc5b0 returns *(*0x7003abda98 + 0x198)) is the universal profile,
//   built at start by the online data object whatever the connection. Finished tutorials are a vector of libc++
//   strings at P+0xa720 (end P+0xa728, 0x18 bytes each); timed copies at P+0xa738 are what the game uploads.
//   f_7000a32ce0(P, name) says whether a name is in the list; the gate that starts a screen's tutorial skips it when
//   the name is there. f_7000a32a5c(P, name) adds a name (none twice) and sends the timed list to the server. Nothing
//   writes the list to a save: after a login the server sends it back. 75 tutorial screens use this list
//   (FRONTEND/TUTORIAL/*.XML); the in-game batting and pitching tips are another system with their own setting.
//
// How: every path into that gate, or into "add a name", starts from a function pointer in main's data (the table's
// slots). Each slot gets a host function. Before the game's function runs it hands the game back any saved name its
// list lacks, through f_7000a32a5c; after it returns it appends names the list gained to the file. While the list's
// hash is the one seen last, the before-step does nothing more than read it (a few dozen short strings). With a
// server that keeps the list (the packages server here does not), its list would replace the game's after login and
// the next pass would add back what only the file knows, so both keep the same list.
// Slot 4 (the screen-change function) is also used by rtts_autosave.c, which installs after this module and calls
// this module's host function.
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"

#define NHOOK 8
// slots[i] holds fns[i]: 0-4 lead to the tutorial gate, 5 asks whether a name is in the list, 6 runs when a tutorial
// ends (adds its name), 7 adds a name for the game's scripts.
static const struct {
    const char *build;
    uint64_t state_ptr, add_name;
    uint64_t slot[NHOOK], fn[NHOOK];
} k_builds[] = {
    {"1.0.15", 0x7003abda98ull, 0x7000a32a5cull,
     {0x7002281240ull, 0x7002280d20ull, 0x700219ce70ull, 0x7002281608ull, 0x700217d580ull, 0x70022925d8ull,
      0x700217d538ull, 0x70022811e8ull},
     {0x70004d34e0ull, 0x70004cb4c8ull, 0x70009cbbccull, 0x70004bcce0ull, 0x70004c779cull, 0x7000cc0200ull,
      0x70004bf2c0ull, 0x70004a8668ull}},
    {"1.0.20", 0x7003abfa98ull, 0x7000a3357cull,
     {0x70022822b0ull, 0x7002281d90ull, 0x700219de88ull, 0x7002282678ull, 0x700217e580ull, 0x7002293658ull,
      0x700217e538ull, 0x7002282258ull},
     {0x70004d3500ull, 0x70004cb4e8ull, 0x70009cbedcull, 0x70004bcd00ull, 0x70004c77bcull, 0x7000cc1700ull,
      0x70004bf2e0ull, 0x70004a8688ull}},
};
static const char *const k_names[NHOOK] = {"<tutorials 0>", "<tutorials 1>", "<tutorials 2>", "<tutorials 3>",
                                           "<tutorials 4>", "<tutorials 5>", "<tutorials 6>", "<tutorials 7>"};
#define LIST_BEGIN 0xa720u
#define LIST_END 0xa728u
#define ENTRY 0x18u

static int g_build = -1;
static uint64_t g_hook[NHOOK];

#define MAXN 512
#define NAMELEN 96
static char g_saved[MAXN][NAMELEN];   // the file's names; the game reads them in place as C strings (guest addresses
static int g_nsaved;                  // are host addresses in this port)
static char g_cur[MAXN][NAMELEN];     // the game's list at the last read
static int g_ncur;
static char g_path[PLAT_PATH_MAX + 32];
static PlatMutex g_lock = PLAT_MUTEX_INIT;
static uint64_t g_settled;            // the list's hash once it held every saved name

static uint64_t rd64(uint64_t a) { return a && mem_guest_readable(a, 8) ? *(const uint64_t *)(uintptr_t)a : 0; }

static uint64_t profile(void) {
    uint64_t g = rd64(k_builds[g_build].state_ptr);
    uint64_t s = g ? rd64(g + 0x198) : 0;
    return s ? rd64(s + 0x318) : 0;
}

// One libc++ string: short when byte 0 is even (length byte 0 / 2, text from byte 1), else size +8, pointer +0x10.
static int name_at(uint64_t e, char *out) {
    if (!mem_guest_readable(e, ENTRY)) return 0;
    uint8_t b0 = *(const uint8_t *)(uintptr_t)e;
    uint64_t n, s;
    if (!(b0 & 1)) n = b0 >> 1, s = e + 1;
    else n = rd64(e + 8), s = rd64(e + 0x10);
    if (!n || n >= NAMELEN || !s || !mem_guest_readable(s, n)) return 0;
    memcpy(out, (const void *)(uintptr_t)s, n);
    out[n] = 0;
    return 1;
}

// The game's list into g_cur; its hash, 0 when it cannot be read. A list never used yet is two null pointers.
static uint64_t read_list(uint64_t p) {
    g_ncur = 0;
    if (!mem_guest_readable(p + LIST_BEGIN, 16)) return 0;
    uint64_t b = rd64(p + LIST_BEGIN), e = rd64(p + LIST_END);
    if ((!b && e) || e < b || (e - b) % ENTRY || (e - b) / ENTRY > 4096) return 0;
    uint64_t h = 0xcbf29ce484222325ull ^ (e - b);
    for (uint64_t a = b; a < e && g_ncur < MAXN; a += ENTRY)
        if (name_at(a, g_cur[g_ncur])) {
            for (const char *q = g_cur[g_ncur]; *q; q++) h = (h ^ (uint8_t)*q) * 0x100000001b3ull;
            h = (h ^ 0xff) * 0x100000001b3ull;
            g_ncur++;
        }
    return h ? h : 1;
}

static int listed(char (*list)[NAMELEN], int n, const char *s) {
    for (int i = 0; i < n; i++)
        if (!strcmp(list[i], s)) return 1;
    return 0;
}

// Tutorial names are screen names: letters, digits, '_', '.' and '-'. Anything else (a list read while the game was
// rebuilding it, a damaged file) is neither saved nor given back.
static int plain_name(const char *s) {
    if (!*s) return 0;
    for (; *s; s++)
        if (!((*s >= 'A' && *s <= 'Z') || (*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '_' ||
              *s == '.' || *s == '-'))
            return 0;
    return 1;
}

static int g_need_newline;   // the file does not end with a line break (a start that was killed mid-write)

static void load_file(void) {
    FILE *f = fopen(g_path, "rb");
    if (!f) return;
    char line[256];
    int last = '\n';
    while (fgets(line, sizeof line, f)) {
        size_t l = strlen(line);
        if (l) last = (unsigned char)line[l - 1];
        if (l && line[l - 1] != '\n' && !feof(f)) {   // longer than any name: skip the rest of the line
            int ch;
            while ((ch = fgetc(f)) != EOF && ch != '\n') {}
            last = '\n';
            continue;
        }
        size_t n = strcspn(line, "\r\n");
        line[n] = 0;
        if (g_nsaved >= MAXN || n >= NAMELEN || !plain_name(line) || listed(g_saved, g_nsaved, line)) continue;
        memcpy(g_saved[g_nsaved++], line, n + 1);
    }
    g_need_newline = last != '\n';
    fclose(f);
}

// Saves names the game's list gained; with give_back, also hands the game the saved names its list lacks (a call
// into the game, so only before the wrapped function runs).
static void sync(Cpu *c, int give_back) {
    if (!plat_mutex_trylock(&g_lock)) return;   // another thread is at it, or a call from inside our own give-back
    uint64_t p = profile();
    uint64_t h = p ? read_list(p) : 0;
    if (h && h != g_settled) {
        int added = 0;
        FILE *f = NULL;
        for (int i = 0; i < g_ncur && g_nsaved < MAXN; i++) {
            if (!plain_name(g_cur[i]) || listed(g_saved, g_nsaved, g_cur[i])) continue;
            strcpy(g_saved[g_nsaved++], g_cur[i]);
            if (!f) {
                f = fopen(g_path, "ab");
                if (f && g_need_newline) fputc('\n', f), g_need_newline = 0;
            }
            if (!f || fprintf(f, "%s\n", g_cur[i]) < 0)
                rt_log("tutorials: could not write %s to %s; it is kept for this run only", g_cur[i], g_path);
            added++;
        }
        if (f) fclose(f);
        if (added) rt_log("tutorials: %d newly finished, %d kept", added, g_nsaved);
        if (give_back) {   // only this pass settles the list
            int back = 0;
            for (int i = 0; i < g_nsaved; i++)
                if (plain_name(g_saved[i]) && !listed(g_cur, g_ncur, g_saved[i])) {
                    rt_call(c, k_builds[g_build].add_name, 2, p, (uint64_t)(uintptr_t)g_saved[i]);
                    back++;
                }
            if (back) {
                h = read_list(p);
                rt_log("tutorials: gave the game back %d finished tutorials (its list holds %d)", back, g_ncur);
            }
            g_settled = h;
        }
    }
    plat_mutex_unlock(&g_lock);
}

static void hook(Cpu *c) {
    int i = 0;
    while (i < NHOOK && g_hook[i] != c->pc) i++;
    if (i == NHOOK) rt_fatal("tutorials: entered at %#llx, not one of its slots", (unsigned long long)c->pc);
    // The give-back calls into the game: the wrapped function gets every register as its caller left it.
    uint64_t x[31];
    __uint128_t v[32];
    memcpy(x, c->x, sizeof x);
    memcpy(v, c->v, sizeof v);
    sync(c, 1);
    memcpy(c->x, x, sizeof x);
    memcpy(c->v, v, sizeof v);
    uint64_t r = rt_call(c, k_builds[g_build].fn[i], 8, x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7]);
    sync(c, 0);   // reads only: the registers stay as the game's function left them
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

// boot.c: after the modules are loaded, before hostfn_seal.
void tutorials_apply(void) {
    if (!cfg_bool("MLB_KEEP_TUTORIALS")) return;
    for (int b = 0; b < (int)(sizeof k_builds / sizeof *k_builds); b++)
        if (!strcmp(rt_game_build, k_builds[b].build)) g_build = b;
    if (g_build < 0) {
        rt_log("tutorials: no addresses for game %s; finished tutorials are not kept", rt_game_build);
        return;
    }
    for (int i = 0; i < NHOOK; i++) {
        uint64_t want = k_builds[g_build].fn[i], have = rd64(k_builds[g_build].slot[i]);
        if (have != want) {
            rt_log("tutorials: slot %#llx holds %#llx, not %#llx; finished tutorials are not kept",
                   (unsigned long long)k_builds[g_build].slot[i], (unsigned long long)have, (unsigned long long)want);
            return;
        }
    }
    snprintf(g_path, sizeof g_path, "%s/tutorials-seen.txt", rt_config()->profile);
    load_file();
    for (int i = 0; i < NHOOK; i++) {
        g_hook[i] = hostfn_register(k_names[i], hook);
        if (!poke64(k_builds[g_build].slot[i], g_hook[i])) {
            for (int j = 0; j < i; j++) poke64(k_builds[g_build].slot[j], k_builds[g_build].fn[j]);
            rt_log("tutorials: could not write slot %#llx; finished tutorials are not kept",
                   (unsigned long long)k_builds[g_build].slot[i]);
            return;
        }
    }
    rt_log("tutorials: finished tutorials are kept in %s (%d there)", g_path, g_nsaved);
}
