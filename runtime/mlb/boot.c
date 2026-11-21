// Adapted from TotK Recomp runtime/boot.c @ ae30a61 (MIT, Copyright (c) 2026 Valiantsin Dzerakh), which adapts
// MacNativeGames games/totk/runtime/loader.c and services.c @ b75be8cf (MIT) and LAS Recomp runtime/main.c @ da35b83
// (MIT). The boot driver: the guest main thread runs the SDK's own nn::init::Start with three host callbacks in
// place of rtld; the second runs DT_INIT of every loaded module (main, sdk); Start then calls nnMain.
// TotK's per-version checkpoints, shader prewarm, patch sets, mods and cheats are not ported.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "host.h"
#include "packages.h"
#include "platform/platform.h"

void res_apply(void);   // resolution.c

#define SYM_INIT_START "_ZN2nn4init5StartEmmPFvvES2_S2_"
#define CTOR_DONE 2   // a module's constructor flag after its DT_INIT ran the init_array

static volatile int32_t inits_done;
uint64_t rt_guest_start_ns;

static uint32_t ctor_state(const RtLoaded *m) { return LD32(m->ctor_flag); }
static const char *caller(const Cpu *c, char *buf, int n) { return ldr_describe(c->x[30] - 4, buf, n); }

// The services main.npdm lets the game open (ACI0 service access control: one byte per entry, bits 0-2 the name
// length - 1, bit 7 a server entry; a trailing '*' matches a prefix). sm answers other names NotAllowed, as Horizon
// does; the SDK probes some (pctl:s) and falls back.
#define SAC_MAX 96
static char sac_names[SAC_MAX][9];
static int sac_count;

static void read_sac(const uint8_t *npdm, size_t n) {
    uint32_t aci_off, aci_size, sac_off, sac_size;
    memcpy(&aci_off, npdm + 0x70, 4);
    memcpy(&aci_size, npdm + 0x74, 4);
    if (aci_off > n || aci_size > n - aci_off || aci_size < 0x40 || memcmp(npdm + aci_off, "ACI0", 4))
        rt_fatal("boot: main.npdm has no ACI0");
    const uint8_t *aci = npdm + aci_off;
    memcpy(&sac_off, aci + 0x28, 4);
    memcpy(&sac_size, aci + 0x2C, 4);
    if (sac_off > aci_size || sac_size > aci_size - sac_off) rt_fatal("boot: main.npdm ACI0 service list out of range");
    for (uint32_t i = 0; i < sac_size;) {
        uint8_t c = aci[sac_off + i];
        uint32_t len = (c & 7u) + 1;
        if (i + 1 + len > sac_size) rt_fatal("boot: main.npdm service list entry past its end");
        if (!(c & 0x80)) {
            if (sac_count == SAC_MAX) rt_fatal("boot: main.npdm lists more than %d services", SAC_MAX);
            memcpy(sac_names[sac_count++], aci + sac_off + i + 1, len);
        }
        i += 1 + len;
    }
    rt_log("boot: main.npdm allows %d services", sac_count);
}

int rt_service_allowed(const char *name) {
    for (int i = 0; i < sac_count; i++) {
        size_t len = strlen(sac_names[i]);
        if (len && sac_names[i][len - 1] == '*' ? !strncmp(sac_names[i], name, len - 1) : !strcmp(sac_names[i], name))
            return 1;
    }
    return 0;
}

// kernel.c builds the main thread with priority 44, core 0 and a 1 MiB stack; MLB 1.0.15's main.npdm asks for the
// same (docs/recon-report.md, NPDM), so a different npdm means a different game build.
static void check_npdm(void) {
    size_t n;
    uint8_t *npdm = ldr_read_verified(rt_config()->exefs, "main.npdm", &n);
    if (n < 0x80 || memcmp(npdm, "META", 4)) rt_fatal("boot: main.npdm has no META header");
    uint32_t stack;
    memcpy(&stack, npdm + 0x1C, 4);
    int prio = npdm[0xE], core = npdm[0xF];
    read_sac(npdm, n);
    free(npdm);
    if (prio != 44 || core != 0 || stack != 0x100000)
        rt_fatal("boot: main.npdm asks for priority %d, core %d, stack %#x; kernel.c builds 44, 0, 0x100000", prio,
                 core, stack);
}

// ---- the three callbacks of nn::init::Start (rtld's job on hardware)
static void cb_loader_ready(Cpu *c) {
    (void)c;
    rt_log("boot: rtld callback: modules linked");
}

// DT_INIT registers the module with musl (__nnmusl_init_dso) and runs its init_array; the constructor flag reads 2
// afterwards.
static void cb_module_inits(Cpu *c) {
    if (plat_cas32(&inits_done, 0, 0)) rt_fatal("boot: module constructors requested twice");
    for (int i = 0; i < ldr_count(); i++) {
        const RtLoaded *m = ldr_module(i);
        uint64_t entries = m->init_array_size / 8;
        if (!m->init) rt_fatal("boot: %s has no DT_INIT", m->name);
        rt_log("boot: ENTER %s DT_INIT (%llu init_array entries)", m->name, (unsigned long long)entries);
        rt_call(c, m->init, 0);
        uint32_t state = ctor_state(m);
        rt_log("boot: DT_INIT %s done, constructor flag %u", m->name, state);
        if (state != CTOR_DONE) rt_fatal("boot: %s DT_INIT left its constructor flag at %u, not 2", m->name, state);
    }
    plat_xchg32(&inits_done, 1);
}

static void cb_module_finis(Cpu *c) {
    char lr[128];
    rt_fatal("boot: the game asked for module finalizers (from %s): the guest exited", caller(c, lr, sizeof lr));
}

void rt_boot_event(const char *what, Cpu *c, const char *detail) {
    char at[128];
    RtStats s = rt_stats();
    rt_log("boot: %s at %s%s%s (%llu SVCs, %llu threads, %llu host calls)", what,
           c ? ldr_describe(c->x[30], at, sizeof at) : "-", detail ? ": " : "", detail ? detail : "",
           (unsigned long long)s.svcs, (unsigned long long)s.threads, (unsigned long long)s.host_calls);
}

static uint64_t cb_addr[3];

static void guest_main(Cpu *c) {
    uint32_t handle = kern_main_thread(&c);
    uint64_t start = ldr_symbol(SYM_INIT_START);
    if (!start) rt_fatal("boot: %s is not exported", SYM_INIT_START);
    char d[128];
    rt_log("boot: ENTER nn::init::Start at %s, main thread %#x", ldr_describe(start, d, sizeof d), handle);
    // nn::init::Start(main thread handle, arguments region, loader_ready, module_inits, module_finis)
    rt_call(c, start, 5, (uint64_t)handle, (uint64_t)0, cb_addr[0], cb_addr[1], cb_addr[2]);
    rt_fatal("boot: nn::init::Start returned");
}

void rt_boot(void) {
    check_npdm();
    packages_start();    // packages.c, only with MLB_OFFLINE_PACKAGES: must come before the modules are linked
    ldr_load(rt_config()->exefs);
    packages_loaded();
    void tutorials_apply(void);
    tutorials_apply();   // tutorials.c: MLB_KEEP_TUTORIALS, the list of finished tutorials kept in the profile
    void rtts_autosave_apply(void);
    rtts_autosave_apply();   // rtts_autosave.c: MLB_RTTS_AUTOSAVE, hub upgrades saved when their screen is left
    rt_patches_init();
    res_apply();   // fastball, resolution.c: MLB_RENDER_SCALE rewrites the scene size table before the game reads it
    cb_addr[0] = hostfn_register("<rtld loader_ready>", cb_loader_ready);
    cb_addr[1] = hostfn_register("<rtld module_inits>", cb_module_inits);
    cb_addr[2] = hostfn_register("<rtld module_finis>", cb_module_finis);
    void mlb_heap_init(void);
    mlb_heap_init();   // heap.c: the census callback (MLB_TRACE=perf, MLB_HEAP_CENSUS=1)
    hostfn_seal();
    rt_log("boot: guest starts %llu ms after process start",
           (unsigned long long)(plat_process_uptime_ns() / 1000000));
    rt_guest_start_ns = kern_now_ns();
    kern_run_on_guest_main(guest_main);
    rt_fatal("boot: the guest main thread ended");
}
