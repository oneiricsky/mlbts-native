// The in-game dev harness panel (F7 once "Dev mode" is on in Settings > Dev). Dear ImGui, present path only, laid out by
// menu.cpp. Compiled only with MLB_DEV_HARNESS; every harness call goes through devpanel_adapter.h.
#pragma once
#ifdef MLB_DEV_HARNESS
#include <stdint.h>

// Lays out the panel window for this frame. esc_closes: Esc closes it (not while the settings menu is open over it).
// Returns true when the panel asked to be closed.
bool devpanel_layout(uint32_t w, uint32_t h, float scale, uint64_t frame, bool esc_closes);
// Which side the panel talks to: "harness.h" or the local stub.
const char *devpanel_backend(void);
// MLB_DEVPANEL_TEST=<frame>: opens the panel at that frame and runs every action once, logging `devpanel:` lines.
// Returns true when the panel should be open at this frame because of the hook.
bool devpanel_test_open(uint64_t frame);
#endif
