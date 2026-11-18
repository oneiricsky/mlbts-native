// fastball: Xbox and PlayStation button icons in the game's prompts (prompts.c). No Vulkan here: vk_texture.c
// records the copies.
#pragma once
#include <stddef.h>
#include <stdint.h>

// A run of BC7 blocks along one row of the icon texture: first block at (bx, by) in blocks, n blocks of 16 bytes.
typedef struct { uint16_t bx, by, n; const uint8_t *blocks; } MlbPromptRun;

// 1 when a texture's shape is a target's (BC7 sRGB, one level, the menu atlas's 1024x1024 or a HUD button's
// 128x128): worth a look at its bytes.
int mlb_prompts_shape(int nvn_format, uint32_t width, uint32_t height, uint32_t levels);
// The target (1 + its index in prompt_icons.h) whose button icons the storage (block-linear, as the game wrote it)
// holds, 0 none. Logs the first other textures of the atlas's shape it is asked about.
int mlb_prompts_is_icons(uint64_t addr, const void *storage, size_t size, uint32_t width);
// The icon set the prompts should show now: -1 the game's own (Switch), else a set index for mlb_prompts_runs.
int mlb_prompts_set(void);
// The runs of a set over one target (index), and the number of blocks in them.
int mlb_prompts_runs(int set, int target, const MlbPromptRun **runs, int *blocks);

// hid.c: the kind of controller in use, for MLB_PROMPTS=auto: 0 none or other (the game's own icons), 1 Xbox,
// 2 PlayStation.
int hid_prompt_kind(void);
// hid.c: 1 when the face buttons map by position now (MLB_PAD_MAP=position, or auto during play), 0 by label.
int hid_face_position(void);
// hid.c: a line of the game's log (services.c lm); the screens it enters switch MLB_PAD_MAP=auto.
void hid_game_log(const char *text, int n);
