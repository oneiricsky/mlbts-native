// The in-game trainer's panel (mlb/trainer.c does the work). It shares the settings menu's ImGui context and input
// (menu.cpp): while the panel is up it has the input focus and the game gets an idle controller (mlb/hid.c).
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void trainer_ui_frame_begin(uint64_t frame);   // each presented frame, present path: settings, test commands, the tick
int trainer_ui_wants_draw(void);               // after frame_begin: the panel or its mark is to be drawn
void trainer_ui_draw(float scale, uint32_t w, uint32_t h);   // inside an ImGui frame
int trainer_ui_key(unsigned vk);               // window thread, no auto-repeat; 1 when it was a trainer key

#ifdef __cplusplus
}
#endif
