// The in-game settings menu (menu.h): Dear ImGui state, the event queue the window adapter fills, gamepad navigation,
// the Vulkan back end on our device and the menu's pages. Free of any window system. ImGui runs on the present path
// only, under gfx_present.c's present lock; the event functions only queue.
//
// From TotK Recomp runtime/ui/menu.cpp @ ae30a61 (MIT, Copyright (c) 2026 Valiantsin Dzerakh): the open state and event
// queue, gamepad navigation, the Vulkan set-up (after LAS Recomp's runtime/nvn/vulkan/imgui_glue.cpp,
// https://github.com/peiikai/LASRecomp @ da35b83a9611d046a9a681aae668d7085954d37f, MIT, Copyright (c) 2026 Peiikai)
// and the look (after SavageWindRecomp's runtime/ui/menu.mm, https://github.com/Revivedx/SavageWindRecomp @
// 575ad88e02f9a89a9a885d90039d48af33c982f4, MIT, Copyright (c) 2026 Revivedx and the Savage Wind Recomp contributors,
// Copyright (c) 2026 Peiikai): dark green panels, gold accents, the tab bar with L / R or Q / E, the window over a
// dimmed game, two-pane option rows (option_rows.cpp).
//
// fastball: MLB's pages (Graphics, Display, Game, Sound, Controls, Advanced) over the settings this port reads,
// with TotK's performance overlay (F10) and its Advanced helpers; English text only. TotK's translated catalog, its
// mods, cheats, amiibo and key binding pages and its TotK-only rows (resolution patches, shadows, DLSS, HDR, frame
// limit, motion, mouse) are not ported. F1, or
// Minus and Plus together on the pad (Back and Start, hid.c), open and close it; B or Esc close it. While it is open the
// game keeps running and gets an idle controller (hid.c). Changes apply at once and go into mlb.cfg (cfg_save).
// Closed, it costs one atomic load per present on top of the F12 capture check (gfx_stubs.c mlb_capture_tick).
#include <atomic>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "imgui.h"
#include "imgui_internal.h"   // ClosePopupToLevel
#include "backends/imgui_impl_vulkan.h"
#include "ui/option_rows.h"

extern "C" {
#include "cfg.h"
#include "platform/platform.h"
#include "ui/menu.h"
// host.h and vk.h pull in cpu.h, which is C only: the functions the menu needs from them, as declared there.
void rt_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
void vk_queue_lock(void);
void vk_queue_unlock(void);
extern const char rt_port_version[], rt_game_build[];   // host.h (modules.c)
int hid_menu_pad(uint64_t *buttons, int32_t *lx, int32_t *ly);   // mlb/hid.c
int vk_aa_status(void);                                          // vk_aa.c
int mlb_capture_tick(uint64_t frame, const char **shot);         // gfx_stubs.c: F12 / MLB_SHOT captures
int hid_stick_percent(double now[2]);                            // mlb/hid.c
int playtime_get(uint64_t *total_s, uint64_t *session_s);        // core/playtime.c
int fs_save_busy(void);                                          // core/fs_host.c
#include "perfmon.h"
#include "sysinfo.h"
}

// Roboto Medium (Apache-2.0, ui/fonts/LICENSE-Roboto.txt) with Latin glyphs.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"   // #embed in C++
static const unsigned char roboto_ttf[] = {
#embed "fonts/Roboto-Medium.ttf"
};
#pragma clang diagnostic pop

// ---- open state, any thread
static std::atomic<int> g_open;     // the menu is open
static std::atomic<int> g_reset;    // opened or closed since the last laid-out frame: drop stale input
static std::atomic<int> g_failed;   // set-up failed for good (the menu stays closed)

// g_open and the log line change together under open_lock, so they cannot disagree when the window thread (F1), the
// pad's polling thread (Minus+Plus) and the present path (Continue, B) race.
static PlatMutex open_lock = PLAT_MUTEX_INIT;

// want 0 or 1 sets the state; -1 flips it. Returns the new state.
static int change_open(int want) {
    plat_mutex_lock(&open_lock);
    int open = want < 0 ? !g_open.load() : want;
    if (g_open.load() != open) {
        g_open.store(open);
        g_reset.store(1);
        rt_log("menu: %s", open ? "open" : "closed");
    }
    plat_mutex_unlock(&open_lock);
    return open;
}

extern "C" int menu_is_open(void) { return g_open.load(std::memory_order_relaxed); }
extern "C" void menu_toggle(void) {
    if (!g_failed.load(std::memory_order_relaxed)) change_open(-1);
}

// ---- events from the window adapter, queued while the menu is open; the present path hands them to ImGui
enum { EV_KEY, EV_POS, EV_BUTTON, EV_WHEEL, EV_FOCUS, EV_MAX = 256 };
struct Ev { int type, a, b; float x, y; };
static PlatMutex ev_lock = PLAT_MUTEX_INIT;
static Ev ev_q[EV_MAX];
static int ev_n;

static void push(Ev e) {
    if (!menu_is_open()) return;
    plat_mutex_lock(&ev_lock);
    if (e.type == EV_POS && ev_n && ev_q[ev_n - 1].type == EV_POS) ev_q[ev_n - 1] = e;   // only the newest position
    else if (ev_n < EV_MAX) ev_q[ev_n++] = e;
    plat_mutex_unlock(&ev_lock);
}

extern "C" void menu_event_key(int key, int down) { push({EV_KEY, key, down, 0, 0}); }
extern "C" void menu_event_mouse_pos(float x, float y) { push({EV_POS, 0, 0, x, y}); }
extern "C" void menu_event_mouse_button(int button, int down) { push({EV_BUTTON, button, down, 0, 0}); }
extern "C" void menu_event_wheel(float dx, float dy) { push({EV_WHEEL, 0, 0, dx, dy}); }
extern "C" void menu_event_focus(int focused) { push({EV_FOCUS, focused, 0, 0, 0}); }

static void drain_events(ImGuiIO &io) {
    Ev q[EV_MAX];
    plat_mutex_lock(&ev_lock);
    int n = ev_n;
    for (int i = 0; i < n; i++) q[i] = ev_q[i];
    ev_n = 0;
    plat_mutex_unlock(&ev_lock);
    for (int i = 0; i < n; i++) {
        const Ev &e = q[i];
        switch (e.type) {
        case EV_KEY: io.AddKeyEvent((ImGuiKey)e.a, e.b != 0); break;
        case EV_POS: io.AddMousePosEvent(e.x, e.y); break;
        case EV_BUTTON: io.AddMouseButtonEvent(e.a, e.b != 0); break;
        case EV_WHEEL: io.AddMouseWheelEvent(e.x, e.y); break;
        case EV_FOCUS: io.AddFocusEvent(e.a != 0); break;
        }
    }
}

// ---- gamepad navigation: the Switch buttons of the controllers (hid.c, after MLB_PAD_MAP) to ImGui's gamepad keys.
// A confirms, B goes back, L / R switch tabs.
enum { P_A = 0, P_B = 1, P_X = 2, P_Y = 3, P_L = 6, P_R = 7, P_ZL = 8, P_ZR = 9, P_LEFT = 12, P_UP = 13, P_RIGHT = 14,
       P_DOWN = 15 };
static const struct { int bit; ImGuiKey key; } pad_keys[] = {
    {P_A, ImGuiKey_GamepadFaceDown}, {P_B, ImGuiKey_GamepadFaceRight}, {P_X, ImGuiKey_GamepadFaceUp},
    {P_Y, ImGuiKey_GamepadFaceLeft}, {P_L, ImGuiKey_GamepadL1}, {P_R, ImGuiKey_GamepadR1},
    {P_ZL, ImGuiKey_GamepadL2}, {P_ZR, ImGuiKey_GamepadR2}, {P_LEFT, ImGuiKey_GamepadDpadLeft},
    {P_UP, ImGuiKey_GamepadDpadUp}, {P_RIGHT, ImGuiKey_GamepadDpadRight}, {P_DOWN, ImGuiKey_GamepadDpadDown},
};
static uint64_t pad_prev;   // buttons at the last frame; a button held when the menu opened counts once released
static int stick_dir = -1;  // the D-pad button the left stick holds, -1 none

// The left stick moves the cursor as the D-pad does (ImGui's own stick handling only scrolls the page): past half way
// it holds the D-pad direction of its larger axis, kept until that axis falls under 0.35; ImGui repeats a held one.
static int stick_to_dpad(int32_t lx, int32_t ly) {
    float x = lx / 32767.0f, y = ly / 32767.0f;   // y up
    float along = stick_dir == P_LEFT ? -x : stick_dir == P_RIGHT ? x : stick_dir == P_UP ? y : stick_dir == P_DOWN ? -y : 0;
    if (stick_dir >= 0 && along > 0.35f) return stick_dir;
    if (fmaxf(fabsf(x), fabsf(y)) < 0.5f) return -1;
    return fabsf(x) > fabsf(y) ? (x < 0 ? P_LEFT : P_RIGHT) : (y > 0 ? P_UP : P_DOWN);
}

static void pad_events(ImGuiIO &io, int reset) {
    uint64_t b;
    int32_t lx, ly;
    int have = hid_menu_pad(&b, &lx, &ly);
    if (have) io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
    else io.BackendFlags &= ~ImGuiBackendFlags_HasGamepad;
    stick_dir = stick_to_dpad(lx, ly);
    if (stick_dir >= 0) b |= 1ull << stick_dir;
    if (reset) {
        pad_prev = b;
        return;
    }
    for (const auto &k : pad_keys) {
        uint64_t m = 1ull << k.bit;
        if ((b ^ pad_prev) & m) io.AddKeyEvent(k.key, (b & m) != 0);
    }
    pad_prev = b;
}

// ---- ImGui and its Vulkan back end (present path)
static int g_ctx_ok;              // context made
static int g_vk_ok;               // back end initialised for g_vk_fmt
static VkFormat g_vk_fmt;
static float g_font_scale;        // the scale of the uploaded font atlas; 0 when none is uploaded
static float g_style_scale;       // the scale the style was last sized for
static ImGuiStyle g_base_style;   // the menu's style at 1080 lines
static uint64_t g_last_ns;

// Sizes are tuned for 1080 lines and follow the window's height, at least the 720-line size scaled by the display's DPI.
static float menu_scale(uint32_t h) {
    float least = 720.0f * (float)gfx_window_dpi() / 96.0f;
    return ((float)h >= least ? (float)h : least) / 1080.0f;
}

static void style_init(ImGuiStyle &s) {
    ImGui::StyleColorsDark(&s);
    s.WindowRounding = 14; s.FrameRounding = 8; s.GrabRounding = 8; s.TabRounding = 8; s.ChildRounding = 10;
    s.WindowPadding = ImVec2(28, 22); s.FramePadding = ImVec2(14, 8); s.ItemSpacing = ImVec2(14, 12);
    s.WindowBorderSize = 0; s.ScrollbarSize = 18;
    ImVec4 *c = s.Colors;
    ImVec4 gold(0.93f, 0.76f, 0.33f, 1), green(0.15f, 0.36f, 0.25f, 1);
    c[ImGuiCol_WindowBg] = ImVec4(0.06f, 0.09f, 0.08f, 0.94f);
    c[ImGuiCol_ChildBg] = ImVec4(0, 0, 0, 0);
    c[ImGuiCol_Text] = ImVec4(0.96f, 0.94f, 0.88f, 1);
    c[ImGuiCol_TextDisabled] = ImVec4(0.62f, 0.64f, 0.58f, 1);
    c[ImGuiCol_Button] = ImVec4(0.14f, 0.22f, 0.18f, 1);
    c[ImGuiCol_ButtonHovered] = green;
    c[ImGuiCol_ButtonActive] = ImVec4(0.21f, 0.50f, 0.34f, 1);
    c[ImGuiCol_Tab] = ImVec4(0.12f, 0.18f, 0.15f, 1);
    c[ImGuiCol_TabHovered] = green;
    c[ImGuiCol_TabSelected] = ImVec4(0.21f, 0.44f, 0.31f, 1);
    c[ImGuiCol_TabSelectedOverline] = gold;
    c[ImGuiCol_NavCursor] = gold;
    c[ImGuiCol_Separator] = ImVec4(0.30f, 0.36f, 0.30f, 1);
}

static void make_context(void) {
    ImGui::CreateContext();
    ImGuiIO &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.LogFilename = nullptr;
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
    io.BackendPlatformName = "mlb_menu";
    style_init(g_base_style);
    ImGui::GetStyle() = g_base_style;
    g_ctx_ok = 1;
}

static void vk_down(void) {
    if (!g_vk_ok) return;
    ImGui_ImplVulkan_Shutdown();
    g_vk_ok = 0;
    g_font_scale = 0;
}

static int vk_up(const MenuTarget *t) {
    if (g_vk_ok && g_vk_fmt == t->format) return 1;
    if (g_vk_ok) {   // the swapchain changed format (the game switched sRGB / UNORM): pipelines for the new one
        vk_queue_lock();
        vkQueueWaitIdle(t->queue);
        vk_queue_unlock();
        vk_down();
    }
    ImGui_ImplVulkan_InitInfo ii = {};
    ii.ApiVersion = VK_API_VERSION_1_3;
    ii.Instance = t->instance;
    ii.PhysicalDevice = t->phys;
    ii.Device = t->device;
    ii.QueueFamily = t->queue_family;
    ii.Queue = t->queue;
    ii.DescriptorPoolSize = 16;
    ii.MinImageCount = 2;
    ii.ImageCount = 4;   // vertex buffers rotate per recorded frame: more than gfx_present.c's 2 frames in flight
    ii.MSAASamples = VK_SAMPLE_COUNT_1_BIT;
    ii.UseDynamicRendering = true;
    g_vk_fmt = t->format;
    ii.PipelineRenderingCreateInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO;
    ii.PipelineRenderingCreateInfo.colorAttachmentCount = 1;
    ii.PipelineRenderingCreateInfo.pColorAttachmentFormats = &g_vk_fmt;
    if (!ImGui_ImplVulkan_Init(&ii)) return 0;
    g_vk_ok = 1;
    return 1;
}

// Roboto Medium (Latin) at 26 px per 1080 lines. Made again when the window height changes; the old texture goes after
// the queue is idle (CreateFontsTexture).
static int fonts_up(float scale) {
    static const ImWchar ranges[] = {0x0020, 0x00FF, 0x2010, 0x2027, 0};
    ImFontAtlas *fa = ImGui::GetIO().Fonts;
    fa->Clear();
    ImFontConfig fc;
    fc.FontDataOwnedByAtlas = false;
    fa->AddFontFromMemoryTTF((void *)roboto_ttf, (int)sizeof roboto_ttf, 26.0f * scale, &fc, ranges);
    vk_queue_lock();   // the upload submits on the queue and waits for it
    int ok = ImGui_ImplVulkan_CreateFontsTexture();
    vk_queue_unlock();
    fa->ClearInputData();
    fa->ClearTexData();
    rt_log("menu: font atlas at %.1f px", 26.0f * scale);
    g_font_scale = ok ? scale : 0;
    return ok;
}

extern "C" void menu_vk_release(void) {
    if (g_ctx_ok) vk_down();
}

extern "C" int menu_font_check(void) { return 1; }

// ---- the pages
enum { TAB_GRAPHICS, TAB_DISPLAY, TAB_GAME, TAB_SOUND, TAB_CONTROLS, TAB_ADVANCED, TAB_COUNT };
static const char *const kTabNames[TAB_COUNT] = {"Graphics", "Display", "Game", "Sound", "Controls", "Advanced"};
static int g_tab;               // the tab shown
static int g_tab_request = -1;  // select this tab at the next layout; -1 none
static int g_focus_page = -1;   // this tab's first row takes the cursor once it is shown; -1 none
static bool g_modal;            // a confirmation is open: B and Esc close it, not the menu; L / R stay on the page

// Every setting the pages show, for "Reset all settings" (cfg_reset) and "Restart now".
static const char *const kMenuKeys[] = {
    "RENDER_SCALE", "UPSCALER", "SHARPNESS", "DLSS", "DLSS_PRESET", "FSR", "FSR_VERSION", "FSR_SHARPNESS", "AA", "AA_STRENGTH", "ANISO", "COLOR_PRESET", "COLOR_BRIGHTNESS", "COLOR_CONTRAST", "COLOR_SATURATION",
    "COLOR_GAMMA", "FULLSCREEN", "WINDOW_SIZE", "VK_PRESENT", "FPS_LIMIT", "ASPECT", "GPU_INDEX", "PERF_OVERLAY", "FRAME_QUEUE",
    "ASSUME_FOCUS", "KEEP_TUTORIALS", "RTTS_AUTOSAVE", "WALKUP_LIGHT", "WALKUP_LEADERS", "VOLUME", "PAD_MAP", "PROMPTS", "RUMBLE", "RUMBLE_STRENGTH", "STICK_DEADZONE", "LSTICK_DEADZONE",
    "RSTICK_DEADZONE", "ASYNC_PREEMPT", "REPLAY_ASYNC", "PIPE_WAIT", "PIPE_SKIP", "LIB_PREBUILD",
    "LIB_PREBUILD_THREADS", "PIPE_PREBUILD", "PREWARM_XLATE", "GPL", "ASTC", "MEMORY", "TEX_ALIAS",
    "TEX_VRAM_PRESSURE", "ASTC_BC", "LOD_GUARD", "FIX_C0", "FIX_ZERO", "BIND_SKIP", "SHADER_MEMO", "PIPE_MEMO",
    "TEX_MEMO", "DESC_TEMPLATE", "PUSH_SKIP", "SPLIT_DRAWS", "VK_VALIDATION", "VK_DYN_VERTEX", "VK_DYN_A2C",
    "VK_SUBGROUP_PIN",
};
enum { N_MENU_KEYS = sizeof kMenuKeys / sizeof *kMenuKeys };

// The settings read only at start: each one's value as this run started, so "Restart now" shows once one differs.
static struct { const char *key; char at_start[64]; } g_restart_keys[N_MENU_KEYS];
static int g_n_restart_keys = -1;

static void note_start_values(void) {
    g_n_restart_keys = 0;
    for (const char *k : kMenuKeys) {
        const CfgMeta *m = cfg_meta(k);
        if (!m || m->live) continue;
        g_restart_keys[g_n_restart_keys].key = k;
        snprintf(g_restart_keys[g_n_restart_keys++].at_start, sizeof g_restart_keys[0].at_start, "%s", cfg_value(k));
    }
}

static bool restart_pending(void) {
    for (int i = 0; i < g_n_restart_keys; i++)
        if (strcmp(cfg_value(g_restart_keys[i].key), g_restart_keys[i].at_start)) return true;
    return false;
}

// NVIDIA DLSS (vk_dlaa.c): what it does in this run, under its row; NULL when it was off at start. The rows DLSS
// replaces while it runs say so.
extern "C" const char *vk_dlaa_status(void);
extern "C" int vk_dlaa_on(void);
extern "C" const char *vk_dlaa_name(void);
// fastball: AMD FSR 3.1 / 4 (vk_ffx.c) runs through the same machinery as DLSS: the rows it replaces name the one
// running.
extern "C" const char *vk_ffx_status(void);
// fastball: rows this PC cannot use, or that do nothing with the other settings as they are, are greyed out
// (opt_unavailable) with the reason. DLSS and FSR rows that are set stay changeable, so they can be turned off.
extern "C" const char *vk_dlaa_missing(void);
extern "C" const char *vk_ffx_missing(void);
extern "C" int vk_ffx_has4(void);
static bool set_on(const char *key) { return strcmp(cfg_value(key), "off") != 0; }
// The temporal upscaler the settings choose (DLSS wins), when this PC can run it: it replaces the internal
// resolution, the upscaling and FXAA. From the settings, not the running one: a change waiting for a restart shows.
static const char *replaced_why(void) {
    if (set_on("DLSS") && !vk_dlaa_missing()) return "Replaced by DLSS";
    if (set_on("FSR") && !vk_ffx_missing()) return "Replaced by FSR";
    return nullptr;
}

// What the antialiasing pass did lately (vk_aa_status), under its value.
static const char *aa_note(void) {
    if (replaced_why()) return nullptr;   // (the greyed row says it)
    switch (vk_aa_status()) {
    case 1: return "active";
    case 2: return "waiting for a 3D scene";
    case 3: return "not supported on this GPU";
    default: return nullptr;
    }
}

// Colour adjustment (vk_color.c): a profile writes the four values (TotK Recomp's presets); moving one of them makes
// the profile Custom.
static void rows_color(void) {
    static const struct { const char *name, *b, *c, *s, *g; } presets[] = {
        {"default", "0", "100", "100", "1"}, {"vivid", "0", "115", "135", "0.95"}, {"clarity", "2", "110", "115", "1"}};
    static const char *const names[] = {"Default", "Vivid", "Clarity", "Custom"};
    opt_group("Colour");
    if (opt_choice("COLOR_PRESET", "Colour profile", names, 4,
                   "Ready-made colour settings. Vivid raises contrast and saturation; Clarity is a gentler lift. "
                   "Changing any value below switches this to Custom.")) {
        const char *p = cfg_value("COLOR_PRESET");
        for (const auto &e : presets)
            if (!strcmp(p, e.name)) {
                cfg_set_saved("COLOR_BRIGHTNESS", e.b), cfg_set_saved("COLOR_CONTRAST", e.c);
                cfg_set_saved("COLOR_SATURATION", e.s), cfg_set_saved("COLOR_GAMMA", e.g);
            }
    }
    bool moved = opt_slider("COLOR_BRIGHTNESS", "Brightness", -30, 30,
                            "Lightens or darkens the whole picture, HUD included.", 1, "%+.0f %%");
    moved |= opt_slider("COLOR_CONTRAST", "Contrast", 70, 150, "Spreads bright and dark parts further apart.", 5,
                        "%.0f %%");
    moved |= opt_slider("COLOR_SATURATION", "Saturation", 50, 200, "How strong the colours are. 100 % is the game's own.",
                        5, "%.0f %%");
    moved |= opt_slider("COLOR_GAMMA", "Gamma", 0.8f, 1.2f, "Brightens (below 1) or deepens (above 1) the mid-tones.",
                        0.02f, "%.2f");
    if (moved && strcmp(cfg_value("COLOR_PRESET"), "custom")) cfg_set_saved("COLOR_PRESET", "custom");
}

// "in use: ..." under the upscaler while FSR has nothing to do (the scene is as large as the picture or larger).
static const char *upscaler_note(void) {
    if (replaced_why()) return nullptr;
    if (strcmp(cfg_value("UPSCALER"), "fsr") || !strcmp(cfg_value("RENDER_SCALE"), "game")) return nullptr;
    return "not used at this resolution";
}

static void tab_graphics(float scale) {
    opt_begin("##graphics", scale);
    opt_group("Resolution");
    static const char *const rs[] = {"game", "100", "125", "150"};
    static const char *const rs_names[] = {"Game (1440 \xc3\x97 810)", "100 % (1920 \xc3\x97 1080)",
                                           "125 % (2400 \xc3\x97 1350)", "150 % (2880 \xc3\x97 1620)"};
    const char *replaced = replaced_why();
    opt_unavailable(replaced);
    opt_choice_list("RENDER_SCALE", "Internal resolution", rs, rs_names, 4,
                    "The size the game draws its 3D scene at. On the TV the game draws it at 1440 x 810 and stretches it "
                    "to 1080p, which makes it soft. 100 % draws it at full 1080p; 125 % and 150 % draw it larger and "
                    "shrink it, which also smooths edges (supersampling). The HUD and menus are always 1080p.\n\n"
                    "Costs GPU time and video memory: 150 % draws about four times the pixels of the game's size. "
                    "200 % runs the game out of its own graphics memory and crashes, so it is not offered.",
                    -1);
    static const char *const up[] = {"FSR 1", "Bilinear"};
    opt_unavailable(replaced);
    opt_choice("UPSCALER", "Upscaling", up, 2,
               "How the 3D scene is stretched to 1080p when the internal resolution is the game's.\n\n"
               "Bilinear is the game's own. FSR 1 (AMD FidelityFX Super Resolution) keeps edges and detail sharper. "
               "It runs before the game draws its HUD, so text is not touched. It also scales the picture up when "
               "the window is larger than 1080p. Costs a fraction of a millisecond.",
               upscaler_note());
    opt_unavailable(replaced ? replaced : strcmp(cfg_value("UPSCALER"), "fsr") ? "Only with Upscaling on FSR 1" : nullptr);
    opt_slider("SHARPNESS", "FSR 1 sharpness", 0, 100,
               "How much FSR 1 sharpens after scaling up; 0 turns the sharpening off.", 5, "%.0f %%");
    opt_group("NVIDIA DLSS");
    static const char *const dlss[] = {"off", "dlaa", "quality", "balanced", "performance", "ultra_performance"};
    static const char *const dlss_names[] = {"Off", "DLAA (1920 \xc3\x97 1080)", "Quality (1440 \xc3\x97 810)",
                                             "Balanced (1114 \xc3\x97 626)", "Performance (960 \xc3\x97 540)",
                                             "Ultra Performance (640 \xc3\x97 360)"};
    const char *dlss_no = vk_dlaa_missing(), *fsr_no = vk_ffx_missing();
    opt_unavailable(set_on("DLSS") ? nullptr : dlss_no);
    bool dlss_set = opt_choice_list("DLSS", "DLSS", dlss, dlss_names, 6,
                    "NVIDIA DLSS on the 3D scene, for GeForce RTX graphics cards. It draws the scene at the size shown "
                    "and uses AI to rebuild a sharp, smooth 1080p picture from it and from the frames before. It "
                    "replaces the internal resolution, the upscaling and the antialiasing above. The HUD and menus are "
                    "not touched.\n\n"
                    "DLAA draws the scene at full 1080p and only smooths it: the best picture, and the most GPU time. "
                    "Quality draws it at the game's own 1440 x 810, as on the TV, and DLSS turns that into a sharp "
                    "1080p picture in place of the game's plain stretch. Balanced, Performance and Ultra Performance "
                    "draw less for more frame rate.\n\n"
                    "Needs nvngx_dlss.dll (NVIDIA's DLSS library) next to mlb.exe; the setup downloads it on "
                    "GeForce RTX cards. Applies after a restart. Turning DLSS on turns AMD FSR off.",
                    -1, vk_dlaa_status());
    if (dlss_set && strcmp(cfg_value("DLSS"), "off")) cfg_set_saved("FSR", "off");   // one temporal upscaler
    static const char *const preset[] = {"default", "k", "j", "m", "l", "e"};
    static const char *const preset_names[] = {"Default", "K (transformer)", "J (transformer)",
                                               "M (transformer 2)", "L (transformer 2)", "E (older CNN)"};
    opt_unavailable(dlss_no ? dlss_no : !set_on("DLSS") ? "Only with DLSS on" : nullptr);
    opt_choice_list("DLSS_PRESET", "DLSS model", preset, preset_names, 6,
                    "Which of NVIDIA's DLSS models rebuilds the picture.\n\n"
                    "Default follows NVIDIA's advice per mode: K for DLAA, Quality and Balanced, M for Performance, "
                    "L for Ultra Performance. K is the transformer model: sharp and stable. J is its sibling, with a "
                    "little less ghosting and a little more flicker. M and L are NVIDIA's newest models (DLSS 4.5), "
                    "made for the low-resolution modes; they cost noticeably more on RTX 20 and 30 cards, which lack "
                    "the FP8 maths they are built for. E is the older CNN model: the cheapest, softer and with more "
                    "ghosting.\n\n"
                    "Applies at once.");
    opt_group("AMD FSR");
    static const char *const fsr[] = {"off", "native", "quality", "balanced", "performance", "ultra_performance"};
    static const char *const fsr_names[] = {"Off", "Native AA (1920 \xc3\x97 1080)", "Quality (1440 \xc3\x97 810)",
                                            "Balanced (1114 \xc3\x97 626)", "Performance (960 \xc3\x97 540)",
                                            "Ultra Performance (640 \xc3\x97 360)"};
    opt_unavailable(set_on("FSR") ? nullptr : fsr_no);
    bool fsr_set = opt_choice_list("FSR", "FSR", fsr, fsr_names, 6,
                    "AMD FidelityFX Super Resolution (FSR 3.1 or FSR 4) on the 3D scene, for any graphics card. Like "
                    "DLSS, it draws the scene at the size shown and rebuilds a sharp, smooth 1080p picture from it and "
                    "from the frames before. It replaces the internal resolution, the upscaling and the antialiasing "
                    "above. The HUD and menus are not touched.\n\n"
                    "Native AA draws the scene at full 1080p and only smooths it. Quality draws it at the game's own "
                    "1440 x 810. Balanced, Performance and Ultra Performance draw less for more frame rate.\n\n"
                    "Needs AMD's FSR libraries (amd_fidelityfx_loader_vk.dll and amd_fidelityfx_upscaler_vk.dll) next "
                    "to mlb.exe; the setup downloads them. Applies after a restart. Turning FSR on turns DLSS off.",
                    -1, vk_ffx_status());
    if (fsr_set && strcmp(cfg_value("FSR"), "off")) cfg_set_saved("DLSS", "off");   // one temporal upscaler
    static const char *const fsr_ver[] = {"4", "3.1"};
    static const char *const fsr_ver_names[] = {"FSR 4 where supported", "FSR 3.1"};
    const char *fsr_off = fsr_no ? fsr_no : !set_on("FSR") ? "Only with FSR on" : nullptr;
    // FSR 4 is known only once AMD's runtime ran (FSR on at start): on a card without it both choices run 3.1
    opt_unavailable(fsr_off ? fsr_off : vk_ffx_has4() == 0 ? "FSR 4 does not run on this graphics card" : nullptr);
    opt_choice_list("FSR_VERSION", "FSR version", fsr_ver, fsr_ver_names, 2,
                    "FSR 4 uses AI to rebuild the picture: the sharpest and steadiest, on the AMD Radeon cards AMD made "
                    "it for (RX 9000, and RX 6000 / 7000 with AMD's newer drivers) with AMD's own driver. Everywhere "
                    "else FSR 3.1 runs instead, which works on every graphics card (NVIDIA and Intel too).\n\n"
                    "FSR 3.1 always uses FSR 3.1. The note under FSR says which one runs. Applies at once.");
    opt_unavailable(fsr_off);
    opt_slider("FSR_SHARPNESS", "FSR 3.1 / 4 sharpness", 0, 100,
               "How much FSR sharpens its picture; 0 turns the sharpening off. Applies at once.", 5, "%.0f %%");
    opt_group("Antialiasing");
    static const char *const aa[] = {"Off", "FXAA"};
    const char *aa_no = replaced ? replaced : vk_aa_status() == 3 ? "Not supported on this graphics card" : nullptr;
    opt_unavailable(aa_no);
    opt_choice("AA", "Antialiasing", aa, 2,
               "Smooths the jagged, stair-stepped edges of the 3D scene (players, the field lines, the stands, the "
               "bat). The game draws its 3D scene at 1440 x 810 without any smoothing and then stretches it to "
               "1080p, which makes the steps larger.\n\n"
               "FXAA finds edges in the finished 3D picture and blends across them. It runs before the game draws "
               "its HUD and menus, so the score bug and text stay sharp. It costs a fraction of a millisecond.",
               aa_note());
    opt_unavailable(aa_no ? aa_no : strcmp(cfg_value("AA"), "fxaa") ? "Only with FXAA on" : nullptr);
    opt_slider("AA_STRENGTH", "FXAA strength", 0, 100,
               "How much FXAA also softens thin details smaller than a pixel (the netting, distant lines, "
               "shimmering on the grass). Higher is smoother but a little blurrier; 0 only smooths the edges.",
               5, "%.0f %%");
    opt_group("Textures");
    static const char *const aniso[] = {"game", "2", "4", "8", "16"};
    static const char *const aniso_names[] = {"Game", "2x", "4x", "8x", "16x"};
    opt_choice_list("ANISO", "Texture filtering", aniso, aniso_names, 5,
                    "Anisotropic filtering: the grass, the infield dirt and the stands seen at a shallow angle stay "
                    "sharp into the distance instead of blurring. Game: the level the game asks for, as on the Switch. "
                    "Higher levels cost a little GPU time.");
    rows_color();
    opt_end();
}

// ---- Display
enum { MAX_GPUS = 8 };
static char g_gpu_names[MAX_GPUS][VK_MAX_PHYSICAL_DEVICE_NAME_SIZE];
static int g_gpu_n = -1;   // -1: not listed yet

// The Vulkan devices in vkEnumeratePhysicalDevices order, which MLB_GPU_INDEX counts in (vk_device.c pick_device).
static void list_gpus(VkInstance inst) {
    if (g_gpu_n >= 0) return;
    VkPhysicalDevice pd[MAX_GPUS];
    uint32_t n = MAX_GPUS;
    if (vkEnumeratePhysicalDevices(inst, &n, pd) < 0) n = 0;   // VK_INCOMPLETE keeps the first MAX_GPUS
    for (uint32_t i = 0; i < n; i++) {
        VkPhysicalDeviceProperties p;
        vkGetPhysicalDeviceProperties(pd[i], &p);
        snprintf(g_gpu_names[i], sizeof g_gpu_names[i], "%s", p.deviceName);
    }
    g_gpu_n = (int)n;
}

static void row_gpu(void) {
    const char *vals[MAX_GPUS + 1], *names[MAX_GPUS + 1];
    char idx[MAX_GPUS][4];
    vals[0] = "";
    names[0] = "Automatic";
    for (int i = 0; i < g_gpu_n; i++) {
        snprintf(idx[i], sizeof idx[i], "%d", i);
        vals[i + 1] = idx[i];
        names[i + 1] = g_gpu_names[i];
    }
    opt_choice_list("GPU_INDEX", "Graphics card", vals, names, g_gpu_n + 1,
                    "The graphics card that draws the game. Automatic picks the first dedicated card.");
}

static const int kSizes[][2] = {{1280, 720}, {1366, 768}, {1600, 900}, {1920, 1080}, {2560, 1440}, {3200, 1800},
                                {3840, 2160}};
enum { MAX_SIZES = sizeof kSizes / sizeof *kSizes + 1 };

// The common 16:9 sizes up to the monitor's (1920 x 1080 always), and the current one when it is another.
static void row_window_size(void) {
    int sz[MAX_SIZES][2], n = 0, mw = 0, mh = 0, cw = 0, ch = 0;
    int have = gfx_window_monitor_size(&mw, &mh);
    int cur_ok = sscanf(cfg_value("WINDOW_SIZE"), "%dx%d", &cw, &ch) == 2;
    bool listed = false;
    for (size_t i = 0; i < sizeof kSizes / sizeof *kSizes; i++) {
        int w = kSizes[i][0], h = kSizes[i][1];
        bool cur = cur_ok && w == cw && h == ch;
        if (have && (w > mw || h > mh) && !cur && !(w == 1920 && h == 1080)) continue;
        listed |= cur;
        sz[n][0] = w, sz[n][1] = h, n++;
    }
    if (cur_ok && !listed) {   // the current size where its area puts it
        int at = n;
        while (at > 0 && (long)sz[at - 1][0] * sz[at - 1][1] > (long)cw * ch) at--;
        memmove(sz[at + 1], sz[at], sizeof sz[0] * (n - at));
        sz[at][0] = cw, sz[at][1] = ch, n++;
    }
    char vals[MAX_SIZES][24], shown[MAX_SIZES][32];
    const char *pv[MAX_SIZES], *pn[MAX_SIZES];
    for (int i = 0; i < n; i++) {
        snprintf(vals[i], sizeof vals[i], "%dx%d", sz[i][0], sz[i][1]);
        snprintf(shown[i], sizeof shown[i], "%d \xc3\x97 %d", sz[i][0], sz[i][1]);   // U+00D7, the multiplication sign
        pv[i] = vals[i];
        pn[i] = shown[i];
    }
    opt_choice_list("WINDOW_SIZE", "Window size", pv, pn, n,
                    "The size of the game window when it is not fullscreen. The game itself still renders at "
                    "1080p and is scaled to the window.");
}

// The menu's name of an MLB_VK_PRESENT mode; NULL for another.
static const char *present_name(const char *mode) {
    return !strcmp(mode, "fifo") ? "VSync" : !strcmp(mode, "mailbox") ? "Fast VSync"
         : !strcmp(mode, "immediate") ? "Off" : nullptr;
}

// "in use: VSync" under the Presentation value when the swapchain got another mode than the setting (a driver without
// mailbox gets fifo); NULL when they agree or before the first swapchain.
static const char *present_note(void) {
    const char *got = gfx_window_present_mode(), *name = present_name(got);
    if (!*got || !strcmp(got, cfg_value("VK_PRESENT")) || !name) return nullptr;
    static char note[64];
    snprintf(note, sizeof note, "in use: %s", name);
    return note;
}

extern "C" const char *frame_rate_note(void);   // runtime/mlb/framerate.c

static void tab_display(float scale) {
    opt_begin("##display", scale);
    opt_toggle("FULLSCREEN", "Fullscreen", "Borderless fullscreen on the monitor the window is on. F11 also switches it.");
    row_window_size();
    static const char *const present[] = {"Fast VSync", "VSync", "Off (tearing)"};
    opt_choice("VK_PRESENT", "Presentation", present, 3,
               "How finished frames reach the screen.\n\nFast VSync shows the newest frame at each refresh without "
               "tearing or waiting. VSync waits for the display's refresh (more input delay). Off shows frames as soon "
               "as they are done and can tear.",
               present_note());
    // fastball: MLB_FPS_LIMIT (runtime/mlb/framerate.c)
    static const char *const fps[] = {"30", "40", "45", "60", "90", "120", "144", "165", "240", "display"};
    static const char *const fps_names[] = {"30", "40", "45", "60 (the game's own)", "90", "120", "144", "165", "240",
                                            "Monitor refresh rate"};
    opt_choice_list("FPS_LIMIT", "Frame rate limit", fps, fps_names, 10,
                    "The most frames per second the game draws. 60 is the game's own.\n\n"
                    "The game moves by the time each frame took, not by a count of frames, so it plays at the same "
                    "speed at any limit. A limit above your monitor's refresh rate only helps with Presentation set to "
                    "Fast VSync or Off. A few game situations step by fixed 1/60 s ticks: there the game keeps its own "
                    "60 fps by itself. Higher limits need more CPU and GPU. Applies at once.",
                    -1, frame_rate_note());
    static const char *const aspect[] = {"Keep 16:9", "Stretch"};
    opt_choice("ASPECT", "Aspect ratio", aspect, 2,
               "Keep 16:9 adds black bars when the window has another shape. Stretch fills the window and distorts "
               "the picture.");
    row_gpu();
    static const char *const perf[] = {"Off", "FPS", "Full"};
    opt_choice("PERF_OVERLAY", "Performance overlay", perf, 3,
               "The frame rate in the top right corner. Full adds frame times with a graph, CPU, GPU and memory load, "
               "temperatures and where the render thread waited. F10 cycles the modes.\n\n"
               "Off costs nothing; FPS next to nothing; Full samples the machine twice a second and times the GPU.");
    opt_end();
}

// ---- Game
// Play time across runs (playtime.c), read only. Hidden while it is not counted (no profile directory).
static void row_play_time(void) {
    uint64_t total, session;
    if (!playtime_get(&total, &session)) return;
    char value[64], desc[512];
    snprintf(value, sizeof value, "%llu h %02u min", (unsigned long long)(total / 3600), (unsigned)(total / 60 % 60));
    snprintf(desc, sizeof desc,
             "Time in the game over all runs, counted while the game window has the focus and the game draws frames. "
             "Kept in playtime.txt in the profile folder, next to the saves.\n\nThis run: %llu h %02u min.",
             (unsigned long long)(session / 3600), (unsigned)(session / 60 % 60));
    opt_button("##play_time", "Play time", desc, value);
}

// The game's code patches (tools/data/patches-<version>.txt, runtime/core/patches.c): -1 when this build has no such set
extern "C" int rt_patch_set(const char *name);

static void tab_game(float scale) {
    const char *no_patches = "Not in this build: it was made without the game's code patches";
    opt_begin("##game", scale);
    // mlbts-native: MLB_SKIP_INTRO (fs_host.c) — the boot logos answered as missing files
    opt_toggle("SKIP_INTRO", "Skip intro logos",
               "Go straight to the game-modes menu at start: the legal screen and the two intro movies are left "
               "out. Applies at the next start of the game.");
    opt_toggle("FRAME_QUEUE", "Frame queue",
               "The game starts a frame while the previous one waits for its turn on screen: far fewer dropped frames "
               "at 60 fps, up to one frame more input delay. Applies at once.");
    opt_toggle("ASSUME_FOCUS", "Keep running out of focus",
               "On (the default), the game keeps running while you are in another window, and the keyboard stays "
               "quiet until the window is in front again. Off, it pauses when its window loses focus, as on the "
               "Switch when Home is pressed.");
    opt_toggle("KEEP_TUTORIALS", "Remember finished tutorials",
               "On (the default), a tutorial you have finished does not come back the next time you start the game. "
               "The list is kept in tutorials-seen.txt in the profile folder; delete it while the game is closed to "
               "see every tutorial again. Off, they come back on every start. Applies after a restart.");
    opt_toggle("RTTS_AUTOSAVE", "Save hub upgrades",
               "On (the default), when you buy perk or attribute upgrades in Road to the Show, the game's own "
               "autosave runs as you leave that screen. Off, they are kept only by a manual save or the autosave "
               "after your next game. Applies after a restart.");
    opt_unavailable(rt_patch_set("walkup_light") < 0 ? no_patches : nullptr);
    opt_toggle("WALKUP_LIGHT", "No freeze before each pitch",
               "Before each pitch the game redid its stadium lighting in one frame, a freeze of about a quarter "
               "second, though it had already prepared the same lighting in the background. On (the default), it "
               "uses the prepared lighting, and after an inning change it prepares the new lighting in the "
               "background (about a second). Applies after a restart.");
    opt_unavailable(rt_patch_set("walkup_leaders") < 0 ? no_patches : nullptr);
    opt_toggle("WALKUP_LEADERS", "Shorter pause at inning changes",
               "At each inning change the game builds its league-leader lists for the broadcast twice in a row. On "
               "(the default), it builds them once. Applies after a restart.");
    row_play_time();
    opt_end();
}

static void tab_sound(float scale) {
    opt_begin("##sound", scale);
    opt_slider("VOLUME", "Volume", 0, 100, "Master volume of the game: crowd, commentary, music and effects.", 5,
               "%.0f %%");
    opt_end();
}

// ---- Controls
static void tab_controls(float scale) {
    opt_begin("##controls", scale);
    static const char *const map[] = {"Automatic", "By label", "By position"};
    opt_choice("PAD_MAP", "Face buttons", map, 3,
               "How the controller's face buttons map to the Switch buttons.\n\nAutomatic (default): menus confirm "
               "with A or cross and go back with B or circle; while you bat, pitch, field or run, every control is "
               "where it is on PlayStation and Xbox (throw to first with B or circle, home with A or cross, power "
               "swing with X or square). The button icons follow.\n\nBy label: always the menu layout, so gameplay "
               "controls move (the right and bottom buttons trade places, and so do the left and top ones).\n\nBy "
               "position: always the gameplay layout, so menus confirm with B or circle, as in the Switch version.");
    static const char *const prompts[] = {"Automatic", "Nintendo", "Xbox", "PlayStation"};
    opt_choice("PROMPTS", "Button icons", prompts, 4,
               "Whose buttons the game's prompts show.\n\nAutomatic: the controller you used last (Xbox or "
               "PlayStation; the game's own Switch icons with a Nintendo controller, or with none). The face buttons "
               "follow the Face buttons row, so each prompt names the button to press.");
    opt_toggle("RUMBLE", "Vibration", "Controller rumble when the game asks for it.");
    opt_slider("RUMBLE_STRENGTH", "Vibration strength", 0, 300,
               "How strongly the controller vibrates. 100 % is the strength the game asks for; above it, weak "
               "rumble gets stronger and strong rumble stays at the motors' maximum.",
               10, "%.0f %%");
    // One dead zone row per stick, falling back to MLB_STICK_DEADZONE (both sticks) while unset. With a controller
    // connected each row shows how far its stick is pushed now, before the dead zone: a drifting stick's resting value.
    opt_group("Analog sticks");
    double now[2];
    bool pad = hid_stick_percent(now) != 0;
    char note[2][48];
    for (int s = 0; s < 2; s++) snprintf(note[s], sizeof note[s], "stick now: %.0f %%", now[s]);
    static const char dz_desc[] =
        "How far a controller stick moves before the game sees it. Raise it if the batting cursor, a fielder or a "
        "menu cursor moves on its own: let go of the stick, read \"stick now\" and set the dead zone a few percent "
        "above it. The rest of the stick's travel is spread over the full range, so full deflection stays full.";
    opt_slider("LSTICK_DEADZONE", "Left stick dead zone", 0, 50, dz_desc, 1, "%.0f %%", pad ? note[0] : nullptr,
               "STICK_DEADZONE");
    opt_slider("RSTICK_DEADZONE", "Right stick dead zone", 0, 50, dz_desc, 1, "%.0f %%", pad ? note[1] : nullptr,
               "STICK_DEADZONE");
    opt_group("Keys");
    opt_text("Keyboard: left stick W A S D, right stick I J K L, d-pad arrow keys, A Enter or Space, B Esc or "
             "Backspace, X R, Y F, L Q, R E, ZL 1, ZR 3, + Tab, - M, stick clicks C and V.\n\n"
             "Controllers: Xbox and PlayStation pads (DualSense, DualShock 4), several at once. Share / Create or the "
             "touchpad click is -, Options is +.\n\n"
             "This menu: F1, the Xbox or PS button, or Back and Start (Create and Options) together on the "
             "controller. Esc or B closes it, Q / E or LB / RB (L1 / R1) switch the tabs. F10 cycles the performance overlay, F11 switches fullscreen.");
    opt_end();
}

// ---- Advanced: the testing and troubleshooting switches MLB reads, the bug report helpers and the reset
static void row_threads(const char *key, const char *label, const char *desc) {
    static const char *const vals[] = {"", "1", "2", "4", "6", "8", "12", "16", "24", "32", "48", "64"};
    static const char *const names[] = {"Automatic", "1", "2", "4", "6", "8", "12", "16", "24", "32", "48", "64"};
    opt_choice_list(key, label, vals, names, sizeof vals / sizeof *vals, desc);
}

// Automatic (unset) / Off / On, for the keys whose default depends on the machine.
static void row_auto(const char *key, const char *label, const char *desc) {
    static const char *const vals[] = {"", "0", "1"}, *const names[] = {"Automatic", "Off", "On"};
    opt_choice_list(key, label, vals, names, 3, desc);
}

static bool validation_layer_present(void) {
    static int have = -1;
    if (have < 0) {
        uint32_t n = 0;
        vkEnumerateInstanceLayerProperties(&n, nullptr);
        VkLayerProperties *l = (VkLayerProperties *)calloc(n ? n : 1, sizeof *l);
        have = 0;
        if (l && vkEnumerateInstanceLayerProperties(&n, l) >= 0)
            for (uint32_t i = 0; i < n && !have; i++) have = !strcmp(l[i].layerName, "VK_LAYER_KHRONOS_validation");
        free(l);
    }
    return have != 0;
}

// A button's result shown in its value for a few seconds: 1 done, -1 failed.
struct ActionNote { uint64_t until; int result; };

static const char *action_value(const ActionNote &a, const char *done_text) {
    if (!a.result || plat_now_ns() > a.until) return "";
    return a.result > 0 ? done_text : "did not work";
}

static void action_done(ActionNote &a, bool ok) { a = {plat_now_ns() + 3000000000ull, ok ? 1 : -1}; }

// A confirmation over the menu: Cancel has the cursor first; B and Esc cancel. True when yes was chosen.
static bool confirm_popup(const char *id, const char *text, const char *yes, const char *warn, bool yes_disabled,
                          const char *back_to) {
    ImGui::SetNextWindowPos(ImGui::GetMainViewport()->GetCenter(), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    if (!ImGui::BeginPopupModal(id, nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize))
        return false;
    g_modal = true;
    ImGui::TextUnformatted(text);
    if (warn) ImGui::TextColored(ImVec4(0.95f, 0.45f, 0.35f, 1), "%s", warn);
    ImGui::Spacing();
    const char *no = "Cancel";
    const ImGuiStyle &st = ImGui::GetStyle();
    float bw = fmaxf(ImGui::CalcTextSize(yes).x, ImGui::CalcTextSize(no).x) + st.FramePadding.x * 4;
    bool close = ImGui::Button(no, ImVec2(bw, 0)), chosen = false;
    if (ImGui::IsWindowAppearing()) ImGui::SetItemDefaultFocus();
    ImGui::SameLine();
    ImGui::BeginDisabled(yes_disabled);
    if (ImGui::Button(yes, ImVec2(bw, 0))) chosen = close = true;
    ImGui::EndDisabled();
    if (ImGui::IsKeyPressed(ImGuiKey_Escape, false) || ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false))
        close = true;
    if (close) {
        ImGui::CloseCurrentPopup();
        if (back_to) opt_focus_key(back_to);   // back on the row it came from
    }
    ImGui::EndPopup();
    return chosen;
}

// "Restart now": writes mlb.cfg, then closes the game as Quit does and starts it again (gfx_window_request_restart).
// It waits while the game writes a save, and the game stays when mlb.cfg cannot be written, as the new settings would
// not come back.
static void restart_confirm(void) {
    bool saving = fs_save_busy() != 0;
    const char *warn = saving ? "The game is saving: Restart is possible in a moment."
                     : !cfg_last_save_ok() ? "Could not save the settings to mlb.cfg." : nullptr;
    if (!confirm_popup("##restart_confirm", "Restart the game now? Progress since your last save is lost.", "Restart",
                       warn, saving, nullptr))
        return;
    opt_save_tick(1);
    if (cfg_last_save_ok()) gfx_window_request_restart();
}

static void reset_all(void) {
    int done = cfg_reset(kMenuKeys, N_MENU_KEYS);
    opt_save_soon();
    rt_log("menu: reset %d settings to their defaults", done);
}

static void tab_advanced(float scale) {
    static ActionNote copy_note, log_note;
    opt_begin("##advanced", scale);
    opt_text("These settings are for testing and troubleshooting. Change them only when you know why.", true);

    opt_group("Scheduling");
    static const char *const preempt[] = {"Off", "On", "Inheritance only"};
    opt_choice("ASYNC_PREEMPT", "Virtual core preemption", preempt, 3,
               "Lets a game thread interrupt another one on the same virtual core, as the Switch does.");
    opt_toggle("REPLAY_ASYNC", "GPU frame prep on its own thread",
               "Prepares frames for the GPU on a separate thread instead of the game's main thread. Off, busy at-bat "
               "scenes ran at 45-55 fps; on, 60. Adds up to one frame of latency.");

    opt_group("Shaders and pipelines");
    static const char *const wait[] = {"Default", "Old (draw)"};
    opt_choice("PIPE_WAIT", "Waiting draw handling", wait, 2,
               "Default keeps the current scheduling with a reserved worker for waiting draws; Old (draw) uses the "
               "previous scheduling.");
    static const char *const skip[] = {"Strict", "Any", "Fullscreen passes"};
    opt_choice("PIPE_SKIP", "Draws skipped while a pipeline builds", skip, 3,
               "Which draws are dropped for a frame instead of waiting for their pipeline to be built.");
    opt_toggle("LIB_PREBUILD", "Stage library prebuild", "Builds shader stage libraries ahead of time in the background.");
    row_threads("LIB_PREBUILD_THREADS", "Stage library prebuild threads",
                "Threads used for the prebuild; Automatic picks a number from your CPU.");
    opt_toggle("PIPE_PREBUILD", "Pipeline prebuild", "Builds known pipelines ahead of time.");
    row_threads("PREWARM_XLATE", "Translator prewarm",
                "Threads that translate known shaders at start; Automatic takes half the CPU threads, at most 16.");
    opt_toggle("GPL", "Graphics pipeline library",
               "Uses the Vulkan pipeline library extension; turn off if your driver misbehaves with it.");

    opt_group("Textures and memory");
    static const char *const astc[] = {"Automatic", "GPU shader", "Native", "CPU"};
    opt_choice("ASTC", "ASTC texture decoding", astc, 4, "Where compressed ASTC textures are decoded.");
    static const char *const mem[] = {"Automatic", "Import", "Mirror", "Verify"};
    opt_choice("MEMORY", "GPU memory mode", mem, 4,
               "How game memory is shared with the GPU. Automatic: a video-memory mirror on a dedicated card, "
               "shared memory on an integrated one.");
    opt_toggle("TEX_ALIAS", "Texture aliasing",
               "A new texture created over a live texture's memory starts with that content instead of empty.");
    opt_slider("TEX_VRAM_PRESSURE", "Texture memory limit", 0, 100,
               "Percent of video memory above which textures the game released are dropped (they come back from "
               "storage when used again). 0 keeps them.",
               1, "%.0f %%");
    row_auto("ASTC_BC", "Compress ASTC to BC3",
             "With the GPU decoder: re-encodes decoded ASTC textures to BC3, a quarter of the video memory. Textures "
             "look slightly blockier. Automatic: on for GPUs with 4 GB of video memory or less.");

    opt_group("Render fixes");
    opt_toggle("LOD_GUARD", "LOD guard",
               "Waits for the game to finish rewriting level-of-detail data before the GPU reads it.");
    opt_toggle("FIX_C0", "Constant buffer fix",
               "Fills the driver-reserved constant bank c0 (storage sizes, dispatch size, point size, base instance) "
               "instead of reading zeros.");
    opt_toggle("FIX_ZERO", "Zero new GPU memory", "New GPU memory pools start zero-filled, as Switch memory does.");
    opt_toggle("BIND_SKIP", "Skip repeated binds", "Optimisation: skips bindings that did not change.");
    opt_toggle("SHADER_MEMO", "Shader memo", "Optimisation: remembers shader lookups.");
    opt_toggle("PIPE_MEMO", "Pipeline memo", "Optimisation: reuses the previous draw's pipeline when its state repeats.");
    opt_toggle("TEX_MEMO", "Texture binding memo", "Optimisation: remembers texture descriptors between draws.");
    opt_toggle("DESC_TEMPLATE", "Descriptor templates", "Optimisation: updates descriptors in bulk.");
    opt_toggle("PUSH_SKIP", "Skip repeated push constants", "Optimisation: skips push constants that did not change.");
    opt_slider("SPLIT_DRAWS", "Early GPU submission", 0, 1000,
               "Submits GPU work in parts every N draws between passes so the GPU starts earlier; 0 turns it off.", 8,
               "%.0f");

    opt_group("Vulkan");
    opt_toggle("VK_VALIDATION", "Validation layer",
               validation_layer_present()
                   ? "Checks every Vulkan call and slows the game down a lot."
                   : "Checks every Vulkan call and slows the game down a lot.\n\nThe validation layer is not installed "
                     "(it comes with the Vulkan SDK): turning this on does nothing.");
    row_auto("VK_DYN_VERTEX", "Dynamic vertex state",
             "Forces dynamic vertex input on or off; Automatic depends on the GPU.");
    row_auto("VK_DYN_A2C", "Dynamic alpha to coverage",
             "Forces dynamic alpha to coverage on or off. Automatic: off on AMD's driver for RDNA 2 and older, on "
             "elsewhere.");
    opt_toggle("VK_SUBGROUP_PIN", "Pin subgroup size", "Fixes the shader subgroup size.");

    opt_group("Diagnostics");
    if (opt_button("##open_log", "Open log folder", "Shows the folder with mlb.log, the log of this run.",
                   action_value(log_note, ""))) {
        char dir[512];
        bool ok = sysinfo_log_folder(dir, sizeof dir) && plat_open_folder(dir);
        if (!ok) action_done(log_note, false);   // success shows as the opened folder
    }
    if (opt_button("##copy_info", "Copy system info",
                   "Copies the GPU, driver, CPU, RAM and every changed setting to the clipboard, for a bug report.",
                   action_value(copy_note, "Copied"))) {
        static char text[16384];
        action_done(copy_note, sysinfo_text(text, sizeof text) > 0 && plat_clipboard_set(text));
    }
    bool ask_reset = opt_button("##reset", "Reset all settings to defaults",
                                "Every setting on every tab back to its default, written to mlb.cfg. Settings an "
                                "environment variable fixes stay.");
    opt_end();
    if (ask_reset) ImGui::OpenPopup("##reset_confirm");   // at the level BeginPopupModal looks it up
    if (confirm_popup("##reset_confirm", "Reset every setting to its default?", "Reset", nullptr, false, "##reset"))
        reset_all();
}

// ---- the window: title, tabs (L / R or Q / E switch), the page, and the bottom row with "Restart now" (once a
// setting read at start changed), "Continue" and "Quit game". B on the gamepad and Esc close it.
static void layout_menu(uint32_t w, uint32_t h, float scale) {
    ImGui::GetBackgroundDrawList()->AddRectFilled(ImVec2(0, 0), ImVec2((float)w, (float)h), IM_COL32(0, 0, 0, 120));
    float ww = fminf(w * 0.88f, 1400 * scale), wh = fminf(h * 0.86f, 820 * scale);
    ImGui::SetNextWindowPos(ImVec2(w * 0.5f, h * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(ww, wh), ImGuiCond_Always);
    ImGui::Begin("##menu", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                        ImGuiWindowFlags_NoSavedSettings);
    ImGui::TextColored(ImVec4(0.93f, 0.76f, 0.33f, 1), "Settings");
    char version[96];   // right-aligned on the title line
    snprintf(version, sizeof version, "Fastball %s, MLB The Show 26 %s", rt_port_version, rt_game_build);
    ImGui::SameLine(ImGui::GetWindowWidth() - ImGui::GetStyle().WindowPadding.x - ImGui::CalcTextSize(version).x);
    ImGui::TextDisabled("%s", version);

    bool was_modal = g_modal;
    g_modal = false;   // set again by a confirmation laid out this frame
    int step = was_modal ? 0
             : ImGui::IsKeyPressed(ImGuiKey_GamepadR1, false) || ImGui::IsKeyPressed(ImGuiKey_E, false) ? 1
             : ImGui::IsKeyPressed(ImGuiKey_GamepadL1, false) || ImGui::IsKeyPressed(ImGuiKey_Q, false) ? -1
                                                                                                         : 0;
    if (step) g_tab_request = (g_tab + step + TAB_COUNT) % TAB_COUNT;
    if (g_tab_request >= 0) g_focus_page = g_tab_request;   // the new page's first row takes the cursor

    const ImGuiStyle &st = ImGui::GetStyle();
    float bottom = ImGui::GetFrameHeight() + st.ItemSpacing.y * 2;
    if (ImGui::BeginTabBar("##tabs", ImGuiTabBarFlags_NoTabListScrollingButtons)) {
        for (int k = 0; k < TAB_COUNT; k++) {
            char label[64];
            snprintf(label, sizeof label, "  %s  ###tab%d", kTabNames[k], k);
            if (!ImGui::BeginTabItem(label, nullptr, g_tab_request == k ? ImGuiTabItemFlags_SetSelected : 0)) continue;
            g_tab = k;
            if (g_focus_page == k) {
                opt_focus_first();
                g_focus_page = -1;
            }
            ImGui::Spacing();
            // the page's rows are a NavFlattened child of this window itself (TotK's note: behind a second child
            // level the rows scrolled out above the tabs won D-pad moves from the buttons and the tabs)
            opt_reserve_bottom(bottom);
            switch (k) {
            case TAB_GRAPHICS: tab_graphics(scale); break;
            case TAB_DISPLAY: tab_display(scale); break;
            case TAB_GAME: tab_game(scale); break;
            case TAB_SOUND: tab_sound(scale); break;
            case TAB_CONTROLS: tab_controls(scale); break;
            case TAB_ADVANCED: tab_advanced(scale); break;
            }
            ImGui::EndTabItem();
        }
        g_tab_request = -1;
        ImGui::EndTabBar();
    }

    // bottom row: the save status on the left, the buttons on the right
    ImGui::Spacing();
    float y = ImGui::GetCursorPosY();
    ImGui::SetCursorPosY(y + st.FramePadding.y);
    if (!cfg_last_save_ok())   // stays until a save succeeds; the settings hold for the session
        ImGui::TextColored(ImVec4(0.95f, 0.45f, 0.35f, 1), "Could not save the settings to mlb.cfg.");
    else
        ImGui::TextDisabled("Changes are saved to mlb.cfg.");
    bool restart = restart_pending();
    const char *rs = "Restart now", *cont = "Continue", *quit = "Quit game";
    float bw = fmaxf(fmaxf(ImGui::CalcTextSize(cont).x, ImGui::CalcTextSize(quit).x), ImGui::CalcTextSize(rs).x) +
               st.FramePadding.x * 4;
    int nb = restart ? 3 : 2;
    ImGui::SetCursorPos(ImVec2(ImGui::GetWindowWidth() - st.WindowPadding.x - bw * nb - st.ItemSpacing.x * (nb - 1), y));
    if (restart) {
        if (ImGui::Button(rs, ImVec2(bw, 0))) ImGui::OpenPopup("##restart_confirm");
        if (ImGui::IsItemHovered()) ImGui::SetTooltip("A setting you changed applies after a restart.");
        restart_confirm();
        ImGui::SameLine();
    }
    if (ImGui::Button(cont, ImVec2(bw, 0))) change_open(0);
    ImGui::SameLine();
    if (ImGui::Button(quit, ImVec2(bw, 0))) gfx_window_request_close();
    if (!was_modal && !g_modal &&
        (ImGui::IsKeyPressed(ImGuiKey_Escape, false) || ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false)))
        change_open(0);
    ImGui::End();
}

static int g_save_pending;   // a changed setting still waits for its write to mlb.cfg (opt_save_tick)

// ---- the performance overlay (MLB_PERF_OVERLAY), in the top right corner, after TotK Recomp's menu.cpp. "fps": the
// frame rate over the presents of the last half second. "full": a panel of perfmon.c's numbers: the machine's load
// and temperatures, the frame rate and frame times with a graph, the render thread's waits. Off, it costs a
// cfg_version load per present.
static unsigned g_perf_ver = ~0u;
static int g_perf_mode;                  // 0 off, 1 fps, 2 full
static std::atomic<int> g_perf_save;     // F10 changed the mode: mlb.cfg is written on the present thread
static uint64_t g_perf_last_ns, g_perf_win_ns;
static int g_perf_frames;
static char g_perf_text[64];

static int perf_mode_of(const char *s) { return !strcmp(s, "full") ? 2 : !strcmp(s, "fps") ? 1 : 0; }

extern "C" void menu_perf_cycle(void) {
    static const char *const modes[] = {"off", "fps", "full"};
    cfg_set_saved("PERF_OVERLAY", modes[(perf_mode_of(cfg_value("PERF_OVERLAY")) + 1) % 3]);
    g_perf_save.store(1);
}

// The device the game renders on, for perfmon's GPU counters (by LUID), NVML (by name) and ADL (by PCI bus, else
// name); once, before full mode.
static void perf_gpu_once(const MenuTarget *t) {
    static bool done;
    if (done) return;
    done = true;
    uint32_t ne = 0;
    vkEnumerateDeviceExtensionProperties(t->phys, NULL, &ne, NULL);
    VkExtensionProperties *ep = (VkExtensionProperties *)calloc(ne ? ne : 1, sizeof *ep);
    bool has_bus = false;
    if (ep && vkEnumerateDeviceExtensionProperties(t->phys, NULL, &ne, ep) >= 0)
        for (uint32_t i = 0; i < ne && !has_bus; i++) has_bus = !strcmp(ep[i].extensionName, VK_EXT_PCI_BUS_INFO_EXTENSION_NAME);
    free(ep);
    VkPhysicalDevicePCIBusInfoPropertiesEXT bus = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PCI_BUS_INFO_PROPERTIES_EXT};
    VkPhysicalDeviceIDProperties id = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES, has_bus ? &bus : nullptr};
    VkPhysicalDeviceProperties2 p2 = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &id};
    vkGetPhysicalDeviceProperties2(t->phys, &p2);
    VkPhysicalDeviceMemoryProperties mp;
    vkGetPhysicalDeviceMemoryProperties(t->phys, &mp);
    uint64_t vram = 0;
    for (uint32_t h = 0; h < mp.memoryHeapCount; h++)
        if (mp.memoryHeaps[h].flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT) vram += mp.memoryHeaps[h].size;
    perfmon_set_gpu(p2.properties.deviceName, id.deviceLUIDValid ? id.deviceLUID : NULL, has_bus ? (int)bus.pciBus : -1,
                    (float)(vram >> 20));
}

static void perf_tick(uint64_t now, const MenuTarget *t) {
    if (cfg_version() != g_perf_ver) {
        g_perf_ver = cfg_version();
        int m = perf_mode_of(cfg_value("PERF_OVERLAY"));
        if (m != g_perf_mode) {
            g_perf_last_ns = 0, g_perf_text[0] = 0;
            if (m == 2) perf_gpu_once(t);
            perfmon_mode(m);
        }
        g_perf_mode = m;
    }
    if (g_perf_mode != 1) return;
    uint64_t d = now - g_perf_last_ns;
    if (!g_perf_last_ns || d > 2000000000ull) {   // first frame, or a stall the window should not average in
        g_perf_win_ns = 0;
        g_perf_frames = 0;
    } else {
        g_perf_win_ns += d;
        g_perf_frames++;
        if (g_perf_win_ns >= 500000000ull) {
            snprintf(g_perf_text, sizeof g_perf_text, "%.0f fps", g_perf_frames * 1e9 / g_perf_win_ns);
            g_perf_win_ns = 0;
            g_perf_frames = 0;
        }
    }
    g_perf_last_ns = now;
}

// The panel keeps its width while the numbers change: every column is as wide as the widest text it can show, measured
// on samples of 8s (Roboto's digits share one width), and the numbers are right-aligned in it.
struct PerfCol { const char *fmt; float sample; };

static float perf_text_w(const char *fmt, float v) {
    char b[64];
    snprintf(b, sizeof b, fmt, v);
    return ImGui::CalcTextSize(b).x;
}

static void perf_column(const char *id, const PerfCol *cols, int n, const char *const *labels = nullptr, int nl = 0) {
    float w = ImGui::CalcTextSize("-").x;
    for (int i = 0; i < n; i++) w = fmaxf(w, perf_text_w(cols[i].fmt, cols[i].sample));
    for (int i = 0; i < nl; i++) w = fmaxf(w, ImGui::CalcTextSize(labels[i]).x);
    ImGui::TableSetupColumn(id, ImGuiTableColumnFlags_WidthFixed, w);
}

static void perf_right(const char *s, bool dim) {
    float pad = ImGui::GetContentRegionAvail().x - ImGui::CalcTextSize(s).x;
    if (pad > 0) ImGui::SetCursorPosX(ImGui::GetCursorPosX() + pad);
    if (dim) ImGui::TextDisabled("%s", s);
    else ImGui::TextUnformatted(s);
}

// One cell of the full panel's table: fmt (one number) with v, or "-" when the machine gives none.
static void perf_cell(const char *fmt, float v) {
    ImGui::TableNextColumn();
    if (v < 0) return perf_right("-", true);
    char b[64];
    snprintf(b, sizeof b, fmt, v);
    perf_right(b, false);
}

static void perf_label(const char *label, const ImVec4 &c) {
    ImGui::TableNextColumn();
    ImGui::TextColored(c, "%s", label);
}

static float perf_gb(float mb) { return mb < 0 ? -1 : mb / 1024; }

// The picture lines: the window, the game image the present shows, how the present scaled it and the presentation
// mode in use.
static void perf_picture(const MenuTarget *t, const ImVec4 &c) {
    char v[4][64];
    snprintf(v[0], sizeof v[0], "%u \xc3\x97 %u", t->width, t->height);
    snprintf(v[1], sizeof v[1], "%d \xc3\x97 %d", t->image_w, t->image_h);
    snprintf(v[2], sizeof v[2], "%s", t->scaler == 2 ? "FSR 1" : t->scaler ? "bilinear" : "none");
    const char *pm = present_name(gfx_window_present_mode());
    snprintf(v[3], sizeof v[3], "%s", pm ? pm : "-");
    static const char *const labels[4] = {"Window", "Game image", "Scaling", "Presentation"};
    if (!ImGui::BeginTable("##perfp", 2, ImGuiTableFlags_SizingFixedFit)) return;
    float vw = 0;
    for (auto &s : v) vw = fmaxf(vw, ImGui::CalcTextSize(s).x);
    ImGui::TableSetupColumn("##p0", ImGuiTableColumnFlags_WidthStretch);
    ImGui::TableSetupColumn("##p1", ImGuiTableColumnFlags_WidthFixed, vw);
    for (int i = 0; i < 4; i++) {
        perf_label(labels[i], c);
        ImGui::TableNextColumn();
        perf_right(v[i], false);
    }
    ImGui::EndTable();
}

#define DEG_C "\xc2\xb0" "C"   // U+00B0, the degree sign

static void perf_full_draw(const MenuTarget *t, float scale) {
    float w = (float)t->width;
    PerfStats s;
    perfmon_snapshot(&s);
    ImGui::SetNextWindowPos(ImVec2(w - 12 * scale, 12 * scale), ImGuiCond_Always, ImVec2(1, 0));
    ImGui::SetNextWindowBgAlpha(0.6f);
    ImGui::Begin("##perf", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize |
                                        ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoNav |
                                        ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoSavedSettings);
    // under the menu while it is open (the settings stay readable), else over everything
    if (g_open.load(std::memory_order_relaxed)) ImGui::BringWindowToDisplayBack(ImGui::GetCurrentWindow());
    else ImGui::BringWindowToDisplayFront(ImGui::GetCurrentWindow());
    ImGui::SetWindowFontScale(0.72f);
    const ImVec4 gpu_c(0.55f, 0.83f, 0.31f, 1), cpu_c(0.18f, 0.59f, 0.80f, 1), ram_c(0.80f, 0.45f, 0.70f, 1),
        fps_c(0.95f, 0.95f, 0.95f, 1), wait_c(0.93f, 0.76f, 0.33f, 1), pic_c(0.62f, 0.70f, 0.95f, 1);
    ImGui::TextDisabled("Fastball %s, MLB The Show 26 %s", rt_port_version, rt_game_build);
    if (ImGui::BeginTable("##perft", 4, ImGuiTableFlags_SizingFixedFit)) {
        static const char *const labels[] = {"GPU", "VRAM", "CPU", "RAM", "FPS", "Frame"};
        static const PerfCol c1[] = {{"%.0f%%", 100}, {"%.1f GB", 888.8f}, {"%.0f", 888}, {"%.1f ms", 888.8f}};
        static const PerfCol c2[] = {{"%.0f " DEG_C, 188}, {"of %.1f GB", 888.8f}, {"1%% low %.0f", 888},
                                     {"max %.1f ms", 8888.8f}};
        static const PerfCol c3[] = {{"%.0f W", 888}, {"%.0f MHz", 8888}, {"game %.0f%%", 100}, {"game %.1f GB", 888.8f},
                                     {"0.1%% low %.0f", 888}};
        perf_column("##c0", nullptr, 0, labels, 6);
        perf_column("##c1", c1, 4);
        perf_column("##c2", c2, 4);
        perf_column("##c3", c3, 5);
        perf_label("GPU", gpu_c);
        perf_cell("%.0f%%", s.gpu_pct);
        perf_cell("%.0f " DEG_C, s.gpu_temp_c);
        perf_cell("%.0f W", s.gpu_power_w);
        perf_label("VRAM", gpu_c);
        perf_cell("%.1f GB", perf_gb(s.vram_used_mb));
        perf_cell("of %.1f GB", perf_gb(s.vram_total_mb));
        perf_cell("%.0f MHz", s.gpu_clock_mhz);
        perf_label("CPU", cpu_c);
        perf_cell("%.0f%%", s.cpu_total_pct);
        perf_cell("%.0f " DEG_C, s.cpu_temp_c);
        perf_cell("game %.0f%%", s.cpu_game_pct);
        perf_label("RAM", ram_c);
        perf_cell("%.1f GB", perf_gb(s.ram_used_mb));
        perf_cell("of %.1f GB", perf_gb(s.ram_total_mb));
        perf_cell("game %.1f GB", perf_gb(s.ram_game_mb));
        ImGui::TableNextRow(ImGuiTableRowFlags_None, 6 * scale);   // a gap between the machine and the frames
        // the frames: the rate over the last second with the lows over the last ten seconds, then the frame times
        perf_label("FPS", fps_c);
        perf_cell("%.0f", s.fps);
        perf_cell("1%% low %.0f", s.low1_fps);
        perf_cell("0.1%% low %.0f", s.low01_fps);
        perf_label("Frame", fps_c);
        perf_cell("%.1f ms", s.frame_ms_avg);
        perf_cell("max %.1f ms", s.frame_ms_max);
        ImGui::TableNextColumn();
        ImGui::EndTable();
    }
    float top = s.frame_ms_max > 50 ? s.frame_ms_max : 50;
    // as wide as the panel the tables size; the plot does not count toward that width, so the panel can still shrink
    ImGuiWindow *win = ImGui::GetCurrentWindow();
    float max_x = win->DC.CursorMaxPos.x;
    ImGui::PlotLines("##ft", s.frame_ms, PERF_HISTORY, 0, nullptr, 0, top, ImVec2(-FLT_MIN, 48 * scale));
    win->DC.CursorMaxPos.x = max_x;
    // per frame, averaged over the last half second
    if (ImGui::BeginTable("##perfw", 2, ImGuiTableFlags_SizingFixedFit)) {
        static const PerfCol c1[] = {{"%.2f ms", 888.88f}, {"%.1f / frame", 888.8f}};
        ImGui::TableSetupColumn("##w0", ImGuiTableColumnFlags_WidthStretch);
        perf_column("##w1", c1, 2);
        perf_label("GPU frame prep", wait_c);
        perf_cell("%.2f ms", s.replay_ms);
        perf_label("GPU time", wait_c);
        perf_cell("%.2f ms", s.gpu_ms);
        perf_label("Pipeline wait", wait_c);
        perf_cell("%.2f ms", s.pipe_wait_ms);
        perf_label("Shader wait", wait_c);
        perf_cell("%.2f ms", s.xlate_ms);
        perf_label("Texture uploads", wait_c);
        perf_cell("%.1f / frame", s.tex_uploads);
        ImGui::EndTable();
    }
    perf_picture(t, pic_c);
    if (s.gpu_name[0]) ImGui::TextDisabled("%s", s.gpu_name);
    if (s.cpu_name[0]) ImGui::TextDisabled("%s", s.cpu_name);
    ImGui::End();
}

static void perf_draw(const MenuTarget *t, float scale) {
    if (g_perf_mode == 2) return perf_full_draw(t, scale);
    float w = (float)t->width;
    if (!g_perf_mode || !g_perf_text[0]) return;
    // with the menu open: under its window, over the dimming layout_menu drew before
    ImDrawList *dl = g_open.load(std::memory_order_relaxed) ? ImGui::GetBackgroundDrawList() : ImGui::GetForegroundDrawList();
    ImVec2 sz = ImGui::CalcTextSize(g_perf_text);
    float pad = 6 * scale;
    ImVec2 p(w - 12 * scale - sz.x - pad * 2, 12 * scale);
    dl->AddRectFilled(p, ImVec2(p.x + sz.x + pad * 2, p.y + sz.y + pad * 2), IM_COL32(0, 0, 0, 150), 4 * scale);
    dl->AddText(ImVec2(p.x + pad, p.y + pad), IM_COL32(255, 255, 255, 235), g_perf_text);
}

// fastball: MLB presents sRGB images, so the swapchain is sRGB (gfx_present.c create_swapchain) and the hardware
// encodes what the menu writes. ImGui's colours are already sRGB values: written as they are, they came out encoded
// twice, the dark green panels a washed-out grey green (first test shot, 2026-11-13). On an sRGB target the vertex
// colours are turned into linear values first; alpha stays.
static bool srgb_format(VkFormat f) {
    return f == VK_FORMAT_B8G8R8A8_SRGB || f == VK_FORMAT_R8G8B8A8_SRGB || f == VK_FORMAT_A8B8G8R8_SRGB_PACK32;
}

static void linear_colours(ImDrawData *dd) {
    static uint8_t lut[256];
    if (!lut[255])
        for (int i = 0; i < 256; i++) {
            float c = i / 255.0f, l = c <= 0.04045f ? c / 12.92f : powf((c + 0.055f) / 1.055f, 2.4f);
            lut[i] = (uint8_t)lrintf(l * 255.0f);
        }
    for (ImDrawList *dl : dd->CmdLists)
        for (ImDrawVert &v : dl->VtxBuffer) {
            ImU32 c = v.col;
            v.col = (c & 0xff000000u) | (ImU32)lut[c >> 16 & 0xff] << 16 | (ImU32)lut[c >> 8 & 0xff] << 8 | lut[c & 0xff];
        }
}

static uint64_t g_cost_ns, g_cost_frames;   // the menu's own CPU time on frames it draws, logged every 600 of them

extern "C" int menu_overlay_frame(uint64_t frame, const MenuTarget *t, const char **shot) {
    *shot = NULL;
    mlb_capture_tick(frame, shot);   // F12 / MLB_SHOT: this frame's picture to a file
    if (g_n_restart_keys < 0) note_start_values();
    if (g_perf_save.exchange(0)) cfg_save();
    perf_tick(plat_now_ns(), t);
    bool open = g_open.load(std::memory_order_relaxed);
    if (!open) {
        if (g_save_pending) g_save_pending = opt_save_tick(1);   // closed: the last change goes to mlb.cfg now
        // Test hook: MLB_MENU_TEST=<frame>[:<tab>] opens the menu at that presented frame (with MLB_SHOT, a picture of it)
        static long test_at = -2;
        if (test_at == -2) {
            const char *e = cfg_get("MLB_MENU_TEST");
            char *end;
            test_at = e && *e ? strtol(e, &end, 10) : -1;
            if (test_at >= 0 && *end == ':') g_tab_request = atoi(end + 1) % TAB_COUNT;
        }
        if (test_at >= 0 && frame == (uint64_t)test_at) {
            change_open(1);
            open = true;
        } else if (!g_perf_mode) {
            return 0;
        }
    }
    if (g_failed.load(std::memory_order_relaxed)) {
        change_open(0);
        return 0;
    }
    uint64_t t0 = plat_now_ns();
    if (!g_ctx_ok) make_context();
    float scale = menu_scale(t->height);
    if (!vk_up(t) || (g_font_scale != scale && !fonts_up(scale))) {
        rt_log("menu: Dear ImGui Vulkan back end set-up failed; the menu stays closed");
        g_failed.store(1);
        change_open(0);
        return 0;
    }
    if (g_style_scale != scale) {
        ImGui::GetStyle() = g_base_style;
        ImGui::GetStyle().ScaleAllSizes(scale);
        g_style_scale = scale;
    }
    list_gpus(t->instance);
    ImGuiIO &io = ImGui::GetIO();
    int reset = g_reset.exchange(0);
    if (reset) {
        io.ClearInputKeys();
        io.ClearInputMouse();
        g_last_ns = 0;
        g_focus_page = g_tab_request >= 0 ? g_tab_request : g_tab;   // opening: the first row has the cursor
        if (GImGui->OpenPopupStack.Size) ImGui::ClosePopupToLevel(0, false);   // a confirmation left open on closing
        g_modal = false;
    }
    io.DisplaySize = ImVec2((float)t->width, (float)t->height);
    double dt = g_last_ns ? (t0 - g_last_ns) / 1e9 : 1 / 60.0;
    io.DeltaTime = (float)(dt < 1e-4 ? 1e-4 : dt > 0.1 ? 0.1 : dt);
    g_last_ns = t0;
    if (open) {   // closed with the overlay on: no input reaches ImGui
        drain_events(io);
        pad_events(io, reset);
    }
    ImGui_ImplVulkan_NewFrame();
    ImGui::NewFrame();
    if (open) layout_menu(t->width, t->height, scale);
    perf_draw(t, scale);
    ImGui::Render();
    if (srgb_format(t->format)) linear_colours(ImGui::GetDrawData());
    if (open) g_save_pending = opt_save_tick(0);
    g_cost_ns += plat_now_ns() - t0;
    return ImGui::GetDrawData()->TotalVtxCount > 0;
}

extern "C" void menu_overlay_draw(VkCommandBuffer cb) {
    uint64_t t0 = plat_now_ns();
    ImGui_ImplVulkan_RenderDrawData(ImGui::GetDrawData(), cb);
    g_cost_ns += plat_now_ns() - t0;
    if (++g_cost_frames == 600) {
        rt_log("menu: %.3f ms CPU per drawn frame (layout and recording, mean of 600)", g_cost_ns / 600 / 1e6);
        g_cost_ns = g_cost_frames = 0;
    }
}
