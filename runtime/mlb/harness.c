// Dev harness core: scenario file, team override, markers, texture dump, clean stop. See harness.h for the format.
// Whole file is compiled only with MLB_DEV_HARNESS (dev builds); release builds never contain it.
#ifdef MLB_DEV_HARNESS
#include "harness.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"
#include "sha256.h"

void gfx_window_request_close(void);   // gfx_window_win.c: as the window's close button, exit code 0

#define OPT_PTR_ADDR 0x7004651350ull   // pointer to the game's match-settings struct (main + 0x4651350, game 1.0.20)

static HarnessScenario g_sc = {.name = "run", .home = -1, .away = -1, .markers = 1};
static int g_active;
static uint64_t g_t0;
static volatile LONG g_frame, g_stop, g_filled, g_dump_seq;
static volatile uint64_t g_opt;   // address of the match-settings struct once filled
static char g_stop_why[96];
static CRITICAL_SECTION g_lock;

static double now_s(void) { return (double)(plat_now_ns() - g_t0) / 1e9; }

int harness_active(void) { return g_active; }
const HarnessScenario *harness_scenario(void) { return &g_sc; }
int harness_match_settings_filled(void) { return g_filled; }
void harness_frame_tick(void) { if (g_active) InterlockedIncrement(&g_frame); }

static char *trim(char *s) {
    while (isspace((unsigned char)*s)) s++;
    char *e = s + strlen(s);
    while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
    return s;
}

static int parse_dump(const char *v, HarnessDump *d, HarnessScenario *sc, int ln) {
    memset(d, 0, sizeof *d);
    d->count = 1;
    const char *colon = strchr(v, ':');
    if (!colon) return -1;
    if (!strncmp(v, "texture", colon - v) && colon - v == 7) d->is_buffer = 0;
    else if (!strncmp(v, "buffer", colon - v) && colon - v == 6) d->is_buffer = 1;
    else return -1;
    char tmp[256];
    snprintf(tmp, sizeof tmp, "%s", colon + 1);
    for (char *p = tmp, *next; p && *p; p = next) {
        next = strchr(p, ',');
        if (next) *next++ = 0;
        char *eq = strchr(p, '=');
        if (!eq) return -1;
        *eq = 0;
        const char *k = trim(p), *val = trim(eq + 1);
        char *end;
        if (!strcmp(k, "fmt") && !d->is_buffer) d->fmt = (unsigned)strtoul(val, &end, 0), d->has_fmt = 1;
        else if (!strcmp(k, "size") && !d->is_buffer) {
            if (sscanf(val, "%ux%u", &d->w, &d->h) != 2) return -1;
            d->has_size = 1;
        } else if (!strcmp(k, "count") && !d->is_buffer) d->count = (unsigned)strtoul(val, &end, 0);
        else if (!strcmp(k, "addr") && d->is_buffer) d->addr = strtoull(val, &end, 0);
        else if (!strcmp(k, "size") && d->is_buffer) d->size = strtoull(val, &end, 0);
        else if (!strcmp(k, "at") && d->is_buffer) snprintf(d->at, sizeof d->at, "%s", val);
        else {
            rt_log("harness: %s line %d: unknown dump option '%s'", sc->path, ln, k);
            sc->errors++;
        }
    }
    if (d->is_buffer && (!d->addr || !d->size)) return -1;
    return 0;
}

static void bad(HarnessScenario *sc, int ln, const char *key, const char *val) {
    rt_log("harness: %s line %d: bad value '%s' for %s", sc->path, ln, val, key);
    sc->errors++;
}

int harness_parse_file(const char *path, HarnessScenario *sc) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    *sc = (HarnessScenario){.name = "run", .home = -1, .away = -1, .markers = 1};
    snprintf(sc->path, sizeof sc->path, "%s", path);
    char line[512];
    for (int ln = 1; fgets(line, sizeof line, f); ln++) {
        char *s = trim(line);
        if (!*s || *s == '#') continue;
        char *eq = strchr(s, '=');
        if (!eq) {
            rt_log("harness: %s line %d: no '=' in '%s'", path, ln, s);
            sc->errors++;
            continue;
        }
        *eq = 0;
        const char *k = trim(s), *v = trim(eq + 1);
        char *end;
        if (!strcmp(k, "name")) {
            int ok = *v != 0;
            for (const char *c = v; *c; c++) ok &= isalnum((unsigned char)*c) || *c == '_' || *c == '-' || *c == '.';
            if (ok) snprintf(sc->name, sizeof sc->name, "%s", v); else bad(sc, ln, k, v);
        } else if (!strcmp(k, "home") || !strcmp(k, "away")) {
            long t = strtol(v, &end, 10);
            if (*v && !*end && t >= 0 && t <= 29) *(k[0] == 'h' ? &sc->home : &sc->away) = (int)t; else bad(sc, ln, k, v);
        } else if (!strcmp(k, "seed")) {
            sc->seed = strtoull(v, &end, 0);
            if (*v && !*end) sc->has_seed = 1; else bad(sc, ln, k, v);
        } else if (!strcmp(k, "fixed_clock")) {
            if (!strcmp(v, "0") || !strcmp(v, "1")) sc->fixed_clock = *v - '0'; else bad(sc, ln, k, v);
        } else if (!strcmp(k, "stop_after_s")) {
            sc->stop_after_s = strtod(v, &end);
            if (!*v || *end || sc->stop_after_s < 0) { sc->stop_after_s = 0; bad(sc, ln, k, v); }
        } else if (!strcmp(k, "stop_at_marker")) {
            snprintf(sc->stop_at_marker, sizeof sc->stop_at_marker, "%s", v);
        } else if (!strcmp(k, "markers")) {
            if (!strcmp(v, "log")) sc->markers = 1; else if (!strcmp(v, "off")) sc->markers = 0; else bad(sc, ln, k, v);
        } else if (!strcmp(k, "dump")) {
            if (sc->ndump >= HARNESS_MAX_DUMPS) { rt_log("harness: %s line %d: too many dumps", path, ln); sc->errors++; }
            else if (parse_dump(v, &sc->dump[sc->ndump], sc, ln) == 0) sc->ndump++;
            else bad(sc, ln, k, v);
        } else {
            rt_log("harness: %s line %d: unknown key '%s'", path, ln, k);
            sc->errors++;
        }
    }
    fclose(f);
    return 0;
}

static void mkdirs(const char *dir) {
    char p[512];
    snprintf(p, sizeof p, "%s", dir);
    for (char *c = p + 1; *c; c++)
        if (*c == '/' || *c == '\\') { char o = *c; *c = 0; CreateDirectoryA(p, NULL); *c = o; }
    CreateDirectoryA(p, NULL);
}

// <out>/<name>-<n>.raw and .sha256 (sha256sum format); returns the hex digest in hex[65].
static void write_dump(const void *data, uint64_t bytes, char hex[65], const char *what) {
    const char *out = cfg_get("MLB_HARNESS_OUT");
    char dir[400], base[480], path[520];
    snprintf(dir, sizeof dir, "%s", out && *out ? out : "harness-out");
    mkdirs(dir);
    int n = (int)InterlockedIncrement(&g_dump_seq) - 1;
    snprintf(base, sizeof base, "%s/%s-%d", dir, g_sc.name, n);
    uint8_t h[32];
    sha256(data, (size_t)bytes, h);
    for (int i = 0; i < 32; i++) sprintf(hex + i * 2, "%02x", h[i]);
    snprintf(path, sizeof path, "%s.raw", base);
    FILE *f = fopen(path, "wb");
    if (!f || fwrite(data, 1, (size_t)bytes, f) != bytes) rt_log("harness: cannot write %s", path);
    if (f) fclose(f);
    snprintf(path, sizeof path, "%s.sha256", base);
    f = fopen(path, "wb");
    if (f) { fprintf(f, "%s  %s-%d.raw\n", hex, g_sc.name, n); fclose(f); }
    uint64_t sum = 0, nz = 0;
    for (uint64_t i = 0; i < bytes; i++) sum += ((const uint8_t *)data)[i], nz += ((const uint8_t *)data)[i] != 0;
    rt_log("harness: dump %s %s-%d.raw bytes %llu sum %llu nonzero %llu sha256 %s", what, g_sc.name, n,
           (unsigned long long)bytes, (unsigned long long)sum, (unsigned long long)nz, hex);
}

static void dump_buffers(const char *marker) {   // marker NULL: at stop
    for (int i = 0; i < g_sc.ndump; i++) {
        HarnessDump *d = &g_sc.dump[i];
        if (!d->is_buffer || d->done) continue;
        if (marker ? strcmp(d->at, marker) : d->at[0]) continue;
        d->done = 1;
        if (!plat_mem_readable(d->addr, d->size)) { rt_log("harness: buffer %#llx not readable", (unsigned long long)d->addr); continue; }
        char hex[65];
        write_dump((const void *)(uintptr_t)d->addr, d->size, hex, "buffer");
    }
}

void harness_request_stop(const char *why) {
    if (!g_active || InterlockedCompareExchange(&g_stop, 1, 0)) return;
    snprintf(g_stop_why, sizeof g_stop_why, "%s", why);
}

void harness_marker(const char *name) {
    if (!g_active) return;
    if (g_sc.markers) rt_log("harness: marker %s frame %ld t %.3f", name, (long)g_frame, now_s());
    EnterCriticalSection(&g_lock);
    dump_buffers(name);
    LeaveCriticalSection(&g_lock);
    if (g_sc.stop_at_marker[0] && !strcmp(name, g_sc.stop_at_marker)) harness_request_stop(name);
}

void harness_texture_write(unsigned fmt, unsigned w, unsigned h, const void *data, uint64_t bytes) {
    if (!g_active) return;
    for (int i = 0; i < g_sc.ndump && data; i++) {
        HarnessDump *d = &g_sc.dump[i];
        if (d->is_buffer || d->done >= d->count) continue;
        if ((d->has_fmt && d->fmt != fmt) || (d->has_size && (d->w != w || d->h != h))) continue;
        EnterCriticalSection(&g_lock);
        if (d->done < d->count) {
            d->done++;
            char hex[65];
            write_dump(data, bytes, hex, "texture");
        }
        LeaveCriticalSection(&g_lock);
    }
    if (fmt == 0x25 && w == 512 && h == 512) harness_marker("field_texture");
}

// Every copy of the team in the match-settings struct; one copy alone gave Dodger Stadium with wrong uniforms.
static void write_teams(uint8_t *o) {
    if (g_sc.home >= 0) o[0x3f] = o[0x47] = o[0x59] = (uint8_t)g_sc.home;
    if (g_sc.away >= 0) o[0x40] = o[0x52] = o[0x54] = o[0x56] = (uint8_t)g_sc.away;
    rt_log("harness: teams home %d away %d written into the match settings at %#llx", o[0x3f], o[0x40],
           (unsigned long long)(uintptr_t)o);
}

void harness_set_teams(int home, int away) {
    if (!g_active) return;
    if (home >= 0 && home <= 29) g_sc.home = home;
    if (away >= 0 && away <= 29) g_sc.away = away;
    if (g_opt) write_teams((uint8_t *)(uintptr_t)g_opt);
}

static DWORD WINAPI watcher(void *arg) {
    (void)arg;
    for (;;) {
        Sleep(2);
        if (!g_filled && plat_mem_readable(OPT_PTR_ADDR, 8)) {
            uint64_t p = *(const uint64_t *)(uintptr_t)OPT_PTR_ADDR;
            // the burst's last field is set and the home team still holds the game's default (LAD): filled, not yet ours
            if (p && plat_mem_readable(p, 0x100) && ((uint8_t *)(uintptr_t)p)[0xff] == 1 && ((uint8_t *)(uintptr_t)p)[0x3f] == 27) {
                g_opt = p;
                InterlockedExchange(&g_filled, 1);
                if (g_sc.home >= 0 || g_sc.away >= 0) write_teams((uint8_t *)(uintptr_t)p);
                harness_marker("match_settings");
            }
        }
        if (!g_stop && g_sc.stop_after_s > 0 && now_s() >= g_sc.stop_after_s) harness_request_stop("stop_after_s");
        if (g_stop) break;
    }
    rt_log("harness: stopping (%s)", g_stop_why);
    harness_marker("stop");
    EnterCriticalSection(&g_lock);
    dump_buffers(NULL);
    LeaveCriticalSection(&g_lock);
    gfx_window_request_close();
    Sleep(20000);
    rt_log("harness: clean stop did not finish in 20 s; forcing exit 4");
    plat_exit(4);
}

void harness_init(void) {
    if (g_active) return;
    const char *path = cfg_get("MLB_HARNESS"), *h = cfg_get("MLB_HARNESS_HOME"), *a = cfg_get("MLB_HARNESS_AWAY");
    if (!(path && *path) && !(h && *h) && !(a && *a)) return;
    InitializeCriticalSection(&g_lock);
    g_t0 = plat_now_ns();
    if (path && *path && harness_parse_file(path, &g_sc) != 0) {
        rt_log("harness: cannot read scenario %s", path);
        plat_exit(2);
    }
    if (g_sc.home < 0 && h && *h) g_sc.home = atoi(h);   // a scenario key wins over the env
    if (g_sc.away < 0 && a && *a) g_sc.away = atoi(a);
    g_active = 1;
    rt_log("harness: scenario '%s' (%s) home %d away %d seed %s fixed_clock %d stop_after_s %.1f stop_at_marker '%s' dumps %d errors %d",
           g_sc.name, g_sc.path[0] ? g_sc.path : "env only", g_sc.home, g_sc.away, g_sc.has_seed ? "set" : "unset",
           g_sc.fixed_clock, g_sc.stop_after_s, g_sc.stop_at_marker, g_sc.ndump, g_sc.errors);
    harness_marker("boot");
    CreateThread(NULL, 0, watcher, NULL, 0, NULL);
}

#endif
