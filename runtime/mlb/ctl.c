// fastball dev control channel: ask a running game questions instead of starting it again (MLB_CTL=<folder>, dev builds only).
//
// The folder holds cmd.txt (written by tools/ctl.py), out.txt (the answers) and done.txt (a counter that goes up after each
// command file). One command per line, numbers in hex:
//   dump ADDR N               N qwords from ADDR, four a line
//   str TEXT                  addresses of TEXT in committed memory (narrow and wide), with the memory's kind
//   refs ADDR [SLACK]         qwords in writable memory that point into [ADDR-SLACK, ADDR], with their surroundings
//   poke ADDR HEXBYTES        write bytes (the page is made writable for the write)
//   watch ADDR LEN [TTLMS]    log every write into [ADDR, ADDR+LEN) with the exact call chain; stops after TTLMS (default 20000)
//   unwatch                   stop all watches
//   trace ADDR[,ADDR...]      the game's function tracer (logs to mlb.log) on these functions; `trace LO-HI` a range; `trace off`
//   press NAME MS             hold a button (A B X Y L R ZL ZR PLUS MINUS LEFT UP RIGHT DOWN) for MS
//   shot PATH                 save the next presented picture as PNG
//   mark TEXT                 a line in mlb.log and in out.txt, to line the log up with the commands
//   frame                     the number of frames presented so far
//   sleep MS                  wait before the next command
// The write watch makes the page read-only, takes the first fault of each write, lets it through with the trap flag and puts the
// protection back; the chain comes from RtlCaptureStackBackTrace inside the handler, so it is the real call chain. tools/ctl.py
// turns the module offsets into function names with the linker map.
#ifdef MLB_DEV_HARNESS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "gfx.h"
#include "host.h"
#include "platform/platform.h"

void hid_ctl_press(uint64_t mask, unsigned ms);
void fnprof_set(const uint64_t *addrs, int n, uint64_t lo, uint64_t hi);

static char g_dir[400];
static FILE *g_out;

static void say(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_out, fmt, ap);
    va_end(ap);
    fputc('\n', g_out);
    fflush(g_out);
}

static int readable(uint64_t a, MEMORY_BASIC_INFORMATION *m) {
    return VirtualQuery((void *)(uintptr_t)a, m, sizeof *m) && m->State == MEM_COMMIT && !(m->Protect & (PAGE_GUARD | PAGE_NOACCESS));
}

// ---- watches
#define NWATCH 8
static struct { uint64_t addr, len, page_lo, page_hi; uint64_t until_ms, hits; int on; } g_w[NWATCH];
static __declspec(thread) uint64_t t_pending_lo, t_pending_hi;

static uint64_t now_ms(void) { return GetTickCount64(); }

static void protect(uint64_t lo, uint64_t hi, DWORD prot) {
    DWORD old;
    VirtualProtect((void *)(uintptr_t)lo, (SIZE_T)(hi - lo), prot, &old);
}

static LONG CALLBACK watch_veh(EXCEPTION_POINTERS *ep) {
    const EXCEPTION_RECORD *er = ep->ExceptionRecord;
    if (er->ExceptionCode == EXCEPTION_SINGLE_STEP && t_pending_hi) {
        for (int i = 0; i < NWATCH; i++)
            if (g_w[i].on && g_w[i].page_lo == t_pending_lo) protect(g_w[i].page_lo, g_w[i].page_hi, PAGE_READONLY);
        ep->ContextRecord->EFlags &= ~0x100u;
        t_pending_lo = t_pending_hi = 0;
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (er->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || er->NumberParameters < 2 || er->ExceptionInformation[0] != 1)
        return EXCEPTION_CONTINUE_SEARCH;
    uint64_t fa = (uint64_t)er->ExceptionInformation[1];
    int hit = -1;
    for (int i = 0; i < NWATCH; i++)
        if (g_w[i].on && fa >= g_w[i].page_lo && fa < g_w[i].page_hi) hit = i;
    if (hit < 0) return EXCEPTION_CONTINUE_SEARCH;
    protect(g_w[hit].page_lo, g_w[hit].page_hi, PAGE_READWRITE);
    if (fa >= g_w[hit].addr && fa < g_w[hit].addr + g_w[hit].len && g_w[hit].hits < 40) {
        g_w[hit].hits++;
        uint64_t base = (uint64_t)(uintptr_t)GetModuleHandleA(NULL);
        void *fr[48];
        USHORT n = RtlCaptureStackBackTrace(0, 48, fr, NULL);
        char line[2200];
        int o = snprintf(line, sizeof line, "hit w%d frame %llu +%llx tid %lu chain:", hit, (unsigned long long)gfx_stats().frames,
                         (unsigned long long)(fa - g_w[hit].addr), GetCurrentThreadId());
        for (USHORT i = 1; i < n && o < 2100; i++) {
            uint64_t a = (uint64_t)(uintptr_t)fr[i];
            if (a > base && a < base + 0x9000000ull) o += snprintf(line + o, sizeof line - o, " %llx", (unsigned long long)(a - base));
        }
        say("%s", line);
    }
    t_pending_lo = g_w[hit].page_lo, t_pending_hi = g_w[hit].page_hi;
    ep->ContextRecord->EFlags |= 0x100u;
    return EXCEPTION_CONTINUE_EXECUTION;
}

static void watch_expire(void) {
    for (int i = 0; i < NWATCH; i++)
        if (g_w[i].on && now_ms() >= g_w[i].until_ms) {
            g_w[i].on = 0;
            protect(g_w[i].page_lo, g_w[i].page_hi, PAGE_READWRITE);
            say("watch w%d ended: %llu hits", i, (unsigned long long)g_w[i].hits);
        }
}

// ---- commands
static uint64_t hx(const char *s) { return strtoull(s, NULL, 16); }

static void cmd_dump(uint64_t a, unsigned n) {
    for (unsigned i = 0; i < n; i += 4) {
        MEMORY_BASIC_INFORMATION m;
        if (!readable(a + i * 8ull, &m)) { say("unreadable at %llx", (unsigned long long)(a + i * 8ull)); return; }
        uint64_t v[4];
        memcpy(v, (void *)(uintptr_t)(a + i * 8ull), sizeof v);
        say("%llx: %016llx %016llx %016llx %016llx", (unsigned long long)(a + i * 8ull), (unsigned long long)v[0], (unsigned long long)v[1],
            (unsigned long long)v[2], (unsigned long long)v[3]);
    }
}

static void cmd_str(const char *text) {
    size_t nl = strlen(text);
    int found = 0;
    for (int wide = 0; wide < 2; wide++) {
        uint8_t pat[256];
        size_t pl = 0;
        for (size_t i = 0; i < nl && pl + 2 < sizeof pat; i++) { pat[pl++] = (uint8_t)text[i]; if (wide) pat[pl++] = 0; }
        uint64_t a = 0x10000ull;
        MEMORY_BASIC_INFORMATION m;
        while (a < 0x7ff000000000ull && VirtualQuery((void *)(uintptr_t)a, &m, sizeof m)) {
            uint64_t base = (uint64_t)(uintptr_t)m.BaseAddress, sz = m.RegionSize;
            if (m.State == MEM_COMMIT && !(m.Protect & (PAGE_GUARD | PAGE_NOACCESS)) && base >= 0x100000000ull) {
                const uint8_t *p = (const uint8_t *)(uintptr_t)base;
                for (uint64_t i = 0; i + pl < sz;) {
                    const uint8_t *q = memchr(p + i, pat[0], sz - i - pl);
                    if (!q) break;
                    i = (uint64_t)(q - p);
                    if (!memcmp(p + i, pat, pl) && found < 60) {
                        say("str %s%s at %llx (%s)", text, wide ? " (wide)" : "", (unsigned long long)(base + i), m.Type == MEM_MAPPED ? "mapped" : "private");
                        found++;
                    }
                    i++;
                }
            }
            a = base + sz;
        }
    }
    say("str: %d found", found);
}

static void cmd_refs(uint64_t target, uint64_t slack) {
    int shown = 0;
    uint64_t a = 0x100000000ull;
    MEMORY_BASIC_INFORMATION m;
    while (a < 0x7ff000000000ull && VirtualQuery((void *)(uintptr_t)a, &m, sizeof m)) {
        uint64_t base = (uint64_t)(uintptr_t)m.BaseAddress, sz = m.RegionSize;
        if (m.State == MEM_COMMIT && (m.Protect & PAGE_READWRITE) && !(m.Protect & PAGE_GUARD)) {
            const uint64_t *p = (const uint64_t *)(uintptr_t)base;
            for (uint64_t i = 4; i + 12 < sz / 8; i++)
                if (p[i] >= target - slack && p[i] <= target && shown < 40) {
                    char line[700];
                    int o = snprintf(line, sizeof line, "ref at %llx -> %llx ctx:", (unsigned long long)(base + i * 8), (unsigned long long)p[i]);
                    for (int k = -4; k < 8; k++) o += snprintf(line + o, sizeof line - o, " %llx", (unsigned long long)p[i + k]);
                    say("%s", line);
                    shown++;
                }
        }
        a = base + sz;
    }
    say("refs: %d shown", shown);
}

static void cmd_poke(uint64_t a, const char *hex) {
    uint8_t buf[512];
    size_t n = 0;
    for (; hex[0] && hex[1] && n < sizeof buf; hex += 2) {
        char b[3] = {hex[0], hex[1], 0};
        buf[n++] = (uint8_t)strtoul(b, NULL, 16);
    }
    MEMORY_BASIC_INFORMATION m;
    if (!readable(a, &m)) { say("poke: unreadable"); return; }
    DWORD old;
    VirtualProtect((void *)(uintptr_t)a, n, PAGE_READWRITE, &old);
    memcpy((void *)(uintptr_t)a, buf, n);
    VirtualProtect((void *)(uintptr_t)a, n, old, &old);
    say("poked %zu bytes at %llx", n, (unsigned long long)a);
}

static void cmd_watch(uint64_t a, uint64_t len, uint64_t ttl) {
    static int veh;
    if (!veh) veh = AddVectoredExceptionHandler(1, watch_veh) != NULL;
    int slot = -1;
    for (int i = 0; i < NWATCH && slot < 0; i++) if (!g_w[i].on) slot = i;
    MEMORY_BASIC_INFORMATION m;
    if (slot < 0 || !readable(a, &m)) { say("watch: no free slot or unreadable"); return; }
    g_w[slot].addr = a, g_w[slot].len = len, g_w[slot].page_lo = a & ~0xfffull, g_w[slot].page_hi = (a + len + 0xfff) & ~0xfffull;
    g_w[slot].until_ms = now_ms() + ttl, g_w[slot].hits = 0, g_w[slot].on = 1;
    protect(g_w[slot].page_lo, g_w[slot].page_hi, PAGE_READONLY);
    say("watch w%d on %llx len %llx for %llu ms", slot, (unsigned long long)a, (unsigned long long)len, (unsigned long long)ttl);
}

static void cmd_trace(char *arg) {
    if (!strcmp(arg, "off")) { fnprof_set(NULL, 0, 0, 0); say("trace off"); return; }
    uint64_t addrs[16], lo = 0, hi = 0;
    int n = 0;
    for (char *p = arg; *p;) {
        char *e;
        uint64_t v = strtoull(p, &e, 16);
        if (e == p) break;
        if (*e == '-') { lo = v; hi = strtoull(e + 1, &e, 16); }
        else if (n < 16) addrs[n++] = v;
        p = e + (*e == ',');
    }
    fnprof_set(addrs, n, lo, hi);
    say("trace on: %d functions, range %llx-%llx (the log, mlb.log, has the calls)", n, (unsigned long long)lo, (unsigned long long)hi);
}

static const struct { const char *n; int bit; } k_btn[] = {{"A", 0}, {"B", 1}, {"X", 2}, {"Y", 3}, {"L", 6}, {"R", 7}, {"ZL", 8}, {"ZR", 9},
                                                          {"PLUS", 10}, {"MINUS", 11}, {"LEFT", 12}, {"UP", 13}, {"RIGHT", 14}, {"DOWN", 15}};

static void run_line(char *line) {
    char *save = NULL, *cmd = strtok_s(line, " \t\r\n", &save);
    if (!cmd) return;
    char *a1 = strtok_s(NULL, " \t\r\n", &save), *a2 = strtok_s(NULL, " \t\r\n", &save), *a3 = strtok_s(NULL, " \t\r\n", &save);
    say("> %s %s %s %s", cmd, a1 ? a1 : "", a2 ? a2 : "", a3 ? a3 : "");
    if (!strcmp(cmd, "dump") && a1 && a2) cmd_dump(hx(a1), (unsigned)hx(a2));
    else if (!strcmp(cmd, "str") && a1) cmd_str(a1);
    else if (!strcmp(cmd, "refs") && a1) cmd_refs(hx(a1), a2 ? hx(a2) : 0);
    else if (!strcmp(cmd, "poke") && a1 && a2) cmd_poke(hx(a1), a2);
    else if (!strcmp(cmd, "watch") && a1 && a2) cmd_watch(hx(a1), hx(a2), a3 ? strtoull(a3, NULL, 10) : 20000);
    else if (!strcmp(cmd, "unwatch")) { for (int i = 0; i < NWATCH; i++) g_w[i].until_ms = 0; watch_expire(); }
    else if (!strcmp(cmd, "trace") && a1) cmd_trace(a1);
    else if (!strcmp(cmd, "press") && a1) {
        int ok = 0;
        for (size_t i = 0; i < sizeof k_btn / sizeof *k_btn; i++)
            if (!_stricmp(a1, k_btn[i].n)) hid_ctl_press(1ull << k_btn[i].bit, a2 ? (unsigned)strtoul(a2, NULL, 10) : 150), ok = 1;
        say(ok ? "pressed %s" : "unknown button %s", a1);
    } else if (!strcmp(cmd, "shot") && a1) { gfx_shot_request(a1); say("shot requested: %s", a1); }
    else if (!strcmp(cmd, "mark") && a1) { rt_log("ctl: mark %s", a1); say("mark %s frame %llu", a1, (unsigned long long)gfx_stats().frames); }
    else if (!strcmp(cmd, "frame")) say("frame %llu", (unsigned long long)gfx_stats().frames);
    else if (!strcmp(cmd, "sleep") && a1) Sleep((DWORD)strtoul(a1, NULL, 10));
    else say("unknown command or missing argument");
}

static DWORD WINAPI ctl_thread(void *arg) {
    (void)arg;
    char cmdp[460], outp[460], donep[460];
    snprintf(cmdp, sizeof cmdp, "%s/cmd.txt", g_dir);
    snprintf(outp, sizeof outp, "%s/out.txt", g_dir);
    snprintf(donep, sizeof donep, "%s/done.txt", g_dir);
    g_out = fopen(outp, "a");
    if (!g_out) return 0;
    say("ctl ready, game pid %lu, module base %llx", GetCurrentProcessId(), (unsigned long long)(uintptr_t)GetModuleHandleA(NULL));
    unsigned seq = 0;
    for (;;) {
        Sleep(40);
        watch_expire();
        FILE *f = fopen(cmdp, "rb");
        if (!f) continue;
        static char buf[16384];
        size_t n = fread(buf, 1, sizeof buf - 1, f);
        fclose(f);
        if (!n) continue;
        buf[n] = 0;
        remove(cmdp);
        for (char *p = buf, *nl; p && *p; p = nl) {
            nl = strchr(p, '\n');
            if (nl) *nl++ = 0;
            run_line(p);
        }
        FILE *d = fopen(donep, "wb");
        if (d) { fprintf(d, "%u\n", ++seq); fclose(d); }
    }
}

void ctl_start(void) {
    const char *d = cfg_get("MLB_CTL");
    if (!d || !*d) return;
    snprintf(g_dir, sizeof g_dir, "%s", d);
    CreateThread(NULL, 0, ctl_thread, NULL, 0, NULL);
    rt_log("ctl: control channel in %s", g_dir);
}
#endif
