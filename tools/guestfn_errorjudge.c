// One recompiled game function against a fake match, without the game: the end-of-play error judge's test "did a
// runner gain on this fielder action?" (guest 0x7000d42f20, 1.0.20; called by the judge at 0x7000d43ce0).
// This file is only our own code. tools/guestfn_test.py copies the game's functions out of the generated C into
// work/scratch/guestfn/, compiles them with this file and runs the result:
//
//   python -I tools/guestfn_test.py
//
// Guest addresses are host addresses (runtime/core/cpu.h), so the fake objects can live anywhere in this program.
// The one fixed address the code reads, the pointer to the two team objects at 0x7003aeb728, is mapped for real.
//
// Tags: [C] read in the game's code (or in a string next to it), [I] our inference about what a field means. The
// checks prove what the function does with the field either way; an [I] only says the baseball wording may be wrong.
// The exit code is the number of failed checks; 77 is the expected fault of --no-global.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

#include "cpu.h"
#include "guestfn_record.h"

void f_7000d42f20(Cpu *c);   // (rules, entry, w2, out) -> w0

// ---- what the generated code expects from the runtime
volatile int g_fnprof;
void fnprof_hit(uint64_t addr, uint64_t lr, uint64_t x0) { (void)addr, (void)lr, (void)x0; }
void rt_udf(Cpu *c, uint64_t pc) {
    (void)c;
    printf("FATAL: undefined instruction reached at 0x%llx\n", (unsigned long long)pc);
    exit(126);
}

// ---- layout (all offsets [C]; the meanings are tagged)
#define TEAMS_GLOBAL 0x7003aeb728ull   // -> {+0x18 team object A, +0x20 team object B}
enum {
    R_OUTS_IDS = 0x148, R_OUTS_N = 0x158,       // ids put out on this play [C: appended where outs are counted]
    R_REC = 0x18c, REC_STRIDE = 0x10,           // 4 records {+0 runner id, +0xc how far when put out}
    R_SCORED_IDS = 0x1d0, R_SCORED_N = 0x1e0,   // ids that scored on this play [C: appended next to "Score: %d to %d"]
    R_ENTRY = 0x22c, R_ENTRY_N = 0xe5c,         // the fielder actions of the play
    E_TYPE = 0x00, E_ID = 0x48, E_BASE = 0x6c,  // four runners: id (-1 none), base held at the action (0 batter) [I]
    E_FLAG = 0x90,                              // unnamed byte
    S_POS = 0x124,                              // runner's progress: 1 first, 3 second, 5 third, 7 home [I, unit C]
    T_STATE = 0x170,                            // 0x10 and 0x14 count; read here as "safe on a base" [I]
    B_BATTING = 0x124,                          // team object B: batting side [C, known-functions.md]
};
enum { SAFE = 0x10, SAFE2 = 0x14, RUNNING = 0x11 };   // RUNNING: any other value
enum { BATTER = 3, ON1 = 7, ON2 = 12, ON3 = 15 };     // our runner ids
static const int k_id[4] = {BATTER, ON1, ON2, ON3};

typedef struct {
    uint8_t info[0x48];      // +0x40 id
    uint8_t move[0x128];     // +8 -> state object, +0x124 position
    uint8_t state[0x178];    // +0x170
    uint8_t slot[0x170];     // the runner proper is at +0x158: {-> info, -> move}
    uint8_t player[0x18];    // +0x10 -> slot
} Runner;

static uint8_t g_rules[0x1000], g_team[2][0x200];
static Runner g_runner[2][4];   // in each team object's table, the same ids
static uint64_t g_teams[8];
static uint8_t g_stack[0x10000] __attribute__((aligned(16)));

static void w8_(uint8_t *p, uint8_t v) { *p = v; }
static void w32(uint8_t *p, int32_t v) { memcpy(p, &v, 4); }
static void w64(uint8_t *p, uint64_t v) { memcpy(p, &v, 8); }
static int32_t r32(const uint8_t *p) { int32_t v; memcpy(&v, p, 4); return v; }
#define P(x) ((uint64_t)(uintptr_t)(x))

static uint8_t *entry(void) { return g_rules + R_ENTRY; }
// The code looks runners up in the object its "fielding team" getter returns: B+0x124 == 0 picks B, else A [C].
static int looked_up(void) { return g_team[1][B_BATTING] == 0; }
static Runner *runner(int i) { return &g_runner[looked_up()][i]; }

// A play with the given runners nowhere yet: on the list one throw (type 3), nobody scored or out.
static void reset(void) {
    memset(g_rules, 0, sizeof g_rules);
    memset(g_team, 0, sizeof g_team);
    memset(g_runner, 0, sizeof g_runner);
    for (int t = 0; t < 2; t++)
        for (int i = 0; i < 4; i++) {
            Runner *r = &g_runner[t][i];
            w32(r->info + 0x40, k_id[i]);
            w64(r->move + 8, P(r->state));
            w64(r->slot + 0x158, P(r->info));
            w64(r->slot + 0x160, P(r->move));
            w64(r->player + 0x10, P(r->slot));
            w64(g_team[t] + 0x18 + 8 * k_id[i], P(r->player));
        }
    g_teams[3] = P(g_team[0]);
    g_teams[4] = P(g_team[1]);
    g_team[1][B_BATTING] = 1;   // so team object A is the one looked in
    for (int i = 0; i < 4; i++) {
        w32(g_rules + R_REC + i * REC_STRIDE, -1);
        w32(entry() + E_ID + 4 * i, -1);
    }
    w32(entry() + E_TYPE, 3);
    w32(g_rules + R_ENTRY_N, 1);
}

// Runner i takes part: held `base` when the ball was thrown, now at `pos` in `state`.
static void put(int i, int base, int pos, int state) {
    w32(entry() + E_ID + 4 * i, k_id[i]);
    w32(entry() + E_BASE + 4 * i, base);
    w32(runner(i)->move + S_POS, pos);
    w32(runner(i)->state + T_STATE, state);
    w32(g_rules + R_REC + i * REC_STRIDE, k_id[i]);
}
static void list_add(int ids, int n, int id) {
    uint64_t count;
    memcpy(&count, g_rules + n, 8);
    w32(g_rules + ids + 4 * (int)count, id);
    w64(g_rules + n, count + 1);
}
static void scored(int i) { list_add(R_SCORED_IDS, R_SCORED_N, k_id[i]); }
static void put_out(int i, int how_far) {
    list_add(R_OUTS_IDS, R_OUTS_N, k_id[i]);
    w32(g_rules + R_REC + i * REC_STRIDE + 0xc, how_far);
}

// ---- the call
#define UNTOUCHED 0x5a5a
static int g_failed, g_checks, g_calls_bad;
static int32_t g_out;

static int call(int w2, int with_out) {
    Cpu c;
    memset(&c, 0, sizeof c);
    g_out = UNTOUCHED;
    c.x[0] = P(g_rules);
    c.x[1] = P(entry());
    c.x[2] = (uint32_t)w2;
    c.x[3] = with_out ? P(&g_out) : 0;
    c.sp = P(g_stack + sizeof g_stack - 0x100);
    for (int r = 19; r <= 29; r++) c.x[r] = 0x1111000000000000ull + r;
    f_7000d42f20(&c);
    // the calling convention: the stack pointer and x19..x29 come back as they went in
    if (c.sp != P(g_stack + sizeof g_stack - 0x100)) g_calls_bad++;
    for (int r = 19; r <= 29; r++)
        if (c.x[r] != 0x1111000000000000ull + r) g_calls_bad++;
    return (int)(uint32_t)c.x[0];
}

// Call with an out pointer and compare the answer and what was written there.
static void expect_(int line, const char *what, int w2, int want, int want_out) {
    int got = call(w2, 1);
    int ok = got == want && g_out == want_out;
    g_checks++;
    g_failed += !ok;
    char out[16];
    snprintf(out, sizeof out, g_out == UNTOUCHED ? "unset" : "%d", g_out);
    printf("%s %-78s w2=%d -> %d, runner %s", ok ? "ok  " : "FAIL", what, w2, got, out);
    if (!ok) printf("   (line %d: wanted %d, %d)", line, want, want_out == UNTOUCHED ? -999 : want_out);
    printf("\n");
}
#define EXPECT(what, w2, want, out) expect_(__LINE__, what, w2, want, out)
#define CHECK(x)                                                             \
    do {                                                                     \
        g_checks++;                                                          \
        if (!(x)) g_failed++, printf("FAIL %s:%d %s\n", __func__, __LINE__, #x); \
    } while (0)

// Each block: a play, its answer, then one field changed (after a fresh setup) and the other answer.
static void batter_only(void) {   // w2 bit 0: only the batter, only first base
    printf("-- batter-only form (w2 = 1)\n");
    reset(), put(0, 0, 1, SAFE);
    EXPECT("wild throw to first, batter safe on first", 1, 1, 0);
    w32(runner(0)->state + T_STATE, SAFE2);
    EXPECT("  flip state 0x10 -> 0x14 (the other accepted state)", 1, 1, 0);
    w32(runner(0)->state + T_STATE, RUNNING);
    EXPECT("  flip state -> 0x11 (not safe on a base)", 1, 0, -1);
    reset(), put(0, 0, 0, SAFE);
    EXPECT("  flip position 1 -> 0 (has not got to first)", 1, 0, -1);

    reset(), put(0, 0, 1, SAFE), put_out(0, -1);
    EXPECT("same throw, but the batter is put out at first", 1, 0, -1);
    reset(), put(0, 0, 1, SAFE), put_out(0, 1);
    EXPECT("put out, recorded at first (1): did not get past it", 1, 0, -1);
    w32(g_rules + R_REC + 0xc, 2);
    EXPECT("  flip record 1 -> 2: past first, thrown out going to second", 1, 1, 0);
    reset(), put(0, 0, 1, RUNNING), put_out(0, 2);
    EXPECT("put out past first, state no longer safe: the record still says yes", 1, 1, 0);
    w64(g_rules + R_OUTS_N, 0);
    EXPECT("  flip outs count 1 -> 0: the record is ignored, the state says no", 1, 0, -1);

    reset(), put(0, 1, 3, SAFE);
    EXPECT("batter already held first at the throw, now on second", 1, 0, -1);
    EXPECT("  flip w2 1 -> 0 (any runner, any base)", 0, 1, 0);
    EXPECT("  w2 = 2 acts like 0 (only bit 0 is read)", 2, 1, 0);

    reset(), put(1, 1, 3, SAFE);
    EXPECT("no batter in the entry, a runner advanced", 1, 0, -1);
    EXPECT("  flip w2 1 -> 0: the runner counts", 0, 1, 1);

    reset(), put(0, 0, 0, RUNNING), scored(0);
    EXPECT("batter came all the way round (in the scored list): out left unset", 1, 1, UNTOUCHED);
    w64(g_rules + R_SCORED_N, 0);
    EXPECT("  flip scored count 1 -> 0 (the id is still in the array)", 1, 0, -1);

    reset(), put(0, 0, 1, SAFE);
    g_out = UNTOUCHED;
    CHECK(call(1, 0) == 1);   // 10 of the judge's 11 calls pass no out pointer
    reset(), put(0, 0, 0, SAFE);
    CHECK(call(1, 0) == 0);
}

static void any_runner(void) {
    printf("-- any-runner form (w2 = 0)\n");
    reset(), put(0, 0, 1, SAFE), put_out(0, -1), put(1, 1, 5, SAFE);
    EXPECT("batter out at first, runner from first takes third", 0, 1, 1);
    w32(runner(1)->move + S_POS, 3);
    EXPECT("  flip position 5 -> 3: the runner only reached second (the next base)", 0, 1, 1);
    w32(runner(1)->move + S_POS, 1);
    EXPECT("  flip position -> 1: the runner held first", 0, 0, -1);

    reset(), put(2, 2, 5, SAFE);
    EXPECT("runner on second reaches third", 0, 1, 2);
    w32(entry() + E_BASE + 8, 3);
    EXPECT("  flip base held 2 -> 3: third is where he started", 0, 0, -1);

    reset(), put(3, 3, 7, SAFE);
    EXPECT("runner from third at position 7, not in the scored list: no", 0, 0, -1);
    scored(3);
    EXPECT("  flip scored count 0 -> 1: he scored, yes (out left unset)", 0, 1, UNTOUCHED);

    reset(), put(0, 0, 1, SAFE), put(1, 1, 3, SAFE);
    EXPECT("batter and runner both advance: the first one is reported", 0, 1, 0);
    w32(entry() + E_ID, -1);
    EXPECT("  flip batter id -> -1: now the runner from first", 0, 1, 1);

    reset(), put(0, 0, 0, RUNNING), put(1, 1, 1, SAFE), put(2, 2, 3, SAFE), put(3, 3, 5, SAFE);
    EXPECT("bases loaded, everyone holds", 0, 0, -1);
    scored(3);
    EXPECT("  flip: the man on third is added to the scored list", 0, 1, UNTOUCHED);

    reset();
    EXPECT("empty entry (no runner ids)", 0, 0, -1);
    reset(), put(1, 4, 9, SAFE);
    EXPECT("base held 4 (next base past home) is skipped", 0, 0, -1);
}

static void odd_corners(void) {
    printf("-- corners the code has\n");
    // An out runner with no record of his own is judged by the fourth record.
    reset(), put(0, 0, 1, SAFE), put_out(0, -1);
    w32(g_rules + R_REC, -1);
    EXPECT("put-out runner with no record: record 4 (empty) says no", 0, 0, -1);
    w32(g_rules + R_REC + 3 * REC_STRIDE + 0xc, 5);
    EXPECT("  flip record 4's distance 0 -> 5: now yes", 0, 1, 0);

    // One action on the list and the byte at +0x90: the batter's base is rewritten to 0.
    reset(), put(0, 1, 1, SAFE);
    EXPECT("batter listed as holding first, still on first", 0, 0, -1);
    CHECK(r32(entry() + E_BASE) == 1);
    reset(), put(0, 1, 1, SAFE), w8_(entry() + E_FLAG, 1);
    EXPECT("  flip byte +0x90 0 -> 1 with one action: counted from home, yes", 0, 1, 0);
    CHECK(r32(entry() + E_BASE) == 0);   // the function writes into the entry
    reset(), put(0, 1, 1, SAFE), w8_(entry() + E_FLAG, 1), w32(g_rules + R_ENTRY_N, 2);
    EXPECT("  flip action count 1 -> 2: no rewrite", 0, 0, -1);
    CHECK(r32(entry() + E_BASE) == 1);

    // Which team object the runners come from: the batting-side byte.
    reset(), put(0, 0, 1, SAFE);
    w32(g_runner[1][0].state + T_STATE, RUNNING);   // team object B's runner 3 is not safe
    EXPECT("batting-side byte 1: runners read from team object A (safe)", 1, 1, 0);
    g_team[1][B_BATTING] = 0;
    EXPECT("  flip batting-side byte 1 -> 0: team object B (not safe)", 1, 0, -1);
}

static void side_effects(void) {   // nothing but the entry's batter base and *out is written
    static uint8_t rules[sizeof g_rules], team[sizeof g_team];
    static Runner run[2][4];
    reset(), put(0, 0, 1, SAFE), put(1, 1, 3, SAFE), put_out(0, 2), scored(2);
    memcpy(rules, g_rules, sizeof rules), memcpy(team, g_team, sizeof team), memcpy(run, g_runner, sizeof run);
    for (int w2 = 0; w2 < 2; w2++) call(w2, 1);
    CHECK(!memcmp(rules, g_rules, sizeof rules));
    CHECK(!memcmp(team, g_team, sizeof team));
    CHECK(!memcmp(run, g_runner, sizeof run));
}

static void speed(void) {
    reset(), put(0, 0, 0, SAFE), put(1, 1, 1, SAFE), put(2, 2, 3, SAFE), put(3, 3, 5, SAFE);   // all four looked at
    LARGE_INTEGER f, a, b;
    QueryPerformanceFrequency(&f);
    int n = 5000000, yes = 0;
    QueryPerformanceCounter(&a);
    for (int i = 0; i < n; i++) yes += call(0, 1);
    QueryPerformanceCounter(&b);
    CHECK(yes == 0);
    double s = (double)(b.QuadPart - a.QuadPart) / (double)f.QuadPart;
    printf("speed: %d calls (four runners each) in %.3f s, %.1f ns a call including setup of the registers\n", n, s,
           s * 1e9 / n);
}

// ---- replay of calls recorded in a live match (tools/guestfn_capture.py)
// broken: 1 gives every runner a state the code does not accept, a control that must produce differences.
static int replay(const char *path, int broken) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        printf("FATAL: cannot open %s\n", path);
        return 125;
    }
    static GfRecord r;
    static Runner many[GF_RUNNERS];
    int calls = 0, differ = 0, yes = 0, with_out_list = 0, with_scored = 0, throws = 0, w2_set = 0, rewrote = 0;
    while (fread(&r, sizeof r, 1, f) == 1) {
        if (r.magic != GF_MAGIC || r.runners > GF_RUNNERS || r.entry_off + 0x9c > GF_RULES) {
            printf("FATAL: record %d is not a record\n", calls);
            return 125;
        }
        reset();
        memset(many, 0, sizeof many);
        memset(g_team, 0, sizeof g_team);
        g_team[1][B_BATTING] = (uint8_t)r.batting;
        memcpy(g_rules, r.rules, GF_RULES);
        for (uint32_t i = 0; i < r.runners; i++) {
            const GfRunner *g = &r.run[i];
            if (!g->ok) continue;
            Runner *x = &many[i];
            w32(x->info + 0x40, g->info_id);
            w64(x->move + 8, P(x->state));
            w32(x->move + S_POS, g->pos);
            w32(x->state + T_STATE, broken ? RUNNING : g->state);
            w64(x->slot + 0x158, P(x->info));
            w64(x->slot + 0x160, P(x->move));
            w64(x->player + 0x10, P(x->slot));
            w64(g_team[looked_up()] + 0x18 + 8 * g->id, P(x->player));
        }
        Cpu c;
        memset(&c, 0, sizeof c);
        int32_t out = r.out_before;
        c.x[0] = P(g_rules);
        c.x[1] = P(g_rules + r.entry_off);
        c.x[2] = r.w2;
        c.x[3] = r.has_out ? P(&out) : 0;
        c.sp = P(g_stack + sizeof g_stack - 0x100);
        f_7000d42f20(&c);
        int result = (int)(uint32_t)c.x[0], base = r32(g_rules + r.entry_off + E_BASE);
        int same = result == r.result && base == r.base_after && (!r.has_out || out == r.out_after);
        if (!same && differ++ < 10)
            printf("DIFF call %d: live %d (out %d, base %d), offline %d (out %d, base %d)\n", calls, r.result,
                   r.out_after, r.base_after, result, out, base);
        calls++;
        yes += r.result & 1;
        uint64_t n_out, n_scored;
        memcpy(&n_out, r.rules + R_OUTS_N, 8), memcpy(&n_scored, r.rules + R_SCORED_N, 8);
        with_out_list += n_out != 0, with_scored += n_scored != 0;
        throws += r32(r.rules + r.entry_off + E_TYPE) == 3;
        w2_set += r.w2 & 1;
        rewrote += r32(r.rules + r.entry_off + E_BASE) != r.base_after;
    }
    fclose(f);
    printf("replayed %d recorded calls: %d differ\n", calls, differ);
    printf("  live answers: %d yes, %d no; throw actions %d; batter-only form %d; with someone put out %d, "
           "with someone scored %d, base rewritten %d\n", yes, calls - yes, throws, w2_set, with_out_list, with_scored,
           rewrote);
    return !calls ? 125 : differ > 124 ? 124 : differ;
}

static LONG WINAPI on_fault(EXCEPTION_POINTERS *e) {
    if (e->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    unsigned long long a = e->ExceptionRecord->ExceptionInformation[1];
    printf("access violation reading 0x%llx\n", a);
    fflush(stdout);
    ExitProcess(a == TEAMS_GLOBAL ? 77 : 124);
}

int main(int argc, char **argv) {
    SetUnhandledExceptionFilter(on_fault);
    if (argc > 1 && !strcmp(argv[1], "--no-global")) {
        reset(), put(0, 0, 1, SAFE);
        printf("without the global: returned %d\n", call(1, 1));
        return 1;
    }
    // Windows reserves in 64 KiB steps; commit only the page that holds the global, so any other fixed address faults.
    void *base = (void *)(uintptr_t)(TEAMS_GLOBAL & ~0xffffull);
    void *page = (void *)(uintptr_t)(TEAMS_GLOBAL & ~0xfffull);
    if (VirtualAlloc(base, 0x10000, MEM_RESERVE, PAGE_NOACCESS) != base ||
        VirtualAlloc(page, 0x1000, MEM_COMMIT, PAGE_READWRITE) != page) {
        printf("FATAL: cannot map the game's address 0x%llx (error %lu)\n", TEAMS_GLOBAL, GetLastError());
        return 125;
    }
    w64((uint8_t *)(uintptr_t)TEAMS_GLOBAL, P(g_teams));

    if (argc > 2 && !strcmp(argv[1], "--replay")) return replay(argv[2], argc > 3 && !strcmp(argv[3], "--broken"));

    batter_only();
    any_runner();
    odd_corners();
    side_effects();
    speed();
    CHECK(g_calls_bad == 0);   // stack pointer and saved registers across every call
    printf("%d checks, %d failed\n", g_checks, g_failed);
    return g_failed > 125 ? 125 : g_failed;
}
