// Native test of the in-game trainer without the game: runtime/mlb/trainer_game.c and trainer.c against a fake match
// in this program's own memory, with the runtime functions they call standing in. No game code and no GPU.
//
//   mkdir -p work/scratch
//   "C:/Program Files/LLVM/bin/clang.exe" -O1 -Wall -std=gnu11 -D_CRT_SECURE_NO_WARNINGS -I runtime/mlb \
//       -I runtime/core -I runtime/gfx -o work/scratch/trainer_test.exe tools/trainer_test.c \
//       runtime/mlb/trainer_game.c runtime/mlb/trainer.c runtime/mlb/trainer_ratings.c && work/scratch/trainer_test.exe
//
// (from the repository root, in bash). The exit code is the number of failed checks.
#include <direct.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "platform/platform.h"
#include "trainer.h"
#include "trainer_game.h"
#include "trainer_ratings.h"
#include "ui/trainer_theme.h"

static int g_failed, g_checks;
#define CHECK(x)                                                              \
    do {                                                                      \
        g_checks++;                                                           \
        if (!(x)) g_failed++, printf("FAIL %s:%d %s\n", __func__, __LINE__, #x); \
    } while (0)

// ---- the fake match: the count object, the two-team table and the settings block, reached as the game reaches them
static uint8_t f_count[0xe60], f_team_b[0x130], f_settings[0x100];
static uint64_t f_count_obj_ptr, f_count_slot, f_table[8], f_teams_slot, f_settings_slot;
static int g_readable_calls;
static uint8_t f_pitcher[0x100], f_hit[0x58];   // the pitcher state and the batted-ball result
static uint8_t f_rec[2][0xb0], f_attr[2][0x48];  // one player a side: record and ratings
static uint8_t f_role[2][0x20];                  // one pitcher object a side
static uint8_t f_input[0x148], f_block[0x70], f_bunt[0x50], f_place[0x110];   // swing input and pitch placement

int mem_guest_readable(uint64_t a, uint64_t n) {
    g_readable_calls++;
    static const struct { const void *p; size_t n; } ok[] = {
        {f_count, sizeof f_count},           {f_team_b, sizeof f_team_b},         {f_settings, sizeof f_settings},
        {&f_count_obj_ptr, 8},               {&f_count_slot, 8},                  {f_table, sizeof f_table},
        {&f_teams_slot, 8},                  {&f_settings_slot, 8},
        {f_pitcher, sizeof f_pitcher},       {f_hit, sizeof f_hit},
        {f_rec[0], sizeof f_rec[0]},         {f_rec[1], sizeof f_rec[1]},
        {f_attr[0], sizeof f_attr[0]},       {f_attr[1], sizeof f_attr[1]},
        {f_role[0], sizeof f_role[0]},       {f_role[1], sizeof f_role[1]},
        {f_input, sizeof f_input},           {f_block, sizeof f_block},           {f_bunt, sizeof f_bunt},
        {f_place, sizeof f_place},           
    };
    for (size_t i = 0; i < sizeof ok / sizeof *ok; i++) {
        uint64_t b = (uint64_t)(uintptr_t)ok[i].p;
        if (a >= b && n <= ok[i].n && a - b <= ok[i].n - n) return 1;
    }
    return 0;
}

static int g_log_lines;
void rt_log(const char *fmt, ...) {
    g_log_lines++;
    va_list ap;
    va_start(ap, fmt);
    printf("  [log] ");
    vprintf(fmt, ap);
    printf("\n");
    va_end(ap);
}

void plat_mutex_lock(PlatMutex *m) { (void)m; }   // one thread
void plat_mutex_unlock(PlatMutex *m) { (void)m; }

static uint32_t fake_u32(int off) {
    uint32_t v;
    memcpy(&v, f_count + off, 4);
    return v;
}
static void fake_set(int off, uint32_t v) { memcpy(f_count + off, &v, 4); }
static void fake_side(int side) { f_team_b[0x124] = (uint8_t)side; }
static void fake_mode(int mode) { f_settings[0x3e + 19] = (uint8_t)mode; }
static void fake_match_gone(void) { f_count_obj_ptr = 0; }
static void fake_match_back(void) { f_count_obj_ptr = (uint64_t)(uintptr_t)f_count; }

static void fake_reset(void) {
    memset(f_count, 0, sizeof f_count);
    memset(f_team_b, 0, sizeof f_team_b);
    memset(f_settings, 0, sizeof f_settings);
    fake_match_back();
    f_count_slot = (uint64_t)(uintptr_t)&f_count_obj_ptr;
    f_table[0x20 / 8] = (uint64_t)(uintptr_t)f_team_b;
    f_teams_slot = (uint64_t)(uintptr_t)f_table;
    f_settings_slot = (uint64_t)(uintptr_t)f_settings;
    fake_mode(5);   // Exhibition
    tr_game_init("1.0.20");
    tr_game_set_slots((uint64_t)(uintptr_t)&f_count_slot, (uint64_t)(uintptr_t)&f_teams_slot,
                      (uint64_t)(uintptr_t)&f_settings_slot);
}

// ---- game access
static void test_version(void) {
    TrCount c;
    fake_reset();
    CHECK(tr_game_init("1.0.15") == TR_WRONG_VERSION);
    CHECK(tr_count_read(&c) == TR_WRONG_VERSION);
    CHECK(tr_count_write(TR_BALLS, 1) == TR_WRONG_VERSION);
    CHECK(tr_game_init("1.0.20") == TR_OK);
}

static void test_read(void) {
    TrCount c;
    fake_reset();
    fake_set(0x8, 4), fake_set(0xc, 3), fake_set(0x10, 3), fake_set(0x14, 2), fake_set(0x18, 1), fake_set(0x20, 13);
    CHECK(tr_count_read(&c) == TR_OK);
    CHECK(c.v[TR_AWAY_SCORE] == 4 && c.v[TR_HOME_SCORE] == 3);
    CHECK(c.v[TR_BALLS] == 3 && c.v[TR_STRIKES] == 2 && c.v[TR_OUTS] == 1 && c.v[TR_HALF] == 13);
}

static void test_write(void) {
    fake_reset();
    CHECK(tr_count_write(TR_OUTS, 2) == TR_OK);
    CHECK(fake_u32(0x18) == 2);
    CHECK(tr_count_write(TR_OUTS, 3) == TR_OUT_OF_RANGE);
    CHECK(fake_u32(0x18) == 2);
    CHECK(tr_count_write(TR_BALLS, -1) == TR_OUT_OF_RANGE);
    CHECK(tr_count_write(TR_STRIKES, 3) == TR_OUT_OF_RANGE);
    CHECK(tr_count_write(TR_BALLS, 3) == TR_OK && fake_u32(0x10) == 3);
}

static void test_no_match(void) {
    TrCount c;
    fake_reset();
    fake_match_gone();
    CHECK(tr_count_read(&c) == TR_NO_MATCH);
    CHECK(tr_count_write(TR_BALLS, 1) == TR_NO_MATCH);
    f_count_obj_ptr = 0x1000;   // unreadable
    CHECK(tr_count_read(&c) == TR_NO_MATCH);
}

static void test_garbage(void) {
    TrCount c;
    fake_reset();
    fake_set(0x10, 700);
    CHECK(tr_count_read(&c) == TR_UNEXPECTED);
    CHECK(tr_count_write(TR_BALLS, 1) == TR_UNEXPECTED);
    CHECK(fake_u32(0x10) == 700);
}

static void test_transition_values(void) {
    TrCount c;
    fake_reset();
    fake_set(0x10, 4), fake_set(0x14, 3), fake_set(0x18, 3);   // the game holds these for a moment
    CHECK(tr_count_read(&c) == TR_OK);
}

static void test_side_mode(void) {
    fake_reset();
    fake_side(1);
    CHECK(tr_batting_side() == 1);
    CHECK(tr_game_mode() == 5);
    f_teams_slot = 0;
    CHECK(tr_batting_side() == -1);
    f_settings_slot = 0;
    CHECK(tr_game_mode() == -1);
}

// ---- rules
static const char *g_profile = "work/scratch/trainer_test_profile";
static TrView v;

static void tick(double s) { trainer_tick((uint64_t)(s * 1e9)); }

static void write_profile(const char *text) {
    char path[300];
    snprintf(path, sizeof path, "%s/trainer.txt", g_profile);
    FILE *f = fopen(path, "wb");
    if (!f) {
        CHECK(!"the profile folder is writable");
        return;
    }
    fputs(text, f);
    fclose(f);
}

static void rules_reset(void) {
    fake_reset();
    _mkdir(g_profile);
    write_profile("");
    trainer_set_enabled(0);
    trainer_init(g_profile);
    trainer_set_enabled(1);
    g_readable_calls = 0;
}

static void test_set_applies_on_tick(void) {
    rules_reset();
    trainer_set(TR_BALLS, 3);
    CHECK(fake_u32(0x10) == 0);
    tick(1);
    CHECK(fake_u32(0x10) == 3);
}

static void test_disabled_touches_nothing(void) {
    rules_reset();
    trainer_set_enabled(0);
    trainer_set(TR_BALLS, 3);
    tick(1);
    CHECK(fake_u32(0x10) == 0);
    CHECK(g_readable_calls == 0);
    trainer_toggle();
    CHECK(!trainer_visible());
    trainer_set_enabled(1);
    tick(2);
    CHECK(fake_u32(0x10) == 0);   // the request made while off is gone
}

static void test_confirm_in_franchise(void) {
    rules_reset();
    fake_mode(3);
    trainer_set(TR_OUTS, 2);
    tick(1);
    trainer_view(&v);
    CHECK(v.needs_confirm && fake_u32(0x18) == 0);
    trainer_confirm(1);
    tick(2);
    CHECK(fake_u32(0x18) == 2);
    trainer_set(TR_BALLS, 1);
    tick(3);
    CHECK(fake_u32(0x10) == 1);
}

static void test_confirm_no_drops(void) {
    rules_reset();
    fake_mode(1);
    trainer_set(TR_OUTS, 2);
    tick(1);
    trainer_confirm(0);
    tick(2);
    trainer_view(&v);
    CHECK(fake_u32(0x18) == 0 && !v.needs_confirm);
}

static void test_confirm_holds_a_load(void) {
    rules_reset();
    fake_set(0x10, 2);
    trainer_slot_save(0);
    tick(1);
    fake_set(0x10, 0);
    fake_mode(4);
    trainer_slot_load(0);
    tick(2);
    trainer_view(&v);
    CHECK(v.needs_confirm && fake_u32(0x10) == 0);
    trainer_confirm(1);
    tick(3);
    CHECK(fake_u32(0x10) == 2);
}

static void test_jump_same_side(void) {
    rules_reset();
    trainer_jump(4);
    tick(1);
    CHECK(fake_u32(0x20) == 3 && fake_u32(0x18) == 2);
    fake_set(0x20, 4);
    tick(2);
    tick(5);
    trainer_view(&v);
    CHECK(!v.jumping);
}

static void test_jump_extra_transition(void) {
    rules_reset();
    trainer_jump(3);
    tick(1);
    CHECK(fake_u32(0x20) == 0 && fake_u32(0x18) == 2);
    fake_set(0x20, 1);
    fake_side(1);
    tick(2);
    tick(5);
    CHECK(fake_u32(0x20) == 2);
    fake_set(0x20, 3);
    tick(6);
    tick(9);
    trainer_view(&v);
    CHECK(!v.jumping);
}

static void test_jump_back_refused(void) {
    rules_reset();
    fake_set(0x20, 6);
    trainer_jump(2);
    tick(1);
    trainer_view(&v);
    CHECK(!v.jumping && fake_u32(0x20) == 6);
    CHECK(strstr(v.message, "cannot go back"));
}

static void test_jump_cancel(void) {
    rules_reset();
    trainer_jump(4);
    tick(1);
    trainer_cancel();
    fake_set(0x20, 4);
    tick(2);
    trainer_view(&v);
    CHECK(!v.jumping);
}

static void test_slot_roundtrip(void) {
    rules_reset();
    fake_set(0x8, 4), fake_set(0xc, 3), fake_set(0x10, 3), fake_set(0x14, 2), fake_set(0x18, 2), fake_set(0x20, 4);
    trainer_slot_save(0);
    tick(1);
    fake_set(0x8, 0), fake_set(0xc, 0), fake_set(0x10, 0), fake_set(0x14, 0), fake_set(0x18, 0);
    trainer_init(g_profile);
    trainer_slot_load(0);
    tick(2);
    CHECK(fake_u32(0x10) == 3 && fake_u32(0x14) == 2 && fake_u32(0x18) == 2);
    CHECK(fake_u32(0x8) == 4 && fake_u32(0xc) == 3);
}

static void test_load_later_inning(void) {
    rules_reset();
    write_profile("slot 1 5 6 1 2 1 4\n");
    trainer_init(g_profile);
    trainer_slot_load(0);
    tick(1);
    CHECK(fake_u32(0x8) == 5 && fake_u32(0x20) == 3 && fake_u32(0x10) == 0);
    fake_set(0x20, 4);
    fake_set(0x18, 0);
    tick(2);
    tick(5);
    CHECK(fake_u32(0x10) == 1 && fake_u32(0x14) == 2 && fake_u32(0x18) == 1);
}

static void test_load_earlier_inning(void) {
    rules_reset();
    write_profile("slot 1 4 3 3 2 1 2\n");
    trainer_init(g_profile);
    fake_set(0x20, 8);
    trainer_slot_load(0);
    tick(1);
    CHECK(fake_u32(0x20) == 8 && fake_u32(0x10) == 3);
    trainer_view(&v);
    CHECK(strstr(v.message, "Inning not restored"));
}

static void test_save_refused_in_transition(void) {
    rules_reset();
    fake_set(0x18, 3);
    trainer_slot_save(0);
    tick(1);
    trainer_view(&v);
    CHECK(!v.used[0]);
}

static void test_bad_slot_lines(void) {
    rules_reset();
    write_profile("slot 1 4 3 3 2 9 4\nslot 9 0 0 0 0 0 0\njunk\nslot 2 1 0 0 0 1 2\nslot 3 5\n");
    trainer_init(g_profile);
    trainer_view(&v);
    CHECK(!v.used[0] && v.used[1] && !v.used[2]);
}

static void test_match_end_drops_pending(void) {
    rules_reset();
    fake_mode(3);
    trainer_set(TR_BALLS, 2);
    trainer_jump(4);
    tick(1);
    fake_match_gone();
    tick(2);
    tick(13);
    fake_match_back();
    fake_set(0x20, 4);
    tick(14);
    tick(20);
    trainer_view(&v);
    CHECK(!v.jumping && !v.needs_confirm && fake_u32(0x10) == 0);
}

static void test_short_gap_keeps_jump(void) {
    rules_reset();
    trainer_jump(4);
    tick(1);
    fake_match_gone();   // the game rebuilds the count object at some transitions
    tick(2);
    fake_match_back();
    fake_set(0x20, 4);
    tick(3);
    trainer_view(&v);
    CHECK(v.jumping);
    tick(6);
    trainer_view(&v);
    CHECK(!v.jumping);
}

static int near_f(float a, float b);

static void test_duplicate_keys(void) {
    int vk[4];
    CHECK(trainer_keys("F4", "F5", "F6", "F7", vk) && vk[0] == 0x73 && vk[3] == 0x76);
    CHECK(!trainer_keys("F3", "F3", "F4", "F6", vk));
    CHECK(vk[0] == 0x71 && vk[1] == 0x72 && vk[2] == 0x73 && vk[3] == 0x75);
    CHECK(!trainer_keys("F2", "F3", "F4", "F2", vk) && vk[3] == 0x75);
    CHECK(!trainer_keys("F2", "F9", "F4", "F6", vk) && vk[1] == 0x72);
}

// ---- slow motion: the factor the frame-step hook multiplies by
static void test_speed(void) {
    rules_reset();
    tick(1);
    CHECK(near_f(trainer_speed_scale(), 1.0f));
    trainer_speed(50);
    CHECK(near_f(trainer_speed_scale(), 0.5f));
    trainer_speed(33);   // not one of the steps
    trainer_speed(0);
    CHECK(near_f(trainer_speed_scale(), 0.5f));
    trainer_slow_toggle();
    CHECK(near_f(trainer_speed_scale(), 1.0f));
    trainer_slow_toggle();
    CHECK(near_f(trainer_speed_scale(), 0.5f));   // the last slow speed chosen
}

static void test_speed_toggle_starts_at_half(void) {
    rules_reset();
    tick(1);
    trainer_slow_toggle();
    CHECK(near_f(trainer_speed_scale(), 0.5f));
}

static void test_speed_only_in_a_match(void) {
    rules_reset();
    fake_match_gone();
    tick(1);
    trainer_speed(25);
    CHECK(near_f(trainer_speed_scale(), 1.0f));   // menus run at full speed
    fake_match_back();
    tick(2);
    CHECK(near_f(trainer_speed_scale(), 0.25f));
    fake_match_gone();
    tick(3);
    CHECK(near_f(trainer_speed_scale(), 1.0f));
    tick(14);
    fake_match_back();
    tick(15);
    CHECK(near_f(trainer_speed_scale(), 1.0f));   // a new match starts at full speed
}

static void test_speed_off_when_disabled(void) {
    rules_reset();
    tick(1);
    trainer_speed(25);
    trainer_set_enabled(0);
    CHECK(near_f(trainer_speed_scale(), 1.0f));
    trainer_set_enabled(1);
    tick(2);
    CHECK(near_f(trainer_speed_scale(), 1.0f));
}

static void test_speed_command(void) {
    rules_reset();
    tick(1);
    CHECK(trainer_command("speed 75") && near_f(trainer_speed_scale(), 0.75f));
    CHECK(!trainer_command("speed 10"));
}

// A system key (Alt held: Alt+F4 closes the window) and auto-repeat are never the trainer's.
static void test_system_keys_left_alone(void) {
    CHECK(trainer_takes_key(0, 0));
    CHECK(!trainer_takes_key(1, 0));
    CHECK(!trainer_takes_key(0, 1));
}

// Quick Manage keeps its simulated innings to itself: the match data stays where it was until play resumes
// (seen 2026-11-24: the screen said "Bottom 1", the data still top 1).
static void game_screen(const char *line) { trainer_game_log(line, (int)strlen(line)); }
#define QM "uiEngine: Entering screen: [PM_Main_Alternate->SportscastManager (1)]"
#define PLAY "uiEngine: Entering screen: [Scorebar->Scorebar (0)]"

static void test_quick_manage_blocks(void) {
    rules_reset();
    tick(1);
    game_screen(QM);
    tick(2);
    trainer_view(&v);
    CHECK(v.status == TR_MANAGING);
    trainer_set(TR_BALLS, 3);
    trainer_slot_save(0);
    trainer_jump(4);
    tick(3);
    trainer_view(&v);
    CHECK(fake_u32(0x10) == 0 && fake_u32(0x20) == 0 && !v.used[0] && !v.jumping);
    game_screen("uiEngine: Entering screen: [PitchHistory->PitchHistory (0)]");
    tick(4);
    trainer_view(&v);
    CHECK(v.status == TR_MANAGING);
    game_screen(PLAY);
    tick(5);
    trainer_view(&v);
    CHECK(v.status == TR_OK);
    CHECK(fake_u32(0x10) == 0);   // what was asked during Quick Manage is gone
}

static void test_quick_manage_is_not_a_match_end(void) {
    rules_reset();
    fake_mode(3);
    trainer_set(TR_BALLS, 1);
    tick(1);
    trainer_confirm(1);
    tick(2);
    game_screen(QM);
    tick(3);
    tick(30);
    game_screen(PLAY);
    trainer_set(TR_BALLS, 2);
    tick(31);
    trainer_view(&v);
    CHECK(!v.needs_confirm && fake_u32(0x10) == 2);
}

static void test_quick_manage_logs_once(void) {
    rules_reset();
    tick(1);
    game_screen(QM);
    tick(2);
    g_log_lines = 0;
    for (int i = 3; i < 20; i++) tick(i);
    CHECK(g_log_lines == 0);   // a status is logged when it changes, not on every frame
    game_screen(PLAY);
    tick(20);
    CHECK(g_log_lines >= 1 && g_log_lines <= 2);
}

static void test_quick_manage_ends_with_the_match(void) {
    rules_reset();
    tick(1);
    game_screen(QM);
    fake_match_gone();   // "End of Game" from Quick Manage: no scorebar again
    tick(2);
    tick(13);
    fake_match_back();
    tick(14);
    trainer_view(&v);
    CHECK(v.status == TR_OK);
}

static void test_other_log_lines_ignored(void) {
    rules_reset();
    game_screen("SportscastManager");
    game_screen("uiEngine: Entering screen: [SportscastManager");
    game_screen("");
    tick(1);
    trainer_view(&v);
    CHECK(v.status == TR_OK);
}

static void test_menu_closes_panel(void) {
    rules_reset();
    trainer_toggle();
    CHECK(trainer_visible());
    trainer_menu_opened();
    CHECK(!trainer_visible());
}

static void test_command(void) {
    rules_reset();
    CHECK(trainer_command("set strikes 2"));
    tick(1);
    CHECK(fake_u32(0x14) == 2);
    CHECK(!trainer_command("set nonsense 1"));
    CHECK(!trainer_command("save 9"));
    CHECK(trainer_command("show") && trainer_visible());
    CHECK(trainer_command("hide") && !trainer_visible());
}

// ---- the panel's colours and sizes (WCAG 2.2: contrast of text, target size)
static double lum(uint32_t rgb) {
    double c[3];
    for (int i = 0; i < 3; i++) {
        double v = ((rgb >> (16 - 8 * i)) & 255) / 255.0;
        c[i] = v <= 0.04045 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

static double contrast(uint32_t a, uint32_t b) {
    double x = lum(a), y = lum(b);
    return x > y ? (x + 0.05) / (y + 0.05) : (y + 0.05) / (x + 0.05);
}

static uint32_t blend(uint32_t over, uint32_t under, int percent) {   // mixed in sRGB values
    uint32_t out = 0;
    for (int s = 0; s <= 16; s += 8) {
        int v = (((over >> s) & 255) * percent + ((under >> s) & 255) * (100 - percent) + 50) / 100;
        out |= (uint32_t)v << s;
    }
    return out;
}

static void test_contrast(void) {
    uint32_t panel = blend(TR_COL_BG, 0xFFFFFF, TR_ALPHA_MIN);   // the worst case: a white picture behind
    printf("contrast over %06X: text %.2f, accent %.2f, dim %.2f\n", panel, contrast(TR_COL_TEXT, panel),
           contrast(TR_COL_ACCENT, panel), contrast(TR_COL_DIM, panel));
    CHECK(contrast(TR_COL_TEXT, panel) >= 7.0);
    CHECK(contrast(TR_COL_ACCENT, panel) >= 7.0);
    CHECK(contrast(TR_COL_DIM, panel) >= 7.0);
    // buttons: the panel's text on the button, hovered and pressed fills (opaque)
    CHECK(contrast(TR_COL_TEXT, TR_COL_BUTTON) >= 7.0);
    CHECK(contrast(TR_COL_TEXT, TR_COL_BUTTON_HOT) >= 7.0);
    CHECK(contrast(TR_COL_TEXT, TR_COL_BUTTON_DOWN) >= 7.0);
    CHECK(contrast(TR_COL_ACCENT, TR_COL_BUTTON) >= 3.0);        // a slider's grab on its track
    CHECK(contrast(TR_COL_ACCENT, TR_COL_BUTTON_DOWN) >= 3.0);   // and while it is held
    CHECK(TR_SLIDER_LABEL_W + TR_SLIDER_W + TR_SPACING + TR_VALUE_NUM_W <= TR_PANEL_W - 2 * TR_PADDING);
    // the focus ring against the panel (non-text contrast, 3:1)
    CHECK(contrast(TR_COL_ACCENT, panel) >= 3.0);
    CHECK(TR_ROW_PX_1080 * 720 / 1080 >= 24);
}

// The widest row, "Jump to [<] bottom 12 [>] [Go]", fits: label column, button, value, button, Go, padding.
static void test_row_width(void) {
    int right = TR_LABEL_W + TR_ROW_PX_1080 + TR_SPACING + TR_VALUE_W + TR_ROW_PX_1080 + TR_SPACING + TR_GO_W;
    CHECK(right + TR_PADDING <= TR_PANEL_W);
}

// ---- pitcher and batted ball (ranges from the 2026-11-24 probe run)
#define PITCHER ((uint64_t)(uintptr_t)f_pitcher)
#define HIT ((uint64_t)(uintptr_t)f_hit)
static float getf(const uint8_t *b, int off) {
    float f;
    memcpy(&f, b + off, 4);
    return f;
}
static void setf(uint8_t *b, int off, float f) { memcpy(b + off, &f, 4); }
static int near_f(float a, float b) { return fabsf(a - b) < 0.01f; }

static void pitcher_fake(float stamina, float energy, float confidence) {
    memset(f_pitcher, 0, sizeof f_pitcher);
    setf(f_pitcher, 0x20, stamina), setf(f_pitcher, 0xf4, energy), setf(f_pitcher, 0xf8, confidence);
}

// +0x40 launch angle, +0x44 direction: the order of the game's "AUTO HIT Azimuth, Incline" log (+0x44, +0x40), and a
// live run where a speed of 112 written with the two swapped went into foul ground.
static void hit_fake(float launch_rad, float direction_rad, float speed) {
    memset(f_hit, 0, sizeof f_hit);
    setf(f_hit, 0x40, launch_rad), setf(f_hit, 0x44, direction_rad), setf(f_hit, 0x48, speed);
}

static void test_pitcher_access(void) {
    TrPitcher p;
    fake_reset();
    pitcher_fake(0.7f, 0.9f, 66);
    CHECK(tr_pitcher_read(PITCHER, &p) == TR_OK);
    CHECK(near_f(p.v[TR_STAMINA], 0.7f) && near_f(p.v[TR_ENERGY], 0.9f) && near_f(p.v[TR_CONFIDENCE], 66));
    CHECK(tr_pitcher_read(0, &p) == TR_NO_MATCH);
    setf(f_pitcher, 0xf4, 4000.0f);   // not a pitcher any more
    CHECK(tr_pitcher_read(PITCHER, &p) == TR_UNEXPECTED);
    setf(f_pitcher, 0xf4, NAN);
    CHECK(tr_pitcher_read(PITCHER, &p) == TR_UNEXPECTED);
}

static void test_hit_access(void) {
    TrHit h;
    fake_reset();
    hit_fake(2.3562f, -0.5236f, 61.5f);   // popped up and back
    CHECK(tr_hit_read(HIT, &h) == TR_OK);
    CHECK(near_f(h.launch, 135) && near_f(h.direction, -30) && near_f(h.speed, 61.5f));
    setf(f_hit, 0x48, 9999);
    CHECK(tr_hit_read(HIT, &h) == TR_UNEXPECTED);
}

static void pitched(double s) {
    trainer_on_pitch(PITCHER);
    tick(s);
}

// Readouts only: a held or written value turned out to be a copy the game overwrites (docs/trainer.md).
static void test_pitcher_readout(void) {
    rules_reset();
    pitcher_fake(0.7f, 0.5f, 66);
    trainer_view(&v);
    CHECK(!v.has_pitcher);
    pitched(1);
    trainer_view(&v);
    CHECK(v.has_pitcher && near_f(v.pitcher.v[TR_ENERGY], 0.5f));
    CHECK(near_f(getf(f_pitcher, 0xf4), 0.5f));
}

static void test_hit_readout(void) {
    rules_reset();
    hit_fake(0.1f, 0.2f, 60);
    trainer_on_hit(HIT);
    trainer_view(&v);
    CHECK(v.has_hit && v.hits == 1 && near_f(v.hit.speed, 60));
    CHECK(near_f(getf(f_hit, 0x48), 60));
    hit_fake(0, 0, 0);   // a miss is not a batted ball
    trainer_on_hit(HIT);
    trainer_view(&v);
    CHECK(v.hits == 1 && near_f(v.hit.speed, 60));
}

static void test_match_end_clears_readouts(void) {
    rules_reset();
    pitcher_fake(0.7f, 0.8f, 66);
    pitched(1);
    hit_fake(0.1f, 0.2f, 60);
    trainer_on_hit(HIT);
    fake_match_gone();
    tick(2);
    tick(13);
    fake_match_back();
    tick(14);
    trainer_view(&v);
    CHECK(!v.has_pitcher && !v.has_hit && v.hits == 0);
}

static void test_hooks_off_when_disabled(void) {
    rules_reset();
    trainer_set_enabled(0);
    hit_fake(0.1f, 0.2f, 60);
    g_readable_calls = 0;
    trainer_on_hit(HIT);
    trainer_on_pitch(PITCHER);
    CHECK(g_readable_calls == 0);
}

// ---- ratings
#define REC(i) ((uint64_t)(uintptr_t)f_rec[i])
static void player_fake(int i, const char *name) {
    memset(f_rec[i], 0, sizeof f_rec[i]);
    memset(f_attr[i], 0, sizeof f_attr[i]);
    snprintf((char *)f_rec[i] + 0x60, 20, "%s", name);
    uint64_t at = (uint64_t)(uintptr_t)f_attr[i];
    memcpy(f_rec[i] + 0x48, &at, 8);
    f_attr[i][4] = 50, f_attr[i][5] = 51, f_attr[i][6] = 52, f_attr[i][7] = 53, f_attr[i][11] = 54;
    f_attr[i][0x28] = 70, f_attr[i][0x36] = 96, f_attr[i][0x37] = 80, f_attr[i][0x3c] = 64;
}

static void ratings_reset(void) {
    rules_reset();
    trainer_ratings_reset();
    player_fake(0, "Away");
    player_fake(1, "Homer");
    trainer_ratings_seen(3, REC(0));
    trainer_ratings_seen(40, REC(1));
    tick(1);
}

static void test_ratings_seen(void) {
    char name[24];
    ratings_reset();
    CHECK(trainer_ratings_player(3, name, sizeof name) && !strcmp(name, "Away"));
    CHECK(trainer_ratings_player(40, name, sizeof name) && !strcmp(name, "Homer"));
    CHECK(!trainer_ratings_player(5, name, sizeof name));
    memset(f_rec[0] + 0x60, 1, 20);   // not a name
    trainer_ratings_seen(6, REC(0));
    CHECK(!trainer_ratings_player(6, name, sizeof name));
    trainer_ratings_seen(200, REC(1));
    trainer_ratings_seen(7, 0);
    CHECK(!trainer_ratings_player(7, name, sizeof name));
}

static void test_preset_and_back(void) {
    ratings_reset();
    trainer_ratings_preset(1, TR_BATTING, TR_BEST);
    tick(2);
    CHECK(f_attr[1][4] == 99 && f_attr[1][7] == 99 && f_attr[1][11] == 99);
    CHECK(f_attr[1][0x36] == 96);          // pitching untouched
    CHECK(f_attr[0][4] == 50);             // the other side untouched
    trainer_ratings_preset(1, TR_BATTING, TR_NORMAL);
    tick(3);
    CHECK(f_attr[1][4] == 50 && f_attr[1][7] == 53 && f_attr[1][11] == 54);
}

static void test_pitch_preset_keeps_empty_slots(void) {
    ratings_reset();
    trainer_ratings_preset(0, TR_PITCHING, TR_WORST);
    tick(2);
    CHECK(f_attr[0][0x36] == 10 && f_attr[0][0x37] == 10 && f_attr[0][0x3c] == 10);
    CHECK(f_attr[0][0x38] == 0);           // he has no third pitch
    CHECK(f_attr[0][4] == 50);
}

static void test_single_value(void) {
    ratings_reset();
    int power_l = -1;
    for (int r = 0; r < tr_rating_count; r++)
        if (tr_ratings[r].off == 6) power_l = r;
    CHECK(power_l >= 0);
    trainer_ratings_set(40, power_l, 88);
    tick(2);
    CHECK(f_attr[1][6] == 88 && trainer_ratings_value(40, power_l) == 88);
    trainer_ratings_set(40, power_l, 300);
    tick(3);
    CHECK(f_attr[1][6] == 88);
    trainer_ratings_preset(1, TR_BATTING, TR_NORMAL);   // normal drops that side's own edits too
    tick(4);
    CHECK(f_attr[1][6] == 52);
}

static void test_ratings_blocked_in_saved_modes(void) {
    ratings_reset();
    trainer_ratings_preset(1, TR_BATTING, TR_BEST);
    tick(2);
    CHECK(f_attr[1][4] == 99);
    fake_mode(3);
    tick(3);
    CHECK(f_attr[1][4] == 50);   // undone at once, and confirming does not allow it
    trainer_confirm(1);
    tick(4);
    CHECK(f_attr[1][4] == 50);
    TrView view;
    trainer_view(&view);
    CHECK(view.ratings_blocked);
}

static void test_ratings_undone_when_disabled(void) {
    ratings_reset();
    trainer_ratings_preset(1, TR_BATTING, TR_BEST);
    tick(2);
    trainer_set_enabled(0);
    CHECK(f_attr[1][4] == 50);
}

static void test_ratings_next_match(void) {
    ratings_reset();
    trainer_ratings_preset(1, TR_BATTING, TR_BEST);
    tick(2);
    fake_match_gone();
    tick(3);
    tick(14);
    char name[24];
    CHECK(!trainer_ratings_player(40, name, sizeof name));
    fake_match_back();
    player_fake(1, "Newman");
    trainer_ratings_seen(40, REC(1));
    tick(15);
    CHECK(f_attr[1][4] == 99);   // the preset is remembered in exhibitions
}

static void test_ratings_remembered_across_starts(void) {
    ratings_reset();
    trainer_ratings_preset(0, TR_PITCHING, TR_BEST);
    tick(2);
    trainer_ratings_reset();
    trainer_init(g_profile);
    CHECK(trainer_ratings_level(0, TR_PITCHING) == TR_BEST);
    CHECK(trainer_ratings_level(1, TR_BATTING) == TR_NORMAL);
}

// The preset rows are the away and home teams, whichever side controller 1 plays (settings key 15).
static void fake_user(int side) { f_settings[0x3e + 15] = (uint8_t)side; }

static void test_user_side(void) {
    fake_reset();
    fake_user(1);
    CHECK(tr_user_side() == 1);
    fake_user(0);
    CHECK(tr_user_side() == 0);
    fake_user(2);   // no side: watching
    CHECK(tr_user_side() == -1);
    f_settings_slot = 0;
    CHECK(tr_user_side() == -1);
}

static void test_presets_are_away_and_home(void) {
    ratings_reset();
    fake_user(1);
    trainer_ratings_preset(TR_AWAY, TR_BATTING, TR_BEST);
    tick(2);
    CHECK(f_attr[0][4] == 99 && f_attr[1][4] == 50);
    fake_user(0);   // switching teams mid-match moves nothing
    tick(3);
    CHECK(f_attr[0][4] == 99 && f_attr[1][4] == 50);
    fake_user(2);
    trainer_ratings_preset(TR_HOME, TR_BATTING, TR_WORST);
    tick(4);
    CHECK(f_attr[1][4] == 10 && f_attr[0][4] == 99);
}

static void test_cycle_keys(void) {
    ratings_reset();
    trainer_ratings_cycle(TR_HOME, TR_PITCHING);
    CHECK(trainer_ratings_level(TR_HOME, TR_PITCHING) == TR_BEST);
    CHECK(trainer_ratings_level(TR_AWAY, TR_PITCHING) == TR_NORMAL);
    trainer_ratings_cycle(TR_HOME, TR_PITCHING);
    CHECK(trainer_ratings_level(TR_HOME, TR_PITCHING) == TR_WORST);
    trainer_ratings_cycle(TR_HOME, TR_PITCHING);
    CHECK(trainer_ratings_level(TR_HOME, TR_PITCHING) == TR_NORMAL);
}

static void test_cheat_key_names(void) {
    CHECK(trainer_cheat_key("5") == '5' && trainer_cheat_key("0") == '0');
    CHECK(trainer_cheat_key("Insert") == 0x2d && trainer_cheat_key("Delete") == 0x2e);
    CHECK(trainer_cheat_key("Home") == 0x24 && trainer_cheat_key("End") == 0x23);
    CHECK(trainer_cheat_key("PageUp") == 0x21 && trainer_cheat_key("PageDown") == 0x22);
    CHECK(!trainer_cheat_key("none") && !trainer_cheat_key("1") && !trainer_cheat_key("W") && !trainer_cheat_key(""));
}

// ---- the pitcher's real energy (role + 0x18, 0..255; role + 0x10 is the energy object, +0x1c the pitcher's id)
#define ROLE(i) ((uint64_t)(uintptr_t)f_role[i])
static void role_fake(int i, int id, float energy) {
    memset(f_role[i], 0, sizeof f_role[i]);
    uint64_t table = 0x70022b6bf8ull;
    memcpy(f_role[i] + 0x10, &table, 8);
    setf(f_role[i], 0x18, energy);
    memcpy(f_role[i] + 0x1c, &id, 4);
}

static void energy_reset(void) {
    rules_reset();
    trainer_ratings_reset();
    fake_user(1);
    role_fake(0, 3, 200);
    role_fake(1, 40, 120);
    trainer_on_role(ROLE(0));
    trainer_on_role(ROLE(1));
    tick(1);
}

static void test_energy_held(void) {
    energy_reset();
    trainer_energy(TR_MINE, TR_ENERGY_FULL);
    tick(2);
    CHECK(near_f(getf(f_role[1], 0x18), 255) && near_f(getf(f_role[0], 0x18), 200));
    trainer_energy(TR_THEIRS, TR_ENERGY_TIRED);
    setf(f_role[1], 0x18, 250);   // the game tires him; it is put back
    tick(3);
    CHECK(near_f(getf(f_role[1], 0x18), 255) && near_f(getf(f_role[0], 0x18), 64));
    trainer_energy(TR_MINE, TR_ENERGY_NORMAL);
    setf(f_role[1], 0x18, 240);
    tick(4);
    CHECK(near_f(getf(f_role[1], 0x18), 240));   // left to the game again, from where it is
}

static void test_energy_refill_once(void) {
    energy_reset();
    trainer_energy_refill(TR_MINE);
    tick(2);
    CHECK(near_f(getf(f_role[1], 0x18), 255));
    setf(f_role[1], 0x18, 100);
    tick(3);
    CHECK(near_f(getf(f_role[1], 0x18), 100));
}

static void test_energy_checks_the_object(void) {
    energy_reset();
    memset(f_role[1] + 0x10, 0, 8);   // no longer a pitcher object
    trainer_energy(TR_MINE, TR_ENERGY_FULL);
    tick(2);
    CHECK(near_f(getf(f_role[1], 0x18), 120));
    role_fake(1, 40, 120);
    setf(f_role[1], 0x18, 9000);
    tick(3);
    CHECK(near_f(getf(f_role[1], 0x18), 9000));
}

static void test_energy_blocked_in_saved_modes(void) {
    energy_reset();
    fake_mode(3);
    trainer_energy(TR_MINE, TR_ENERGY_FULL);
    trainer_energy_refill(TR_THEIRS);
    tick(2);
    CHECK(near_f(getf(f_role[1], 0x18), 120) && near_f(getf(f_role[0], 0x18), 200));
}

static void test_energy_match_end_and_memory(void) {
    energy_reset();
    trainer_energy(TR_MINE, TR_ENERGY_FULL);
    tick(2);
    fake_match_gone();
    tick(3);
    tick(14);
    setf(f_role[1], 0x18, 90);
    fake_match_back();
    tick(15);
    CHECK(near_f(getf(f_role[1], 0x18), 90));   // the old match's object is forgotten
    trainer_on_role(ROLE(1));
    tick(16);
    CHECK(near_f(getf(f_role[1], 0x18), 255));  // the choice is remembered
    trainer_ratings_reset();
    trainer_init(g_profile);
    CHECK(trainer_energy_level(TR_MINE) == TR_ENERGY_FULL);
}

static void test_energy_command(void) {
    energy_reset();
    CHECK(trainer_command("energy 0 1"));
    tick(2);
    CHECK(near_f(getf(f_role[1], 0x18), 255));
    CHECK(!trainer_command("energy 0 9") && !trainer_command("energy 3 1"));
}

static void test_ratings_command(void) {
    ratings_reset();
    fake_user(0);
    CHECK(trainer_command("ratings 1 1 2"));   // home, pitching, worst
    tick(2);
    CHECK(f_attr[1][0x36] == 10);
    CHECK(!trainer_command("ratings 2 0 1") && !trainer_command("ratings 0 0 7"));
}

// ---- the guaranteed cheats
#define INPUT ((uint64_t)(uintptr_t)f_input)
#define PLACE ((uint64_t)(uintptr_t)f_place)

static void swing_fake(void) {
    memset(f_input, 0, sizeof f_input), memset(f_block, 0, sizeof f_block), memset(f_bunt, 0, sizeof f_bunt);
    uint64_t block = (uint64_t)(uintptr_t)f_block, bunt = (uint64_t)(uintptr_t)f_bunt;
    memcpy(f_input + 0x18, &block, 8);
    memcpy(f_input + 0x140, &bunt, 8);
}

static void test_force_hit_sets_and_restores(void) {
    fake_reset(), swing_fake();
    memset(f_block + 0x28, 0, 4);
    memset(f_block + 0x3c, 0x5a, 0x30);
    uint8_t before[sizeof f_block], saved[TR_OVERRIDE_BYTES];
    memcpy(before, f_block, sizeof f_block);
    TrForced f = {-10, 29, 112};
    CHECK(tr_force_hit(INPUT, &f, saved) == TR_OK);
    uint32_t flag;
    memcpy(&flag, f_block + 0x28, 4);
    CHECK(flag == 1);
    CHECK(near_f(getf(f_block, 0x30), -10) && near_f(getf(f_block, 0x34), 29) && near_f(getf(f_block, 0x38), 112));
    CHECK(near_f(getf(f_block, 0x4c), 0));   // no spin left over: the game works one out
    tr_force_hit_end(INPUT, saved);
    CHECK(!memcmp(before, f_block, sizeof f_block));
}

static void test_force_hit_refuses(void) {
    fake_reset(), swing_fake();
    uint8_t saved[TR_OVERRIDE_BYTES];
    TrForced bad = {0, 29, 500}, good = {0, 29, 112};
    CHECK(tr_force_hit(INPUT, &bad, saved) == TR_OUT_OF_RANGE);
    CHECK(tr_force_hit(0, &good, saved) == TR_NO_MATCH);
    f_block[0x29] = 7;   // not a flag
    CHECK(tr_force_hit(INPUT, &good, saved) == TR_UNEXPECTED);
    CHECK(near_f(getf(f_block, 0x38), 0));
    tr_game_init("1.0.15");
    CHECK(tr_force_hit(INPUT, &good, saved) == TR_WRONG_VERSION);
}

static void test_bunt_flags(void) {
    fake_reset(), swing_fake();
    CHECK(!tr_is_bunt(INPUT));
    f_bunt[0x4d] = 1;
    CHECK(tr_is_bunt(INPUT));
    f_bunt[0x4d] = 0, f_bunt[0x4e] = 1;
    CHECK(tr_is_bunt(INPUT));
}

static void test_pitch_center(void) {
    fake_reset();
    memset(f_place, 0, sizeof f_place);
    setf(f_place, 0x38, 1.5f), setf(f_place, 0x100, 0.4f), setf(f_place, 0x104, -0.2f);
    float miss[3];
    CHECK(tr_pitch_center(PLACE, miss) == TR_OK);
    CHECK(near_f(miss[0], 0.4f) && near_f(miss[1], -0.2f));
    CHECK(near_f(getf(f_place, 0x100), 0) && near_f(getf(f_place, 0x104), 0));
    CHECK(near_f(getf(f_place, 0x38), 1.5f));   // the aim point stays
    setf(f_place, 0x100, 1e9f);
    CHECK(tr_pitch_center(PLACE, miss) == TR_UNEXPECTED && getf(f_place, 0x100) > 1e8f);
}

// The game's batting byte is 1 while the away team bats and 0 while the home team does.
#define AWAY_BATS 1
#define HOME_BATS 0
static void test_batting_team(void) {
    fake_reset();
    fake_side(AWAY_BATS);
    CHECK(tr_batting_team() == 0);
    fake_side(HOME_BATS);
    CHECK(tr_batting_team() == 1);
    fake_side(7);
    CHECK(tr_batting_team() == -1);
}

// A match in the top of an inning (away bats) with the controller on the home side.
static void cheat_reset(void) {
    rules_reset();
    fake_side(AWAY_BATS);
    f_settings[0x3e + 15] = 1;
    tick(1);
}

static void test_cheat_sides_follow_the_batter(void) {
    cheat_reset();
    trainer_cheat(TR_CHEAT_MISS, 1 << TR_THEIRS);
    CHECK(trainer_swing_misses());   // away bats: theirs
    fake_side(HOME_BATS);
    CHECK(!trainer_swing_misses());
    trainer_cheat(TR_CHEAT_MISS, 1 << TR_MINE);
    CHECK(trainer_swing_misses());
    trainer_cheat(TR_CHEAT_MISS, 0);
    CHECK(!trainer_swing_misses());
}

static void test_cheat_sides_follow_the_pitcher(void) {
    cheat_reset();
    trainer_cheat(TR_CHEAT_AIM, 1 << TR_MINE);      // home pitches in the top half
    trainer_cheat(TR_CHEAT_STRIKE, 1 << TR_THEIRS);
    CHECK(trainer_pitch_centered() && !trainer_strike_called());
    fake_side(HOME_BATS);
    CHECK(!trainer_pitch_centered() && trainer_strike_called());
}

static void test_cheat_watching_means_away_and_home(void) {
    cheat_reset();
    f_settings[0x3e + 15] = 2;
    trainer_cheat(TR_CHEAT_MISS, 1 << 0);   // away
    CHECK(trainer_swing_misses());
    fake_side(HOME_BATS);
    CHECK(!trainer_swing_misses());
}

static void test_cheat_miss_excludes_contact(void) {
    cheat_reset();
    trainer_cheat(TR_CHEAT_CONTACT, TR_SIDES_ALL);
    trainer_cheat(TR_CHEAT_HOMER, TR_SIDES_ALL);
    trainer_cheat(TR_CHEAT_MISS, 1 << TR_THEIRS);
    CHECK(trainer_cheat_sides(TR_CHEAT_CONTACT) == 1 << TR_MINE);
    CHECK(trainer_cheat_sides(TR_CHEAT_HOMER) == 1 << TR_MINE);
    trainer_cheat(TR_CHEAT_HOMER, TR_SIDES_ALL);
    CHECK(trainer_cheat_sides(TR_CHEAT_MISS) == 0);
}

static int forced_in(const TrForced *f, float az, float lo, float hi, float slow, float fast) {
    return fabsf(f->azimuth) <= az && f->launch >= lo && f->launch <= hi && f->speed >= slow && f->speed <= fast;
}

static void test_force_swing_rules(void) {
    cheat_reset();
    TrForced f;
    CHECK(!trainer_force_swing(0, &f) && !trainer_force_swing(1, &f));
    trainer_cheat(TR_CHEAT_HOMER, TR_SIDES_ALL);
    CHECK(!trainer_force_swing(1, &f));   // a miss stays a miss
    int good = 0;
    for (int n = 0; n < 1000; n++) good += trainer_force_swing(0, &f) && forced_in(&f, 25, 27, 31, 110, 114);
    CHECK(good == 1000);
    trainer_cheat(TR_CHEAT_CONTACT, TR_SIDES_ALL);
    CHECK(trainer_force_swing(1, &f) && forced_in(&f, 25, 27, 31, 110, 114));   // both: even a miss goes out
    trainer_cheat(TR_CHEAT_HOMER, 0);
    CHECK(!trainer_force_swing(0, &f));   // contact alone leaves a hit as it was
    good = 0;
    for (int n = 0; n < 1000; n++) good += trainer_force_swing(1, &f) && forced_in(&f, 35, -2, 22, 62, 88);
    CHECK(good == 1000);
}

static void test_cheat_outside_a_match(void) {
    rules_reset();
    fake_match_gone();
    tick(1);
    trainer_cheat(TR_CHEAT_MISS, TR_SIDES_ALL);
    trainer_cheat_cycle(TR_CHEAT_AIM);
    CHECK(trainer_cheat_sides(TR_CHEAT_MISS) == 0 && trainer_cheat_sides(TR_CHEAT_AIM) == 0);
}

static void test_cheat_cycle_and_command(void) {
    cheat_reset();
    for (int want = 1; want <= 4; want++) {
        trainer_cheat_cycle(TR_CHEAT_STRIKE);
        CHECK(trainer_cheat_sides(TR_CHEAT_STRIKE) == (want & 3));
    }
    CHECK(trainer_command("cheat homer 2") && trainer_cheat_sides(TR_CHEAT_HOMER) == 2);
    CHECK(!trainer_command("cheat homer 4") && !trainer_command("cheat fly 1") && !trainer_command("cheat homer"));
}

static void test_cheat_confirm_in_saved_mode(void) {
    cheat_reset();
    fake_mode(3);
    trainer_cheat(TR_CHEAT_MISS, TR_SIDES_ALL);
    CHECK(!trainer_swing_misses());
    tick(2);
    trainer_view(&v);
    CHECK(v.needs_confirm && !trainer_swing_misses());
    trainer_confirm(1);
    tick(3);
    trainer_view(&v);
    CHECK(!v.needs_confirm && trainer_swing_misses());
}

static void test_cheat_declined(void) {
    cheat_reset();
    fake_mode(1);
    trainer_cheat(TR_CHEAT_MISS, TR_SIDES_ALL);
    tick(2);
    trainer_confirm(0);
    tick(3);
    trainer_view(&v);
    CHECK(!v.needs_confirm && trainer_cheat_sides(TR_CHEAT_MISS) == 0);
}

static void test_cheat_ends_with_the_match_and_the_trainer(void) {
    cheat_reset();
    trainer_cheat(TR_CHEAT_MISS, TR_SIDES_ALL);
    fake_match_gone();
    tick(2);
    CHECK(!trainer_swing_misses());   // nothing is changed while no match reads
    tick(14);
    CHECK(trainer_cheat_sides(TR_CHEAT_MISS) == 0);
    fake_match_back();
    tick(15);
    trainer_cheat(TR_CHEAT_AIM, TR_SIDES_ALL);
    trainer_set_enabled(0);
    CHECK(!trainer_pitch_centered() && trainer_cheat_sides(TR_CHEAT_AIM) == 0);
}

static void test_cheat_held_off_in_quick_manage(void) {
    cheat_reset();
    trainer_cheat(TR_CHEAT_MISS, TR_SIDES_ALL);
    game_screen("uiEngine: Entering screen: [x->SportscastManager ]");
    CHECK(!trainer_swing_misses());
    game_screen("uiEngine: Entering screen: [x->Scorebar ]");
    tick(2);
    CHECK(trainer_swing_misses());
}

// ---- wild throws

static void test_wild_only_on_a_live_ball(void) {
    cheat_reset();
    trainer_cheat(TR_CHEAT_WILD, TR_SIDES_ALL);
    CHECK(!trainer_throw_wild());   // nothing in play yet
    game_screen("GAME_STATE_IN_PLAY: state = IN_PITCH");
    CHECK(!trainer_throw_wild());
    game_screen("GAME_STATE_IN_PLAY: state = IN_PLAY\n");
    CHECK(trainer_throw_wild());
    game_screen("GAME_STATE_IN_PLAY: state = PLAY_OVER");
    CHECK(!trainer_throw_wild());
    game_screen("GAME_STATE_IN_PLAY: state = IN_PLAY");
    game_screen("GAME_STATE_IN_PLAY: state = POST_PITCH");
    CHECK(!trainer_throw_wild());
    game_screen("GAME_STATE_IN_PLAY: state = IN_PLAY");
    game_screen("FLOW STATE EXIT: GAME_STATE_IN_PLAY");
    CHECK(!trainer_throw_wild());
}

static void test_wild_goes_by_the_fielding_team(void) {
    cheat_reset();   // away bats, so the home team (mine) fields
    game_screen("GAME_STATE_IN_PLAY: state = IN_PLAY");
    trainer_cheat(TR_CHEAT_WILD, 1 << TR_THEIRS);
    CHECK(!trainer_throw_wild());
    fake_side(HOME_BATS);
    CHECK(trainer_throw_wild());
    CHECK(trainer_command("cheat wild 1") && !trainer_throw_wild());
}

static void test_wild_ends_with_the_match(void) {
    cheat_reset();
    game_screen("GAME_STATE_IN_PLAY: state = IN_PLAY");
    fake_match_gone();
    tick(2);
    tick(14);
    fake_match_back();
    tick(15);
    trainer_cheat(TR_CHEAT_WILD, TR_SIDES_ALL);
    CHECK(!trainer_throw_wild());   // the last match's play is not this one's
}

int main(void) {
    test_wild_only_on_a_live_ball();
    test_wild_goes_by_the_fielding_team();
    test_wild_ends_with_the_match();
    test_force_hit_sets_and_restores();
    test_force_hit_refuses();
    test_bunt_flags();
    test_batting_team();
    test_pitch_center();
    test_cheat_sides_follow_the_batter();
    test_cheat_sides_follow_the_pitcher();
    test_cheat_watching_means_away_and_home();
    test_cheat_miss_excludes_contact();
    test_force_swing_rules();
    test_cheat_outside_a_match();
    test_cheat_cycle_and_command();
    test_cheat_confirm_in_saved_mode();
    test_cheat_declined();
    test_cheat_ends_with_the_match_and_the_trainer();
    test_cheat_held_off_in_quick_manage();
    test_ratings_seen();
    test_preset_and_back();
    test_pitch_preset_keeps_empty_slots();
    test_single_value();
    test_ratings_blocked_in_saved_modes();
    test_ratings_undone_when_disabled();
    test_ratings_next_match();
    test_ratings_remembered_across_starts();
    test_user_side();
    test_presets_are_away_and_home();
    test_cycle_keys();
    test_cheat_key_names();
    test_energy_held();
    test_energy_refill_once();
    test_energy_checks_the_object();
    test_energy_blocked_in_saved_modes();
    test_energy_match_end_and_memory();
    test_energy_command();
    test_ratings_command();
    test_pitcher_access();
    test_hit_access();
    test_pitcher_readout();
    test_hit_readout();
    test_match_end_clears_readouts();
    test_hooks_off_when_disabled();
    test_contrast();
    test_row_width();
    test_set_applies_on_tick();
    test_disabled_touches_nothing();
    test_confirm_in_franchise();
    test_confirm_no_drops();
    test_confirm_holds_a_load();
    test_jump_same_side();
    test_jump_extra_transition();
    test_jump_back_refused();
    test_jump_cancel();
    test_slot_roundtrip();
    test_load_later_inning();
    test_load_earlier_inning();
    test_save_refused_in_transition();
    test_bad_slot_lines();
    test_match_end_drops_pending();
    test_short_gap_keeps_jump();
    test_duplicate_keys();
    test_speed();
    test_speed_toggle_starts_at_half();
    test_speed_only_in_a_match();
    test_speed_off_when_disabled();
    test_speed_command();
    test_system_keys_left_alone();
    test_quick_manage_blocks();
    test_quick_manage_is_not_a_match_end();
    test_quick_manage_logs_once();
    test_quick_manage_ends_with_the_match();
    test_other_log_lines_ignored();
    test_menu_closes_panel();
    test_command();
    test_version();
    test_read();
    test_write();
    test_no_match();
    test_garbage();
    test_transition_values();
    test_side_mode();
    printf("%d checks, %d failed\n", g_checks, g_failed);
    return g_failed;
}
