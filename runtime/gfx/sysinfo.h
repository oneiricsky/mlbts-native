// fastball: from TotK Recomp runtime/sysinfo.h @ ae30a61 (MIT, Copyright (c) 2026 Valiantsin Dzerakh), for the settings
// menu (ui/menu.cpp). MLB names.
// What a bug report needs about the machine (sysinfo.c), for the menu's "Copy system info" and "Open log folder".
#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Plain text, one item per line: OS and build, CPU, RAM, the GPU and its driver as the Vulkan device reports them, and
// every setting with a value (mlb.cfg, the menu, the environment). Technical text for the developers, in English like
// the log. The length written (truncated to n - 1), or 0 on failure.
int sysinfo_text(char *buf, size_t n);
// The CPU's brand string ("AMD Ryzen 7 7800X3D 8-Core Processor"); "" when the CPU has none.
void sysinfo_cpu_name(char *out, size_t n);
// The folder with the log: the folder of logs\mlb.log when this run writes it, else of the file stderr goes to, else
// of mlb.exe. 0 on failure.
int sysinfo_log_folder(char *out, size_t n);

#ifdef __cplusplus
}
#endif
