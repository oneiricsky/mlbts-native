// Settings pages in two panes (ui/option_rows.cpp): option rows on the left, the selected (controller) or hovered (mouse)
// row's description on the right. Each row shows a setting of the cfg table (cfg.h) and changes it through
// cfg_set_saved: A or a click steps it (toggle, next value), left and right step it. A row marks the default value, says
// "after restart" when the setting is read at start, and is greyed out with a note when an environment variable fixes it.
//
//   opt_begin("##screen", scale);
//   opt_toggle("MLB_FULLSCREEN", "Fullscreen", "What it does.");
//   opt_end();
//
// key: the setting's name, which must have a cfg_meta row. Present path only (ImGui).
// From TotK Recomp runtime/ui/option_rows.h @ ae30a61 (MIT): the menu catalog's text ids are plain English strings
// here, and the binding, movable and text-field rows are not ported.
#pragma once
#include "imgui.h"

void opt_begin(const char *id, float scale);
void opt_end(void);
// The height the next pages leave free under their panes (the menu's bottom row).
void opt_reserve_bottom(float h);
// The next page's first row takes the controller's cursor (opening the menu, switching tabs).
void opt_focus_first(void);
// The row of this key (or button id) takes the cursor when it is next drawn (back from a confirmation).
void opt_focus_key(const char *key);
// mlb.cfg is written a moment from now, as after a row's change (a change made outside the rows: reset).
void opt_save_soon(void);

// Page text that is not a row: a group heading in the accent colour, a wrapped paragraph (warn: the warning colour).
void opt_group(const char *title);
void opt_text(const char *text, bool warn = false);

// fastball: the next row is unavailable: greyed out and not changeable (still selectable, so its description shows),
// with why under its label and in the description ("Needs an NVIDIA GeForce RTX graphics card"). NULL: available.
void opt_unavailable(const char *why);

// The return value of every row: true when it changed the setting this frame.
bool opt_toggle(const char *key, const char *label, const char *desc);
// One name per value of the key's cfg_meta values list, in its order. note: a short line under the value in place of
// the "default" mark (NULL: none).
bool opt_choice(const char *key, const char *label, const char *const *names, int n, const char *desc,
                const char *note = nullptr);
// A choice over a list the caller builds (window sizes): values[i] is written, names[i] shown. cur: the index in
// effect, -1 to find cfg_value(key) in values (no match: the value shown as it is).
bool opt_choice_list(const char *key, const char *label, const char *const *values, const char *const *names, int n,
                     const char *desc, int cur = -1, const char *note = nullptr);
// A row that runs an action: true on A or a click. id: unique on the page and not a setting ("##reset"); value: shown
// on the right ("" none).
bool opt_button(const char *id, const char *label, const char *desc, const char *value = "");
// lo..hi in steps of step (left and right held for a second go ten times as fast); fmt formats the value ("%.0f %%").
// fallback: a key whose value the row shows while key is unset (the per-stick dead zones fall back to both sticks'
// one); landing on the fallback's value unsets key again.
bool opt_slider(const char *key, const char *label, float lo, float hi, const char *desc, float step = 1,
                const char *fmt = "%g", const char *note = nullptr, const char *fallback = nullptr);

// mlb.cfg is written a moment after the last change (a held slider would rewrite it every frame) and when the menu
// closes. opt_save_tick: on every frame the menu lays out; force: write now if anything is pending. 1 while a write is
// pending.
int opt_save_tick(int force);
