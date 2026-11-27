// The in-game trainer's rules: requests from the panel, the Season-mode confirmation, the inning jump and the saved
// situations. Every function may be called from any thread; trainer_tick is the only place that writes the game.
#pragma once
#include <stdint.h>

#include "trainer_game.h"

#define TR_SLOTS 3

typedef struct {
    TrStatus status;
    TrCount now;
    int enabled, visible, jumping, jump_target, needs_confirm, slot;
    int used[TR_SLOTS];
    TrCount slots[TR_SLOTS];
    char message[96];
    int has_pitcher, has_hit;
    int speed;          // the match's speed in percent: 100, 75, 50 or 25
    int ratings_blocked;   // a saved mode: ratings are not edited (undoing them there is not proven)
    int user_side;         // 0 away, 1 home, -1 watching
    unsigned hits;      // contacts seen since the match began
    TrPitcher pitcher;
    TrHit hit;          // the last batted ball
} TrView;

void trainer_init(const char *profile_dir);   // reads <profile_dir>/trainer.txt; drops everything pending
void trainer_set_enabled(int on);             // off: hidden, pending dropped, the tick reads no game memory
void trainer_set(TrField f, int value);
void trainer_slot_select(int slot);           // slots are 0..2 here, 1..3 in the file, the panel and commands
void trainer_slot_save(int slot);
void trainer_slot_load(int slot);
void trainer_jump(int half_index);
void trainer_cancel(void);
void trainer_confirm(int yes);
void trainer_toggle(void);                    // no effect while disabled
void trainer_menu_opened(void);               // hides the panel
int trainer_visible(void);                    // visible = has the input focus
// Every line the game logs: the play's state (wild throws), and Quick Manage ("...->SportscastManager") keeps the match data frozen until the scorebar
// returns, so the trainer reads TR_MANAGING and changes nothing in between.
void trainer_game_log(const char *text, int n);
void trainer_tick(uint64_t now_ns);           // once per presented frame
void trainer_view(TrView *out);
// The virtual-key codes for the show, save, load and slow-motion keys ("F2".."F7"). 0 when a name is unknown or two
// are the same: vk is then F2, F3, F4, F6.
int trainer_keys(const char *show, const char *save, const char *load, const char *slow, int vk[4]);
// A pitcher's energy, for mine or theirs (trainer_ratings.h TR_MINE): left to the game, held full or held tired.
enum { TR_ENERGY_NORMAL, TR_ENERGY_FULL, TR_ENERGY_TIRED, TR_ENERGY_LEVELS };
void trainer_energy(int who, int level);
int trainer_energy_level(int who);
void trainer_energy_refill(int who);     // full once
void trainer_on_role(uint64_t role);     // from the hooks: a pitcher object at his pitch
// The guaranteed cheats. Each is on for a set of sides, a bit per who (TR_MINE, TR_THEIRS; away and home when
// watching), and lasts until the match ends. Contact, home run and miss go by the batting side, the others by the
// side in the field. Miss and the two contact cheats shut each other off for a side. In saved modes they wait for the
// same confirmation as any change.
enum { TR_CHEAT_CONTACT, TR_CHEAT_HOMER, TR_CHEAT_MISS, TR_CHEAT_AIM, TR_CHEAT_STRIKE, TR_CHEAT_WILD, TR_CHEATS };
#define TR_SIDES_ALL 3
void trainer_cheat(int cheat, int sides);   // ignored outside a match
void trainer_cheat_cycle(int cheat);        // off, mine, theirs, both
int trainer_cheat_sides(int cheat);
const char *trainer_cheat_name(int cheat);
// For the hooks, about the pitch being played. All are 0 when nothing may be changed.
int trainer_swing_misses(void);
// missed: the swing as the game judged it. 1 with the ball to give instead (a home run, or contact after a miss).
int trainer_force_swing(int missed, TrForced *out);
int trainer_pitch_centered(void);
int trainer_strike_called(void);
int trainer_throw_wild(void);   // only while a batted ball is in play, by the game's own state lines
// The virtual-key code of a cheat key: "5".."9", "0", "Insert", "Delete", "Home", "End", "PageUp", "PageDown" (keys
// the game does not use); 0 for "none" and anything else.
int trainer_cheat_key(const char *name);
void trainer_speed(int percent);       // 100, 75, 50 or 25; other values are ignored
void trainer_slow_toggle(void);        // full speed and the last slow speed (50 at first)
float trainer_speed_scale(void);       // what the frame step is multiplied by; 1 outside a match. Any thread, no lock
// 1 when a key press may be a trainer key: not a system key (Alt held, so Alt+F4 closes the window) and not a repeat.
int trainer_takes_key(int system_key, int auto_repeat);
void trainer_on_pitch(uint64_t state);        // from the hooks, on the game's thread
void trainer_on_hit(uint64_t result);
// Test hook: show | hide | set <field> <n> | save <1..3> | load <1..3> | jump <half index> | confirm | cancel |
// speed <percent> | ratings <who 0 mine|1 theirs> <group 0 bat|1 pitch> <level 0 normal|1 best|2 worst> |
// energy <who> <level 0 normal|1 full|2 tired> |
// cheat <contact|homer|miss|aim|strike|wild> <sides 0 off|1 mine|2 theirs|3 both>
int trainer_command(const char *cmd);
