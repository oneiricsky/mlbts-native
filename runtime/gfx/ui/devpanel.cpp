// The in-game dev harness panel, see devpanel.h. Four parts: match setup, scenario drop-in, recorder controls and live
// readouts. Keyboard and mouse only (Tab and the arrows move between widgets, Enter or Space press, a click or Ctrl+click
// types into a field). The harness calls all go through devpanel_adapter.h.
#ifdef MLB_DEV_HARNESS
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "imgui.h"
#include "ui/devpanel.h"
#include "ui/devpanel_adapter.h"

extern "C" {
#include "cfg.h"
#include "perfmon.h"
#include "platform/platform.h"
}

static const char *const kTeamAbbr[30] = {
    "BAL", "BOS", "NYY", "TB",  "TOR", "CWS", "CLE", "DET", "KC",  "MIN", "HOU", "LAA", "ATH", "SEA", "TEX",
    "ATL", "MIA", "NYM", "PHI", "WSH", "CHC", "CIN", "MIL", "PIT", "STL", "AZ",  "COL", "LAD", "SD",  "SF"};
static char g_team_label[30][24];   // "2  NYY"; 12 (ATH) is not confirmed

// STUB: the scenario source is being researched (the game's own Situation / Moment code). Until it lands this fixed list
// stands in; dh_apply_scenario (devpanel_adapter.h) is what a real list will call.
static const DhSit kScenarios[] = {
    {"Top 1, 0 out, empty bases, 0-0 count, tied 0-0", 1, 0, 0, 0, 0, 0, 0, 0},
    {"Bottom 9, 2 out, full count, tied 3-3, bases loaded", 9, 1, 2, 3, 2, 3, 3, 7},
    {"Top 7, 1 out, runner on second, 1-2 count, away 2-1", 7, 0, 1, 1, 2, 2, 1, 2},
    {"Bottom 3, 0 out, runners on first and third, 2-0 count, home 4-0", 3, 1, 0, 2, 0, 0, 4, 5},
    {"Top 12, 2 out, runner on third, 0-2 count, tied 5-5", 12, 0, 2, 0, 2, 5, 5, 4},
};
enum { N_SCENARIOS = sizeof kScenarios / sizeof *kScenarios };

static struct {
    int home = 2, away = 1, scenario = 0;
    uint32_t seed = 1;
    char clock[40] = "";
    char marker[48] = "marker", tex[64] = "texture:fmt=0x25,size=512x512", shot[48] = "ref";
    char status[200] = "";
    uint64_t status_until = 0;
    bool ready = false;
} S;

static void status(const char *what, int ok) {
    snprintf(S.status, sizeof S.status, "%s: %s", what,
             ok == DH_OFF ? "harness is off: start the game with MLB_HARNESS=<file> or MLB_HARNESS_HOME / _AWAY"
             : ok == DH_STUB ? "logged only, not in harness.h yet (stub)" : ok ? "done" : "failed");
    S.status_until = plat_now_ns() + 6000000000ull;
}

// MLB_DEVPANEL_RECTS=1: the centre of every widget (client pixels) is logged once, so tools/devpanel_input_test.py can click
// the real widgets without guessing coordinates. Off, it costs one test of a static per widget.
static void R(const char *name) {
    static int on = -1;
    static char seen[64][40];
    static int n_seen;
    if (on < 0) {   // cfg_get, not cfg_bool: a key without a settings row is fatal there
        const char *e = cfg_get("MLB_DEVPANEL_RECTS");
        on = e && *e && *e != '0';
    }
    if (!on) return;
    for (int i = 0; i < n_seen; i++)
        if (!strcmp(seen[i], name)) return;
    if (n_seen < 64) snprintf(seen[n_seen++], sizeof seen[0], "%s", name);
    ImVec2 a = ImGui::GetItemRectMin(), b = ImGui::GetItemRectMax();
    rt_log("devpanel: rect '%s' %d %d", name, (int)((a.x + b.x) / 2), (int)((a.y + b.y) / 2));
}

static void act_apply(void) {
    DhSetup s = {S.home, S.away, S.seed, {0}};
    snprintf(s.fixed_clock, sizeof s.fixed_clock, "%s", S.clock);
    status("Apply setup", dh_apply_setup(&s));
}
static void act_restart(void) { status("Restart match", dh_restart_match()); }
static void act_scenario(void) { status("Apply scenario", dh_apply_scenario(&kScenarios[S.scenario])); }
static void act_marker(uint64_t frame) { status("Marker", dh_marker(S.marker, frame)); }
static void act_dump(void) { status("Texture dump", dh_dump_texture(S.tex)); }
static void act_shot(void) { status("Reference screenshot", dh_screenshot_ref(S.shot)); }
static void act_framelog(void) {
    int on = !dh_framelog_active();
    status(on ? "Frame log start" : "Frame log stop", dh_framelog(on));
}

static void init_once(void) {
    if (S.ready) return;
    S.ready = true;
    for (int i = 0; i < 30; i++)
        snprintf(g_team_label[i], sizeof g_team_label[i], "%2d  %s%s", i, kTeamAbbr[i], i == 12 ? " (unconfirmed)" : "");
}

static const ImVec4 kGold(0.93f, 0.76f, 0.33f, 1), kGood(0.45f, 0.85f, 0.50f, 1), kBad(0.95f, 0.45f, 0.35f, 1);

static void team_combo(const char *label, int *v) {
    if (!ImGui::BeginCombo(label, g_team_label[*v])) return;
    for (int i = 0; i < 30; i++)
        if (ImGui::Selectable(g_team_label[i], i == *v)) *v = i;
    ImGui::EndCombo();
}

static void part_setup(void) {
    team_combo("Home team", &S.home);
    team_combo("Away team", &S.away);
    ImGui::InputScalar("Seed", ImGuiDataType_U32, &S.seed);
    R("Seed");
    ImGui::InputTextWithHint("Fixed clock", "empty = real clock", S.clock, sizeof S.clock);
    if (ImGui::Button("Apply")) act_apply();
    R("Apply");
    ImGui::SameLine();
    if (ImGui::Button("Restart match")) act_restart();
    R("Restart match");
    ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyle().Colors[ImGuiCol_TextDisabled]);
    ImGui::TextWrapped("%s", dh_setup_is_live() ? "Apply takes effect now, mid-game."
                                                 : "Teams apply at the next match setup, not mid-game. Seed and fixed clock: not wired to the game yet (stub).");
    ImGui::PopStyleColor();
}

static void part_scenario(void) {
    ImGui::PushStyleColor(ImGuiCol_Text, kBad);
    ImGui::TextWrapped("STUB list: the real scenarios come from the game's Situation / Moment code.");
    ImGui::PopStyleColor();
    if (ImGui::BeginListBox("##scn", ImVec2(-FLT_MIN, 5.5f * ImGui::GetTextLineHeightWithSpacing()))) {
        for (int i = 0; i < N_SCENARIOS; i++) {
            if (ImGui::Selectable(kScenarios[i].name, i == S.scenario)) S.scenario = i;
            if (i == 2) R("Scenario 3");
        }
        ImGui::EndListBox();
    }
    const DhSit &d = kScenarios[S.scenario];
    ImGui::PushTextWrapPos(0);
    ImGui::TextDisabled("%s %d, %d out, count %d-%d, score away %d home %d, runners %s%s%s%s", d.bottom ? "Bottom" : "Top",
                        d.inning, d.outs, d.balls, d.strikes, d.away_score, d.home_score, d.runners & 1 ? "1B " : "",
                        d.runners & 2 ? "2B " : "", d.runners & 4 ? "3B " : "", d.runners ? "" : "none");
    ImGui::PopTextWrapPos();
    if (ImGui::Button("Drop into scenario")) act_scenario();
    R("Drop into scenario");
}

static void part_recorder(uint64_t frame) {
    ImGui::InputText("##marker", S.marker, sizeof S.marker);
    ImGui::SameLine();
    if (ImGui::Button("Drop marker")) act_marker(frame);
    R("Drop marker");
    ImGui::InputText("##tex", S.tex, sizeof S.tex);
    ImGui::SameLine();
    if (ImGui::Button("Dump texture")) act_dump();
    R("Dump texture");
    ImGui::InputText("##shot", S.shot, sizeof S.shot);
    ImGui::SameLine();
    if (ImGui::Button("Reference screenshot")) act_shot();
    R("Reference screenshot");
    bool on = dh_framelog_active() != 0;
    if (ImGui::Button(on ? "Stop frame log" : "Start frame log")) act_framelog();
    R(on ? "Stop frame log" : "Start frame log");
    ImGui::SameLine();
    ImGui::TextColored(on ? kGood : ImGui::GetStyle().Colors[ImGuiCol_TextDisabled], "%s", on ? "recording" : "not recording");
}

static void part_readouts(float scale) {
    PerfStats p;
    perfmon_snapshot(&p);
    float top = p.frame_ms_max > 34 ? p.frame_ms_max : 34;
    ImGui::PlotLines("##ft", p.frame_ms, PERF_HISTORY, 0, nullptr, 0, top, ImVec2(-FLT_MIN, 64 * scale));
    ImGui::Text("%.0f fps   frame %.1f ms avg, %.1f ms max", p.fps, p.frame_ms_avg, p.frame_ms_max);
    ImGui::Separator();
    int n = dh_marker_count();
    ImGui::Text("Markers (%d), newest first", n);
    if (ImGui::BeginChild("##markers", ImVec2(-FLT_MIN, 4.2f * ImGui::GetTextLineHeightWithSpacing()), ImGuiChildFlags_Borders)) {
        for (int i = 0; i < n; i++) {
            const char *name;
            uint64_t f;
            if (dh_marker_get(i, &name, &f)) ImGui::Text("frame %llu  %s", (unsigned long long)f, name);
        }
    }
    ImGui::EndChild();
    char detail[160];
    int r = dh_last_result(detail, sizeof detail);
    if (r < 0) ImGui::TextDisabled("Last run: none yet");
    else ImGui::TextColored(r ? kGood : kBad, "Last run: %s %s", r ? "PASS" : "FAIL", detail);
}

// MLB_DEVPANEL_TEST=<frame>: the panel opens at that frame (menu.cpp) and, two frames later, every action runs once with
// the logged result; a line also says how many frame times the graph holds.
static long g_test_at = -2;
static bool g_test_done, g_test_graph_done;

bool devpanel_test_open(uint64_t frame) {
    if (g_test_at == -2) {
        const char *e = cfg_get("MLB_DEVPANEL_TEST");
        g_test_at = e && *e ? atol(e) : -1;
    }
    return g_test_at >= 0 && frame == (uint64_t)g_test_at;
}

static void run_test(uint64_t frame) {
    g_test_done = true;
    S.home = 27, S.away = 28, S.seed = 12345;
    snprintf(S.clock, sizeof S.clock, "2026-04-01T19:05:00");
    S.scenario = 1;
    act_apply(), act_restart(), act_scenario();
    act_marker(frame), act_dump(), act_shot(), act_framelog();
    PerfStats p;
    perfmon_snapshot(&p);
    int nz = 0;
    for (int i = 0; i < PERF_HISTORY; i++) nz += p.frame_ms[i] > 0;
    rt_log("devpanel: test: %d of %d frame times in the graph, %d markers, frame log %s, status '%s'", nz, PERF_HISTORY,
           dh_marker_count(), dh_framelog_active() ? "on" : "off", S.status);
}

const char *devpanel_backend(void) { return dh_backend(); }

bool devpanel_layout(uint32_t w, uint32_t h, float scale, uint64_t frame, bool esc_closes) {
    init_once();
    if (g_test_at >= 0 && !g_test_done && frame >= (uint64_t)g_test_at + 2) run_test(frame);
    if (g_test_done && !g_test_graph_done && frame >= (uint64_t)g_test_at + 200) {
        PerfStats p;
        perfmon_snapshot(&p);
        int nz = 0;
        for (int i = 0; i < PERF_HISTORY; i++) nz += p.frame_ms[i] > 0;
        rt_log("devpanel: test: graph at +200 frames: %d of %d frame times, %.1f fps, avg %.2f ms, max %.2f ms", nz,
               PERF_HISTORY, p.fps, p.frame_ms_avg, p.frame_ms_max);
        g_test_graph_done = true;
    }
    bool closed = false;
    ImGui::SetNextWindowPos(ImVec2(16 * scale, 16 * scale), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(fminf(1300 * scale, w * 0.8f), h - 32 * scale), ImGuiCond_FirstUseEver);
    bool open = true;
    if (ImGui::Begin("Dev harness  (F7 closes)###devpanel", &open, ImGuiWindowFlags_NoSavedSettings)) {
        char scn[64];
        ImGui::TextDisabled("Harness: %s", dh_backend());
        if (!dh_harness_on()) {
            ImGui::PushStyleColor(ImGuiCol_Text, kBad);
            ImGui::TextWrapped("Harness is OFF: teams and markers do nothing. Start with MLB_HARNESS=<scenario file> or "
                               "MLB_HARNESS_HOME / MLB_HARNESS_AWAY.");
            ImGui::PopStyleColor();
        }
        ImGui::TextDisabled("Scenario file: %s   match settings filled: %s", dh_scenario_name(scn, sizeof scn) ? scn : "none",
                            dh_teams_ready() ? "yes" : "not yet");
        if (ImGui::BeginTable("##cols", 2, ImGuiTableFlags_SizingStretchSame)) {   // two columns: the 720p window is short
            ImGui::TableNextColumn();
            ImGui::TextColored(kGold, "Match setup");
            part_setup();
            ImGui::Spacing();
            ImGui::TextColored(kGold, "Scenario drop-in");
            part_scenario();
            ImGui::TableNextColumn();
            ImGui::TextColored(kGold, "Recorder");
            part_recorder(frame);
            ImGui::Spacing();
            ImGui::TextColored(kGold, "Readouts");
            part_readouts(scale);
            ImGui::EndTable();
        }
        if (S.status[0] && plat_now_ns() < S.status_until) ImGui::TextUnformatted(S.status);
    }
    ImGui::End();
    if (!open || (esc_closes && ImGui::IsKeyPressed(ImGuiKey_Escape, false))) closed = true;
    return closed;
}
#endif
