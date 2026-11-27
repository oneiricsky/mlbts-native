// The overlay's controller buttons against Dear ImGui, without the game or a GPU: any button the settings menu and the
// trainer panel hand to ImGui, held while a keyboard key arrives, must not abort the program. (2026-11-24: a play
// session ended with "Assertion failed: IsNamedKey(key)", ImGui's window-switching mode started by the pad's Y.)
//
//   "C:/Program Files/LLVM/bin/clang++.exe" -O1 -std=c++17 -D_CRT_SECURE_NO_WARNINGS -I runtime/gfx \
//       -I runtime/third_party/imgui -o work/scratch/menu_nav_test.exe tools/menu_nav_test.cpp \
//       runtime/third_party/imgui/imgui.cpp runtime/third_party/imgui/imgui_draw.cpp \
//       runtime/third_party/imgui/imgui_tables.cpp runtime/third_party/imgui/imgui_widgets.cpp \
//       && work/scratch/menu_nav_test.exe
//
// (from the repository root, in bash). Exit 0 when every case survives; ImGui's assertion ends the program otherwise.
#include <stdio.h>
#include <stdlib.h>

#include "imgui.h"
#include "ui/pad_keys.h"

static void frame(bool window) {
    ImGui::NewFrame();
    if (window) {
        ImGui::Begin("##panel", nullptr, ImGuiWindowFlags_NoDecoration);
        ImGui::Button("a");
        ImGui::Button("b");
        ImGui::End();
    }
    ImGui::EndFrame();
}

int main() {
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);   // a failed run ends without a dialog
    _set_error_mode(_OUT_TO_STDERR);
    const ImGuiKey keyboard[] = {ImGuiKey_DownArrow, ImGuiKey_Enter, ImGuiKey_Escape, ImGuiKey_Q};
    int cases = 0;
    for (const auto &k : kPadKeys) {
        for (ImGuiKey kb : keyboard) {
            printf("pad %s, then keyboard %s\n", ImGui::GetKeyName(k.key), ImGui::GetKeyName(kb));
            fflush(stdout);
            ImGui::CreateContext();
            ImGuiIO &io = ImGui::GetIO();
            io.IniFilename = nullptr;
            io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
            io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
            io.DisplaySize = ImVec2(1280, 720);
            io.DeltaTime = 1 / 60.0f;
            unsigned char *px;
            int w, h;
            io.Fonts->GetTexDataAsRGBA32(&px, &w, &h);
            for (int i = 0; i < 3; i++) frame(true);
            io.AddKeyEvent(k.key, true);   // the button goes down in the panel
            for (int i = 0; i < 3; i++) frame(true);
            io.AddKeyEvent(kb, true);      // a key on the keyboard while it is held
            for (int i = 0; i < 3; i++) frame(true);
            io.AddKeyEvent(kb, false);
            io.ClearInputKeys();           // the panel closes and opens again, as menu.cpp does it
            for (int i = 0; i < 3; i++) frame(false);
            io.AddKeyEvent(kb, true);
            for (int i = 0; i < 3; i++) frame(true);
            io.AddKeyEvent(kb, false);
            for (int i = 0; i < 3; i++) frame(true);
            ImGui::DestroyContext();
            cases++;
        }
    }
    printf("%d cases, 0 failed\n", cases);
    return 0;
}
