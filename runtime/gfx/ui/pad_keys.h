// The Switch button bits the settings menu and the trainer panel hand to Dear ImGui as gamepad keys. A header of its
// own so tools/menu_nav_test.cpp checks the same table.
// Y (ImGui's FaceLeft) is not handed over: ImGui starts its window-switching mode with it, and a keyboard key arriving
// while it is held aborts the program ("IsNamedKey(key)", imgui.cpp NavUpdateWindowing, 1.91.9). No panel uses Y.
#pragma once
#include "imgui.h"

enum { P_A = 0, P_B = 1, P_X = 2, P_Y = 3, P_L = 6, P_R = 7, P_ZL = 8, P_ZR = 9, P_LEFT = 12, P_UP = 13, P_RIGHT = 14,
       P_DOWN = 15 };
static const struct { int bit; ImGuiKey key; } kPadKeys[] = {
    {P_A, ImGuiKey_GamepadFaceDown}, {P_B, ImGuiKey_GamepadFaceRight}, {P_X, ImGuiKey_GamepadFaceUp},
    {P_L, ImGuiKey_GamepadL1}, {P_R, ImGuiKey_GamepadR1},
    {P_ZL, ImGuiKey_GamepadL2}, {P_ZR, ImGuiKey_GamepadR2}, {P_LEFT, ImGuiKey_GamepadDpadLeft},
    {P_UP, ImGuiKey_GamepadDpadUp}, {P_RIGHT, ImGuiKey_GamepadDpadRight}, {P_DOWN, ImGuiKey_GamepadDpadDown},
};
