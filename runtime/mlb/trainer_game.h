// The only part of the in-game trainer that knows game addresses: checked reads and writes of the running match.
#pragma once
#include <stdint.h>

typedef enum { TR_OK, TR_WRONG_VERSION, TR_NO_MATCH, TR_UNEXPECTED, TR_OUT_OF_RANGE, TR_MANAGING } TrStatus;
// TR_HALF: the half-inning index, even top, odd bottom (inning = TR_HALF / 2 + 1)
typedef enum { TR_AWAY_SCORE, TR_HOME_SCORE, TR_BALLS, TR_STRIKES, TR_OUTS, TR_HALF, TR_FIELD_COUNT } TrField;
typedef struct { int v[TR_FIELD_COUNT]; } TrCount;
// The pitcher's state as the fatigue calculation holds it: stamina and energy 0..1, confidence 0..100 (seen 66..73).
typedef enum { TR_STAMINA, TR_ENERGY, TR_CONFIDENCE, TR_PITCH_COUNT } TrPitchField;
typedef struct { float v[TR_PITCH_COUNT]; } TrPitcher;
// A batted ball: direction (degrees, 0 to centre field, beyond 45 foul), launch angle (degrees, over 90 goes back),
// speed (mph). All zero when the swing missed.
typedef struct { float direction, launch, speed; } TrHit;

TrStatus tr_game_init(const char *build);   // TR_OK for a build whose addresses are known (1.0.20)
void tr_game_set_slots(uint64_t count_slot, uint64_t teams_slot, uint64_t settings_slot);   // the host test
TrStatus tr_count_read(TrCount *out);
TrStatus tr_count_write(TrField f, int value);   // refused unless the whole count reads as TR_OK
int tr_write_range_ok(TrField f, int value);
int tr_batting_side(void);   // 0 or 1; -1 unknown
int tr_batting_team(void);   // who bats: 0 away, 1 home; -1 unknown
int tr_game_mode(void);      // settings key 19; -1 unknown
// role: the pitcher's game object, as the fatigue hook sees it. energy 0..255, id the pitcher's.
TrStatus tr_energy_read(uint64_t role, float *energy, int *id);
TrStatus tr_energy_write(uint64_t role, float energy);
int tr_user_side(void);      // settings key 15, controller 1: 0 away, 1 home; -1 no side or unknown
const char *tr_status_text(TrStatus s);
// A batted ball the contact model builds from given figures instead of the swing: degrees, degrees, mph.
typedef struct { float azimuth, launch, speed; } TrForced;
#define TR_OVERRIDE_BYTES 0x44
// input: the contact model's second argument. tr_force_hit sets its override block and keeps the old bytes in saved;
// tr_force_hit_end puts them back. A bunt has a model of its own, which does not look at the block.
TrStatus tr_force_hit(uint64_t input, const TrForced *f, uint8_t saved[TR_OVERRIDE_BYTES]);
void tr_force_hit_end(uint64_t input, const uint8_t saved[TR_OVERRIDE_BYTES]);
int tr_is_bunt(uint64_t input);
// placement: the object of the pitch placement call; clears the miss it holds. miss: what it was (x, y, z).
TrStatus tr_pitch_center(uint64_t placement, float miss[3]);
// state and result: the pointers the hooks see (trainer_hooks.c). Read only: see docs/trainer.md.
TrStatus tr_pitcher_read(uint64_t state, TrPitcher *out);
TrStatus tr_hit_read(uint64_t result, TrHit *out);
