// Adapted from MacNativeGames games/totk/runtime/fs_host.h @ b75be8cf (MIT, Copyright (c) 2026 MacNativeGames
// contributors).
// The nn::fs host layer (fs_host.c): the read-only RomFS and writable save, temporary and cache storage under the
// profile directory, registered as nn::fs overrides with HOST_OVERRIDE. fastball: TotK's romfs.c interface is
// gone (the RomFS is a mount kind of fs_host.c), fs_title added.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>

// ---- nn::fs results
#define FS_R_PATH_NOT_FOUND 0x202u
#define FS_R_ALREADY_EXISTS 0x402u
#define FS_R_NOT_EMPTY 0x1002u
#define FS_R_UNSUPPORTED_OPEN 0x6402u    // RomFS: any open mode but read
#define FS_R_INVALID 0xe402u             // RomFS: bad handle, offset or argument
#define FS_R_TARGET_NOT_FOUND 0x7d402u
#define FS_R_INVALID_ARGUMENT 0x2ee202u
#define FS_R_INVALID_PATH 0x2ee602u
#define FS_R_OPEN_MODE 0x307402u
#define FS_R_APPEND_REQUIRED 0x2f5e02u

enum { FS_OPEN_READ = 1, FS_OPEN_WRITE = 2, FS_OPEN_APPEND = 4 };   // nn::fs::OpenMode
enum { FS_ENTRY_DIRECTORY = 0, FS_ENTRY_FILE = 1 };                 // nn::fs::DirectoryEntryType

// ---- fastball: the title's figures from its NACP, which the game layer supplies (runtime/mlb/game.c)
typedef struct {
    uint64_t program_id;                   // save data owner: IsSaveDataExisting, MountSaveDataReadOnly
    int64_t save_size, save_journal;       // user account save data, before any ExtendSaveData
    int64_t save_size_max, save_journal_max;
    int64_t temp_size;                     // temporary storage (GetFreeSpaceSize)
} FsTitle;
extern const FsTitle fs_title;
void fs_trace(const char *what, const char *path);         // MLB_TRACE=fs: one line per open

// ---- fs_host.c
int probe_fs(void);                                        // --probe-fs; 0 when every check passed
void fs_host_set_profile(const char *dir);                 // profile directory; before the first storage mount only
                                                           // (default rt_config()->profile)
int fs_save_busy(void);                                    // a save is being written: a save file open for writing,
                                                           // or save data changed in the last 3 s and not committed
// fastball: --import-save. The committed save becomes a copy of the files in src (another emulator's save folder);
// the save it replaces goes to out->backup. 0 on success, else -1 with out->why (fs_host.c).
// stuck: it failed halfway and why says where each copy is.
typedef struct { int files, stuck; uint64_t bytes; char backup[1100], why[1400]; } FsImport;
int fs_save_import(const char *src, FsImport *out);
int save_import_main(const char *arg);                     // --import-save [ryujinx | folder] (save_import.c); exit code
void fs_save_flush(void);                                  // wait for a save Commit still running in the background;
                                                           // every exit path calls it before the process ends
