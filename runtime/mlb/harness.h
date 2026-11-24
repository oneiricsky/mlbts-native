// Dev harness core (research fork). Compiled only when MLB_DEV_HARNESS is defined (tools/build.py defines it for the
// dev target, not for --toolchain release builds); without it every call below does nothing and harness.c is empty.
//
// Settings (cfg.c rows, env MLB_X or --set):
//   MLB_HARNESS=<path>      scenario file; harness is on when it, MLB_HARNESS_HOME or MLB_HARNESS_AWAY is set
//   MLB_HARNESS_OUT=<dir>   where dumps go (default: harness-out beside the log)
//   MLB_HARNESS_HOME / MLB_HARNESS_AWAY = 0..29   team override without a scenario file (a scenario key wins)
//
// On and active. A dev build always runs harness_init, so the harness is on in every dev build: markers, the frame log,
// harness_dump_now and harness_request_stop work without a scenario file (the dev panel uses them that way).
// harness_active() is narrower: 1 only while a scenario file or the team override is set.
//
// Scenario file: UTF-8 text, one `key = value` per line, `#` starts a comment line, blank lines ignored.
//   name = <word>               run name; dump files are <out>/<name>-<n>.raw
//   home = 0..29                home team (rosters.bin TEAM_INX, BAL=0 .. SF=29); default 27 (LAD)
//   away = 0..29                away team; default 4 (TOR)
//   seed = <integer>            fixed random seed (read by the determinism code through harness_scenario()->seed)
//   fixed_clock = 0|1           fixed clock (same)
//   stop_after_s = <seconds>    clean stop this long after boot
//   stop_at_marker = <name>     clean stop when this marker is logged
//   dump = texture:fmt=0x25,size=512x512[,count=N]   dump nvnTextureWriteTexels data into a texture of that format and size
//                               (size is the texture's, not the written region's; count: writes to dump, 1..1000, default 1)
//   dump = buffer:addr=0x7004651350,size=256[,at=<marker>]   dump guest memory at a marker (default: at stop); at most
//                               64 MiB
//   framelog = <file>           record every frame to this file from boot; closed at a harness stop. One line per
//                               presented frame, `frame <n> t <s> dt_ms <ms>` (ms since the previous frame), and
//                               `marker <name> frame <n> t <s>` per marker; t is seconds since boot. A relative path
//                               is under MLB_HARNESS_OUT
//   markers = log|off           default log
// A key not in this list is reported in the log (`harness: unknown key ...`), never silently ignored; so is a bad value
// (the line and the key), and a dump with an unknown option or a number it does not use in full.
// Built-in markers: boot, match_settings, field_texture, stop.
//
// Outside a scenario file (the dev panel; any thread; they do nothing before harness_init):
//   harness_marker(name)                           a marker now, also a line in the frame log
//   harness_framelog_start(path) / harness_framelog_stop()   the frame log on demand; closed at exit too
//   harness_dump_now("buffer:addr=0x...,size=N")   guest memory written now (an `at=` is ignored)
//   harness_dump_now("texture:fmt=0x25,size=512x512[,count=N]")   armed for the next matching texture write
//   harness_set_teams(home, away)                  the team override; -1 keeps a team
//   harness_request_stop(why)                      a clean stop (exit code 0) within a few ms
#pragma once

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
    char framelog[256];         // "" = none
    int markers;                // 1 = log markers (default)
    HarnessDump dump[HARNESS_MAX_DUMPS];
    int ndump;
    int errors;                 // unknown keys and bad values reported
} HarnessScenario;

#ifdef MLB_DEV_HARNESS

int harness_active(void);                              // 1 while MLB_HARNESS or MLB_HARNESS_HOME/AWAY is set
void harness_init(void);                               // main.c, after log_open: read the scenario, start the watcher thread
const HarnessScenario *harness_scenario(void);         // the parsed scenario (always valid, defaults when none)
int harness_parse_file(const char *path, HarnessScenario *out);   // for the runner/tests: 0 ok, -1 unreadable; errors logged
void harness_marker(const char *name);                 // logs `[host] harness: marker <name> frame <n> t <s>`; any thread; may trigger the stop and buffer dumps
void harness_frame_tick(void);                         // gfx_present.c: once per presented frame (the frame number in markers)
int harness_framelog_start(const char *path);          // frame log to path (1 ok): the lines above; when already logging 0
void harness_framelog_stop(void);                      // closes it; also at a harness stop and at exit
int harness_framelog_active(void);                     // 1 while logging; off costs one pointer test per frame
int harness_dump_now(const char *what);                // one-off dump in a scenario's dump form (1 ok): a buffer is written now, a texture is armed for the next matching write
void harness_set_teams(int home, int away);            // UI/runtime: change teams now (-1 keeps one); writes the match settings if filled
int harness_match_settings_filled(void);               // 1 once the match-settings struct is filled
void harness_request_stop(const char *why);            // clean stop as the window's close button, exit code 0
void harness_texture_write(unsigned fmt, unsigned w, unsigned h, const void *data, uint64_t bytes);   // nvn_api_obj.c hook

#else

// The types stay, so a caller compiles the same in both builds. Every call is empty or answers "off".
static inline const HarnessScenario *harness_scenario(void) {   // the defaults, as without a scenario
    static const HarnessScenario sc = {.name = "run", .home = -1, .away = -1, .markers = 1};
    return &sc;
}
#define harness_active() 0
#define harness_init() ((void)0)
#define harness_parse_file(p, o) ((void)(o), -1)
#define harness_marker(name) ((void)0)
#define harness_frame_tick() ((void)0)
#define harness_framelog_start(p) 0
#define harness_framelog_stop() ((void)0)
#define harness_framelog_active() 0
#define harness_dump_now(w) 0
#define harness_set_teams(h, a) ((void)0)
#define harness_match_settings_filled() 0
#define harness_request_stop(why) ((void)0)
#define harness_texture_write(f, w, h, d, b) ((void)0)

#endif
