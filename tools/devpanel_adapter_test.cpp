// Checks that the dev panel's recorder calls (runtime/gfx/ui/devpanel_adapter.h) really record, on the real
// runtime/mlb/harness.c with the runtime functions it uses standing in for runtime/core. No game and no GPU.
//
//   L="C:/Program Files/LLVM/bin"; F="-DMLB_DEV_HARNESS -D_CRT_SECURE_NO_WARNINGS -I runtime/mlb -I runtime/core -I runtime/gfx"
//   "$L/clang.exe" $F -c runtime/mlb/harness.c -o work/scratch/dpa_harness.o
//   "$L/clang.exe" $F -c runtime/core/sha256.c -o work/scratch/dpa_sha.o
//   "$L/clang++.exe" -std=c++17 $F tools/devpanel_adapter_test.cpp work/scratch/dpa_harness.o work/scratch/dpa_sha.o \
//       "C:/Program Files/LLVM/lib/clang/"*/lib/windows/clang_rt.builtins-x86_64.lib -o work/scratch/devpanel_adapter_test.exe
//   work/scratch/devpanel_adapter_test.exe
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <string>

#include "ui/devpanel_adapter.h"

static std::string g_out;

extern "C" {
const char *cfg_get(const char *name) { return !strcmp(name, "MLB_HARNESS_OUT") ? g_out.c_str() : nullptr; }
uint64_t plat_now_ns(void) { return GetTickCount64() * 1000000ull; }
int plat_mem_readable(uint64_t addr, uint64_t) {   // the harness watcher asks for the game's addresses
    MEMORY_BASIC_INFORMATION m;
    return VirtualQuery((void *)(uintptr_t)addr, &m, sizeof m) && m.State == MEM_COMMIT;
}
__declspec(noreturn) void plat_exit(int code) { ExitProcess((UINT)code); }
void gfx_window_request_close(void) {}
void rt_log(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    putchar('\n');
}
}

static int failed;
static void check(const char *what, int ok) {
    printf("%s: %s\n", ok ? "ok" : "FAIL", what);
    failed |= !ok;
}

static std::string slurp(const std::string &path) {
    FILE *f = fopen(path.c_str(), "rb");
    if (!f) return "";
    char buf[4096];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    return std::string(buf, n);
}

int main() {
    char tmp[MAX_PATH];
    GetTempPathA(MAX_PATH, tmp);
    std::string root = std::string(tmp) + "devpanel_adapter_" + std::to_string(GetCurrentProcessId());
    CreateDirectoryA(root.c_str(), nullptr);
    g_out = root + "/out";   // not there yet, as in a run that has made no dump
    harness_init();

    check("no frame log at start", !dh_framelog_active());
    check("Start frame log succeeds", dh_framelog(1) == 1);
    check("the panel's 'recording' state is the harness's", dh_framelog_active() && harness_framelog_active());
    harness_frame_tick();
    check("Stop frame log succeeds", dh_framelog(0) == 1);
    check("stopped", !dh_framelog_active());
    std::string log = slurp(g_out + "/devpanel-framelog-1.txt");
    check("the frame log file holds the frame", log.find("frame 1 ") != std::string::npos);

    check("a second log gets its own file", dh_framelog(1) == 1 && dh_framelog(0) == 1 &&
                                                !slurp(g_out + "/devpanel-framelog-2.txt").empty());

    check("Dump texture arms the dump", dh_dump_texture("texture:fmt=0x25,size=4x4") == 1);
    const char texels[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    harness_texture_write(0x25, 4, 4, texels, sizeof texels);
    check("the next matching write is dumped", slurp(g_out + "/run-0.raw") == std::string(texels, sizeof texels));
    check("a bad dump text fails", dh_dump_texture("tex") == 0);
    return failed;
}
