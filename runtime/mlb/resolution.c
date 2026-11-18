// fastball: the size MLB renders its 3D scene at (MLB_RENDER_SCALE, the settings menu's Graphics tab).
//
// MLB draws its 3D scene into one image smaller than its 1920x1080 output and stretches it there in its final pass
// (vk_exec_draw.c aa_composite: fragment shader daf10a59), with the HUD drawn into a separate 1080p layer. The scene's
// size comes from a table in main's read-only data [C] (1.0.15, traced 2026-11-13 with a size trace on
// nvnTextureBuilderSetSize2D): f_70005a5368 returns entry min(level, 4) of five {w, h} pairs whose address it loads
// from 0x7002283d80 (the table sits at 0x7001d818a0):
//     960x540  1280x720  1366x768  1440x810  1600x900
// and f_70005a4634 resizes the scene's render targets (f_70005a4b88: colour, depth and a third target, all 1440x810
// on the TV) to it. Docked, the game picks level 3, 1440x810: 75 % of the output on each side. Its output size comes
// from a second table at 0x7001d81890 (1280x720 handheld, 1920x1080 docked), left alone here.
// 1.0.20 moved them (tools/addrmap.py, checked in the disassembly): f_70005a5388 loads the table's address from
// 0x7002284df0, and the table sits at 0x7001d82910.
//
// MLB_RENDER_SCALE = "game" (default: the table as shipped) or a percentage of the 1920x1080 output. Every entry is
// scaled by that percentage over the game's 75 %, so the level the game picks keeps its place (100: 1920x1080, 150:
// 2880x1620, 200: 3840x2160). Above 100 the game supersamples its scene and its final pass shrinks it to 1080p,
// which smooths edges at the cost of GPU time and video memory. The table is rewritten once, after main is loaded and
// before any guest code runs; when its bytes are not the shipped ones (another game version) it is left alone.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"

// main: the address the scene size function loads the table's address from, per game version
static const struct { const char *build; uint64_t ptr; } table_ptrs[] = {{"1.0.15", 0x7002283d80ull},
                                                                         {"1.0.20", 0x7002284df0ull}};
#define SCENE_LEVELS 5
#define GAME_PCT 75.0                     // the docked level's share of the 1920x1080 output, per side
#define SCENE_MAX 4096                    // per side

static const uint32_t shipped[SCENE_LEVELS][2] = {{960, 540}, {1280, 720}, {1366, 768}, {1440, 810}, {1600, 900}};

// MLB_DLSS (vk_dlaa.c): with DLSS on, the mode decides the scene's size in place of MLB_RENDER_SCALE, as a percentage
// of the 1080p output per side: DLAA 100 (1920x1080), Quality the game's own sizes (75, 1440x810: the table as
// shipped; NVIDIA's own Quality ratio is 66.7, 1280x720, a softer start), Balanced 58 (1114x626), Performance 50
// (960x540), Ultra Performance 33.3 (640x360); DLSS scales it up to 1080p. Only when DLSS can run: the driver has
// NVIDIA's NGX core and nvngx_dlss.dll sits next to mlb.exe (a smaller scene without DLSS would only look worse).
// 0: DLSS off or missing.
static const char *dlss_pct(void) {
    static const struct { const char *mode, *pct; } modes[] = {{"dlaa", "100"}, {"quality", "game"},
                                                               {"balanced", "58"}, {"performance", "50"},
                                                               {"ultra_performance", "33.3333"}};
    const char *m = cfg_value("DLSS");
    const char *pct = NULL;
    for (size_t i = 0; i < sizeof modes / sizeof modes[0]; i++)
        if (!strcmp(m, modes[i].mode)) pct = modes[i].pct;
    if (!pct) return NULL;
    char core[PLAT_PATH_MAX], exe[PLAT_PATH_MAX], dll[PLAT_PATH_MAX + 32];
    if (!plat_ngx_core_path(core, sizeof core)) {
        rt_log("res: MLB_DLSS=%s needs an NVIDIA driver with NGX, which this machine lacks; MLB_RENDER_SCALE applies", m);
        return NULL;
    }
    const char *sep = plat_exe_path(exe, sizeof exe) ? plat_last_sep(exe) : NULL;
    if (sep) snprintf(dll, sizeof dll, "%.*s/nvngx_dlss.dll", (int)(sep - exe), exe);
    if (!sep || !plat_file_exists(dll)) {
        rt_log("res: MLB_DLSS=%s needs nvngx_dlss.dll next to mlb.exe, which is missing; MLB_RENDER_SCALE applies", m);
        return NULL;
    }
    rt_log("res: MLB_DLSS=%s: the 3D scene at %s%s (MLB_RENDER_SCALE is not used)", m, pct,
           strcmp(pct, "game") ? " % of 1080p" : "'s own size");
    return pct;
}

void res_apply(void) {
    const char *v = dlss_pct();
    if (!v) v = cfg_value("RENDER_SCALE");
    if (!strcmp(v, "game")) return;
    char *end;
    double pct = strtod(v, &end);
    if (end == v || *end || pct < 25 || pct > 300) {
        rt_log("res: MLB_RENDER_SCALE=%s is not \"game\" or a percentage from 25 to 300; the game's own sizes stay", v);
        return;
    }
    uint64_t ptr = 0;
    for (size_t i = 0; i < sizeof table_ptrs / sizeof table_ptrs[0]; i++)
        if (!strcmp(rt_game_build, table_ptrs[i].build)) ptr = table_ptrs[i].ptr;
    if (!ptr) {
        rt_log("res: no scene size table known for game %s; MLB_RENDER_SCALE is ignored", rt_game_build);
        return;
    }
    uint32_t *t = (uint32_t *)(uintptr_t)*(const uint64_t *)(uintptr_t)ptr;
    if (memcmp(t, shipped, sizeof shipped)) {
        rt_log("res: the scene size table at %p is not the shipped one; MLB_RENDER_SCALE is ignored", (void *)t);
        return;
    }
    uint64_t page = (uint64_t)(uintptr_t)t & ~0xfffull, n = ((uint64_t)(uintptr_t)(t + 2 * SCENE_LEVELS) - page + 0xfff) & ~0xfffull;
    if (!plat_mem_protect(page, n, PLAT_PROT_RW)) {
        rt_log("res: cannot unprotect the scene size table; the game's own sizes stay");
        return;
    }
    double k = pct / GAME_PCT;
    char line[256];
    int at = 0;
    for (int i = 0; i < SCENE_LEVELS; i++) {
        // even sizes, as the game's own; at most SCENE_MAX a side
        uint32_t w = (uint32_t)lround(shipped[i][0] * k / 2) * 2, h = (uint32_t)lround(shipped[i][1] * k / 2) * 2;
        if (w > SCENE_MAX) w = SCENE_MAX;
        if (h > SCENE_MAX) h = SCENE_MAX;
        t[2 * i] = w, t[2 * i + 1] = h;
        at += snprintf(line + at, sizeof line - at, " %ux%u", w, h);
    }
    plat_mem_protect(page, n, PLAT_PROT_READ);
    rt_log("res: MLB_RENDER_SCALE=%s: the 3D scene's sizes are now%s (the TV uses the fourth, 1440x810 as shipped)", v,
           line);
}
