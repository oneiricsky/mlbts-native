// fastball: PS5 textures in place of the Switch ones (MLB_HD_TEXTURES).
//
// The game creates each head texture at its Switch size and copies the file's decompressed storage into it; it does not
// take the size from the file. So a texture is recognised when it is uploaded: a hash of the first 16 KiB of its storage
// (the same bytes the file holds once decompressed) finds its entry in the index tools/make_hd_index.py writes, and
// vk_texture.c gives it a bigger image made from the PS5 file of the same name.
//
// The PS5 file (docs/ps5-textures.md): the TX12 container of the Switch files, raw. After the header (file size minus
// the data size at 0x0c) come the levels: 0 and 1 first, then the smaller ones in reverse order (smallest first), each
// level's size in the rows at 0x1a0 (32 bytes each, size at +4, the bytes left after it at +0). Blocks sit in 64-byte
// units along strips four block rows high: 2x4 blocks for 8-byte blocks, 1x4 for 16-byte ones.
//
// MLB_HD_TEXTURES: unset, the "hdtex" folder of the working directory when it has an index.txt; "off" or 0 none; else
// the folder. index.txt: "root <PS5 app folder>", then "<hash> <width> <height> <levels> <drop> <PS5 file>" lines.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "hdtex.h"
#include "platform/platform.h"

struct MlbHdEntry {
    uint64_t hash;
    uint16_t w, h, levels, drop;
    char *path;
};

static MlbHdEntry *entries;
static int nentries;
static char root[1024];
static PlatOnce once = PLAT_ONCE_INIT;

static int cmp_entry(const void *a, const void *b) {
    uint64_t x = ((const MlbHdEntry *)a)->hash, y = ((const MlbHdEntry *)b)->hash;
    return x < y ? -1 : x > y;
}

static void init(void *arg) {
    (void)arg;
    const char *v = cfg_get("MLB_HD_TEXTURES");
    if (v && (!strcmp(v, "off") || !strcmp(v, "0"))) return;
    char path[1100];
    snprintf(path, sizeof path, "%s/index.txt", v && *v ? v : "hdtex");
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[1400];
    int cap = 0;
    while (fgets(line, sizeof line, f)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (!strncmp(line, "root ", 5)) {
            snprintf(root, sizeof root, "%s", line + 5);
            continue;
        }
        unsigned long long h;
        unsigned w, ht, lv, drop;
        int off = 0;
        if (sscanf(line, "%llx %u %u %u %u %n", &h, &w, &ht, &lv, &drop, &off) < 5 || !off) continue;
        if (nentries == cap) {
            cap = cap ? cap * 2 : 64;
            if (!(entries = realloc(entries, sizeof *entries * (size_t)cap))) rt_fatal("hdtex: out of memory");
        }
        entries[nentries++] = (MlbHdEntry){h, (uint16_t)w, (uint16_t)ht, (uint16_t)lv, (uint16_t)drop, _strdup(line + off)};
    }
    fclose(f);
    qsort(entries, (size_t)nentries, sizeof *entries, cmp_entry);
    rt_log("hdtex: %d PS5 textures indexed (%s), from %s", nentries, path, root);
}

int mlb_hd_on(void) {
    plat_once(&once, init, NULL);
    return nentries > 0;
}

int mlb_hd_shape(uint32_t w, uint32_t h, uint32_t levels) {
    if (!mlb_hd_on()) return 0;
    for (int i = 0; i < nentries; i++)
        if (entries[i].w == w && entries[i].h == h && entries[i].levels == levels) return 1;
    return 0;
}

const MlbHdEntry *mlb_hd_find(const void *storage, size_t size, uint32_t w, uint32_t h, uint32_t levels) {
    if (!mlb_hd_on() || !storage) return NULL;
    size_t n = size < 16384 ? size : 16384;
    const uint8_t *p = storage;
    uint64_t hash = 0xcbf29ce484222325ull;
    for (size_t i = 0; i < n; i++) hash = (hash ^ p[i]) * 0x100000001b3ull;
    MlbHdEntry key = {.hash = hash};
    const MlbHdEntry *e = bsearch(&key, entries, (size_t)nentries, sizeof *entries, cmp_entry);
    if (!e || e->w != w || e->h != h || e->levels != levels) return NULL;
    return e;
}

uint64_t mlb_hd_hash(const MlbHdEntry *e) { return e->hash; }
const char *mlb_hd_name(const MlbHdEntry *e) { return e->path; }

static uint32_t rd32(const uint8_t *d, size_t o) { return d[o] | d[o + 1] << 8 | d[o + 2] << 16 | (uint32_t)d[o + 3] << 24; }
static uint32_t blk4(uint32_t s) { return (s + 3) / 4; }
static uint32_t mip(uint32_t s, unsigned l) { s >>= l; return s ? s : 1; }

// One PS5 level's bytes into plain block rows (lh rows of lw blocks).
static void level_to_rows(const uint8_t *src, size_t srclen, uint32_t lw, uint32_t lh, uint32_t bpb, uint8_t *dst) {
    uint32_t uw = bpb == 8 ? 2 : 1, upr = (lw + uw - 1) / uw, rows = blk4(lh) * 4;
    memset(dst, 0, (size_t)lw * lh * bpb);
    size_t n = (size_t)upr * uw * rows;
    for (size_t i = 0; i < n; i++) {
        size_t unit = i / (4 * uw), within = i % (4 * uw);
        uint32_t bx = (uint32_t)(unit % upr) * uw + (uint32_t)(within % uw), by = (uint32_t)(unit / upr) * 4 + (uint32_t)(within / uw);
        if (bx < lw && by < lh && (i + 1) * bpb <= srclen) memcpy(dst + ((size_t)by * lw + bx) * bpb, src + i * bpb, bpb);
    }
}

// A file that cannot be read (the dump's drive gone) is tried again at every upload of its texture: logged a few times.
static void fail(const char *fmt, const char *path) {
    static volatile int32_t n;
    if (__atomic_add_fetch(&n, 1, __ATOMIC_RELAXED) <= 8) rt_log(fmt, path);
}

int mlb_hd_load(const MlbHdEntry *e, MlbHdTex *out) {
    memset(out, 0, sizeof *out);
    char path[1500];
    snprintf(path, sizeof path, "%s/%s", root, e->path);
    FILE *f = fopen(path, "rb");
    if (!f) { fail("hdtex: cannot open %s", path); return 0; }
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    // The header (the level table ends below 0x3a0), then only the bytes of the levels the image keeps: the largest level
    // comes first in the file and is the bulk of it, and the drive of the dump is slow (35 ms a file read whole).
    uint8_t d[0x400];
    size_t hn = (size_t)len < sizeof d ? (size_t)len : sizeof d;
    if (len < 0 || fread(d, 1, hn, f) != hn) { fclose(f); fail("hdtex: cannot read %s", path); return 0; }
    int ok = 0;
    uint8_t *body = NULL;
    uint32_t sizes[16], offs[16];
    do {
        if (len < 0x1a0 + 32 || memcmp(d, "TX12PS5", 8)) { rt_log("hdtex: %s is not a PS5 texture", path); break; }
        uint32_t data = rd32(d, 0x0c), nm = rd32(d, 0x8c), code = rd32(d, 0x15c) & 0xFFFF;
        uint32_t W = d[0x84] | d[0x85] << 8, H = d[0x86] | d[0x87] << 8;
        if (nm < 2 || nm > 16 || (size_t)len < data || 0x1a0 + 32u * nm > (size_t)len - data) { rt_log("hdtex: %s: odd header", path); break; }
        size_t hs = (size_t)len - data;
        uint64_t sum = 0;
        for (uint32_t i = 0; i < nm; i++) sum += sizes[i] = rd32(d, 0x1a0 + 32u * i + 4);
        uint32_t bpb = sizes[0] / (blk4(W) * blk4(H));
        if (sum != data || (bpb != 8 && bpb != 16) || sizes[0] != blk4(W) * blk4(H) * bpb || (bpb == 16) != (code == 22) ||
            (bpb == 8 && code != 13)) {
            rt_log("hdtex: %s: %ux%u, %u-byte blocks, format code %u: not handled", path, W, H, bpb, code);
            break;
        }
        offs[0] = 0, offs[1] = sizes[0];
        uint32_t t = sizes[0] + sizes[1], tail = 0, run = 0;
        for (uint32_t i = 2; i < nm; i++) tail += sizes[i];
        for (uint32_t i = 2; i < nm; i++) run += sizes[i], offs[i] = t + tail - run;
        uint32_t drop = e->drop;
        if (drop >= nm) { rt_log("hdtex: %s: drop %u leaves no level", path, drop); break; }
        size_t lo = (size_t)-1, hi = 0;
        for (uint32_t i = drop; i < nm; i++) {
            if (offs[i] < lo) lo = offs[i];
            if ((size_t)offs[i] + sizes[i] > hi) hi = (size_t)offs[i] + sizes[i];
        }
        if (hs + hi > (size_t)len) { rt_log("hdtex: %s: levels outside the file", path); break; }
        body = malloc(hi - lo);
        if (!body || fseek(f, (long)(hs + lo), SEEK_SET) || fread(body, 1, hi - lo, f) != hi - lo) { fail("hdtex: cannot read %s", path); break; }
        out->width = mip(W, drop), out->height = mip(H, drop), out->levels = nm - drop, out->bpb = bpb;
        size_t total = 0;
        for (uint32_t l = 0; l < out->levels; l++) {
            out->lw[l] = blk4(mip(out->width, l)), out->lh[l] = blk4(mip(out->height, l));
            out->off[l] = total;
            total += (((size_t)out->lw[l] * out->lh[l] * bpb) + 15) & ~(size_t)15;
        }
        out->data = calloc(1, total);
        if (!out->data) rt_fatal("hdtex: out of memory");
        out->size = total;
        for (uint32_t l = 0; l < out->levels; l++)
            level_to_rows(body + (offs[drop + l] - lo), sizes[drop + l], out->lw[l], out->lh[l], bpb, out->data + out->off[l]);
        ok = out->levels > 0;
    } while (0);
    fclose(f);
    free(body);
    if (!ok) mlb_hd_free(out);
    return ok;
}

void mlb_hd_free(MlbHdTex *t) {
    free(t->data);
    memset(t, 0, sizeof *t);
}
