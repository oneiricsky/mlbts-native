// Native test of the dev harness without the game: the scenario and dump parser (harness_parse_file), and markers, the
// frame log, one-off dumps and the clean stop, on the real runtime/mlb/harness.c with the six runtime functions it
// uses standing in for runtime/core. No game code and no GPU: it links harness.c and sha256.c only.
//
//   mkdir -p work/scratch
//   "C:/Program Files/LLVM/bin/clang.exe" -O1 -Wall -std=gnu11 -DMLB_DEV_HARNESS -D_CRT_SECURE_NO_WARNINGS \
//       -I runtime/mlb -I runtime/core -o work/scratch/harness_parse_test.exe tools/harness_parse_test.c \
//       runtime/mlb/harness.c runtime/core/sha256.c "C:/Program Files/LLVM/lib/clang/"*/lib/windows/clang_rt.builtins-x86_64.lib
//   work/scratch/harness_parse_test.exe
//
// (from the repository root, in bash; the last file is clang's runtime library, which sha256.c needs to ask the CPU its
// features: the one tools/build.py links). The exit code is the number of failed checks; 254 when the test crashed and
// 253 when the C runtime refused a call, each with a line that says so.
//
// Arguments: none (a folder of its own under %TEMP%, removed afterwards); a folder that exists (kept, to look at the
// files); `bare`, or a folder and `bare`: only the part without a scenario file and without a team override, the state
// of a dev build started without them. The first run starts itself a second time that way, because harness_init runs
// once in a process. `crash` and `refuse` only end the test the two ways a defect does, to check the lines above.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "harness.h"
#include "sha256.h"

// ---- what harness.c calls in the runtime
static char g_dir[400], g_out[400], g_scenario[400], g_env_home[64], g_env_away[64];
static volatile LONG g_close;   // the watcher asked for the window to close

const char *cfg_get(const char *name) {
    if (!strcmp(name, "MLB_HARNESS_OUT")) return g_out;
    if (!strcmp(name, "MLB_HARNESS")) return g_scenario[0] ? g_scenario : NULL;
    if (!strcmp(name, "MLB_HARNESS_HOME")) return g_env_home[0] ? g_env_home : NULL;
    if (!strcmp(name, "MLB_HARNESS_AWAY")) return g_env_away[0] ? g_env_away : NULL;
    return NULL;
}

uint64_t plat_now_ns(void) {
    static LARGE_INTEGER f;
    LARGE_INTEGER t;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t);
    return (uint64_t)((double)t.QuadPart * 1e9 / (double)f.QuadPart);
}

int plat_mem_readable(uint64_t addr, uint64_t n) {   // as the real one: VirtualQuery on the host address
    MEMORY_BASIC_INFORMATION mbi;
    return VirtualQuery((void *)(uintptr_t)addr, &mbi, sizeof mbi) && mbi.State == MEM_COMMIT &&
           !(mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) && addr + n <= (uint64_t)(uintptr_t)mbi.BaseAddress + mbi.RegionSize;
}

_Noreturn void plat_exit(int code) { ExitProcess((UINT)code); }
void gfx_window_request_close(void) { InterlockedExchange(&g_close, 1); }

// rt_log keeps its lines (any thread) for the checks
static CRITICAL_SECTION g_log_lock;
static char *g_log;
static size_t g_log_n, g_log_cap;
static void log_put(const char *s, size_t n) {
    EnterCriticalSection(&g_log_lock);
    if (g_log_n + n + 1 > g_log_cap) {
        g_log_cap = g_log_cap ? g_log_cap * 2 : 1 << 16;
        g_log = realloc(g_log, g_log_cap);
    }
    memcpy(g_log + g_log_n, s, n);
    g_log_n += n;
    g_log[g_log_n] = 0;
    LeaveCriticalSection(&g_log_lock);
}
void rt_log(const char *fmt, ...) {
    char buf[2048];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof buf) n = sizeof buf - 1;
    log_put(buf, (size_t)n);
    log_put("\n", 1);
}
static int count(const char *text) {   // how often the log holds the text
    int c = 0;
    for (const char *p = g_log; p && (p = strstr(p, text)); p += strlen(text)) c++;
    return c;
}
#define HAS(t) (count(t) > 0)

// ---- checks and files
static int g_fail;
#define CHECK(c, msg) do { if (!(c)) { g_fail++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, msg); } } while (0)

static void write_file(const char *path, const char *text) {
    FILE *f = fopen(path, "wb");
    if (!f || fwrite(text, 1, strlen(text), f) != strlen(text)) CHECK(0, "cannot write a test file");
    if (f) fclose(f);
}

static char *read_file(const char *path, size_t *n) {   // its bytes and a final 0; NULL when there is no such file
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *b = malloc((size_t)sz + 1);
    size_t got = fread(b, 1, (size_t)sz, f);
    fclose(f);
    b[got] = 0;
    if (n) *n = got;
    return b;
}

static char g_p[600];
static const char *in_dir(const char *name) { snprintf(g_p, sizeof g_p, "%s/%s", g_dir, name); return g_p; }

static const char *hex_of(const void *data, size_t bytes, char out[65]) {
    uint8_t h[32];
    sha256(data, bytes, h);
    for (int i = 0; i < 32; i++) snprintf(out + i * 2, 3, "%02x", h[i]);
    return out;
}

// <dir>/<stem>.raw holds exactly these bytes, and <dir>/<stem>.sha256 is sha256sum's line for it: the two files every
// dump leaves, named as the game runs name them
static void check_dump(const char *stem, const void *data, size_t bytes) {
    char path[600], hex[65], want[128];
    snprintf(path, sizeof path, "%s/%s.raw", g_dir, stem);
    size_t n = 0;
    char *b = read_file(path, &n);
    if (!b) { g_fail++; printf("FAIL: %s is missing\n", path); return; }
    if (n != bytes || memcmp(b, data, bytes)) { g_fail++; printf("FAIL: %s has %llu bytes or other bytes\n", path, (unsigned long long)n); }
    free(b);
    size_t len = strlen(path);
    snprintf(path + len - 4, sizeof path - (len - 4), ".sha256");   // .raw becomes .sha256
    snprintf(want, sizeof want, "%s  %s.raw\n", hex_of(data, bytes, hex), stem);
    b = read_file(path, NULL);
    if (!b) { g_fail++; printf("FAIL: %s is missing\n", path); return; }
    if (strcmp(b, want)) { g_fail++; printf("FAIL: %s is not sha256sum's line for %s.raw\n", path, stem); }
    free(b);
}

// The frame log <dir>/<name>: `frames` frame lines with numbers that follow each other, then the markers in order,
// each on the last frame, and nothing else. Header lines start with `# `.
static void check_framelog(const char *name, int frames, const char *const *markers, int nmarkers) {
    char path[600];
    snprintf(path, sizeof path, "%s/%s", g_dir, name);
    char *b = read_file(path, NULL), *text = b;
    if (!b) { g_fail++; printf("FAIL: %s is missing\n", path); return; }
    int nf = 0, nm = 0, wrong = 0;
    long prev = 0, last = 0;
    for (char *line = strtok(b, "\n"); line; line = strtok(NULL, "\n")) {
        long f;
        double t, dt;
        if (!strncmp(line, "# ", 2)) continue;
        if (sscanf(line, "frame %ld t %lf dt_ms %lf", &f, &t, &dt) == 3) {
            if ((nf && f != prev + 1) || t < 0 || dt < 0) wrong++;
            prev = last = f;
            nf++;
            continue;
        }
        char m[64];
        long mf;
        double mt;
        if (sscanf(line, "marker %63s frame %ld t %lf", m, &mf, &mt) == 3) {
            if (nm >= nmarkers || strcmp(m, markers[nm]) || mf != last) wrong++;
            nm++;
            continue;
        }
        wrong++;
    }
    if (nf != frames || nm != nmarkers || wrong) {
        g_fail++;
        printf("FAIL: %s: %d frame lines (%d wanted), %d marker lines (%d wanted), %d wrong\n", path, nf, frames, nm, nmarkers, wrong);
        printf("%s", text);
    }
    free(text);
}

// ---- 1. the scenario and dump parser
static void test_parser(void) {
    HarnessScenario sc;
    write_file(in_dir("good.txt"),
               "\xef\xbb\xbf" "# Bal (0) at team 1: a UTF-8 byte order mark (Notepad) and Windows line endings\r\n"
               "name = bal-field\r\n  home = 0 \r\naway = 1\r\nseed = 0x10\r\nfixed_clock = 1\r\nstop_after_s = 40.5\r\n"
               "stop_at_marker = field_texture\r\nframelog = frames.txt\r\nmarkers = off\r\n"
               "dump = texture:fmt=0x25,size=512x512\r\ndump = texture:fmt=0x25,size=512x512,count=3\r\n"
               "dump = buffer:addr=0x7004651350,size=8,at=match_settings\r\ndump = buffer:addr=0x7004651350,size=8\r\n"
               "\r\n# a blank line above, a comment here\r\n");
    g_log_n = 0;
    CHECK(harness_parse_file(in_dir("good.txt"), &sc) == 0, "good.txt does not parse");
    CHECK(!strcmp(sc.name, "bal-field") && !strcmp(sc.path, g_p), "name or path");
    CHECK(sc.home == 0 && sc.away == 1, "home, away");
    CHECK(sc.has_seed && sc.seed == 16 && sc.fixed_clock == 1, "seed, fixed_clock");
    CHECK(sc.stop_after_s == 40.5 && !strcmp(sc.stop_at_marker, "field_texture"), "stop_after_s, stop_at_marker");
    CHECK(!strcmp(sc.framelog, "frames.txt") && sc.markers == 0, "framelog, markers");
    CHECK(sc.ndump == 4 && sc.errors == 0, "4 dumps, no errors");
    CHECK(sc.dump[0].is_buffer == 0 && sc.dump[0].has_fmt && sc.dump[0].fmt == 0x25 && sc.dump[0].has_size &&
          sc.dump[0].w == 512 && sc.dump[0].h == 512 && sc.dump[0].count == 1, "dump 0: the field texture");
    CHECK(sc.dump[1].count == 3, "dump 1: count 3");
    CHECK(sc.dump[2].is_buffer && sc.dump[2].addr == 0x7004651350ull && sc.dump[2].size == 8 &&
          !strcmp(sc.dump[2].at, "match_settings"), "dump 2: at a marker");
    CHECK(sc.dump[3].is_buffer && sc.dump[3].at[0] == 0, "dump 3: at stop");
    CHECK(count("harness: ") == 0, "good.txt: a line was reported");
    if (count("harness: ")) printf("%s", g_log);

    // One problem a line, each reported with its line number; nothing of it reaches the scenario
    write_file(in_dir("bad.txt"),
               "home = 30\n"                                        // 1
               "away = -1\n"                                        // 2
               "home =\n"                                           // 3
               "seed =\n"                                           // 4
               "fixed_clock = 2\n"                                  // 5
               "stop_after_s = abc\n"                               // 6
               "stop_after_s = nan\n"                               // 7
               "markers = maybe\n"                                  // 8
               "bogus = 1\n"                                        // 9
               "no equals here\n"                                   // 10
               "name = two words\n"                                 // 11
               "dump = texture\n"                                   // 12
               "dump = image:fmt=1\n"                               // 13
               "dump = texture:\n"                                  // 14
               "dump = texture:fmt=,size=512x512\n"                 // 15
               "dump = texture:fmt=0x25,size=512x\n"                // 16
               "dump = texture:fmt=0x25,size=0x512\n"               // 17
               "dump = texture:fmt=0x25,size=512x512,count=0\n"     // 18
               "dump = texture:fmt=0x25,count=-1\n"                 // 19
               "dump = texture:fmt=0x25,coutn=2\n"                  // 20
               "dump = buffer:addr=0x7004651350\n"                  // 21
               "dump = buffer:addr=0,size=8\n"                      // 22
               "dump = buffer:addr=0x7004651350,size=67108865\n"    // 23
               "dump = texture:addr=0x7004651350,size=8\n"          // 24
               "dump = buffer:addr=0x7004651350,size=8,at=\n"       // 25
               "home = 5 # a comment after a value is not a comment\n");   // 26
    g_log_n = 0;
    CHECK(harness_parse_file(in_dir("bad.txt"), &sc) == 0, "bad.txt does not read");
    CHECK(sc.errors == 26, "bad.txt: 26 problems");
    CHECK(count(" line ") == 26, "bad.txt: not every problem names its line");
    CHECK(sc.ndump == 0, "bad.txt: a bad dump was kept");
    CHECK(!strcmp(sc.name, "run") && sc.home == -1 && sc.away == -1 && !sc.has_seed && !sc.fixed_clock &&
          sc.stop_after_s == 0 && sc.markers == 1, "bad.txt: a bad value was applied");
    CHECK(HAS(" line 9: unknown key 'bogus'") && HAS(" line 10: no '='") && HAS(" line 19: bad value '-1' for count") &&
          HAS(" line 20: unknown dump option 'coutn'") && HAS(" line 24: unknown dump option 'addr'") &&
          HAS(" line 13: bad value 'image' for dump"), "bad.txt: a message reads wrong");
    if (sc.errors != 26 || count(" line ") != 26) printf("%s", g_log);

    CHECK(harness_parse_file(in_dir("missing.txt"), &sc) == -1, "a missing file reads");
}

// ---- 2. markers, the frame log, dumps and the stop, with a scenario
static uint8_t g_buf[64];
static const uint8_t g_tex[64] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
                                  27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50,
                                  51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64};

static DWORD WINAPI hammer(void *arg) {   // frame ticks and markers from other threads while the frame log stops and starts
    for (int i = 0; i < 30000; i++) {
        harness_frame_tick();
        if (!(i % 1000)) harness_marker("hammer");
        if ((int)(uintptr_t)arg & 1) Sleep(0);
    }
    return 0;
}

static void test_scenario(void) {
    char text[1024];
    snprintf(text, sizeof text,
             "name = t\nframelog = frames.txt\nstop_at_marker = go\ndump = buffer:addr=%#llx,size=4,at=go\n"
             "dump = buffer:addr=%#llx,size=4\ndump = texture:fmt=0x25,size=2x2,count=2\n",
             (unsigned long long)(uintptr_t)g_buf, (unsigned long long)(uintptr_t)g_buf);
    write_file(in_dir("s.txt"), text);
    snprintf(g_scenario, sizeof g_scenario, "%s", in_dir("s.txt"));
    snprintf(g_env_home, sizeof g_env_home, "3");
    snprintf(g_env_away, sizeof g_env_away, "bogus");
    g_log_n = 0;
    harness_init();
    const HarnessScenario *sc = harness_scenario();
    CHECK(harness_active() == 1, "active with a scenario");
    CHECK(sc->home == 3 && sc->away == -1 && sc->errors == 1, "the env gives the home team; a bad one is refused");
    CHECK(HAS("MLB_HARNESS_AWAY=bogus is not a team") && HAS("marker boot frame 0"), "boot messages");
    CHECK(harness_framelog_active() == 1, "the scenario's framelog starts the frame log");
    CHECK(harness_framelog_start(in_dir("again.txt")) == 0 && !read_file(in_dir("again.txt"), NULL),
          "a second start is refused and leaves no file");
    harness_frame_tick();
    harness_frame_tick();
    harness_frame_tick();
    harness_marker("m1");

    // one-off dumps
    snprintf(text, sizeof text, "buffer:addr=%#llx,size=8,at=ignored", (unsigned long long)(uintptr_t)g_buf);
    CHECK(harness_dump_now(text) == 1, "dump_now: a buffer");
    check_dump("t-0", g_buf, 8);
    CHECK(harness_dump_now("buffer:addr=0x10,size=16") == 0 && HAS("dump_now: buffer 0x10 is not readable"), "dump_now: an unreadable buffer");
    CHECK(harness_dump_now("texture") == 0 && harness_dump_now("texture:") == 0 && harness_dump_now("") == 0 && harness_dump_now(NULL) == 0,
          "dump_now: bad forms are refused");
    CHECK(sc->dump[0].done == 0 && sc->dump[1].done == 0, "dump_now did not use the scenario's buffer dumps");
    CHECK(harness_dump_now("texture:fmt=0x24,size=2x2") == 1, "dump_now: a texture form");
    harness_texture_write(0x24, 4, 4, g_tex, 64);                 // the size differs: no dump
    harness_texture_write(0x25, 2, 2, g_tex, 16);                 // the scenario's texture dump, 1 of 2
    harness_texture_write(0x24, 2, 2, g_tex + 16, 16);            // the armed one
    harness_texture_write(0x25, 2, 2, g_tex + 32, 16);            // the scenario's texture dump, 2 of 2
    harness_texture_write(0x25, 2, 2, g_tex, 16);                 // both are finished: nothing
    check_dump("t-1", g_tex, 16);
    check_dump("t-2", g_tex + 16, 16);
    check_dump("t-3", g_tex + 32, 16);
    CHECK(!read_file(in_dir("t-4.raw"), NULL), "a finished dump dumped again");
    int armed = 0;
    for (int i = 0; i < 20; i++) {   // more one-offs than the 16 slots: a finished one's slot is used again
        snprintf(text, sizeof text, "texture:fmt=0x%x,size=1x1", 0x30 + i);
        armed += harness_dump_now(text);
        harness_texture_write(0x30u + (unsigned)i, 1, 1, g_tex, 4);
        char name[32];
        snprintf(name, sizeof name, "t-%d", 4 + i);
        check_dump(name, g_tex, 4);
    }
    CHECK(armed == 20 && !read_file(in_dir("t-24.raw"), NULL), "20 one-off texture dumps");

    harness_set_teams(7, 8);
    harness_set_teams(30, -1);
    CHECK(sc->home == 7 && sc->away == 8, "set_teams; 30 and -1 change nothing");

    // other threads tick and mark while this one stops and starts the frame log: no crash
    HANDLE th[4];
    for (int i = 0; i < 4; i++) th[i] = CreateThread(NULL, 0, hammer, (void *)(uintptr_t)(i + 1), 0, NULL);
    int cycles = 0;
    for (int i = 0; i < 300; i++) {
        harness_framelog_stop();
        if (harness_framelog_active() != 0) continue;
        if (harness_framelog_start(in_dir("frames.txt")) != 1) continue;
        cycles++;
    }
    WaitForMultipleObjects(4, th, TRUE, INFINITE);
    for (int i = 0; i < 4; i++) CloseHandle(th[i]);
    CHECK(cycles == 300, "300 stop and start cycles");

    // the stop: marker go dumps its buffer and asks for it; the watcher marks stop, closes the frame log, dumps the rest
    harness_framelog_stop();
    CHECK(harness_framelog_start(in_dir("frames2.txt")) == 1, "the frame log before the stop");
    harness_frame_tick();
    harness_frame_tick();
    harness_frame_tick();
    harness_marker("pre-stop");
    harness_marker("go");
    for (int i = 0; i < 5000 && !g_close; i++) Sleep(1);
    CHECK(g_close == 1, "the clean stop did not close the window");
    CHECK(HAS("stopping (go)") && HAS("marker stop frame"), "the stop names its marker");
    CHECK(count("harness: stopping") == 1, "one stop");
    CHECK(harness_framelog_active() == 0, "the stop closes the frame log");
    harness_request_stop("late");
    Sleep(20);
    CHECK(count("harness: stopping") == 1, "a second stop request does nothing");
    harness_frame_tick();
    harness_marker("after");
    const char *markers[] = {"pre-stop", "go", "stop"};
    check_framelog("frames2.txt", 3, markers, 3);
    check_dump("t-24", g_buf, 4);
    check_dump("t-25", g_buf, 4);
    CHECK(!read_file(in_dir("t-26.raw"), NULL), "a buffer dump after the stop");
    if (g_fail) printf("%s", g_log);
}

// ---- 3. no scenario file and no team override (second run, argument `bare`)
static void test_bare(void) {
    g_log_n = 0;
    harness_init();
    CHECK(harness_active() == 0, "not active without a scenario");
    CHECK(HAS("scenario 'run' (none)"), "the boot line says none");
    harness_marker("bare");
    CHECK(HAS("harness: marker bare frame 0"), "a marker without a scenario");
    CHECK(harness_framelog_start(in_dir("bare.txt")) == 1 && harness_framelog_active() == 1, "the frame log without a scenario");
    harness_frame_tick();
    harness_frame_tick();
    harness_marker("m");
    harness_framelog_stop();
    CHECK(harness_framelog_active() == 0, "stopped");
    const char *markers[] = {"m"};
    check_framelog("bare.txt", 2, markers, 1);
    char what[96];
    snprintf(what, sizeof what, "buffer:addr=%#llx,size=4", (unsigned long long)(uintptr_t)g_buf);
    CHECK(harness_dump_now(what) == 1, "dump_now without a scenario");
    check_dump("run-0", g_buf, 4);
    harness_set_teams(1, 2);
    CHECK(harness_scenario()->home == 1 && harness_scenario()->away == 2, "teams are kept for when the settings fill");
    harness_request_stop("bare stop");
    for (int i = 0; i < 5000 && !g_close; i++) Sleep(1);
    CHECK(g_close == 1 && HAS("stopping (bare stop)"), "a stop without a scenario");
    if (g_fail) printf("%s", g_log);
}

static void remove_folder(void) {   // only a folder the test made itself
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(in_dir("*"), &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (strcmp(fd.cFileName, ".") && strcmp(fd.cFileName, "..")) DeleteFileA(in_dir(fd.cFileName));
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
    RemoveDirectoryA(g_dir);
}

static LONG WINAPI crashed(EXCEPTION_POINTERS *e) {   // a crash in any thread ends the process here: say so
    printf("FAIL: the test crashed, exception %#lx at %p\n", e->ExceptionRecord->ExceptionCode, e->ExceptionRecord->ExceptionAddress);
    ExitProcess(254);
    return EXCEPTION_EXECUTE_HANDLER;
}

// The C runtime refuses a call (stdio given no stream is how a frame-log race shows) and would end the process
// without a word
static void refused(const wchar_t *expr, const wchar_t *func, const wchar_t *file, unsigned line, uintptr_t reserved) {
    (void)reserved;
    printf("FAIL: the C runtime refused a call: %ls (%ls, %ls line %u)\n", expr ? expr : L"", func ? func : L"", file ? file : L"", line);
    ExitProcess(253);
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);   // a fatal path ends the process with ExitProcess: the lines before it are out
    SetUnhandledExceptionFilter(crashed);
    _set_invalid_parameter_handler(refused);
    // `crash` and `refuse` end the test the two ways a defect does, to check that each prints its line
    if (argc == 2 && !strcmp(argv[1], "crash")) *(volatile int *)0 = 1;
    if (argc == 2 && !strcmp(argv[1], "refuse")) {
        FILE *none = NULL;   // the compiler must not see it, it warns about a call it knows is wrong
        fprintf(none, "no stream");
        printf("FAIL: fprintf with no stream was not refused\n");
        return 1;
    }
    InitializeCriticalSection(&g_log_lock);
    for (int i = 0; i < 64; i++) g_buf[i] = (uint8_t)(i * 7 + 1);
    int bare = argc > 1 && !strcmp(argv[argc - 1], "bare");
    int given = argc > (bare ? 2 : 1);   // a folder is named: it is used and kept
    if (given) snprintf(g_dir, sizeof g_dir, "%s", argv[1]);
    else {
        char t[400];
        GetTempPathA(sizeof t, t);
        snprintf(g_dir, sizeof g_dir, "%sharness_parse_test_%lu", t, (unsigned long)GetCurrentProcessId());
        CreateDirectoryA(g_dir, NULL);
    }
    snprintf(g_out, sizeof g_out, "%s", g_dir);
    DWORD attr = GetFileAttributesA(g_dir);
    if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
        printf("FAIL: %s is not a folder. Arguments: none, a folder that exists, `bare`, or a folder and `bare`.\n", g_dir);
        return 1;
    }
    if (bare) test_bare();
    else {
        test_parser();
        test_scenario();
        // the second run is a new process: harness_init runs once in a process. Its own path is the module's, not
        // argv[0] (relative, with forward slashes, empty under some shells)
        char exe[1000], cmd[1800];
        GetModuleFileNameA(NULL, exe, sizeof exe);
        snprintf(cmd, sizeof cmd, "\"%s\" \"%s\" bare", exe, g_dir);
        STARTUPINFOA si = {.cb = sizeof si};
        PROCESS_INFORMATION pi;
        int ok = CreateProcessA(exe, cmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi);
        if (!ok) { g_fail++; printf("FAIL: cannot start the bare run, error %lu: %s\n", GetLastError(), cmd); }
        if (ok) {
            WaitForSingleObject(pi.hProcess, 30000);
            DWORD code = 1;
            GetExitCodeProcess(pi.hProcess, &code);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            CHECK(code == 0, "the bare run failed (its lines are above)");
        }
    }
    if (!given) remove_folder();
    printf("harness parse test: %s, %d failed\n", bare ? "bare" : "with a scenario", g_fail);
    return g_fail < 255 ? g_fail : 255;
}
