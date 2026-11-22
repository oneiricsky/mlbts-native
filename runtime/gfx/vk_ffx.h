// fastball (vk_ffx.c): AMD FSR 3.1 and FSR 4 through AMD's signed Vulkan runtime, the second backend of the temporal
// upscaling vk_dlaa.c runs on MLB's 3D scene (MLB_FSR, MLB_FSR_VERSION, MLB_FSR_SHARPNESS; the settings menu's
// Graphics page). vk_dlaa.c finds the scene, jitters it, makes the camera motion vectors and sizes the work images for
// both backends; this file only loads the runtime and runs it.
#pragma once
#include "vk.h"

#define FFX_LOADER_DLL "amd_fidelityfx_loader_vk.dll"
#define FFX_UPSCALER_DLL "amd_fidelityfx_upscaler_vk.dll"

int vk_ffx_wanted(void);      // MLB_FSR was a mode at start (the scene's size follows it, resolution.c)
// vk_device.c, after vk_dlaa_init: loads the runtime from mlb.exe's folder and asks it which FSR versions this GPU
// has. Not when DLSS came up: DLSS takes the scene then.
void vk_ffx_init(void);
int vk_ffx_available(void);   // an FSR 3.1 or FSR 4 provider is there
int vk_ffx_ml_wanted(void);   // FSR 4 will be used for the next context made (MLB_FSR_VERSION=4 and the GPU has it)
const char *vk_ffx_status(void);   // the menu's note: NULL when MLB_FSR was off at start
// The settings menu: why FSR cannot run on this PC (AMD's two DLLs missing), NULL when it can; whether this run's GPU
// has FSR 4 (1, 0; -1 not known: AMD's runtime was not started, MLB_FSR off at start).
const char *vk_ffx_missing(void);
int vk_ffx_has4(void);
void vk_ffx_ran(void);       // vk_dlaa.c, after each FSR frame (the status's "active")

// One upscaling of the scene. Every image is in VK_IMAGE_LAYOUT_GENERAL, as every image of the back end; the inputs
// are moved to shader-read for FSR (AMD's Vulkan integration guide) and back. jx, jy: the jitter the scene was drawn
// with, in render pixels (window x right, y down); the motion vectors are render pixels, without the jitter, pointing
// from this frame's position to last frame's (DLSS's convention, which FSR shares).
// reactive: FSR's reactive mask (R32F at the render size, vk_dlaa.c mask_pass), VK_NULL_HANDLE for none.
typedef struct {
    VkImage color, depth, mv, out, reactive;
    VkFormat color_fmt, depth_fmt;      // the scene's light target and depth formats; mv RG16F, out RGBA16F
    uint32_t color_level, color_layer, depth_level, depth_layer;
    uint32_t w, h, ow, oh;              // render size, output size
    float jx, jy, dt_ms, near_z, far_z, fov_y;
    int reset;
} VkFfxFrame;
// Records FSR into cb (the recorder drained first: AMD's runtime records into it itself), making the context in *ctx
// for this size when there is none (FSR 4 where wanted, FSR 3.1 when FSR 4 fails). 0: not run (the caller falls back).
int vk_ffx_dispatch(VkCommandBuffer cb, void **ctx, const VkFfxFrame *f);
void vk_ffx_destroy(void *ctx);       // the GPU must be done with its last dispatch
int vk_ffx_ctx_ml(const void *ctx);   // 1: the context is FSR 4
