// mlbts-native: PS5 textures in place of the Switch ones (hdtex.c). No Vulkan here: vk_texture.c makes the images.
#pragma once
#include <stddef.h>
#include <stdint.h>

typedef struct MlbHdEntry MlbHdEntry;

// An index was found (MLB_HD_TEXTURES, tools/make_hd_index.py): looked for once.
int mlb_hd_on(void);
// 1 when a texture of this Switch shape is in the index: worth hashing its storage.
int mlb_hd_shape(uint32_t width, uint32_t height, uint32_t levels);
// The entry whose Switch texture the storage is (a hash of its first 16 KiB, as the game wrote it), NULL none.
const MlbHdEntry *mlb_hd_find(const void *storage, size_t storage_size, uint32_t width, uint32_t height, uint32_t levels);
uint64_t mlb_hd_hash(const MlbHdEntry *e);
const char *mlb_hd_name(const MlbHdEntry *e);

// A PS5 texture read and rearranged into plain block rows, one level after another (16-byte aligned).
typedef struct {
    uint32_t width, height, levels, bpb;   // top level of the image; bytes per 4x4 block: 8 (BC1) or 16 (BC7)
    uint32_t lw[16], lh[16];               // blocks across and down each level
    size_t off[16];
    uint8_t *data;
    size_t size;
} MlbHdTex;
int mlb_hd_load(const MlbHdEntry *e, MlbHdTex *out);   // 0 on failure (logged)
void mlb_hd_free(MlbHdTex *t);
