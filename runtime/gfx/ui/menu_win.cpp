// Win32 adapter of the in-game settings menu: window messages to menu events (menu.h). Window thread.
// From TotK Recomp runtime/ui/menu_win.cpp @ ae30a61 (MIT, Copyright (c) 2026 Valiantsin Dzerakh).
// fastball: F1 alone opens and closes the menu. Esc does not open it, because Esc is the game's B (hid.c); with the
// menu open, Esc goes to the menu, which closes. F10 cycles the performance overlay, as in TotK. The game reads the
// keyboard with GetAsyncKeyState (hid.c), which gets nothing while the menu is open.
#include <windows.h>
#include <windowsx.h>

#include "imgui.h"

extern "C" {
#include "ui/menu.h"
#include "ui/trainer_ui.h"
int trainer_visible(void);   // mlb/trainer.c
int trainer_takes_key(int system_key, int auto_repeat);
}

static ImGuiKey key_of(WPARAM vk) {
    switch (vk) {
    case VK_UP: return ImGuiKey_UpArrow;
    case VK_DOWN: return ImGuiKey_DownArrow;
    case VK_LEFT: return ImGuiKey_LeftArrow;
    case VK_RIGHT: return ImGuiKey_RightArrow;
    case VK_RETURN: return ImGuiKey_Enter;
    case VK_SPACE: return ImGuiKey_Space;
    case VK_ESCAPE: return ImGuiKey_Escape;
    case VK_TAB: return ImGuiKey_Tab;
    case VK_BACK: return ImGuiKey_Backspace;
    case VK_DELETE: return ImGuiKey_Delete;
    case VK_HOME: return ImGuiKey_Home;
    case VK_END: return ImGuiKey_End;
    case VK_PRIOR: return ImGuiKey_PageUp;
    case VK_NEXT: return ImGuiKey_PageDown;
    case VK_SHIFT: return ImGuiKey_LeftShift;
    case VK_CONTROL: return ImGuiKey_LeftCtrl;
    case 'Q': return ImGuiKey_Q;   // previous tab
    case 'E': return ImGuiKey_E;   // next tab
    default: return ImGuiKey_None;
    }
}

extern "C" int menu_window_msg(HWND h, UINT m, WPARAM w, LPARAM l, LRESULT *res) {
    (void)h;
    switch (m) {
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        if (w == VK_F1) {
            if (!(l & (1 << 30))) menu_toggle();   // bit 30: auto-repeat
            *res = 0;
            return 1;
        }
#ifdef MLB_DEV_HARNESS
        if (w == VK_F7) {   // the dev harness panel; F7 is free (F1 menu, F8 state dump, F9 / F12 capture, F10 overlay, F11)
            if (!(l & (1 << 30))) menu_dev_toggle();
            *res = 0;
            return 1;
        }
#endif
        if (w == VK_F10) {   // a system key: handled here, Windows would otherwise move the focus to the menu bar
            if (!(l & (1 << 30))) menu_perf_cycle();
            *res = 0;
            return 1;
        }
        // fastball: the trainer's show, save and replay keys (not while the settings menu is up)
        if (!menu_is_open() && trainer_takes_key(m == WM_SYSKEYDOWN, (l & (1 << 30)) != 0) &&   // bit 30: auto-repeat
            trainer_ui_key((unsigned)w)) {
            *res = 0;
            return 1;
        }
        [[fallthrough]];
    case WM_KEYUP:
    case WM_SYSKEYUP:
        if (!menu_is_open() && !trainer_visible()) return 0;
        if (ImGuiKey k = key_of(w)) menu_event_key(k, m == WM_KEYDOWN || m == WM_SYSKEYDOWN);
        return 0;   // F11, F12 and the system keys keep working
#ifdef MLB_DEV_HARNESS
    case WM_CHAR:
        if (menu_is_open() && w >= 0x20 && w != 0x7f) menu_event_char((unsigned)w);
        return 0;
#endif
    case WM_MOUSEMOVE:
        if (menu_is_open() || trainer_visible()) menu_event_mouse_pos((float)GET_X_LPARAM(l), (float)GET_Y_LPARAM(l));
        return 0;
    case WM_LBUTTONDOWN: case WM_LBUTTONUP:
    case WM_RBUTTONDOWN: case WM_RBUTTONUP:
    case WM_MBUTTONDOWN: case WM_MBUTTONUP: {
        if (!menu_is_open() && !trainer_visible()) return 0;
        int b = m == WM_LBUTTONDOWN || m == WM_LBUTTONUP ? 0 : m == WM_RBUTTONDOWN || m == WM_RBUTTONUP ? 1 : 2;
        int down = m == WM_LBUTTONDOWN || m == WM_RBUTTONDOWN || m == WM_MBUTTONDOWN;
        menu_event_mouse_pos((float)GET_X_LPARAM(l), (float)GET_Y_LPARAM(l));
        menu_event_mouse_button(b, down);
        return 0;
    }
    case WM_MOUSEWHEEL:
        if (menu_is_open() || trainer_visible()) menu_event_wheel(0, (float)GET_WHEEL_DELTA_WPARAM(w) / WHEEL_DELTA);
        return 0;
    case WM_SETFOCUS:
    case WM_KILLFOCUS:
        menu_event_focus(m == WM_SETFOCUS);
        return 0;
    }
    return 0;
}
