// Checks runtime/mlb/hdtex.c against every head texture of the game, without the game and without a GPU: each Switch
// file is decompressed into the "storage" the game would upload, and the real lookup and PS5 loader run on it.
//
//   mkdir -p work/scratch
//   "C:/Program Files/LLVM/bin/clang.exe" -O2 -Wall -std=gnu11 -D_CRT_SECURE_NO_WARNINGS -I runtime/mlb \
//       -I runtime/core -o work/scratch/hdtex_test.exe tools/hdtex_test.c
//   work/scratch/hdtex_test.exe work/build/hdtex work/build/game/romfs
//
// (from the repository root, in bash). Needs the PS5 dump the index names. Each head is looked up as in a match that
// opened only that head's two files. The exit code is 0 when every check passes.
#include <stdarg.h>
#include <windows.h>

#include "../runtime/mlb/hdtex.c"

// ---- stand-ins for the runtime functions hdtex.c calls
static const char *g_index;
static int g_logs;
const char *cfg_get(const char *name) { return strcmp(name, "MLB_HD_TEXTURES") ? NULL : g_index; }
int cfg_bool(const char *name) { (void)name; return 0; }   // no prefetch thread
void rt_log(const char *fmt, ...) {
    if (++g_logs > 12) return;
    va_list a;
    va_start(a, fmt);
    printf("  log: "), vprintf(fmt, a), printf("\n");
    va_end(a);
}
void rt_fatal(const char *fmt, ...) {
    va_list a;
    va_start(a, fmt);
    vprintf(fmt, a);
    exit(2);
}
void plat_once(PlatOnce *o, void (*fn)(void *), void *arg) {
    static int done;
    (void)o;
    if (!done) done = 1, fn(arg);
}
void plat_mutex_lock(PlatMutex *m) { (void)m; }
void plat_mutex_unlock(PlatMutex *m) { (void)m; }
void plat_cond_wait(PlatCond *c, PlatMutex *m) { (void)c, (void)m; }
void plat_cond_signal(PlatCond *c) { (void)c; }
int plat_thread_spawn(PlatThreadFn fn, void *arg, const char *name, size_t stack) {
    (void)fn, (void)arg, (void)name, (void)stack;
    return 0;
}
void plat_thread_priority(int prio) { (void)prio; }
uint64_t plat_now_ns(void) { return GetTickCount64() * 1000000ull; }

static int g_failed;
#define CHECK(x, ...)                                                     \
    do {                                                                  \
        if (!(x)) {                                                       \
            if (++g_failed <= 20) printf("FAIL %d: ", __LINE__), printf(__VA_ARGS__), printf("\n"); \
        }                                                                 \
    } while (0)

static uint8_t *read_file(const char *path, size_t *n) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    *n = (size_t)ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *d = malloc(*n ? *n : 1);
    if (fread(d, 1, *n, f) != *n) free(d), d = NULL;
    fclose(f);
    return d;
}

static void lz4(const uint8_t *s, uint8_t *d, size_t want) {
    size_t i = 0, o = 0;
    while (o < want) {
        unsigned t = s[i++], b;
        size_t lit = t >> 4, ml = t & 15;
        if (lit == 15) do lit += b = s[i++]; while (b == 255);
        for (; lit && o < want; lit--) d[o++] = s[i++];
        if (o >= want) break;
        size_t off = s[i] | s[i + 1] << 8;
        i += 2;
        if (ml == 15) do ml += b = s[i++]; while (b == 255);
        for (ml += 4; ml && o < want; ml--, o++) d[o] = d[o - off];
    }
}

// The texture data of two PS5 files is the same (the headers differ by the name).
static int same_ps5(const char *a, const char *b) {
    char pa[1500], pb[1500];
    snprintf(pa, sizeof pa, "%s/%s", root, a);
    snprintf(pb, sizeof pb, "%s/%s", root, b);
    size_t na, nb;
    uint8_t *da = read_file(pa, &na), *db = read_file(pb, &nb);
    int same = da && db && na == nb && na > 1440 && !memcmp(da + 1440, db + 1440, na - 1440);
    free(da), free(db);
    return same;
}

static void open_head(const char *name) {
    char p[600];
    for (int k = 0; k < 2; k++) {
        snprintf(p, sizeof p, "FS_Rom:/NSW/CHARACTERS/HEADS/%s/%s-%s.TEX", name, name, k ? "NORMAL" : "COLOR");
        rt_host_opened(p);
    }
}
static void close_all(void) {
    for (int i = 0; i < nentries; i++) entries[i].opened = 0;
}

int main(int argc, char **argv) {
    if (argc != 3) return printf("usage: hdtex_test <index folder> <romfs folder>\n"), 2;
    g_index = argv[1];
    if (!mlb_hd_on()) return printf("no index in %s\n", g_index), 2;
    uint8_t *loaded = calloc((size_t)nentries, 1);
    char dir[1200];
    snprintf(dir, sizeof dir, "%s/NSW/CHARACTERS/HEADS/*", argv[2]);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(dir, &fd);
    if (h == INVALID_HANDLE_VALUE) return printf("no heads under %s\n", argv[2]), 2;
    int heads = 0, textures[2] = {0}, exact[2] = {0}, twin[2] = {0}, switch_kept[2] = {0}, nload = 0, tail_checked = 0,
        by_open = 0;
    do {
        if (fd.cFileName[0] == '.') continue;
        heads++;
        for (int k = 0; k < 2; k++) {
            const char *kind = k ? "NORMAL" : "COLOR";
            char path[1500], want[600];
            snprintf(path, sizeof path, "%s/NSW/CHARACTERS/HEADS/%s/%s-%s.TEX", argv[2], fd.cFileName, fd.cFileName, kind);
            snprintf(want, sizeof want, "PS5/CHARACTERS/HEADS/%s/%s-%s.TEX", fd.cFileName, fd.cFileName, kind);
            size_t n;
            uint8_t *d = read_file(path, &n);
            if (!d) continue;
            uint32_t hs = rd32(d, 0x154), nv = rd32(d, 0x170);
            for (uint32_t v = 0; v < nv && v < 2; v++) {
                // One LZ4 block per segment; the first variant of two is its own block followed by the second's.
                uint32_t total = rd32(d, v ? 0x104 : 0x10), at = v ? rd32(d, 0x10c) : 0, dim = v ? 0xa4 : 0x84;
                uint32_t head = nv == 2 && !v ? total - rd32(d, 0x104) : total;
                uint32_t w = d[dim] | d[dim + 1] << 8, ht = d[dim + 2] | d[dim + 3] << 8, lv = rd32(d, v ? 0xac : 0x8c);
                size_t size = (size_t)total + 4096;   // storage beyond the file's bytes: must not matter
                uint8_t *st = malloc(size);
                memset(st, 0xAA, size);
                lz4(d + hs + at, st, head);
                if (head < total) lz4(d + hs + rd32(d, 0x10c), st + head, total - head);
                textures[k]++;
                CHECK(mlb_hd_shape(w, ht, lv), "%s v%u: shape %ux%u/%u not in the index", want, v, w, ht, lv);
                close_all();
                const MlbHdEntry *cold = mlb_hd_find(st, size, w, ht, lv);
                open_head(fd.cFileName);
                const MlbHdEntry *e = mlb_hd_find(st, size, w, ht, lv);
                DWORD has_ps5;
                char ps5[1500];
                snprintf(ps5, sizeof ps5, "%s/%s", root, want);
                has_ps5 = GetFileAttributesA(ps5) != INVALID_FILE_ATTRIBUTES;
                if (!e) {
                    switch_kept[k]++;
                    CHECK(!has_ps5, "%s v%u: has a PS5 file and was not found", want, v);
                } else if (!strcmp(e->path, want)) {
                    exact[k]++;
                } else {
                    twin[k]++;
                    CHECK(has_ps5 && same_ps5(e->path, want), "%s v%u: got %s, another picture", want, v, e->path);
                }
                if (e && !cold) {   // told apart only by the opened file: with two candidates open it must stay Switch
                    by_open++;
                    close_all();
                    for (int i = 0; i < nentries; i++)
                        if (entries[i].hash == e->hash) entries[i].opened = 1;
                    CHECK(!mlb_hd_find(st, size, w, ht, lv), "%s v%u: two candidates open, still replaced", want, v);
                }
                if (e && e->full_len) {   // the whole-storage hash decides: one changed byte past 16 KiB, no match
                    tail_checked++;
                    st[e->full_len - 1] ^= 1;
                    CHECK(!mlb_hd_find(st, size, w, ht, lv), "%s v%u: a changed storage still matched", want, v);
                    CHECK(!mlb_hd_find(st, e->full_len - 1, w, ht, lv), "%s v%u: matched a storage too short", want, v);
                }
                if (e && !loaded[e - entries]) {
                    loaded[e - entries] = 1;
                    MlbHdTex t;
                    int ok = mlb_hd_load(e, &t);
                    CHECK(ok, "%s: does not load", e->path);
                    if (ok) {
                        nload++;
                        CHECK(t.width == 1024 && t.height == 512 && t.levels == 10 && t.bpb == 16, "%s: %ux%u, %u levels, %u",
                              e->path, t.width, t.height, t.levels, t.bpb);
                        mlb_hd_free(&t);
                    }
                }
                free(st);
            }
            free(d);
        }
    } while (FindNextFileA(h, &fd));
    FindClose(h);
    printf("%d head folders, %d index lines\n", heads, nentries);
    for (int k = 0; k < 2; k++)
        printf("%s: %d Switch textures: %d got their own PS5 file, %d an identical twin's, %d stay Switch\n",
               k ? "NORMAL" : "COLOR", textures[k], exact[k], twin[k], switch_kept[k]);
    printf("%d needed the opened file, %d checked against a changed storage, %d index lines loaded\n", by_open,
           tail_checked, nload);

    // the fallback: a dump that is gone loads nothing
    MlbHdTex t;
    snprintf(root, sizeof root, "%s", "Z:/no-such-dump");
    CHECK(!mlb_hd_load(&entries[0], &t) && !t.data, "a missing PS5 file loaded");
    printf("%s (%d failed checks)\n", g_failed ? "FAIL" : "PASS", g_failed);
    return g_failed != 0;
}
