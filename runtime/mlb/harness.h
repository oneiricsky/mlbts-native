// Dev harness core (research fork). Compiled only when MLB_DEV_HARNESS is defined (tools/build.py defines it for the
// dev target, not for --toolchain release builds); without it every call below is an empty macro and harness.c is empty.
//
// Settings (cfg.c rows, env MLB_X or --set):
//   MLB_HARNESS=<path>      scenario file; unset = harness off (markers still log when MLB_HARNESS_MARKERS=1 is not needed:
//                           harness_marker always logs once the harness is on)
//   MLB_HARNESS_OUT=<dir>   where dumps go (default: harness-out beside the log)
//   MLB_HARNESS_HOME / MLB_HARNESS_AWAY = 0..29   team override without a scenario file (a scenario key wins)
//
// Scenario file: UTF-8 text, one `key = value` per line, `#` starts a comment line, blank lines ignored.
//   name = <word>               run name; dump files are <out>/<name>-<n>.raw
//   home = 0..29                home team (rosters.bin TEAM_INX, BAL=0 .. SF=29); default 27 (LAD)
//   away = 0..29                away team; default 4 (TOR)
//   seed = <integer>            fixed random seed (read by the determinism code through harness_scenario()->seed)
//   fixed_clock = 0|1           fixed clock (same)
//   stop_after_s = <seconds>    clean stop this long after boot
//   stop_at_marker = <name>     clean stop when this marker is logged
//   dump = texture:fmt=0x25,size=512x512[,count=N]   dump matching nvnTextureWriteTexels data (count: default 1 write)
//   dump = buffer:addr=0x7004651350,size=256[,at=<marker>]   dump guest memory at a marker (default: at stop)
//   markers = log|off           default log
// A key not in this list is reported in the log (`harness: unknown key ...`), never silently ignored; so is a bad value.
// Built-in markers: boot, match_settings, field_texture, stop.
#pragma once

#ifdef MLB_DEV_HARNESS

#include <stdint.h>

#define HARNESS_MAX_DUMPS 16

typedef struct {
    int is_buffer;              // 0 texture, 1 buffer
    int has_fmt, has_size;      // texture filters: NVN format (fmt) and region size (w x h) when given
    unsigned fmt, w, h;
    unsigned count;             // texture: how many matching writes to dump (default 1)
    uint64_t addr, size;        // buffer: guest address and bytes
    char at[64];                // buffer: marker that triggers it ("" = at stop)
    unsigned done;              // dumps written so far
} HarnessDump;

typedef struct {
    char path[512];             // the file it came from ("" = none, env only)
    char name[64];              // default "run"
    int home, away;             // -1 = not set (the game's own choice)
    int has_seed; uint64_t seed;
    int fixed_clock;
    double stop_after_s;        // 0 = never
    char stop_at_marker[64];
    int markers;                // 1 = log markers (default)
    HarnessDump dump[HARNESS_MAX_DUMPS];
    int ndump;
    int errors;                 // unknown keys and bad values reported
} HarnessScenario;

int harness_active(void);                              // 1 when MLB_HARNESS or MLB_HARNESS_HOME/AWAY is set
void harness_init(void);                               // main.c, after log_open: read the scenario, start the watcher thread
const HarnessScenario *harness_scenario(void);         // the parsed scenario (always valid, defaults when none)
int harness_parse_file(const char *path, HarnessScenario *out);   // for the runner/tests: 0 ok, -1 unreadable; errors logged
void harness_marker(const char *name);                 // logs `[host] harness: marker <name> frame <n> t <s>`; any thread; may trigger the stop and buffer dumps
void harness_frame_tick(void);                         // gfx_present.c: once per presented frame (the frame number in markers)
void harness_set_teams(int home, int away);            // UI/runtime: change teams now (-1 keeps one); writes the match settings if filled
int harness_match_settings_filled(void);               // 1 once the match-settings struct is filled
void harness_request_stop(const char *why);            // clean stop as the window's close button, exit code 0
void harness_texture_write(unsigned fmt, unsigned w, unsigned h, const void *data, uint64_t bytes);   // nvn_api_obj.c hook

#else

#define harness_active() 0
#define harness_init() ((void)0)
#define harness_marker(name) ((void)0)
#define harness_frame_tick() ((void)0)
#define harness_set_teams(h, a) ((void)0)
#define harness_match_settings_filled() 0
#define harness_request_stop(why) ((void)0)
#define harness_texture_write(f, w, h, d, b) ((void)0)

#endif
