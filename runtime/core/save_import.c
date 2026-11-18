// fastball: mlb.exe --import-save [ryujinx | <folder>]: the game's save from another Switch host into this
// profile, then exit. fs_save_import (fs_host.c) swaps it in and keeps the replaced save; this file finds the source.
//
// A Switch save is the same files on every host, so nothing is converted. What the argument names:
//   ryujinx (or nothing)  Ryujinx's data folder %APPDATA%\Ryujinx
//   a Ryujinx data folder  the one holding bis\ (a portable Ryujinx's "portable" folder)
//   a save folder          Ryujinx's bis\user\save\<id> (its "0" inside is taken), or any folder of the save's files
//                          themselves (Ryujinx's <id>\0, yuzu's and its forks' nand\user\save\0...0\<user>\<title>)
//
// Ryujinx's save index is bis/system/save/8000000000000000/0/imkvdb.arc (LibHac's SaveDataIndexer; "0" is the
// committed copy): "IMKV", u32 reserved, u32 entry count, then per entry "IMEN", u32 key size, u32 value size, the key
// and the value. The key is nn::fs::SaveDataAttribute (0x40 bytes: program id u64 at 0, user id 16 bytes at 8, system
// save data id u64 at 0x18, type u8 at 0x20, 1 = account), the value SaveDataIndexerValue (0x40 bytes: save data id
// u64 at 0). The files are in bis/user/save/<save data id, %016x>/0 (LibHac's DirectorySaveDataFileSystem: "0" is
// committed, "1" the working copy). Seen with Ryujinx 1.x and MLB 1.0.15: MLB's account save has id 1,
// bis/user/save/0000000000000001/0 holding CARR<n>/, PLYA<n>/ and SETT<n>/, each with SAVEINFO and SAVE_000.
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fs.h"
#include "host.h"
#include "platform/platform.h"

#define CAP 1100
#define INDEX "bis/system/save/8000000000000000/0/imkvdb.arc"
#define SAVE_TYPE_ACCOUNT 1

static void say(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void say(const char *fmt, ...) {
    char buf[2048];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    rt_log("save import: %s", buf);   // the log also shows on the console
}

static int is_dir(const char *p) { return plat_fs_kind(p) == PLAT_FS_DIR; }
static int is_file(const char *p) { return plat_fs_kind(p) == PLAT_FS_FILE; }

// The newest last-write time (Windows FILETIME units) of the files under dir, and their count.
typedef struct { uint64_t newest; int files; char dir[CAP]; } Walk;
static int walk_cb(const char *name, int kind, uint64_t size, void *ctx);
static void walk(Walk *w, const char *dir) {
    char saved[CAP];
    snprintf(saved, sizeof saved, "%s", w->dir);
    snprintf(w->dir, sizeof w->dir, "%s", dir);
    plat_fs_list(dir, walk_cb, w);
    snprintf(w->dir, sizeof w->dir, "%s", saved);
}
static int walk_cb(const char *name, int kind, uint64_t size, void *ctx) {
    (void)size;
    Walk *w = ctx;
    char p[CAP];
    snprintf(p, sizeof p, "%s/%s", w->dir, name);
    if (kind == PLAT_FS_DIR) walk(w, p);
    else if (kind == PLAT_FS_FILE) {
        PlatFile *f = plat_fs_open(p, 0, NULL);
        PlatFileId id;
        if (f && plat_file_id(f, &id) && id.write_time > w->newest) w->newest = id.write_time;
        if (f) plat_file_close(f);
        w->files++;
    }
    return 1;
}

static uint64_t rd64(const uint8_t *p) {
    uint64_t v;
    memcpy(&v, p, 8);
    return v;
}

// The game's account save in the Ryujinx data folder root: into out, 0 on success. With several users' saves the
// newest is taken and the others are named.
static int ryujinx_find(const char *root, char *out, size_t cap) {
    char p[CAP];
    snprintf(p, sizeof p, "%s/" INDEX, root);
    uint64_t n = 0;
    uint8_t *b = plat_file_read(p, &n);
    if (!b || n < 12 || memcmp(b, "IMKV", 4)) {
        say("%s is not a Ryujinx save index", p);
        free(b);
        return -1;
    }
    uint32_t count;
    memcpy(&count, b + 8, 4);
    int found = 0;
    uint64_t best_time = 0;
    size_t at = 12;
    for (uint32_t i = 0; i < count && at + 12 <= n; i++) {
        uint32_t ks, vs;
        memcpy(&ks, b + at + 4, 4);
        memcpy(&vs, b + at + 8, 4);
        if (memcmp(b + at, "IMEN", 4) || ks < 0x21 || vs < 8 || at + 12 + ks + vs > n) break;
        const uint8_t *key = b + at + 12, *val = key + ks;
        at += 12 + (size_t)ks + vs;
        if (rd64(key) != fs_title.program_id || key[0x20] != SAVE_TYPE_ACCOUNT) continue;
        char dir[CAP];
        snprintf(dir, sizeof dir, "%s/bis/user/save/%016llx/0", root, (unsigned long long)rd64(val));
        Walk w = {0};
        if (is_dir(dir)) walk(&w, dir);
        // the user id as Ryujinx shows it (Profiles.json): LibHac's Id128 is High then Low
        say("Ryujinx save for user %016llx%016llx: %s (%d files)", (unsigned long long)rd64(key + 8),
            (unsigned long long)rd64(key + 16), dir, w.files);
        if (!w.files) continue;
        if (found) say("  several users have a save: the one written last is taken; name a folder to choose another");
        if (!found++ || w.newest > best_time) {
            best_time = w.newest;
            snprintf(out, cap, "%s", dir);
        }
    }
    free(b);
    if (!found) say("Ryujinx at %s has no save of this game (title %016llX)", root, (unsigned long long)fs_title.program_id);
    return found ? 0 : -1;
}

// The folder of save files arg names (the table at the top); 0 on success.
static int source_dir(const char *arg, char *out, size_t cap) {
    char root[CAP], p[CAP];
    if (!arg || !*arg || !strcmp(arg, "ryujinx")) {
        char appdata[CAP];
        if (!plat_getenv("APPDATA", appdata, sizeof appdata)) {
            say("APPDATA is not set: name the Ryujinx folder instead");
            return -1;
        }
        snprintf(root, sizeof root, "%s/Ryujinx", appdata);
        snprintf(p, sizeof p, "%s/" INDEX, root);
        if (!is_file(p)) {
            say("no Ryujinx data in %s (a portable Ryujinx: name its \"portable\" folder)", root);
            return -1;
        }
        return ryujinx_find(root, out, cap);
    }
    snprintf(p, sizeof p, "%s/" INDEX, arg);
    if (is_file(p)) return ryujinx_find(arg, out, cap);
    if (!is_dir(arg)) {
        say("%s is not a folder", arg);
        return -1;
    }
    char zero[CAP], one[CAP], extra[CAP];
    snprintf(zero, sizeof zero, "%s/0", arg);
    snprintf(one, sizeof one, "%s/1", arg);
    snprintf(extra, sizeof extra, "%s/ExtraData0", arg);
    if (is_dir(zero) && (is_dir(one) || is_file(extra))) {   // Ryujinx's bis/user/save/<id>: its committed copy
        snprintf(out, cap, "%s", zero);
        return 0;
    }
    snprintf(out, cap, "%s", arg);
    return 0;
}

int save_import_main(const char *arg) {
    char src[CAP];
    if (source_dir(arg, src, sizeof src)) {
        say("nothing was changed");
        return 1;
    }
    Walk w = {0};
    walk(&w, src);
    say("importing %s (%d files)", src, w.files);
    FsImport r;
    if (fs_save_import(src, &r)) {
        say("import failed: %s", r.why);
        if (!r.stuck) say("nothing was changed");
        return 1;
    }
    say("done: %d files, %.1f MiB. The game loads them at its next start.", r.files, r.bytes / 1048576.0);
    if (*r.backup) say("your previous save is kept in %s", r.backup);
    return 0;
}
