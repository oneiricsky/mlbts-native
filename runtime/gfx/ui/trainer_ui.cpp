// The trainer panel (trainer_ui.h): a compact window in a screen corner over the running game. It only reads the
// trainer's view and sends requests; game memory is mlb/trainer_game.c's. Off (MLB_TRAINER=0) it costs one
// cfg_version load and one uncontended lock per present.
#include <atomic>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "imgui.h"
#include "ui/trainer_theme.h"
#include "ui/trainer_ui.h"

extern "C" {
#include "cfg.h"
#include "platform/platform.h"
#include "trainer.h"
#include "trainer_hooks.h"
#include "trainer_ratings.h"
// host.h pulls in cpu.h, which is C only: what the panel needs from it, as declared there.
void rt_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
extern const char rt_game_build[];
typedef struct { const char *exefs, *romfs, *profile; int boot; double seconds; const char *shot, *gpu; } RtConfig;
const RtConfig *rt_config(void);
}

static std::atomic<int> g_on;                       // MLB_TRAINER, for the window thread
static std::atomic<int> g_vk_show, g_vk_save, g_vk_load, g_vk_slow;
static std::atomic<int> g_vk_refill;
static std::atomic<int> g_vk_cheat[4];   // away batting, away pitching, home batting, home pitching
static std::atomic<int> g_vk_sure[TR_CHEATS];   // the guaranteed cheats, in trainer.h's order
static int g_corner = 1;                            // bit 0 right, bit 1 bottom
static int g_opacity = 90;
static char g_show_name[8] = "F2";
static TrView g_view;
static int g_page;   // the panel's page: Match, Pitcher, Hitting, Ratings, Cheats
enum { PAGES = 5 };

static void settings_read(void) {
    static unsigned seen;
    static int read;
    unsigned v = cfg_version();
    if (read && v == seen) return;
    read = 1, seen = v;
    int on = cfg_bool("TRAINER") != 0;
    const char *c = cfg_value("TRAINER_CORNER");
    g_corner = (strstr(c, "right") ? 1 : 0) | (strstr(c, "bottom") ? 2 : 0);
    g_opacity = cfg_int("TRAINER_OPACITY");
    if (g_opacity < TR_ALPHA_MIN || g_opacity > 100) g_opacity = 90;
    const char *show = cfg_value("TRAINER_KEY_SHOW");
    int vk[4];
    int ok = trainer_keys(show, cfg_value("TRAINER_KEY_SAVE"), cfg_value("TRAINER_KEY_LOAD"),
                          cfg_value("TRAINER_KEY_SLOW"), vk);
    if (!ok && on) rt_log("trainer: the four keys must differ and be F2..F7; using F2, F3, F4, F6");
    snprintf(g_show_name, sizeof g_show_name, "%s", ok ? show : "F2");
    g_vk_show.store(vk[0]), g_vk_save.store(vk[1]), g_vk_load.store(vk[2]), g_vk_slow.store(vk[3]);
    static const char *const cheat_rows[4] = {"TRAINER_KEY_AWAY_BAT", "TRAINER_KEY_AWAY_PITCH",
                                              "TRAINER_KEY_HOME_BAT", "TRAINER_KEY_HOME_PITCH"};
    for (int k = 0; k < 4; k++) g_vk_cheat[k].store(trainer_cheat_key(cfg_value(cheat_rows[k])));
    static const char *const sure_rows[TR_CHEATS] = {"TRAINER_KEY_CONTACT", "TRAINER_KEY_HOMER", "TRAINER_KEY_MISS",
                                                     "TRAINER_KEY_AIM", "TRAINER_KEY_STRIKE",
                                                     "TRAINER_KEY_WILD"};
    for (int k = 0; k < TR_CHEATS; k++) g_vk_sure[k].store(trainer_cheat_key(cfg_value(sure_rows[k])));
    g_vk_refill.store(trainer_cheat_key(cfg_value("TRAINER_KEY_REFILL")));
    g_on.store(on);
    trainer_set_enabled(on);
    trainer_hooks_switch(on);
}

#ifdef MLB_DEV_HARNESS
// MLB_TRAINER_TEST="<frames>:<command>;...": trainer_command that many presented frames after the trainer first reads a
// match (match starts drift by thousands of frames between runs). Test runs only.
static void test_commands(uint64_t frame) {
    static const char *next;
    static int read;
    if (!read) next = cfg_get("MLB_TRAINER_TEST"), read = 1;
    static uint64_t start;
    if (next && !start) {
        if (!g_view.enabled || g_view.status != TR_OK) return;   // (an unfilled view reads as TR_OK)
        start = frame;
        rt_log("trainer: test clock starts at frame %llu", (unsigned long long)frame);
    }
    while (next && *next) {
        char *end;
        unsigned long long at = strtoull(next, &end, 10);
        if (end == next || *end != ':') {
            rt_log("trainer: MLB_TRAINER_TEST is not <frame>:<command>;... at \"%s\"", next);
            next = nullptr;
            return;
        }
        if (frame - start < at) return;
        const char *cmd = end + 1, *stop = strchr(cmd, ';');
        char one[64];
        snprintf(one, sizeof one, "%.*s", (int)(stop ? stop - cmd : (long long)strlen(cmd)), cmd);
        int page;
        int ok = sscanf(one, "page %d", &page) == 1 ? page >= 0 && page < PAGES && (g_page = page, 1) : trainer_command(one);
        rt_log("trainer: test +%llu: %s%s", at, one, ok ? "" : " (not understood)");
        next = stop ? stop + 1 : nullptr;
    }
}
#endif

extern "C" void trainer_ui_frame_begin(uint64_t frame) {
    static int started;
    if (!started) {
        tr_game_init(rt_game_build);
        trainer_init(rt_config()->profile);
        started = 1;
    }
    settings_read();
#ifdef MLB_DEV_HARNESS
    test_commands(frame);
#else
    (void)frame;
#endif
    trainer_tick(plat_now_ns());
    trainer_view(&g_view);
}

// What is active while the panel is hidden, for the corner mark; NULL when nothing is.
static const char *mark_text(void) {
    if (!g_view.enabled) return nullptr;
    if (g_view.needs_confirm) return "TRAINER: open the panel to confirm";
    if (g_view.jumping) return "TRAINER: waiting for the next out";
    if (g_view.speed != 100) return "TRAINER: slow motion";
    for (int k = 0; k < TR_CHEATS; k++)
        if (trainer_cheat_sides(k)) return "TRAINER: cheats on";
    for (int who = 0; who < 2; who++)
        for (int group = 0; group < TR_GROUPS; group++)
            if (!g_view.ratings_blocked && trainer_ratings_level(who, group) != TR_NORMAL) return "TRAINER: ratings edited";
    return nullptr;
}

extern "C" int trainer_ui_wants_draw(void) { return g_view.enabled && (g_view.visible || mark_text()); }

extern "C" int trainer_ui_key(unsigned vk) {
    if (!g_on.load()) return 0;
    if ((int)vk == g_vk_show.load()) {
        trainer_toggle();
        return 1;
    }
    for (int k = 0; k < 4; k++)
        if (vk && (int)vk == g_vk_cheat[k].load()) {
            trainer_ratings_cycle(k / 2, k % 2);   // rows in TR_AWAY/TR_HOME by TR_BATTING/TR_PITCHING order
            return 1;
        }
    for (int k = 0; k < TR_CHEATS; k++)
        if (vk && (int)vk == g_vk_sure[k].load()) {
            trainer_cheat_cycle(k);
            return 1;
        }
    if (vk && (int)vk == g_vk_refill.load()) {
        trainer_energy_refill(TR_MINE);
        return 1;
    }
    if ((int)vk == g_vk_slow.load()) {
        trainer_slow_toggle();
        return 1;
    }
    int save = (int)vk == g_vk_save.load();
    if (!save && (int)vk != g_vk_load.load()) return 0;
    TrView v;
    trainer_view(&v);
    if (save) trainer_slot_save(v.slot);
    else trainer_slot_load(v.slot);
    return 1;
}

static ImVec4 col(unsigned rgb, float a = 1.0f) {
    return ImVec4(((rgb >> 16) & 255) / 255.0f, ((rgb >> 8) & 255) / 255.0f, (rgb & 255) / 255.0f, a);
}

static void half_text(char *out, size_t n, int half) {
    snprintf(out, n, "%s %d", half & 1 ? "bottom" : "top", half / 2 + 1);
}

// "<label>  [<] value [>]"; returns -1, 0 or 1.
static int stepper(const char *label, const char *value, bool can_down, bool can_up, float scale) {
    float side = TR_ROW_PX_1080 * scale;
    int step = 0;
    ImGui::PushID(label);
    ImGui::AlignTextToFramePadding();
    ImGui::TextUnformatted(label);
    ImGui::SameLine(TR_LABEL_W * scale);
    ImGui::BeginDisabled(!can_down);
    if (ImGui::Button("<", ImVec2(side, side))) step = -1;
    ImGui::EndDisabled();
    ImGui::SameLine();
    float x = ImGui::GetCursorPosX(), w = TR_VALUE_W * scale;
    ImGui::SetCursorPosX(x + (w - ImGui::CalcTextSize(value).x) * 0.5f);
    ImGui::TextUnformatted(value);
    ImGui::SameLine(x + w);
    ImGui::BeginDisabled(!can_up);
    if (ImGui::Button(">", ImVec2(side, side))) step = 1;
    ImGui::EndDisabled();
    ImGui::PopID();
    return step;
}

static void count_row(const char *label, TrField f, float scale) {
    int v = g_view.now.v[f];
    char text[16];
    snprintf(text, sizeof text, "%d", v);
    int step = stepper(label, text, tr_write_range_ok(f, v - 1), tr_write_range_ok(f, v + 1), scale);
    if (step) trainer_set(f, v + step);
}

static void pitcher_page(float scale) {
    if (!trainer_hooks_available()) {
        ImGui::TextWrapped("This build has no trainer hooks: it was made without the game's code patches.");
        return;
    }
    if (!g_view.has_pitcher) {
        ImGui::TextUnformatted("Waiting for a pitch.");
        return;
    }
    const float *v = g_view.pitcher.v;
    ImGui::Text("Energy %.0f%%", v[TR_ENERGY] * 100);
    ImGui::Text("Stamina %.0f%%", v[TR_STAMINA] * 100);
    ImGui::Text("Confidence %.0f", v[TR_CONFIDENCE]);
    ImGui::TextColored(col(TR_COL_DIM), "As of the last pitch.");
    ImGui::Separator();
    if (g_view.ratings_blocked) {
        ImGui::TextWrapped("Energy is not edited in Season, Franchise or Road to the Show.");
        return;
    }
    static const char *const levels[TR_ENERGY_LEVELS] = {"Normal", "Full", "Tired"};
    static const char *const sides[2][2] = {{"Away arm", "Home arm"}, {"My pitcher", "Their arm"}};
    for (int who = 0; who < 2; who++) {
        int level = trainer_energy_level(who);
        int d = stepper(sides[g_view.user_side < 0 ? 0 : 1][who], levels[level], level > 0,
                        level < TR_ENERGY_LEVELS - 1, scale);
        if (d) trainer_energy(who, level + d);
    }
    if (ImGui::Button("Refill once", ImVec2(0, TR_ROW_PX_1080 * scale))) trainer_energy_refill(TR_MINE);
}

static void hitting_page(void) {
    if (!trainer_hooks_available()) {
        ImGui::TextWrapped("This build has no trainer hooks: it was made without the game's code patches.");
        return;
    }
    if (!g_view.has_hit) {
        ImGui::TextUnformatted("No batted ball yet.");
        return;
    }
    const TrHit &h = g_view.hit;
    ImGui::Text("Last batted ball (%u this match)", g_view.hits);
    ImGui::Text("Speed %.0f mph", h.speed);
    ImGui::Text("Launch %.0f\xc2\xb0", h.launch);
    ImGui::Text("Direction %+.0f\xc2\xb0%s", h.direction, fabsf(h.direction) > 45 ? ", foul" : "");
    ImGui::TextColored(col(TR_COL_DIM), "Read only.");
}

// Every value of one player, in a list that scrolls: drag a slider, or focus it and press to adjust it.
static void ratings_list(int id, float scale) {
    float row = TR_ROW_PX_1080 * scale, gap = ImGui::GetStyle().ItemSpacing.y;
    float room = ImGui::GetIO().DisplaySize.y - ImGui::GetCursorScreenPos().y - (16 + TR_PADDING) * scale;
    float want = TR_LIST_ROWS * (row + gap), height = room < want ? (room > 2 * row ? room : 2 * row) : want;
    const struct { ImGuiCol i; ImVec4 c; } colours[] = {
        {ImGuiCol_ChildBg, ImVec4(0, 0, 0, 0)},
        {ImGuiCol_FrameBg, col(TR_COL_BUTTON)},
        {ImGuiCol_FrameBgHovered, col(TR_COL_BUTTON_HOT)},
        {ImGuiCol_FrameBgActive, col(TR_COL_BUTTON_DOWN)},
        {ImGuiCol_SliderGrab, col(TR_COL_ACCENT)},
        {ImGuiCol_SliderGrabActive, col(TR_COL_ACCENT)},
    };
    for (const auto &c : colours) ImGui::PushStyleColor(c.i, c.c);
    ImGui::BeginChild("##ratings", ImVec2(0, height), ImGuiChildFlags_NavFlattened);
    for (int r = 0; r < tr_rating_count; r++) {
        ImGui::PushID(r);
        ImGui::AlignTextToFramePadding();
        ImGui::TextUnformatted(tr_ratings[r].label);
        ImGui::SameLine(TR_SLIDER_LABEL_W * scale);
        int value = trainer_ratings_value(id, r);
        ImGui::SetNextItemWidth(TR_SLIDER_W * scale);
        // the figure stands beside the slider: over the grab it would not have the contrast
        if (ImGui::SliderInt("##value", &value, 0, TR_RATING_MAX, "", ImGuiSliderFlags_AlwaysClamp))
            trainer_ratings_set(id, r, value);
        ImGui::SameLine();
        ImGui::Text("%d", value);
        ImGui::PopID();
    }
    ImGui::EndChild();
    ImGui::PopStyleColor((int)(sizeof colours / sizeof *colours));
}

// A team's batting or pitching at the game's values, all best or all worst; then one player's values, a slider each.
static void ratings_page(float scale) {
    if (!trainer_hooks_available()) {
        ImGui::TextWrapped("This build has no trainer hooks: it was made without the game's code patches.");
        return;
    }
    if (g_view.ratings_blocked) {
        ImGui::TextWrapped("Ratings are not edited in Season, Franchise or Road to the Show.");
        return;
    }
    static const char *const levels[TR_LEVELS] = {"Normal", "Best", "Worst"};
    static const char *const rows[2][TR_GROUPS] = {{"Away batting", "Away pitching"},
                                                   {"Home batting", "Home pitching"}};
    for (int side = 0; side < 2; side++)
        for (int group = 0; group < TR_GROUPS; group++) {
            int level = trainer_ratings_level(side, group);
            int d = stepper(rows[side][group], levels[level], level > 0, level < TR_LEVELS - 1, scale);
            if (d) trainer_ratings_preset(side, group, level + d);
        }
    ImGui::Separator();
    static int id;
    char name[24] = "";
    if (!trainer_ratings_player(id, name, sizeof name)) {   // the first player there is
        for (id = 0; id < TR_PLAYERS && !trainer_ratings_player(id, name, sizeof name); id++) {}
        if (id == TR_PLAYERS) {
            id = 0;
            ImGui::TextUnformatted("Players appear after a pitch.");
            return;
        }
    }
    char shown[48];
    snprintf(shown, sizeof shown, "%s %s", id < TR_PLAYERS / 2 ? "A" : "H", name);
    int d = stepper("Player", shown, true, true, scale);
    if (d)
        for (int k = 1; k <= TR_PLAYERS; k++) {
            int next = (id + d * k + TR_PLAYERS * 2) % TR_PLAYERS;
            if (trainer_ratings_player(next, name, sizeof name)) {
                id = next;
                break;
            }
        }
    ratings_list(id, scale);
}

// The guaranteed cheats, each for no side, one side or both.
static void cheats_page(float scale) {
    if (!trainer_hooks_available()) {
        ImGui::TextWrapped("This build has no trainer hooks: it was made without the game's code patches.");
        return;
    }
    static const char *const names[TR_CHEATS] = {"Contact", "Home run", "Always miss", "Perfect aim", "Strikes",
                                                  "Wild throws"};
    static const char *const by_side[4] = {"Off", "Away", "Home", "Both"};
    static const char *const by_user[4] = {"Off", "Mine", "Theirs", "Both"};
    const char *const *sides = g_view.user_side < 0 ? by_side : by_user;
    for (int k = 0; k < TR_CHEATS; k++) {
        if (k == TR_CHEAT_CONTACT) ImGui::TextColored(col(TR_COL_DIM), "For the batter:");
        if (k == TR_CHEAT_AIM) ImGui::TextColored(col(TR_COL_DIM), "For the pitcher:");
        if (k == TR_CHEAT_WILD) ImGui::TextColored(col(TR_COL_DIM), "For the fielders:");
        int on = trainer_cheat_sides(k);
        int d = stepper(names[k], sides[on], on > 0, on < TR_SIDES_ALL, scale);
        if (d) trainer_cheat(k, on + d);
    }
    ImGui::TextColored(col(TR_COL_DIM), "Off again when the match ends.");
}

static void panel_body(float scale, bool appearing) {
    float row = TR_ROW_PX_1080 * scale;
    ImGui::TextColored(col(TR_COL_ACCENT), "TRAINER");
    ImGui::SameLine((TR_PANEL_W - 140) * scale);
    ImGui::TextColored(col(TR_COL_DIM), "%s hide", g_show_name);
    static const char *const pages[PAGES] = {"Match", "Pitcher", "Hitting", "Ratings", "Cheats"};
    if (ImGui::IsKeyPressed(ImGuiKey_GamepadR1, false) || ImGui::IsKeyPressed(ImGuiKey_E, false)) g_page = (g_page + 1) % PAGES;
    if (ImGui::IsKeyPressed(ImGuiKey_GamepadL1, false) || ImGui::IsKeyPressed(ImGuiKey_Q, false)) g_page = (g_page + PAGES - 1) % PAGES;
    float tab = (TR_PANEL_W - 2 * TR_PADDING - (PAGES - 1) * TR_SPACING) * scale / PAGES;
    for (int k = 0; k < PAGES; k++) {
        if (k) ImGui::SameLine();
        // the page shown is marked in words, not by colour alone
        char label[24];
        snprintf(label, sizeof label, k == g_page ? "[%s]##page%d" : "%s##page%d", pages[k], k);
        if (ImGui::Button(label, ImVec2(tab, row))) g_page = k;
    }
    ImGui::Separator();
    if (g_view.status != TR_OK) {
        ImGui::TextUnformatted(tr_status_text(g_view.status));
        return;
    }
    static bool confirm_was;
    bool confirm_new = g_view.needs_confirm && (appearing || !confirm_was);
    confirm_was = g_view.needs_confirm;
    if (g_view.needs_confirm) {
        ImGui::TextUnformatted("This match goes into your save.");
        ImGui::TextUnformatted("Change it?");
        if (ImGui::Button("Yes, change it", ImVec2(0, row))) trainer_confirm(1);
        ImGui::SameLine();
        if (confirm_new) ImGui::SetKeyboardFocusHere();   // the cursor starts on "No"
        if (ImGui::Button("No", ImVec2(row * 2, row))) trainer_confirm(0);
        return;
    }
    if (g_page == 1) return pitcher_page(scale);
    if (g_page == 2) return hitting_page();
    if (g_page == 3) return ratings_page(scale);
    if (g_page == 4) return cheats_page(scale);
    if (appearing) ImGui::SetKeyboardFocusHere(1);   // past the disabled-or-not "<": the first ">"
    count_row("Balls", TR_BALLS, scale);
    count_row("Strikes", TR_STRIKES, scale);
    count_row("Outs", TR_OUTS, scale);
    count_row("Away", TR_AWAY_SCORE, scale);
    count_row("Home", TR_HOME_SCORE, scale);
    if (trainer_hooks_available()) {
        char speed[8];
        snprintf(speed, sizeof speed, "%d%%", g_view.speed);
        int d = stepper("Speed", speed, g_view.speed > 25, g_view.speed < 100, scale);
        if (d) trainer_speed(g_view.speed + d * 25);
    }
    ImGui::Separator();

    static int jump_to = -1;
    int now = g_view.now.v[TR_HALF];
    if (appearing || jump_to <= now) jump_to = now + 1;
    char text[64];
    if (g_view.jumping) {
        half_text(text, sizeof text, g_view.jump_target);
        ImGui::AlignTextToFramePadding();
        ImGui::Text("Going to the %s", text);
        ImGui::SameLine();
        if (ImGui::Button("Cancel", ImVec2(0, row))) trainer_cancel();
    } else {
        half_text(text, sizeof text, jump_to);
        jump_to += stepper("Jump to", text, jump_to > now + 1, tr_write_range_ok(TR_HALF, jump_to + 1), scale);
        ImGui::SameLine();
        if (ImGui::Button("Go", ImVec2(TR_GO_W * scale, row))) trainer_jump(jump_to);
    }
    ImGui::Separator();

    int slot = g_view.slot;
    snprintf(text, sizeof text, "%d", slot + 1);
    int step = stepper("Slot", text, slot > 0, slot < TR_SLOTS - 1, scale);
    if (step) trainer_slot_select(slot + step);
    if (g_view.used[slot]) {
        const int *v = g_view.slots[slot].v;
        char half[16];
        half_text(half, sizeof half, v[TR_HALF]);
        ImGui::TextColored(col(TR_COL_DIM), "%d-%d, %d out, %d-%d, %s", v[TR_BALLS], v[TR_STRIKES], v[TR_OUTS],
                           v[TR_AWAY_SCORE], v[TR_HOME_SCORE], half);
    } else {
        ImGui::TextColored(col(TR_COL_DIM), "empty");
    }
    if (ImGui::Button("Save", ImVec2(row * 3, row))) trainer_slot_save(slot);
    ImGui::SameLine();
    ImGui::BeginDisabled(!g_view.used[slot]);
    if (ImGui::Button("Replay", ImVec2(row * 3, row))) trainer_slot_load(slot);
    ImGui::EndDisabled();
    if (g_view.message[0]) ImGui::TextWrapped("%s", g_view.message);
}

extern "C" void trainer_ui_draw(float scale, uint32_t w, uint32_t h) {
    static bool was_visible;
    bool visible = g_view.enabled && g_view.visible;
    bool appearing = visible && !was_visible;
    was_visible = visible;
    float pad = 16 * scale;
    ImVec2 pos((g_corner & 1) ? w - pad : pad, (g_corner & 2) ? h - pad : pad);
    ImVec2 pivot((g_corner & 1) ? 1.0f : 0.0f, (g_corner & 2) ? 1.0f : 0.0f);
    if (!visible) {
        const char *mark = mark_text();
        if (!mark) return;
        ImDrawList *dl = ImGui::GetForegroundDrawList();
        ImVec2 sz = ImGui::CalcTextSize(mark);
        float m = 6 * scale;
        ImVec2 p(pos.x - pivot.x * (sz.x + 2 * m), pos.y - pivot.y * (sz.y + 2 * m));
        dl->AddRectFilled(p, ImVec2(p.x + sz.x + 2 * m, p.y + sz.y + 2 * m),
                          ImGui::ColorConvertFloat4ToU32(col(TR_COL_BG, g_opacity / 100.0f)), 4 * scale);
        dl->AddText(ImVec2(p.x + m, p.y + m), ImGui::ColorConvertFloat4ToU32(col(TR_COL_ACCENT)), mark);
        return;
    }
    const struct { ImGuiCol i; ImVec4 c; } colours[] = {
        {ImGuiCol_WindowBg, col(TR_COL_BG, g_opacity / 100.0f)},
        {ImGuiCol_Text, col(TR_COL_TEXT)},
        {ImGuiCol_Button, col(TR_COL_BUTTON)},
        {ImGuiCol_ButtonHovered, col(TR_COL_BUTTON_HOT)},
        {ImGuiCol_ButtonActive, col(TR_COL_BUTTON_DOWN)},
        {ImGuiCol_NavCursor, col(TR_COL_ACCENT)},
    };
    for (const auto &c : colours) ImGui::PushStyleColor(c.i, c.c);
    float font = ImGui::GetFontSize();
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding, ImVec2(8 * scale, (TR_ROW_PX_1080 * scale - font) * 0.5f));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(TR_PADDING * scale, TR_PADDING * scale));
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(TR_SPACING * scale, 6 * scale));
    ImGui::SetNextWindowPos(pos, ImGuiCond_Always, pivot);
    ImGui::SetNextWindowSizeConstraints(ImVec2(TR_PANEL_W * scale, 0), ImVec2(TR_PANEL_W * scale, h - 2 * pad));
    if (appearing) ImGui::SetNextWindowFocus();
    ImGui::Begin("##trainer", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                           ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_AlwaysAutoResize);
    panel_body(scale, appearing);
    ImGui::End();
    ImGui::PopStyleVar(3);
    ImGui::PopStyleColor((int)(sizeof colours / sizeof *colours));
    if (ImGui::IsKeyPressed(ImGuiKey_Escape, false) || ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false))
        trainer_toggle();
}
