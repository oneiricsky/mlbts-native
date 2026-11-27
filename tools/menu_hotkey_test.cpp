// Checks who gets F7 in a dev build (runtime/gfx/ui/menu_win.cpp): the trainer when one of its keys is F7, else the
// dev panel. The menu and the trainer stand in; no game and no GPU.
//
//   "C:/Program Files/LLVM/bin/clang++.exe" -std=c++17 -DMLB_DEV_HARNESS -D_CRT_SECURE_NO_WARNINGS -I runtime/gfx \
//       -I runtime/third_party/imgui -I <deps>/include -o work/scratch/menu_hotkey_test.exe tools/menu_hotkey_test.cpp \
//       runtime/gfx/ui/menu_win.cpp -luser32 && work/scratch/menu_hotkey_test.exe
// <deps> holds the Vulkan headers (menu.h): the --deps folder of tools/build.py.
#include <windows.h>

#include <stdio.h>

static int g_open, g_dev_toggles, g_trainer_presses, g_trainer_key;   // g_trainer_key: the key the trainer has, 0 none

extern "C" {
int menu_window_msg(HWND h, UINT m, WPARAM w, LPARAM l, LRESULT *res);
int menu_is_open(void) { return g_open; }
void menu_toggle(void) {}
void menu_dev_toggle(void) { g_dev_toggles++; }
void menu_perf_cycle(void) {}
void menu_event_key(int, int) {}
void menu_event_char(unsigned) {}
void menu_event_mouse_pos(float, float) {}
void menu_event_mouse_button(int, int) {}
void menu_event_wheel(float, float) {}
void menu_event_focus(int) {}
int trainer_visible(void) { return 0; }
int trainer_takes_key(int system_key, int auto_repeat) { return !system_key && !auto_repeat; }
int trainer_ui_key(unsigned vk) {
    if ((int)vk != g_trainer_key) return 0;
    g_trainer_presses++;
    return 1;
}
}

static int failed;
static void check(const char *what, int ok) {
    printf("%s: %s\n", ok ? "ok" : "FAIL", what);
    failed |= !ok;
}

static void press(int open, int trainer_key, int repeat) {
    g_open = open, g_trainer_key = trainer_key, g_dev_toggles = g_trainer_presses = 0;
    LRESULT r;
    menu_window_msg(nullptr, WM_KEYDOWN, VK_F7, repeat ? 1 | 1 << 30 : 1, &r);
}

int main() {
    press(0, 0, 0);
    check("F7 opens the dev panel when no trainer key is F7", g_dev_toggles == 1 && !g_trainer_presses);
    press(0, VK_F7, 0);
    check("F7 goes to the trainer when it has the key", g_trainer_presses == 1 && !g_dev_toggles);
    press(0, VK_F7, 1);
    check("holding it down opens nothing", !g_trainer_presses && !g_dev_toggles);
    press(1, VK_F7, 0);
    check("with a panel or the menu open, F7 still closes the dev panel", g_dev_toggles == 1 && !g_trainer_presses);
    return failed;
}
