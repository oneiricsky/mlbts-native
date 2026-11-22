// Settings (cfg.c). Interface from TotK Recomp runtime/cfg.h @ ae30a61 (MIT): the settings file and the menu's
// save are not ported. Keys are TotK's names ("TOTK_X" or "X"); MLB_X in the environment wins over TOTK_X.
#pragma once

// What the table knows about a setting. key: without TOTK_, upper case. def: the value when unset ("" = the consumer
// picks). values: "0|1", "a|b|c", a range "0..300", or NULL for free text. live: applies at once.
typedef struct { const char *key, *def, *values; int live; } CfgMeta;

void cfg_init(void);                        // idempotent; memory.c calls it first thing
const char *cfg_get(const char *name);      // environment (MLB_, TOTK_), then cfg_set; NULL when unset
void cfg_set(const char *name, const char *value);   // for this run
unsigned cfg_version(void);                 // changes with every cfg_set
int cfg_is_set(const char *name);
// fastball: the in-game menu's changes. cfg_set_saved is cfg_set plus a note that cfg_save writes the key into
// mlb.cfg (its line updated in place, or added); cfg_save returns 1 when written. cfg_from_env: the environment
// (MLB_X or TOTK_X) sets the key, so a change in the menu would not apply.
void cfg_set_saved(const char *name, const char *value);
int cfg_save(void);
int cfg_from_env(const char *name);
int cfg_last_save_ok(void);                 // the last cfg_save wrote mlb.cfg (1 before any)
// Every key given that the environment does not set back to its table default, as a menu change (cfg_save writes
// them); the number reset.
int cfg_reset(const char *const *keys, int n);
const CfgMeta *cfg_meta_at(int i);          // the table's rows in order; NULL past the last
// Every setting with a value (mlb.cfg, the menu, the environment), for the system info text: fn(key without prefix,
// value, set by the environment, ctx).
void cfg_each_active(void (*fn)(const char *key, const char *value, int from_env, void *ctx), void *ctx);
int cfg_load_file(void);                    // fastball: <exe dir>/mlb.cfg into cfg_set; the settings it applied
const CfgMeta *cfg_meta(const char *key);
const char *cfg_value(const char *name);    // cfg_get, else the table's default; fatal for a key without a row
int cfg_int(const char *name);              // unparsable: the default
double cfg_double(const char *name);
int cfg_bool(const char *name);             // anything but "0"
