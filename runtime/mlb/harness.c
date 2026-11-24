// Dev harness core: scenario file, team override, markers, frame log, dumps, clean stop. See harness.h for the format.
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
#define MAX_BUFFER (64u << 20)         // a buffer dump's limit in bytes: a typo must not fill the disk

static HarnessScenario g_sc = {.name = "run", .home = -1, .away = -1, .markers = 1};
static int g_active;   // a scenario or the env team override is set
static int g_on;       // harness_init ran (dev build): markers, frame log and dump_now work without a scenario
static uint64_t g_t0;
static volatile LONG g_frame, g_stop, g_filled, g_dump_seq;
static volatile uint64_t g_opt;   // address of the match-settings struct once filled
static char g_stop_why[96];       // g_lock; complete once g_stop is set
static CRITICAL_SECTION g_lock;     // the dump list and the stop: harness_dump_now against texture writes and the watcher
static CRITICAL_SECTION g_fl_lock;  // the frame log's stream, in a lock of its own: the present thread never waits for a dump

static double now_s(void) { return (double)(plat_now_ns() - g_t0) / 1e9; }

int harness_active(void) { return g_active; }
const HarnessScenario *harness_scenario(void) { return &g_sc; }
int harness_match_settings_filled(void) { return g_filled; }

// ---- frame log. The frame tick runs on the present thread, markers on any thread, start and stop on the dev panel's
// thread or the watcher's. g_fl is read without the lock only to skip it; every use of the stream is under g_fl_lock,
// and a stop clears g_fl under that lock before it closes the stream, so nothing uses it after fclose.
static FILE *volatile g_fl;   // NULL when off: the per-frame cost is one pointer test
static uint64_t g_fl_last;    // plat_now_ns of the last line written

void harness_frame_tick(void) {
    if (!g_on) return;
    LONG n = InterlockedIncrement(&g_frame);
    if (!g_fl) return;
    EnterCriticalSection(&g_fl_lock);
    if (g_fl) {
        uint64_t t = plat_now_ns();
        fprintf(g_fl, "frame %ld t %.4f dt_ms %.3f\n", (long)n, (double)(t - g_t0) / 1e9,
                g_fl_last ? (double)(t - g_fl_last) / 1e6 : 0.0);
        g_fl_last = t;
        if (!(n & 0xff)) fflush(g_fl);   // every 256 frames: a crash or a forced exit loses at most 4 s at 60 fps
    }
    LeaveCriticalSection(&g_fl_lock);
}

void harness_framelog_stop(void) {
    if (!g_on) return;
    EnterCriticalSection(&g_fl_lock);
    FILE *f = g_fl;   // the hand-over: from here only this thread can reach the stream
    g_fl = NULL;
    LeaveCriticalSection(&g_fl_lock);
    if (f) { fclose(f); rt_log("harness: framelog stopped"); }
}

// exit() closes the streams after the atexit handlers while other threads may still present: ours is closed first
static void framelog_atexit(void) { harness_framelog_stop(); }

int harness_framelog_start(const char *path) {
    if (!g_on || !path || !*path) return 0;
    if (g_fl) { rt_log("harness: framelog not started (%s): one is running", path); return 0; }
    FILE *f = fopen(path, "wb");
    if (!f) { rt_log("harness: framelog cannot open %s", path); return 0; }
    setvbuf(f, NULL, _IOFBF, 1 << 16);
    fprintf(f, "# harness framelog v1; t = seconds since boot\n# frame <n> t <s> dt_ms <ms since the previous frame>\n# marker <name> frame <n> t <s>\n");
    EnterCriticalSection(&g_fl_lock);
    int ok = !g_fl;   // a second start that raced this one loses
    if (ok) { g_fl_last = 0; g_fl = f; }
    LeaveCriticalSection(&g_fl_lock);
    if (ok) atexit(framelog_atexit);
    else fclose(f);
    rt_log(ok ? "harness: framelog started %s" : "harness: framelog not started (%s): one is running", path);
    return ok;
}

int harness_framelog_active(void) { return g_fl != NULL; }

// ---- scenario file
static char *trim(char *s) {
    while (isspace((unsigned char)*s)) s++;
    char *e = s + strlen(s);
    while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
    return s;
}

// logs the line and the key; the return ends the caller
static int bad(HarnessScenario *sc, const char *where, const char *key, const char *val) {
    rt_log("harness: %s: bad value '%s' for %s", where, val, key);
    sc->errors++;
    return -1;
}

// The whole of val as one number (base 0) from min to max: 1 ok. "-1" wraps to a huge number and fails.
static int num(const char *val, uint64_t min, uint64_t max, uint64_t *out) {
    if (!*val) return 0;
    char *end;
    uint64_t n = strtoull(val, &end, 0);
    if (*end || n < min || n > max) return 0;
    *out = n;
    return 1;
}

// "texture:fmt=0x25,size=512x512[,count=N]" or "buffer:addr=0x7004651350,size=256[,at=<marker>]" into d. 0 ok; else -1
// with the problem logged under where (`<file> line <n>`, or `dump_now`): a bad value or an unknown option.
static int parse_dump(const char *v, HarnessDump *d, HarnessScenario *sc, const char *where) {
    memset(d, 0, sizeof *d);
    d->count = 1;
    char tmp[256];
    snprintf(tmp, sizeof tmp, "%s", v);
    char *colon = strchr(tmp, ':');
    if (!colon) return bad(sc, where, "dump", v);
    *colon = 0;
    if (!strcmp(tmp, "texture")) d->is_buffer = 0;
    else if (!strcmp(tmp, "buffer")) d->is_buffer = 1;
    else return bad(sc, where, "dump", tmp);
    if (!colon[1]) return bad(sc, where, "dump", v);   // a dump with nothing to match dumps anything
    for (char *p = colon + 1, *next; p; p = next) {
        next = strchr(p, ',');
        if (next) *next++ = 0;
        char *eq = strchr(p, '=');
        if (!eq || !*(eq + 1)) return bad(sc, where, "dump option", p);
        *eq = 0;
        const char *k = trim(p), *val = trim(eq + 1);
        uint64_t n;
        if (!strcmp(k, "fmt") && !d->is_buffer) {
            if (!num(val, 1, 0x7fffffff, &n)) return bad(sc, where, k, val);
            d->fmt = (unsigned)n, d->has_fmt = 1;
        } else if (!strcmp(k, "size") && !d->is_buffer) {
            unsigned w, h;
            int used = 0;
            if (sscanf(val, "%ux%u%n", &w, &h, &used) != 2 || val[used] || !w || !h || w > 65536 || h > 65536)
                return bad(sc, where, k, val);
            d->w = w, d->h = h, d->has_size = 1;
        } else if (!strcmp(k, "count") && !d->is_buffer) {
            if (!num(val, 1, 1000, &n)) return bad(sc, where, k, val);
            d->count = (unsigned)n;
        } else if (!strcmp(k, "addr") && d->is_buffer) {
            if (!num(val, 1, 0xffffffffffffull, &n)) return bad(sc, where, k, val);
            d->addr = n;
        } else if (!strcmp(k, "size") && d->is_buffer) {
            if (!num(val, 1, MAX_BUFFER, &n)) return bad(sc, where, k, val);
            d->size = n;
        } else if (!strcmp(k, "at") && d->is_buffer) {
            snprintf(d->at, sizeof d->at, "%s", val);
        } else {
            rt_log("harness: %s: unknown dump option '%s' in a %s dump", where, k, d->is_buffer ? "buffer" : "texture");
            sc->errors++;
            return -1;
        }
    }
    if (d->is_buffer && (!d->addr || !d->size)) return bad(sc, where, "dump", v);
    return 0;
}

// "0".."29" or empty into out: 1 when it is a team, 0 (reported) otherwise
static int team(const char *v, int *out) {
    char *end;
    long t = *v ? strtol(v, &end, 10) : -1;
    if (*v && !*end && t >= 0 && t <= 29) { *out = (int)t; return 1; }
    return 0;
}

int harness_parse_file(const char *path, HarnessScenario *sc) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    *sc = (HarnessScenario){.name = "run", .home = -1, .away = -1, .markers = 1};
    snprintf(sc->path, sizeof sc->path, "%s", path);
    char line[512], where[600];
    for (int ln = 1; fgets(line, sizeof line, f); ln++) {
        if (ln == 1 && !strncmp(line, "\xef\xbb\xbf", 3)) memmove(line, line + 3, strlen(line + 3) + 1);   // Notepad's UTF-8
        snprintf(where, sizeof where, "%s line %d", path, ln);
        char *s = trim(line);
        if (!*s || *s == '#') continue;
        char *eq = strchr(s, '=');
        if (!eq) {
            rt_log("harness: %s: no '=' in '%s'", where, s);
            sc->errors++;
            continue;
        }
        *eq = 0;
        const char *k = trim(s), *v = trim(eq + 1);
        char *end;
        if (!strcmp(k, "name")) {
            int ok = *v != 0;
            for (const char *c = v; *c; c++) ok &= isalnum((unsigned char)*c) || *c == '_' || *c == '-' || *c == '.';
            if (ok) snprintf(sc->name, sizeof sc->name, "%s", v); else bad(sc, where, k, v);
        } else if (!strcmp(k, "home") || !strcmp(k, "away")) {
            int t;
            if (team(v, &t)) *(k[0] == 'h' ? &sc->home : &sc->away) = t; else bad(sc, where, k, v);
        } else if (!strcmp(k, "seed")) {
            sc->seed = strtoull(v, &end, 0);
            if (*v && !*end) sc->has_seed = 1; else bad(sc, where, k, v);
        } else if (!strcmp(k, "fixed_clock")) {
            if (!strcmp(v, "0") || !strcmp(v, "1")) sc->fixed_clock = *v - '0'; else bad(sc, where, k, v);
        } else if (!strcmp(k, "stop_after_s")) {
            sc->stop_after_s = strtod(v, &end);
            if (!*v || *end || !(sc->stop_after_s >= 0)) { sc->stop_after_s = 0; bad(sc, where, k, v); }
        } else if (!strcmp(k, "stop_at_marker")) {
            snprintf(sc->stop_at_marker, sizeof sc->stop_at_marker, "%s", v);
        } else if (!strcmp(k, "framelog")) {
            snprintf(sc->framelog, sizeof sc->framelog, "%s", v);
        } else if (!strcmp(k, "markers")) {
            if (!strcmp(v, "log")) sc->markers = 1; else if (!strcmp(v, "off")) sc->markers = 0; else bad(sc, where, k, v);
        } else if (!strcmp(k, "dump")) {
            if (sc->ndump >= HARNESS_MAX_DUMPS) { rt_log("harness: %s: more than %d dumps", where, HARNESS_MAX_DUMPS); sc->errors++; }
            else if (parse_dump(v, &sc->dump[sc->ndump], sc, where) == 0) sc->ndump++;
        } else {
            rt_log("harness: %s: unknown key '%s'", where, k);
            sc->errors++;
        }
    }
    fclose(f);
    return 0;
}

// ---- dumps
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

// g_lock. marker NULL: the dumps without an `at`
static void dump_buffers(const char *marker) {
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
    if (!g_on) return;
    EnterCriticalSection(&g_lock);
    if (!g_stop) {   // the reason is complete before the watcher can see the stop
        snprintf(g_stop_why, sizeof g_stop_why, "%s", why ? why : "?");
        InterlockedExchange(&g_stop, 1);
    }
    LeaveCriticalSection(&g_lock);
}

void harness_marker(const char *name) {
    if (!g_on || !name) return;
    if (g_sc.markers) rt_log("harness: marker %s frame %ld t %.3f", name, (long)g_frame, now_s());
    EnterCriticalSection(&g_fl_lock);
    if (g_fl) {
        fprintf(g_fl, "marker %s frame %ld t %.4f\n", name, (long)g_frame, now_s());
        fflush(g_fl);   // markers are rare; a crash keeps the log up to the last one
    }
    LeaveCriticalSection(&g_fl_lock);
    EnterCriticalSection(&g_lock);
    dump_buffers(name);
    LeaveCriticalSection(&g_lock);
    if (g_sc.stop_at_marker[0] && !strcmp(name, g_sc.stop_at_marker)) harness_request_stop(name);
}

void harness_texture_write(unsigned fmt, unsigned w, unsigned h, const void *data, uint64_t bytes) {
    if (!g_on) return;
    int nd = g_sc.ndump;
    for (int i = 0; i < nd && data; i++) {
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

// One-off dump on demand, in a scenario's dump form: a buffer is written now, a texture form is armed for the next
// matching write.
int harness_dump_now(const char *what) {
    if (!g_on || !what) return 0;
    HarnessDump d;
    if (parse_dump(what, &d, &g_sc, "dump_now") != 0) return 0;
    EnterCriticalSection(&g_lock);
    int ok = 1;
    if (d.is_buffer) {
        if (plat_mem_readable(d.addr, d.size)) {
            char hex[65];
            write_dump((const void *)(uintptr_t)d.addr, d.size, hex, "buffer");
        } else {
            rt_log("harness: dump_now: buffer %#llx is not readable", (unsigned long long)d.addr);
            ok = 0;
        }
    } else {
        // a finished texture dump's slot is used again, so repeated one-offs do not run out of the 16
        int i = 0;
        while (i < g_sc.ndump && (g_sc.dump[i].is_buffer || g_sc.dump[i].done < g_sc.dump[i].count)) i++;
        if (i < HARNESS_MAX_DUMPS) {
            if (i == g_sc.ndump) g_sc.ndump++;
            g_sc.dump[i] = d;
            rt_log("harness: texture dump armed (%s)", what);
        } else {
            rt_log("harness: dump_now: %d texture dumps are armed already", HARNESS_MAX_DUMPS);
            ok = 0;
        }
    }
    LeaveCriticalSection(&g_lock);
    return ok;
}

// ---- teams
// Every copy of the team in the match-settings struct; one copy alone gave Dodger Stadium with wrong uniforms.
static void write_teams(uint8_t *o) {
    if (g_sc.home >= 0) o[0x3f] = o[0x47] = o[0x59] = (uint8_t)g_sc.home;
    if (g_sc.away >= 0) o[0x40] = o[0x52] = o[0x54] = o[0x56] = (uint8_t)g_sc.away;
    rt_log("harness: teams home %d away %d written into the match settings at %#llx", o[0x3f], o[0x40],
           (unsigned long long)(uintptr_t)o);
}

void harness_set_teams(int home, int away) {
    if (!g_on) return;
    if (home >= 0 && home <= 29) g_sc.home = home;
    if (away >= 0 && away <= 29) g_sc.away = away;
    if (g_opt) write_teams((uint8_t *)(uintptr_t)g_opt);
}

// ---- watcher thread
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
    harness_framelog_stop();
    EnterCriticalSection(&g_lock);
    dump_buffers(NULL);
    LeaveCriticalSection(&g_lock);
    gfx_window_request_close();
    Sleep(20000);
    rt_log("harness: clean stop did not finish in 20 s; forcing exit 4");
    plat_exit(4);
}

void harness_init(void) {
    if (g_on) return;
    const char *path = cfg_get("MLB_HARNESS"), *h = cfg_get("MLB_HARNESS_HOME"), *a = cfg_get("MLB_HARNESS_AWAY");
    InitializeCriticalSection(&g_lock);
    InitializeCriticalSection(&g_fl_lock);
    g_t0 = plat_now_ns();
    g_on = 1;
    if (path && *path && harness_parse_file(path, &g_sc) != 0) {
        rt_log("harness: cannot read scenario %s", path);
        plat_exit(2);
    }
    if (g_sc.home < 0 && h && *h && !team(h, &g_sc.home)) {   // a scenario key wins over the env
        rt_log("harness: MLB_HARNESS_HOME=%s is not a team 0..29", h);
        g_sc.errors++;
    }
    if (g_sc.away < 0 && a && *a && !team(a, &g_sc.away)) {
        rt_log("harness: MLB_HARNESS_AWAY=%s is not a team 0..29", a);
        g_sc.errors++;
    }
    g_active = (path && *path) || (h && *h) || (a && *a);
    rt_log("harness: scenario '%s' (%s) home %d away %d seed %s fixed_clock %d stop_after_s %.1f stop_at_marker '%s' dumps %d errors %d",
           g_sc.name, g_sc.path[0] ? g_sc.path : g_active ? "env only" : "none", g_sc.home, g_sc.away,
           g_sc.has_seed ? "set" : "unset", g_sc.fixed_clock, g_sc.stop_after_s, g_sc.stop_at_marker, g_sc.ndump, g_sc.errors);
    const char *prof = cfg_get("MLB_PROFILE");
    rt_log("harness: profile %s", prof && *prof ? prof : "(default, beside mlb.exe)");
    harness_marker("boot");
    if (g_sc.framelog[0]) {
        const char *o = cfg_get("MLB_HARNESS_OUT"), *base = o && *o ? o : "harness-out";
        char fp[700];
        int abs = g_sc.framelog[1] == ':' || g_sc.framelog[0] == '/' || g_sc.framelog[0] == '\\';
        if (abs) snprintf(fp, sizeof fp, "%s", g_sc.framelog);
        else { mkdirs(base); snprintf(fp, sizeof fp, "%s/%s", base, g_sc.framelog); }
        harness_framelog_start(fp);
    }
    CreateThread(NULL, 0, watcher, NULL, 0, NULL);
}

#endif
