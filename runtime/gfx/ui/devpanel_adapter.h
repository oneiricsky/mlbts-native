// The dev panel's only contact with the harness (runtime/mlb/harness.h, owned by the harness-core work). Every call
// the panel makes goes through a dh_* function here, so a rename in harness.h costs one edit in this file.
// Compiled only with MLB_DEV_HARNESS. What harness.h has (teams, markers, the frame log, texture dumps) is called for
// real; what it lacks (reference screenshot, restart, situation, seed and clock, last result) logs a
// `devpanel: ... (stub)` line and returns DH_STUB, so the panel says so. Map a stub to its harness.h function here when
// it lands. tools/devpanel_adapter_test.cpp checks the recorder calls without the game.
#pragma once
#ifdef MLB_DEV_HARNESS
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern "C" void rt_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

extern "C" {
#include "cfg.h"
#include "harness.h"
}
struct DhSetup { int home, away; uint32_t seed; char fixed_clock[40]; };   // fixed_clock "" = the real clock
// A game situation to drop the players into.
struct DhSit {
    const char *name;
    int inning, bottom, outs, balls, strikes, away_score, home_score;
    int runners;   // bit 0 first, bit 1 second, bit 2 third
};
#define DH_OFF 3    // a dh_* result: the harness is off (no scenario file or MLB_HARNESS_HOME / _AWAY), the call did nothing
#define DH_STUB 2   // a dh_* result: only logged, harness.h has no such function yet

static inline const char *dh_backend(void) { return "harness.h: teams, markers, frame log, texture dumps; the rest logged only (stub)"; }

// ---- recorder
static inline int dh_marker(const char *name, uint64_t frame);
static inline int dh_dump_texture(const char *what);
static inline int dh_screenshot_ref(const char *name);
static inline int dh_framelog(int on);
static inline int dh_framelog_active(void);
// ---- match setup
static inline int dh_apply_setup(const DhSetup *s);
static inline int dh_setup_is_live(void);   // 1: Apply takes effect mid-game, 0: at the next match start
static inline int dh_restart_match(void);
// ---- scenario drop-in
static inline int dh_apply_scenario(const DhSit *s);
// ---- readouts
static inline int dh_marker_count(void);
static inline int dh_marker_get(int i, const char **name, uint64_t *frame);
static inline int dh_last_result(char *detail, size_t n);   // -1 no run yet, 0 failed, 1 passed

// ---- real: harness.h (harness-core)
static inline int dh_scenario_name(char *out, size_t n) {   // the run's scenario, "" when the harness is off
    snprintf(out, n, "%s", harness_active() ? harness_scenario()->name : "");
    return harness_active();
}
static inline int dh_harness_on(void) { return harness_active(); }
static inline int dh_teams_ready(void) { return harness_match_settings_filled(); }

// The panel keeps its own marker history: harness.h logs markers but has no count/get yet.
struct DhMarker { char name[48]; uint64_t frame; };
static DhMarker dh_markers[64];
static int dh_marker_n;

static inline int dh_marker(const char *name, uint64_t frame) {
    harness_marker(name);   // does nothing while the harness is off; the panel's own list still records it
    DhMarker &m = dh_markers[dh_marker_n % 64];
    snprintf(m.name, sizeof m.name, "%s", name);
    m.frame = frame;
    dh_marker_n++;
    return harness_active() ? 1 : DH_OFF;
}
static inline int dh_marker_count(void) { return dh_marker_n < 64 ? dh_marker_n : 64; }
static inline int dh_marker_get(int i, const char **name, uint64_t *frame) {
    if (i < 0 || i >= dh_marker_count()) return 0;
    const DhMarker &m = dh_markers[(dh_marker_n - 1 - i + 64 * 2) % 64];   // newest first
    *name = m.name, *frame = m.frame;
    return 1;
}
// Teams: harness_set_teams writes the live match settings once the game filled them, else when it does; either way it
// is for the next match setup, not mid-game. Seed and fixed clock belong to the determinism work (harness_det): logged only.
static inline int dh_apply_setup(const DhSetup *s) {
    harness_set_teams(s->home, s->away);
    rt_log("devpanel: seed %u and fixed clock '%s' not applied: no harness.h function for them yet", s->seed, s->fixed_clock);
    return harness_active() ? 1 : DH_OFF;
}
static inline int dh_setup_is_live(void) { return 0; }

// A scenario's texture dump form ("texture:fmt=0x25,size=512x512[,count=N]"): armed for the next matching write.
static inline int dh_dump_texture(const char *what) { return harness_dump_now(what); }
// Each start makes devpanel-framelog-<n>.txt where the dumps go.
static inline int dh_framelog(int on) {
    if (!on) {
        harness_framelog_stop();
        return 1;
    }
    static int n;
    const char *out = cfg_get("MLB_HARNESS_OUT");
    char path[600];
    snprintf(path, sizeof path, "%s/devpanel-framelog-%d.txt", out && *out ? out : "harness-out", ++n);
    return harness_framelog_start(path);
}
static inline int dh_framelog_active(void) { return harness_framelog_active(); }

// ---- stub: no harness.h function yet; each logs its call and returns DH_STUB
static inline int dh_screenshot_ref(const char *name) { rt_log("devpanel: reference screenshot '%s' (stub)", name); return DH_STUB; }
static inline int dh_restart_match(void) { rt_log("devpanel: restart match (stub)"); return DH_STUB; }
static inline int dh_apply_scenario(const DhSit *s) {
    rt_log("devpanel: apply scenario '%s' inning %d %s outs %d count %d-%d score %d-%d runners 0x%x (stub)", s->name,
           s->inning, s->bottom ? "bottom" : "top", s->outs, s->balls, s->strikes, s->away_score, s->home_score, s->runners);
    return DH_STUB;
}
static inline int dh_last_result(char *detail, size_t n) { if (n) detail[0] = 0; return -1; }
#endif
