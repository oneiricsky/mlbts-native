// fastball: the game's cache storage exists, so what the game keeps there survives a restart (MLB_CACHE_STORAGE, on
// by default). Issue 19: custom batting cameras were back to their defaults on every start.
//
// What the game does [C, 1.0.15 addresses; read 2026-11-20]: at start f_7000570280 mounts cache storage 0 as
// "FS_GameData" (nn::fs::MountCacheStorage, the result unused) and then creates FS_GameData:/FS_Debug and commits.
// The game keeps files there through its file layer (location 3 in f_7000570c50):
//   CUSTOMCAMS_<n>.CAM         custom batting cameras (looked up by f_7000d197fc when a mode starts, written by
//                              f_7000d199bc)
//   AUDIOUNLOCKABLES_<id>.DAT  the Settings menu's Audio Unlockables
//   PXP_SAVE.BIN, PA_SAVE.BIN  read back through "ReloadSaveData" (f_7001029cd8, f_70003eea50)
//   INV_<account id>           a copy of the player's inventory, read when the inventory loads
//   TEXTURE_CACHE.XML, LG.DAT, UI_DOWNLOAD/, FS_Debug/
// It never creates the storage itself and its NACP declares none, so on this port the mount failed (no
// "fs mount FS_GameData" line in mlb.log) and every one of these writes was dropped. This makes <profile>/cache/0
// before the game starts, as the system does for a title that declares cache storage. Off: nothing is created
// (a folder made earlier stays and is still used; delete <profile>/cache/0 to go back).
#include <stdio.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"

// boot.c: before the guest starts.
void cache_storage_apply(void) {
    if (!cfg_bool("MLB_CACHE_STORAGE")) return;
    const char *profile = rt_config()->profile;
    char p[PLAT_PATH_MAX + 32];
    snprintf(p, sizeof p, "%s/cache/0", profile);
    if (plat_fs_kind(p) == PLAT_FS_DIR) return;
    plat_file_mkdir_p(p);
    if (plat_fs_kind(p) == PLAT_FS_DIR)
        rt_log("cache storage: made %s for the game's FS_GameData (custom cameras and more)", p);
    else rt_log("cache storage: could not make %s", p);
}
