// NVIDIA DLSS and DLAA on MLB's 3D scene (MLB_DLSS: off, dlaa, quality, balanced, performance, ultra_performance; the
// settings menu's Graphics page). NGX is loaded at run time from the driver's NGX core (_nvngx.dll, found through
// HKLM\SOFTWARE\NVIDIA Corporation\Global\NGXCore), and NGX loads the DLSS model library nvngx_dlss.dll from the folder
// of mlb.exe. No NVIDIA SDK code or header is compiled in: the few NGX types used are declared here from the SDK's
// documented ABI.
//
// The NGX half (core loading, extensions, the parameter object's vtable, init, the DLSS feature and its evaluation, the
// work images, jitter sequence and presets) is TotK Recomp's runtime/vk_dlaa.c @ ae30a61 (MIT, LICENSE.totk-recomp),
// kept close to the original. Where it runs in the frame, the camera and the motion vectors are MLB's own (fastball),
// described in the section "where DLSS runs in MLB's frame".
//
// The core's parameter object is a C++ class whose virtual functions are called through its vtable: the Set overloads
// in slots 0-7 and the Get overloads in 8-15. MSVC (the Windows core) lays out each group of overloads in reverse
// declaration order. vtable_ok checks the layout with a set-then-get round trip before anything relies on it.
//
// fastball: AMD FSR 3.1 and FSR 4 (MLB_FSR, vk_ffx.c) are a second backend of the same machinery. When DLSS did not
// come up and AMD's runtime did, everything below (the scene found at its pass, the jitter, the camera, the motion
// vectors, the work images per size, the texture LOD bias) runs as for DLSS, and the one evaluation is FSR's
// (fsr_eval) instead of NGX's. DLSS wins when both are set; the settings menu sets only one. FSR alone also gets a
// reactive mask (mask_pass): it cannot tell on its own where the camera-only motion vectors are wrong, as DLSS can.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#include "cfg.h"
#include "gfx.h"
#include "host.h"
#include "nvn_api.h"
#include "platform/platform.h"
#include "vk.h"
#include "vk_dlaa.h"
#include "vk_exec.h"
#include "vk_ffx.h"
#include "vk_rec.h"
#include "dlss_mv_spv.h"
#include "fsr_mask_spv.h"

typedef int NgxResult;   // NVSDK_NGX_Result: 1 success, 0xBAD00000 | n failures
#define NGX_OK(r) (((unsigned)(r) & 0xFFF00000u) != 0xBAD00000u)
#define NGX_VERSION_API 0x15
#define NGX_FEATURE_SUPERSAMPLING 1
#define NGX_PERFQ_DLAA 5   // NVSDK_NGX_PerfQuality_Value: 0 performance, 1 balanced, 2 quality, 3 ultra performance
typedef struct NgxParam NgxParam;
typedef struct NgxHandle NgxHandle;
typedef struct { void *slot[17]; } NgxParamVtbl;
struct NgxParam { const NgxParamVtbl *vt; };
typedef struct {   // NVSDK_NGX_ImageViewInfo_VK
    VkImageView view;
    VkImage image;
    VkImageSubresourceRange range;
    VkFormat format;
    unsigned width, height;
} NgxImageView;
typedef struct {   // NVSDK_NGX_Resource_VK
    union { NgxImageView img; struct { VkBuffer buffer; unsigned bytes; } buf; } r;
    int type;      // 0 image view, 1 buffer
    _Bool rw;
} NgxResourceVK;

typedef NgxResult (*PFN_Init)(unsigned long long app, const wchar_t *path, VkInstance, VkPhysicalDevice, VkDevice,
                              PFN_vkGetInstanceProcAddr, PFN_vkGetDeviceProcAddr, int version, const void *info);
typedef NgxResult (*PFN_ReqExt)(unsigned *ni, const char ***ie, unsigned *nd, const char ***de);
typedef NgxResult (*PFN_Params)(NgxParam **);
typedef NgxResult (*PFN_DestroyParams)(NgxParam *);
typedef NgxResult (*PFN_Create)(VkCommandBuffer, int feature, NgxParam *, NgxHandle **);
typedef NgxResult (*PFN_Evaluate)(VkCommandBuffer, const NgxHandle *, const NgxParam *, void *callback);
typedef NgxResult (*PFN_Release)(NgxHandle *);

static struct {
    void *core;   // the NGX core library (an HMODULE)
    PFN_Init init;
    PFN_ReqExt req_ext;
    PFN_Params caps, alloc_params;
    PFN_DestroyParams destroy_params;
    PFN_Create create;
    PFN_Evaluate evaluate;
    PFN_Release release;
    int tried, loaded, inited, available, driver_old;
} N;

typedef void (*SetI)(NgxParam *, const char *, int);
typedef void (*SetU)(NgxParam *, const char *, unsigned);
typedef void (*SetF)(NgxParam *, const char *, float);
typedef void (*SetP)(NgxParam *, const char *, void *);
typedef NgxResult (*GetI)(const NgxParam *, const char *, int *);
typedef NgxResult (*GetU)(const NgxParam *, const char *, unsigned *);
typedef NgxResult (*GetF)(const NgxParam *, const char *, float *);
typedef NgxResult (*GetP)(const NgxParam *, const char *, void **);
// The SDK declares Set(u64), Set(float), Set(double), Set(u32), Set(int), Set(ID3D11Resource *), Set(ID3D12Resource *),
// Set(void *), then the Get overloads in the same order, then Reset; MSVC reverses each group.
enum { S_P = 0, S_D12, S_D11, S_I, S_U32, S_D, S_F, S_U64, G_P, G_D12, G_D11, G_I, G_U32, G_D, G_F, G_U64 };
static void p_seti(NgxParam *p, const char *n, int v) { ((SetI)p->vt->slot[S_I])(p, n, v); }
static void p_setu(NgxParam *p, const char *n, unsigned v) { ((SetU)p->vt->slot[S_U32])(p, n, v); }
static void p_setf(NgxParam *p, const char *n, float v) { ((SetF)p->vt->slot[S_F])(p, n, v); }
static void p_setp(NgxParam *p, const char *n, void *v) { ((SetP)p->vt->slot[S_P])(p, n, v); }
static int p_geti(const NgxParam *p, const char *n, int *v) { return NGX_OK(((GetI)p->vt->slot[G_I])(p, n, v)); }
static int p_getu(const NgxParam *p, const char *n, unsigned *v) { return NGX_OK(((GetU)p->vt->slot[G_U32])(p, n, v)); }
static int p_getf(const NgxParam *p, const char *n, float *v) { return NGX_OK(((GetF)p->vt->slot[G_F])(p, n, v)); }
static int p_getp(const NgxParam *p, const char *n, void **v) { return NGX_OK(((GetP)p->vt->slot[G_P])(p, n, v)); }

// NGX is brought up only when MLB_DLSS is on at start: its device extensions can only be asked for at device creation,
// the scene's size is set before the game starts (resolution.c), and loading the driver's NGX core on every NVIDIA
// machine would cost start time and change the device with DLSS off. So the setting applies after a restart; switched
// off, nothing else of DLSS runs.
int vk_dlaa_wanted(void) {
    static int wanted = -1;
    if (wanted < 0) wanted = strcmp(cfg_value("DLSS"), "off") != 0;
    return wanted;
}

static int core_load(void) {
    if (N.tried) return N.loaded;
    N.tried = 1;
    char path[PLAT_PATH_MAX];
    if (!plat_ngx_core_path(path, sizeof path)) {
        rt_log("dlss: the driver has no NGX core (registry NGXCore missing; not an NVIDIA driver?): DLSS off");
        return 0;
    }
    N.core = plat_lib_open(path);
    if (!N.core) {
        char why[256];
        plat_lib_error(why, sizeof why);
        rt_log("dlss: cannot load %s (%s; not an NVIDIA driver, or one without NGX): DLSS off", path, why);
        return 0;
    }
#define FN(f, name) N.f = plat_lib_sym(N.core, name)
    FN(init, "NVSDK_NGX_VULKAN_Init_Ext2");
    FN(req_ext, "NVSDK_NGX_VULKAN_RequiredExtensions");
    FN(caps, "NVSDK_NGX_VULKAN_GetCapabilityParameters");
    FN(alloc_params, "NVSDK_NGX_VULKAN_AllocateParameters");
    FN(destroy_params, "NVSDK_NGX_VULKAN_DestroyParameters");
    FN(create, "NVSDK_NGX_VULKAN_CreateFeature");
    FN(evaluate, "NVSDK_NGX_VULKAN_EvaluateFeature");
    FN(release, "NVSDK_NGX_VULKAN_ReleaseFeature");
#undef FN
    if (!N.init || !N.req_ext || !N.caps || !N.alloc_params || !N.create || !N.evaluate || !N.release) {
        rt_log("dlss: the NGX core %s lacks Vulkan entry points: DLSS off", path);
        return 0;
    }
    N.loaded = 1;
    rt_log("dlss: NGX core %s", path);
    return 1;
}

static int listed(const char *const *list, uint32_t n, const char *s) {
    for (uint32_t i = 0; i < n; i++)
        if (!strcmp(list[i], s)) return 1;
    return 0;
}

void vk_dlaa_instance_exts(const char **ext, uint32_t *n, uint32_t max) {
    unsigned ni = 0, nd = 0;
    const char **ie = NULL, **de = NULL;
    if (!vk_dlaa_wanted() || !core_load() || !NGX_OK(N.req_ext(&ni, &ie, &nd, &de))) return;
    for (unsigned i = 0; i < ni; i++)
        if (!listed(ext, *n, ie[i]) && *n < max) ext[(*n)++] = ie[i];
}

void vk_dlaa_device_exts(const VkExtensionProperties *have, uint32_t nhave, const char **ext, uint32_t *n,
                         uint32_t max) {
    unsigned ni = 0, nd = 0;
    const char **ie = NULL, **de = NULL;
    if (!vk_dlaa_wanted() || !core_load() || !NGX_OK(N.req_ext(&ni, &ie, &nd, &de))) return;
    for (unsigned i = 0; i < nd; i++) {
        int ok = 0;
        for (uint32_t k = 0; k < nhave && !ok; k++) ok = !strcmp(have[k].extensionName, de[i]);
        if (!ok) rt_log("dlss: the device lacks %s, which NGX asks for", de[i]);
        else if (!listed(ext, *n, de[i]) && *n < max) ext[(*n)++] = de[i];
    }
}

static int vtable_ok(void) {
    NgxParam *p = NULL;
    if (!NGX_OK(N.alloc_params(&p)) || !p) return 0;
    int i = 0;
    unsigned u = 0;
    float f = 0;
    void *v = NULL;
    p_seti(p, "MLB.Test.I", -12345);
    p_setu(p, "MLB.Test.U", 4000000000u);
    p_setf(p, "MLB.Test.F", 1.25f);
    p_setp(p, "MLB.Test.P", (void *)p);
    int ok = p_geti(p, "MLB.Test.I", &i) && i == -12345 && p_getu(p, "MLB.Test.U", &u) && u == 4000000000u &&
             p_getf(p, "MLB.Test.F", &f) && f == 1.25f && p_getp(p, "MLB.Test.P", &v) && v == (void *)p;
    if (N.destroy_params) N.destroy_params(p);
    if (!ok) rt_log("dlss: NGX parameter layout check failed (i=%d u=%u f=%g p=%p): DLSS off", i, u, f, v);
    return ok;
}

void vk_dlaa_init(void) {
    if (!vk_dlaa_wanted() || !core_load()) return;
    // The executable's folder, where NGX looks for the DLSS model library and writes its logs.
    wchar_t wdir[PLAT_PATH_MAX];
    if (!plat_exe_dir_wide(wdir, PLAT_PATH_MAX)) {
        rt_log("dlss: cannot name the executable's folder for NGX: DLSS off");
        return;
    }
    // 231313132: the application id NVIDIA's DLSS samples use for builds without an NVIDIA-issued id
    const VkCtx *c = vk_ctx();
    NgxResult r = N.init(231313132ull, wdir, c->instance, c->phys, c->device, vkGetInstanceProcAddr,
                         vkGetDeviceProcAddr, NGX_VERSION_API, NULL);
    if (!NGX_OK(r)) {
        rt_log("dlss: NGX init failed (%08x): DLSS off", (unsigned)r);
        return;
    }
    N.inited = 1;
    if (!vtable_ok()) return;
    NgxParam *caps = NULL;
    int avail = 0, driver = 0;
    if (NGX_OK(N.caps(&caps)) && caps) {
        p_geti(caps, "SuperSampling.Available", &avail);
        p_geti(caps, "SuperSampling.NeedsUpdatedDriver", &driver);
    }
    N.available = avail != 0, N.driver_old = driver != 0;
    rt_log("dlss: NGX up; DLSS %s%s", avail ? "available" : "NOT available (is nvngx_dlss.dll next to mlb.exe?)",
           driver ? "; the driver needs an update" : "");
}

int vk_dlaa_available(void) { return vk_dlaa_wanted() && N.available; }

// fastball: why DLSS cannot run on this PC, whatever MLB_DLSS says (the settings menu greys its rows): NULL when it can
// (an NVIDIA RTX card, the driver's NGX core, nvngx_dlss.dll next to mlb.exe). Looked at once.
const char *vk_dlaa_missing(void) {
    static const char *why = "";
    if (why && !*why) {
        const VkCtx *c = vk_ctx();
        if (!c || !c->device) return "The graphics device is not up yet";   // (not kept: looked at again)
        char core[PLAT_PATH_MAX], exe[PLAT_PATH_MAX], dll[PLAT_PATH_MAX + 32];
        const char *sep = plat_exe_path(exe, sizeof exe) ? plat_last_sep(exe) : NULL;
        if (sep) snprintf(dll, sizeof dll, "%.*s/nvngx_dlss.dll", (int)(sep - exe), exe);
        if (!c || c->props.vendorID != 0x10de || !strstr(c->props.deviceName, "RTX"))
            why = "Needs an NVIDIA GeForce RTX graphics card";
        else if (!plat_ngx_core_path(core, sizeof core)) why = "Needs a newer NVIDIA driver (no NGX)";
        else if (!sep || !plat_file_exists(dll)) why = "nvngx_dlss.dll is missing (run the setup again)";
        else why = NULL;
    }
    return why;
}

// ---------------------------------------------------------------- where DLSS runs in MLB's frame (fastball)
// Measured in the drawlogs and RenderDoc captures of 2026-11-10/11 (play, menus, RTTS, celebrations): MLB is a forward
// renderer. Its 3D scene is drawn in one pass into a B10G11R11 float colour target (0x154ea0000, linear HDR before the
// game's exposure) with a D24S8 depth target (0x155878000, D32_SFLOAT_S8_UINT here), both at the scene size (1440x810
// on the TV); the pass is interrupted once for a 120x68 exposure pass and resumes with the same pair. Before it come the
// shadow maps (depth only) and a 1280x720 RGBA16F pass with a D32F depth (the stadium's video boards); after it the HUD
// is drawn into a separate 1920x1080 layer with a depth target of its own, and one full-screen draw (vk_exec_draw.c
// aa_composite: fragment shaders daf10a59, 1d3e4d6b) tone-maps the scene, scales it to 1080p and lays the HUD over it.
//
// So: a pass with one B10G11R11 colour target and a depth-stencil target of the same size arms the frame with that
// pair (vk_dlaa_pass). At the composite draw (vk_dlaa_scene, called by vk_exec_draw.c aa_before_draw, where FXAA and
// FSR also run) DLSS reads the armed scene and its depth and writes its picture at the composite's size (or the scene's,
// when that is larger: DLAA), and the composite samples that picture in the scene's place. The HUD is never jittered
// nor passed through DLSS.
//
// A frame starts when the next scene pass begins after DLSS ran (or two presents after an armed frame that never reached
// the composite), not at the present: the replay can begin the next frame's work before this frame's present is handled.
//
// The camera: every scene vertex shader writes gl_Position = c3[0] * x + c3[1] * y + c3[2] * z + c3[3] * w (RenderDoc,
// capture of frame 18520, event 4746), so the first 64 bytes of the vertex stage's constant bank c3 are the camera's
// view-projection, column-major. In a frame of play 173 of the scene's 174 depth-tested draws bind the same c3 block
// (the other is a sky-like draw of its own), so the block most draws bind is the camera. Clip depth is 0..w (NVN depth
// mode near-is-zero) unless the game set -w..w.
static struct {
    VkExecTarget color, depth;   // the armed pair, valid in the frame it was armed
    int armed, done;             // this frame: armed on the scene, DLSS ran (or tried to)
    uint64_t arm_frame;          // gfx_counters.frames when it was armed
    VkImageView out_now;         // this frame's DLSS output: a second composite draw reads it too
    struct Size {                // a DLSS feature and its work images per scene and output size
        uint32_t w, h, ow, oh;   // render size, output size
        VkImage out, mv;
        VmaAllocation out_mem, mv_mem;
        VkImageView out_view, mv_view;
        // fastball: the view of out the composite samples, alpha read as 1 (size_for says why)
        VkImageView out_tex;
        NgxHandle *feat;
        void *ffx;               // fastball: the FSR context of this size (vk_ffx.c), with FSR
        // fastball, FSR only (mask_pass, made at its first FSR frame): the scene depth as clip w, this frame's into
        // zh[zi] and last frame's in zh[zi ^ 1] (valid when zvalid), and FSR's reactive mask; all R32F at the scene size
        VkImage zh[2], mask;
        VmaAllocation zh_mem[2], mask_mem;
        VkImageView zh_view[2], mask_view;
        int zi, zvalid;
        uint64_t used;           // evals count when it last ran
    } sizes[3], *last;           // last: the one the previous DLSS frame ran with
    VkImage last_color;          // the target DLSS ran on last frame: another one means a new history
    NgxParam *params;
    int failed, reset;
    uint64_t evals, frames_missed, mv_frames, mv_none, cuts;
    uint64_t why[3];             // history resets: size changed, no camera, scene target changed
    // jitter (vk_dlaa_viewport)
    VkImage jdepth;              // the scene depth of the last frame DLSS ran on: passes drawing with it are jittered
    float jx, jy;                // the offset the next scene draws take, render pixels (window x right, y down)
    float ux, uy;                // the offset this frame's scene draws took (DLSS and the motion vectors get these)
    uint32_t jframe;
    int jit_ok, jit_used, hold;  // jitter allowed this frame / a draw used it / frames left without it
    uint64_t holds;
    // camera (vk_dlaa_draw): the vertex c3 blocks this frame's scene draws bound, with their first 64 bytes
    struct Cam { uint64_t addr; uint32_t n; float vp[16]; } cams[8];
    int ncams;
    double prev_vp[16];          // last frame's view-projection, row-major
    int prev_ok;
    // motion vectors (mv_pass)
    VkDescriptorSetLayout mv_dsl;
    VkPipelineLayout mv_layout;
    VkPipeline mv_pipe;
    VkSampler mv_samp;
    int mv_ok;                   // -1 not built, 0 failed, 1 ready
    float mv_m[16];              // the matrix this frame's motion pass used (GLSL order), when mv_m_ok
    int mv_m_ok;
    // FSR's reactive mask (mask_pass, fastball)
    VkDescriptorSetLayout mask_dsl;
    VkPipelineLayout mask_layout;
    VkPipeline mask_pipe;
    int mask_ok;                 // -1 not built, 0 failed, 1 ready
    float pjx, pjy;              // the jitter of the frame the mask pass last ran on
    int preset, preset_dirty;   // the DLSS model features are created with (preset_value); a change pending
    unsigned cfg_seen;           // cfg_version when preset was read
    uint64_t last_eval_ns;       // plat_now_ns of the previous evaluation (FrameTimeDeltaInMsec)
    float bias;                  // the texture LOD bias in effect (vk_sampler_dlss_bias)
} D = {.mv_ok = -1, .mask_ok = -1, .cfg_seen = ~0u};

const VkTexImage *vk_dlaa_swap_img;
VkImageView vk_dlaa_swap_view;

// fastball: FSR is the backend when DLSS is not there and AMD's runtime is (vk_ffx_init runs only without DLSS)
static int use_fsr(void) { return !N.available && vk_ffx_available(); }
static const char *tag(void) { return use_fsr() ? "fsr" : "dlss"; }
static int dl_active(void) { return (N.available || vk_ffx_available()) && !D.failed; }

static void dl_fail(const char *what, NgxResult r) {
    rt_log("%s: %s failed (%08x): %s off for this run (the game's own scaling, or FSR 1, takes over)", tag(), what,
           (unsigned)r, use_fsr() ? "FSR" : "DLSS");
    D.failed = 1;
}

const char *vk_dlaa_status(void) {
    if (!vk_dlaa_wanted()) return NULL;
    if (!N.tried) return "starting";
    if (!N.loaded) return "needs an NVIDIA RTX graphics card and driver";
    if (!N.inited) return "NVIDIA's NGX did not start (see mlb.log)";
    if (!N.available)
        return N.driver_old ? "needs a newer NVIDIA driver" : "nvngx_dlss.dll is missing next to mlb.exe";
    if (D.failed) return "stopped after an error (see mlb.log)";
    uint64_t now = plat_now_ns();
    return D.last_eval_ns && now - D.last_eval_ns < 1000000000ull ? "active" : "waiting for a 3D scene";
}

static int image2d(uint32_t w, uint32_t h, VkFormat f, VkImageUsageFlags usage, VkImage *img, VmaAllocation *mem,
                   VkImageView *view) {
    const VkCtx *c = vk_ctx();
    VkImageCreateInfo ii = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D, .format = f,
                            .extent = {w, h, 1}, .mipLevels = 1, .arrayLayers = 1, .samples = VK_SAMPLE_COUNT_1_BIT,
                            .tiling = VK_IMAGE_TILING_OPTIMAL, .usage = usage,
                            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE};
    if (vmaCreateImage(c->vma, &ii, &ai, img, mem, NULL) != VK_SUCCESS) return *img = VK_NULL_HANDLE, 0;
    VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = *img,
                                .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = f,
                                .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    return vkCreateImageView(c->device, &vi, NULL, view) == VK_SUCCESS;
}

static void free_size(struct Size *e) {
    const VkCtx *c = vk_ctx();
    rec_wait_submits();   // fastball: parts handed to the recorder are in the queue first (vk_rec.h rec_submit_part)
    vkDeviceWaitIdle(c->device);   // a fourth size (rare): the evicted images may still be in flight
    if (e->out_view) vkDestroyImageView(c->device, e->out_view, NULL);
    if (e->out_tex) vkDestroyImageView(c->device, e->out_tex, NULL);
    if (e->mv_view) vkDestroyImageView(c->device, e->mv_view, NULL);
    if (e->out) vmaDestroyImage(c->vma, e->out, e->out_mem);
    if (e->mv) vmaDestroyImage(c->vma, e->mv, e->mv_mem);
    for (int i = 0; i < 2; i++) {
        if (e->zh_view[i]) vkDestroyImageView(c->device, e->zh_view[i], NULL);
        if (e->zh[i]) vmaDestroyImage(c->vma, e->zh[i], e->zh_mem[i]);
    }
    if (e->mask_view) vkDestroyImageView(c->device, e->mask_view, NULL);
    if (e->mask) vmaDestroyImage(c->vma, e->mask, e->mask_mem);
    if (e->feat) N.release(e->feat);
    if (e->ffx) vk_ffx_destroy(e->ffx);
    memset(e, 0, sizeof *e);
}

// New images (up to 4) from UNDEFINED to GENERAL, where the back end keeps every image.
static void to_general(VkCommandBuffer cb, const VkImage *im, uint32_t n) {
    VkImageMemoryBarrier2 ib[4];
    for (uint32_t i = 0; i < n; i++)
        ib[i] = (VkImageMemoryBarrier2){.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
                                        .srcStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                                        .dstStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                                        .dstAccessMask = VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT,
                                        .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED, .newLayout = VK_IMAGE_LAYOUT_GENERAL,
                                        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                                        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .image = im[i],
                                        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    VkDependencyInfo di = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .imageMemoryBarrierCount = n,
                           .pImageMemoryBarriers = ib};
    vkCmdPipelineBarrier2(cb, &di);
}

// The entry for a scene and output size: its output (RGBA16F at the output size, written by DLSS and sampled by the
// composite) and motion vectors (RG16F at the scene size, render pixels), both kept in GENERAL like every image of the
// back end. The least recently used entry goes for a new size.
static struct Size *size_for(VkCommandBuffer cb, uint32_t w, uint32_t h, uint32_t ow, uint32_t oh) {
    enum { NS = sizeof D.sizes / sizeof D.sizes[0] };
    struct Size *e = NULL, *lru = &D.sizes[0];
    for (int i = 0; i < NS; i++) {
        if (D.sizes[i].w == w && D.sizes[i].h == h && D.sizes[i].ow == ow && D.sizes[i].oh == oh) return &D.sizes[i];
        if (!D.sizes[i].out && !e) e = &D.sizes[i];
        if (D.sizes[i].used < lru->used) lru = &D.sizes[i];
    }
    if (!e) {
        if (D.last == lru) D.last = NULL;
        free_size(e = lru);
    }
    VkImageUsageFlags u = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                          VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    if (!image2d(ow, oh, VK_FORMAT_R16G16B16A16_SFLOAT, u, &e->out, &e->out_mem, &e->out_view) ||
        !image2d(w, h, VK_FORMAT_R16G16_SFLOAT, u, &e->mv, &e->mv_mem, &e->mv_view)) {
        free_size(e);
        return NULL;
    }
    // fastball: the composite reads the scene's alpha. Its fragment shader (daf10a59) averages all four channels of
    // the scene over 9 taps and, in shots where the game sets c5[9].z (the close-ups between pitches), blends the
    // scene with something darker by that alpha; it also writes it as the picture's alpha. MLB's scene is B10G11R11,
    // so the game always reads 1 there. The output here is RGBA16F and holds what the upscaler wrote in alpha: 1 from
    // FSR 3.1, but not from FSR 4 (issue #27: between-pitch shots dark with a tile grid on an RX 9070 XT, black on an
    // RX 6650 XT). So the composite samples a view that reads alpha as 1, as the scene does (out_view stays the
    // upscalers' plain storage view; a swizzled view cannot be a storage image).
    {
        const VkCtx *c = vk_ctx();
        VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = e->out,
                                    .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = VK_FORMAT_R16G16B16A16_SFLOAT,
                                    .components = {VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY,
                                                   VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_ONE},
                                    .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
        if (vkCreateImageView(c->device, &vi, NULL, &e->out_tex) != VK_SUCCESS) {
            e->out_tex = VK_NULL_HANDLE;
            free_size(e);
            return NULL;
        }
    }
    VkImage im[2] = {e->out, e->mv};
    to_general(cb, im, 2);
    e->w = w, e->h = h, e->ow = ow, e->oh = oh;
    return e;
}

// fastball: the mask pass's images of e, at its first FSR frame (DLSS never needs them). 0: not made (no mask).
static int mask_images(VkCommandBuffer cb, struct Size *e) {
    VkImageUsageFlags u = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    int ok = 1;
    for (int i = 0; i < 2; i++)
        ok = ok && image2d(e->w, e->h, VK_FORMAT_R32_SFLOAT, u, &e->zh[i], &e->zh_mem[i], &e->zh_view[i]);
    ok = ok && image2d(e->w, e->h, VK_FORMAT_R32_SFLOAT, u, &e->mask, &e->mask_mem, &e->mask_view);
    if (!ok) {
        const VkCtx *c = vk_ctx();
        for (int i = 0; i < 2; i++) {
            if (e->zh_view[i]) vkDestroyImageView(c->device, e->zh_view[i], NULL);
            if (e->zh[i]) vmaDestroyImage(c->vma, e->zh[i], e->zh_mem[i]);
        }
        if (e->mask_view) vkDestroyImageView(c->device, e->mask_view, NULL);
        if (e->mask) vmaDestroyImage(c->vma, e->mask, e->mask_mem);
        memset(e->zh, 0, sizeof e->zh), memset(e->zh_view, 0, sizeof e->zh_view);
        e->mask = VK_NULL_HANDLE, e->mask_view = VK_NULL_HANDLE;
        return 0;
    }
    VkImage im[3] = {e->zh[0], e->zh[1], e->mask};
    to_general(cb, im, 3);
    e->zi = 0, e->zvalid = 0;
    return 1;
}

static void full_barrier(VkCommandBuffer cb) {
    VkMemoryBarrier2 mb = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER_2,
                           .srcStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                           .srcAccessMask = VK_ACCESS_2_MEMORY_WRITE_BIT,
                           .dstStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                           .dstAccessMask = VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT};
    VkDependencyInfo di = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .memoryBarrierCount = 1, .pMemoryBarriers = &mb};
    vkCmdPipelineBarrier2(cb, &di);
}

static NgxResourceVK res_image(VkImageView v, VkImage img, VkFormat f, uint32_t w, uint32_t h, VkImageAspectFlags a,
                               int rw) {
    NgxResourceVK r;
    memset(&r, 0, sizeof r);
    r.r.img = (NgxImageView){v, img, {a, 0, 1, 0, 1}, f, w, h};
    r.type = 0;
    r.rw = rw;
    return r;
}

// ---------------------------------------------------------------- timing (MLB_DLSS_TIMES=1, test)
// GPU timestamps around the motion pass and DLSS's evaluation, averaged and logged every TIMES_SUMMARY frames. Each
// frame takes its own slot of TIMES_SLOTS; a slot's results are read when it comes round again (by then the GPU is long
// done with it; not ready: that frame is left out). Off (the default) it costs one branch per DLSS frame.
enum { T_MV0, T_MV1, T_DL1, T_N };
#define TIMES_SLOTS 8u
#define TIMES_SUMMARY 600
static struct {
    int on;   // -1 not read
    VkQueryPool pool;
    uint32_t slot;
    int used[TIMES_SLOTS];
    double gpu[2];
    uint64_t frames;
} T = {.on = -1};

static void times_mark(VkCommandBuffer cb, int which) {
    if (T.on < 0) {
        T.on = rt_knob("DLSS_TIMES", "0");
        VkQueryPoolCreateInfo qi = {.sType = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO,
                                    .queryType = VK_QUERY_TYPE_TIMESTAMP, .queryCount = TIMES_SLOTS * T_N};
        if (T.on && vkCreateQueryPool(vk_ctx()->device, &qi, NULL, &T.pool) != VK_SUCCESS) T.on = 0;
    }
    if (!T.on) return;
    if (which == T_MV0) {   // a new frame's slot: the last results of the slot first
        T.slot = (T.slot + 1) % TIMES_SLOTS;
        uint64_t q[T_N];
        if (T.used[T.slot] && vkGetQueryPoolResults(vk_ctx()->device, T.pool, T.slot * T_N, T_N, sizeof q, q,
                                                    sizeof q[0], VK_QUERY_RESULT_64_BIT) == VK_SUCCESS) {
            double ms = vk_ctx()->props.limits.timestampPeriod / 1e6;
            T.gpu[0] += (double)(q[T_MV1] - q[T_MV0]) * ms, T.gpu[1] += (double)(q[T_DL1] - q[T_MV1]) * ms;
            if (++T.frames % TIMES_SUMMARY == 0) {
                rt_log("%s times: gpu motion vectors %.3f ms, %s %.3f ms (averages of %d frames)", tag(),
                       T.gpu[0] / TIMES_SUMMARY, use_fsr() ? "FSR" : "DLSS", T.gpu[1] / TIMES_SUMMARY, TIMES_SUMMARY);
                T.gpu[0] = T.gpu[1] = 0;
            }
        }
        T.used[T.slot] = 0;
        vkCmdResetQueryPool(cb, T.pool, T.slot * T_N, T_N);
    }
    vkCmdWriteTimestamp2(cb, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT, T.pool, T.slot * T_N + (uint32_t)which);
    if (which == T_DL1) T.used[T.slot] = 1;
}

// ---------------------------------------------------------------- motion vectors (fastball)
// A compute pipeline whose bindings (b[0] a combined image sampler, the others storage images) are pushed with each
// dispatch, with push bytes of push constants. 0: it could not be made.
static int compute_pipe(const uint32_t *spv, size_t bytes, uint32_t nb, uint32_t push, VkDescriptorSetLayout *dsl,
                        VkPipelineLayout *layout, VkPipeline *pipe) {
    const VkCtx *c = vk_ctx();
    VkDescriptorSetLayoutBinding b[4];
    for (uint32_t i = 0; i < nb; i++)
        b[i] = (VkDescriptorSetLayoutBinding){i, i ? VK_DESCRIPTOR_TYPE_STORAGE_IMAGE
                                                   : VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
                                              1, VK_SHADER_STAGE_COMPUTE_BIT, NULL};
    VkDescriptorSetLayoutCreateInfo dci = {.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
                                           .flags = VK_DESCRIPTOR_SET_LAYOUT_CREATE_PUSH_DESCRIPTOR_BIT_KHR,
                                           .bindingCount = nb, .pBindings = b};
    VkPushConstantRange pr = {VK_SHADER_STAGE_COMPUTE_BIT, 0, push};
    VkShaderModuleCreateInfo mi = {.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .codeSize = bytes,
                                   .pCode = spv};
    VkShaderModule m = VK_NULL_HANDLE;
    if (vkCreateDescriptorSetLayout(c->device, &dci, NULL, dsl) != VK_SUCCESS) return 0;
    VkPipelineLayoutCreateInfo li = {.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, .setLayoutCount = 1,
                                     .pSetLayouts = dsl, .pushConstantRangeCount = 1, .pPushConstantRanges = &pr};
    if (vkCreatePipelineLayout(c->device, &li, NULL, layout) != VK_SUCCESS ||
        vkCreateShaderModule(c->device, &mi, NULL, &m) != VK_SUCCESS)
        return 0;
    VkComputePipelineCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
                                      .stage = {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                                                .stage = VK_SHADER_STAGE_COMPUTE_BIT, .module = m, .pName = "main"},
                                      .layout = *layout};
    VkResult r = vkCreateComputePipelines(c->device, VK_NULL_HANDLE, 1, &ci, NULL, pipe);
    vkDestroyShaderModule(c->device, m, NULL);
    return r == VK_SUCCESS;
}

static int mv_init(void) {
    if (D.mv_ok >= 0) return D.mv_ok;
    D.mv_ok = 0;
    VkSamplerCreateInfo si = {.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO, .magFilter = VK_FILTER_NEAREST,
                              .minFilter = VK_FILTER_NEAREST, .mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST,
                              .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                              .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                              .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE};
    if (!compute_pipe(dlss_mv_spv, sizeof dlss_mv_spv, 2, 88, &D.mv_dsl, &D.mv_layout, &D.mv_pipe) ||
        vkCreateSampler(vk_ctx()->device, &si, NULL, &D.mv_samp) != VK_SUCCESS) {
        rt_log("%s: the motion-vector pass could not be set up: it runs with zero motion", tag());
        return 0;
    }
    return D.mv_ok = 1;
}

// Inverse of a row-major 4x4 in double precision (Gauss-Jordan); 0 when singular. From TotK Recomp's vk_dlaa.c inv4.
static int inv4(const double m[16], double o[16]) {
    double a[4][8];
    for (int r = 0; r < 4; r++)
        for (int k = 0; k < 8; k++) a[r][k] = k < 4 ? m[r * 4 + k] : (k - 4 == r);
    for (int col = 0; col < 4; col++) {
        int piv = col;
        for (int r = col + 1; r < 4; r++)
            if (fabs(a[r][col]) > fabs(a[piv][col])) piv = r;
        if (fabs(a[piv][col]) < 1e-300) return 0;
        for (int k = 0; k < 8; k++) { double t = a[col][k]; a[col][k] = a[piv][k]; a[piv][k] = t; }
        double d = a[col][col];
        for (int k = 0; k < 8; k++) a[col][k] /= d;
        for (int r = 0; r < 4; r++)
            if (r != col) {
                double f = a[r][col];
                for (int k = 0; k < 8; k++) a[r][k] -= f * a[col][k];
            }
    }
    for (int r = 0; r < 4; r++)
        for (int k = 0; k < 4; k++) o[r * 4 + k] = a[r][k + 4];
    return 1;
}

static double len3(const double *v) { return sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); }

// A camera cut between last frame's view-projection p and this frame's c (row-major): the view turned by more than
// about 10 degrees or the field of view changed by more than 10 %. MLB cuts between broadcast cameras all the time
// (pitcher, batter, fielders, replays); reprojected history across a cut is all disocclusion, and DLSS asks for a reset
// there. Row 3 of a view-projection is the view's depth axis (times the projection's -1 or 1), row 1 the view's up axis
// times the vertical focal length, so |row 1| / |row 3| follows the field of view and row 3's direction the view's.
static int camera_cut(const double p[16], const double c[16]) {
    double lp = len3(p + 12), lc = len3(c + 12);
    if (lp < 1e-12 || lc < 1e-12) return 1;
    double cosang = (p[12] * c[12] + p[13] * c[13] + p[14] * c[14]) / (lp * lc);
    double fp = len3(p + 4) / lp, fc = len3(c + 4) / lc;
    return cosang < 0.985 || fc > fp * 1.1 || fc < fp / 1.1;
}

// The camera this frame's scene draws used most (vk_dlaa_draw), row-major into vp. 0: none seen.
static int frame_camera(double vp[16]) {
    const struct Cam *best = NULL;
    for (int i = 0; i < D.ncams; i++)
        if (!best || D.cams[i].n > best->n) best = &D.cams[i];
    if (!best) return 0;
    for (int r = 0; r < 4; r++)
        for (int k = 0; k < 4; k++) vp[r * 4 + k] = best->vp[k * 4 + r];   // the block holds the matrix's columns
    return 1;
}

// The motion vectors into e->mv, recorded through the recorder like the replay's own commands. 0: no history to move
// along (no camera this frame or last, or a camera cut): the caller clears the vectors and DLSS starts a new history.
static int mv_pass(VkExec *ex, struct Size *e, VkImageView zv, float jx, float jy) {
    double cur[16], ci[16], m[16];
    if (!mv_init() || !frame_camera(cur)) {
        D.mv_none++;
        D.prev_ok = 0;
        return 0;
    }
    int had = D.prev_ok, cut = had && camera_cut(D.prev_vp, cur), inv = inv4(cur, ci);
    if (had && !cut && inv)
        for (int r = 0; r < 4; r++)
            for (int k = 0; k < 4; k++) {
                double v = 0;
                for (int j = 0; j < 4; j++) v += D.prev_vp[r * 4 + j] * ci[j * 4 + k];
                m[r * 4 + k] = v;
            }
    memcpy(D.prev_vp, cur, sizeof cur);
    D.prev_ok = 1;
    if (cut) D.cuts++;
    if (!had || cut || !inv) return 0;
    VkCommandBuffer cb = ex->cb;
    uint32_t w = e->w, h = e->h;
    struct { float m[16], size[2], jitter[2], z[2]; } pc;
    for (int r = 0; r < 4; r++)
        for (int k = 0; k < 4; k++) pc.m[k * 4 + r] = (float)m[r * 4 + k];   // GLSL mat4: columns
    memcpy(D.mv_m, pc.m, sizeof D.mv_m), D.mv_m_ok = 1;   // (FSR's mask pass takes the same motion)
    pc.size[0] = (float)w, pc.size[1] = (float)h, pc.jitter[0] = jx, pc.jitter[1] = jy;
    int mw = nvn_depth_minus_w();
    pc.z[0] = mw ? 2.0f : 1.0f, pc.z[1] = mw ? -1.0f : 0.0f;
    VkDescriptorImageInfo zi = {D.mv_samp, zv, VK_IMAGE_LAYOUT_GENERAL};
    VkDescriptorImageInfo oi = {VK_NULL_HANDLE, e->mv_view, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet wr[2] = {
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = 0, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .pImageInfo = &zi},
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = 1, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .pImageInfo = &oi}};
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, D.mv_pipe);
    rec_push(vk_pipeline_push_fn(), cb, VK_PIPELINE_BIND_POINT_COMPUTE, D.mv_layout, 0, 2, wr);
    vkCmdPushConstants(cb, D.mv_layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    vkCmdDispatch(cb, (w + 7) / 8, (h + 7) / 8, 1);
    full_barrier(cb);
    D.mv_frames++;
    return 1;
}

// fastball: FSR's reactive mask for what moves on its own (runtime/shaders/fsr_mask.comp says why FSR needs it and DLSS
// does not) into e->mask, after mv_pass, FSR only. It also keeps the scene depth for the next frame's comparison. 1:
// the mask holds this frame (pass it to FSR); 0: no mask this frame (no camera, a new history, MLB_FSR_MASK=0).
static int mask_pass(VkExec *ex, struct Size *e, VkImageView zv, float jx, float jy) {
    static int on = -1;
    if (on < 0) on = rt_knob("FSR_MASK", "1");   // MLB_FSR_MASK=0: no reactive mask (test, A/B)
    if (!on || D.mv_ok != 1 || !D.prev_ok) return e->zvalid = 0, 0;   // (no camera this frame: no clip w)
    if (D.mask_ok < 0) {
        D.mask_ok = compute_pipe(fsr_mask_spv, sizeof fsr_mask_spv, 4, 108, &D.mask_dsl, &D.mask_layout, &D.mask_pipe);
        if (!D.mask_ok) rt_log("fsr: the reactive mask pass could not be set up: FSR runs without it");
    }
    if (!D.mask_ok || (!e->mask && !mask_images(ex->cb, e))) return 0;
    // this frame's clip w from ndc z: row 2 of a perspective view-projection is a * row 3 + b * (0,0,0,1) (see
    // camera_planes), so ndc z = a + b / w; D.prev_vp holds this frame's camera after mv_pass
    const double *c = D.prev_vp;
    double r33 = c[12] * c[12] + c[13] * c[13] + c[14] * c[14];
    if (r33 < 1e-24) return e->zvalid = 0, 0;
    double a = (c[8] * c[12] + c[9] * c[13] + c[10] * c[14]) / r33, b = c[11] - a * c[15];
    int have = D.mv_m_ok && e->zvalid && e == D.last;   // last frame's depth is this size's and m leads to it
    struct { float m[16], size[2], jitter[2], pjitter[2], z[2], wc[2], have; } pc;
    _Static_assert(sizeof pc == 108, "fsr_mask.comp's push constants");
    memcpy(pc.m, D.mv_m, sizeof pc.m);
    pc.size[0] = (float)e->w, pc.size[1] = (float)e->h, pc.jitter[0] = jx, pc.jitter[1] = jy;
    pc.pjitter[0] = D.pjx, pc.pjitter[1] = D.pjy;
    int mw = nvn_depth_minus_w();
    pc.z[0] = mw ? 2.0f : 1.0f, pc.z[1] = mw ? -1.0f : 0.0f;
    pc.wc[0] = (float)a, pc.wc[1] = (float)b, pc.have = have ? 1.0f : 0.0f;
    VkDescriptorImageInfo ii[4] = {{D.mv_samp, zv, VK_IMAGE_LAYOUT_GENERAL},
                                   {VK_NULL_HANDLE, e->zh_view[e->zi ^ 1], VK_IMAGE_LAYOUT_GENERAL},
                                   {VK_NULL_HANDLE, e->zh_view[e->zi], VK_IMAGE_LAYOUT_GENERAL},
                                   {VK_NULL_HANDLE, e->mask_view, VK_IMAGE_LAYOUT_GENERAL}};
    VkWriteDescriptorSet wr[4];
    for (int i = 0; i < 4; i++)
        wr[i] = (VkWriteDescriptorSet){.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = (uint32_t)i,
                                       .descriptorCount = 1,
                                       .descriptorType = i ? VK_DESCRIPTOR_TYPE_STORAGE_IMAGE
                                                           : VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
                                       .pImageInfo = &ii[i]};
    VkCommandBuffer cb = ex->cb;
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, D.mask_pipe);
    rec_push(vk_pipeline_push_fn(), cb, VK_PIPELINE_BIND_POINT_COMPUTE, D.mask_layout, 0, 4, wr);
    vkCmdPushConstants(cb, D.mask_layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    vkCmdDispatch(cb, (e->w + 7) / 8, (e->h + 7) / 8, 1);
    full_barrier(cb);
    e->zi ^= 1, e->zvalid = 1;
    D.pjx = jx, D.pjy = jy;
    return have;
}

// ---------------------------------------------------------------- jitter
// The scene's draws (every pass drawing with the scene depth, until DLSS ran) have their viewport moved by a sub-pixel
// Halton(2,3) offset, which shifts what they rasterise as a jittered projection would; full-screen passes that shade
// by window position are unaffected. Jitter only follows a frame DLSS ran on: a jittered frame that DLSS does not
// resolve shakes on screen, so a missed DLSS point stops the jitter for a second.
static float halton(uint32_t i, uint32_t b) {
    float f = 1, r = 0;
    for (; i; i /= b) f /= (float)b, r += f * (float)(i % b);
    return r;
}

void vk_dlaa_viewport(VkExec *ex, VkViewport *v) {
    if (!D.jit_ok || D.done || !ex->depth.image || ex->depth.image != D.jdepth) return;
    v->x += D.jx, v->y += D.jy;
    D.ux = D.jx, D.uy = D.jy, D.jit_used = 1;
}

// The sequence is as long as NVIDIA's DLSS guide asks for the upscaling ratio, 8 x (output / scene)^2 phases (18 in
// Quality, 24 in Balanced, 32 in Performance, 72 in Ultra Performance), and 16 at least.
static void next_jitter(uint32_t w, uint32_t ow) {
    static int nj = -1;
    if (nj < 0) nj = !rt_knob("DLSS_JITTER", "1");   // MLB_DLSS_JITTER=0: no jitter (test)
    double r = w ? (double)ow / w : 1.0;
    uint32_t phases = (uint32_t)ceil(8.0 * r * r - 1e-6);
    if (phases < 16) phases = 16;
    if (phases > 72) phases = 72;
    uint32_t i = D.jframe++ % phases + 1;
    D.jx = halton(i, 2) - 0.5f, D.jy = halton(i, 3) - 0.5f;
    D.jit_ok = !D.hold && !nj;
}

// ---------------------------------------------------------------- the frame (fastball)
// The end of a frame, at the begin of the next frame's scene: a frame that armed but never reached the composite
// (a screen whose composite shader aa_composite does not know) counts as missed, and if its scene was jittered the
// jitter stops for a second.
static void frame_end(void) {
    if (D.armed && !D.done) {
        D.frames_missed++;
        if (D.jit_used) D.hold = 60, D.holds++;
        D.jit_ok = 0;
    } else if (D.hold && D.done) {
        D.hold--;
    }
    D.armed = D.done = D.jit_used = 0, D.ncams = 0, D.out_now = VK_NULL_HANDLE;
}

static int scene_depth(VkFormat f) {
    return f == VK_FORMAT_D32_SFLOAT_S8_UINT || f == VK_FORMAT_D24_UNORM_S8_UINT;
}

void vk_dlaa_pass(VkExec *ex) {
    if (!dl_active()) return;
    const VkExecTarget *c = &ex->color[0], *z = &ex->depth;
    if (ex->pass_ncolor != 1 || !c->image || c->format != VK_FORMAT_B10G11R11_UFLOAT_PACK32 || !z->image ||
        !scene_depth(z->format) || c->width != z->width || c->height != z->height || c->width < DLAA_SCENE_MIN_W ||
        c->samples > 1 || c->is3d)
        return;
    uint64_t f = __atomic_load_n(&gfx_counters.frames, __ATOMIC_RELAXED);
    if (D.done || (D.armed && f >= D.arm_frame + 2)) frame_end();
    if (D.armed && (c->image == D.color.image || c->width < D.color.width)) return;   // the scene pass resumes
    if (D.armed) D.ncams = 0;   // a larger pair takes over: its own camera
    D.color = *c, D.depth = *z, D.armed = 1, D.arm_frame = f;
}

// Each scene draw that tests depth notes its vertex c3 block, the camera's view-projection (see above); the bytes are
// the ones of the submit call (vk_usnap.c), else guest memory as it is now.
void vk_dlaa_draw(VkExec *ex) {
    if (!D.armed || D.done || ex->depth.image != D.depth.image || !ex->pipe.ds.dt) return;
    const p_bind_buf *b = &ex->ubo[0][0];
    if (!b->addr || b->size < 64) return;
    for (int i = 0; i < D.ncams; i++)
        if (D.cams[i].addr == b->addr) return (void)D.cams[i].n++;
    if (D.ncams == (int)(sizeof D.cams / sizeof D.cams[0])) return;
    const uint8_t *s = vk_usnap_bytes(b->addr, 64);
    if (!s && plat_mem_readable(b->addr, 64)) s = (const uint8_t *)(uintptr_t)b->addr;
    if (!s) return;
    struct Cam *cm = &D.cams[D.ncams];
    memcpy(cm->vp, s, sizeof cm->vp);
    // a perspective camera: a w row (each column's w) and finite numbers
    float wl = cm->vp[3] * cm->vp[3] + cm->vp[7] * cm->vp[7] + cm->vp[11] * cm->vp[11];
    for (int i = 0; i < 16; i++)
        if (!isfinite(cm->vp[i])) return;
    if (!(wl > 1e-12f)) return;
    cm->addr = b->addr, cm->n = 1;
    D.ncams++;
}

// The DLSS model (MLB_DLSS_PRESET, live): default takes NVIDIA's model per mode (evaluate: K for DLAA, Quality and
// Balanced, M for Performance, L for Ultra Performance), 0 here. A letter a..m takes that model in every mode. The value
// is an NVSDK_NGX_DLSS_Hint_Render_Preset (1 A ... 13 M), read when a feature is created; a change recreates them.
static int preset_value(void) {
    const char *v = cfg_get("DLSS_PRESET");
    int c = v && v[0] && !v[1] ? v[0] | 0x20 : 0;
    return c >= 'a' && c <= 'm' ? c - 'a' + 1 : 0;
}

// The quality setting DLSS is created with, from the scene's share of the output width.
static int perf_quality(uint32_t w, uint32_t ow) {
    if (w >= ow) return NGX_PERFQ_DLAA;
    double k = (double)w / ow;
    return k >= 0.66 ? 2 : k >= 0.57 ? 1 : k >= 0.49 ? 0 : 3;
}

static int dlss_eval(VkExec *ex, struct Size *e, VkImageView zv, float jx, float jy, float dtms);
static int fsr_eval(VkExec *ex, struct Size *e, VkImageView zv, float jx, float jy, float dtms);

// DLSS (or FSR) on the armed scene into an image of ow x oh; its view, VK_NULL_HANDLE when it did not run.
static VkImageView evaluate(VkExec *ex, uint32_t ow, uint32_t oh) {
    const VkExecTarget *t = &D.color, *z = &D.depth;
    uint32_t w = t->width, h = t->height;
    VkCommandBuffer cb = ex->cb;
    vk_exec_barrier(ex);   // what drew the scene is done (no pass is open here)
    if (D.preset_dirty) {   // another model: features are created with it, so every size gets a new one
        for (int i = 0; i < (int)(sizeof D.sizes / sizeof D.sizes[0]); i++)
            if (D.sizes[i].out) free_size(&D.sizes[i]);
        D.last = NULL, D.preset_dirty = 0;
    }
    struct Size *e = size_for(cb, w, h, ow, oh);
    if (!e) return dl_fail("work image creation", 0), VK_NULL_HANDLE;
    if (e != D.last) D.reset = 1, D.why[0]++;   // another size's history is from another moment
    VkImageView zv = vk_exec_target_view(z->img, z->format, VK_IMAGE_VIEW_TYPE_2D, VK_IMAGE_ASPECT_DEPTH_BIT, z->level,
                                         z->base_layer, 1, 0);
    float jx = D.jit_used ? D.ux : 0.0f, jy = D.jit_used ? D.uy : 0.0f;
    static int no_mv = -1;
    if (no_mv < 0) no_mv = !rt_knob("DLSS_MV", "1");   // MLB_DLSS_MV=0: zero motion (test)
    times_mark(cb, T_MV0);
    D.mv_m_ok = 0;
    if (no_mv || !mv_pass(ex, e, zv, jx, jy)) {
        VkClearColorValue zero = {{0, 0, 0, 0}};
        VkImageSubresourceRange all = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        vkCmdClearColorImage(cb, e->mv, VK_IMAGE_LAYOUT_GENERAL, &zero, 1, &all);
        full_barrier(cb);
        if (!no_mv) D.reset = 1, D.why[1]++;   // no camera or a cut: the history cannot be moved along
    }
    times_mark(cb, T_MV1);
    if (D.last_color != t->image) D.reset = 1, D.why[2]++, D.last_color = t->image;
    // The time since the previous evaluation, which DLSS and FSR weigh their history by. After a gap (a pause, a load,
    // a screen without a 3D scene) the history is stale: a new one.
    uint64_t now = plat_now_ns();
    double dt = D.last_eval_ns ? (now - D.last_eval_ns) / 1e6 : 0;
    D.last_eval_ns = now;
    if (dt > 250) D.reset = 1;
    float dtms = dt > 0 && dt < 100 ? (float)dt : 16.67f;
    if (use_fsr() ? !fsr_eval(ex, e, zv, jx, jy, dtms) : !dlss_eval(ex, e, zv, jx, jy, dtms)) return VK_NULL_HANDLE;
    times_mark(cb, T_DL1);   // through the recorder, after NGX's or AMD's own commands
    D.reset = 0;
    D.last = e, e->used = D.evals + 1;
    full_barrier(cb);
    // MLB_DLSS_MVDEBUG=1 (test): the motion vectors in place of the picture, x in red and y in green, render pixels
    // as scene light (the game's exposure and tone curve still run over them)
    static int mvdebug = -1;
    if (mvdebug < 0) mvdebug = rt_knob("DLSS_MVDEBUG", "0");
    if (mvdebug) {
        VkImageBlit bl = {.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .srcOffsets = {{0, 0, 0}, {(int32_t)w, (int32_t)h, 1}},
                          .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .dstOffsets = {{0, 0, 0}, {(int32_t)ow, (int32_t)oh, 1}}};
        vkCmdBlitImage(cb, e->mv, VK_IMAGE_LAYOUT_GENERAL, e->out, VK_IMAGE_LAYOUT_GENERAL, 1, &bl, VK_FILTER_NEAREST);
        full_barrier(cb);
    }
    ex->recorded += 4;
    vk_exec_draw_new_cb();   // NGX / AMD bound pipelines and descriptor sets of their own: the next draw binds all again
    D.jdepth = z->image;
    next_jitter(w, ow);
    if (++D.evals == 1 || D.evals == 300 || D.evals % 3600 == 0)
        rt_log("%s: %llu frames (scene %ux%u, output %ux%u; %llu frames without the composite, %llu with camera "
               "motion, %llu without a camera, %llu camera cuts, %llu jitter holds; resets: %llu size, %llu camera, "
               "%llu target)",
               tag(), (unsigned long long)D.evals, w, h, ow, oh, (unsigned long long)D.frames_missed,
               (unsigned long long)D.mv_frames, (unsigned long long)D.mv_none, (unsigned long long)D.cuts,
               (unsigned long long)D.holds, (unsigned long long)D.why[0], (unsigned long long)D.why[1],
               (unsigned long long)D.why[2]);
    return e->out_tex;
}

// NGX's DLSS on the armed scene into e->out. 0: it failed (DLSS off for the run).
static int dlss_eval(VkExec *ex, struct Size *e, VkImageView zv, float jx, float jy, float dtms) {
    const VkExecTarget *t = &D.color, *z = &D.depth;
    uint32_t w = e->w, h = e->h, ow = e->ow, oh = e->oh;
    VkCommandBuffer cb = ex->cb;
    if (!D.params && !NGX_OK(N.alloc_params(&D.params))) return dl_fail("parameter allocation", 0), 0;
    NgxParam *p = D.params;
    rec_drain();   // NGX records into the command buffer itself: the recorder thread must have made every call so far
    if (!e->feat) {
        p_setu(p, "CreationNodeMask", 1);
        p_setu(p, "VisibilityNodeMask", 1);
        p_setu(p, "Width", w);
        p_setu(p, "Height", h);
        p_setu(p, "OutWidth", ow);
        p_setu(p, "OutHeight", oh);
        p_seti(p, "PerfQualityValue", perf_quality(w, ow));
        // IsHDR | MVLowRes | AutoExposure: linear scene light, motion vectors at the render size, no exposure texture.
        // MLB's depth is not inverted (near is 0, the depth test LEQUAL).
        p_seti(p, "DLSS.Feature.Create.Flags", (1 << 0) | (1 << 1) | (1 << 6));
        p_seti(p, "DLSS.Enable.Output.Subrects", 0);
        // The model per mode (NVSDK_NGX_DLSS_Hint_Render_Preset: 1 A ... 11 K, 12 L, 13 M), as NVIDIA recommends for
        // DLSS 4.5 (310.x): K (transformer) for DLAA, Quality and Balanced, M for Performance, L for Ultra Performance.
        // M and L cost more on cards without FP8 (RTX 20/30). MLB_DLSS_PRESET takes one model for every mode instead.
        int pk = D.preset ? D.preset : 11, pm = D.preset ? D.preset : 13, pl = D.preset ? D.preset : 12;
        p_setu(p, "DLSS.Hint.Render.Preset.DLAA", (unsigned)pk);
        p_setu(p, "DLSS.Hint.Render.Preset.UltraQuality", (unsigned)pk);
        p_setu(p, "DLSS.Hint.Render.Preset.Quality", (unsigned)pk);
        p_setu(p, "DLSS.Hint.Render.Preset.Balanced", (unsigned)pk);
        p_setu(p, "DLSS.Hint.Render.Preset.Performance", (unsigned)pm);
        p_setu(p, "DLSS.Hint.Render.Preset.UltraPerformance", (unsigned)pl);
        NgxResult r = N.create(cb, NGX_FEATURE_SUPERSAMPLING, p, &e->feat);
        if (!NGX_OK(r) || !e->feat) return dl_fail("DLSS feature creation", r), 0;
        D.reset = 1;
        int q = perf_quality(w, ow), pr = q == 0 ? pm : q == 3 ? pl : pk;
        rt_log("dlss: feature created at %ux%u -> %ux%u, quality value %d, preset %c (scene format %d, depth format %d)",
               w, h, ow, oh, q, 'A' + pr - 1, (int)t->format, (int)z->format);
    }
    VkImageView cv = vk_exec_target_view(t->img, t->format, VK_IMAGE_VIEW_TYPE_2D, VK_IMAGE_ASPECT_COLOR_BIT, t->level,
                                         t->base_layer, 1, 0);
    NgxResourceVK rc = res_image(cv, t->image, t->format, w, h, VK_IMAGE_ASPECT_COLOR_BIT, 0);
    NgxResourceVK ro = res_image(e->out_view, e->out, VK_FORMAT_R16G16B16A16_SFLOAT, ow, oh, VK_IMAGE_ASPECT_COLOR_BIT, 1);
    NgxResourceVK rz = res_image(zv, z->image, z->format, w, h, VK_IMAGE_ASPECT_DEPTH_BIT, 0);
    NgxResourceVK rm = res_image(e->mv_view, e->mv, VK_FORMAT_R16G16_SFLOAT, w, h, VK_IMAGE_ASPECT_COLOR_BIT, 0);
    p_setp(p, "Color", &rc);
    p_setp(p, "Output", &ro);
    p_setp(p, "Depth", &rz);
    p_setp(p, "MotionVectors", &rm);
    p_setf(p, "Jitter.Offset.X", jx);
    p_setf(p, "Jitter.Offset.Y", jy);
    p_setf(p, "Sharpness", 0.0f);
    p_setp(p, "DLSS.Input.Bias.Current.Color.Mask", NULL);
    p_setf(p, "MV.Scale.X", 1.0f);
    p_setf(p, "MV.Scale.Y", 1.0f);
    p_setu(p, "DLSS.Render.Subrect.Dimensions.Width", w);
    p_setu(p, "DLSS.Render.Subrect.Dimensions.Height", h);
    p_setf(p, "DLSS.Pre.Exposure", 1.0f);
    p_setf(p, "DLSS.Exposure.Scale", 1.0f);
    p_setf(p, "FrameTimeDeltaInMsec", dtms);
    p_seti(p, "Reset", D.reset);
    NgxResult r = N.evaluate(cb, e->feat, p, NULL);
    if (!NGX_OK(r)) return dl_fail("DLSS evaluation", r), 0;
    return 1;
}

// fastball: the camera's near and far distances and vertical field of view, which FSR weighs disocclusion with, from
// this frame's view-projection (mv_pass left it in prev_vp). With w = row 3 . x (the view depth, rows normalised so
// row 3's direction is a unit vector) and row 2 = a * row 3 + b * (0,0,0,1) for any perspective projection, ndc z is
// a + b / w, so the depth at ndc z is b / (z - a): the near plane at NVN's near z (0, or -1 with -w..w depth), the far
// one at 1. Row 1's length over row 3's is the vertical focal length (camera_cut). Without a camera: 0.1, 1000, 1 rad.
// Measured 2026-11-18 on the main menu's 3D scene: rows z (0 -1.0001 0 0), w (0 -1 0 1), so near 1, far 9999, 35
// degrees, depth 0 at the near plane (not inverted). The view's unit is not known: FSR is told 1 unit is 1 metre.
static void camera_planes(float *nz, float *fz, float *fov) {
    *nz = 0.1f, *fz = 1000.0f, *fov = 1.0f;
    if (!D.prev_ok) return;
    const double *m = D.prev_vp;
    double l = len3(m + 12);
    if (l < 1e-12) return;
    double r2[4], r3[4];
    for (int i = 0; i < 4; i++) r2[i] = m[8 + i] / l, r3[i] = m[12 + i] / l;
    double a = r2[0] * r3[0] + r2[1] * r3[1] + r2[2] * r3[2], b = r2[3] - a * r3[3];
    double z0 = nvn_depth_minus_w() ? -1.0 : 0.0;
    double dn = b / (z0 - a), df = b / (1.0 - a);
    if (!(dn > 0) || !isfinite(dn)) return;
    if (!(df > 0) || !isfinite(df) || df > 1e7) df = 1e7;   // (an infinite far plane)
    if (dn > df) { double s = dn; dn = df; df = s; }
    double f1 = len3(m + 4) / l;
    *nz = (float)dn, *fz = (float)df;
    if (f1 > 1e-6) *fov = (float)(2.0 * atan(1.0 / f1));
}

// fastball: AMD FSR 3.1 / 4 (vk_ffx.c) on the armed scene into e->out. 0: not run (FSR off for the run when AMD's
// runtime failed; a scene it cannot take is only skipped). With the reactive mask (mask_pass) where it has one.
static int fsr_eval(VkExec *ex, struct Size *e, VkImageView zv, float jx, float jy, float dtms) {
    const VkExecTarget *t = &D.color, *z = &D.depth;
    int masked = mask_pass(ex, e, zv, jx, jy);
    VkFfxFrame f = {.color = t->image, .depth = z->image, .mv = e->mv, .out = e->out,
                    .reactive = masked ? e->mask : VK_NULL_HANDLE, .color_fmt = t->format,
                    .depth_fmt = z->format, .color_level = t->level, .color_layer = t->base_layer,
                    .depth_level = z->level, .depth_layer = z->base_layer, .w = e->w, .h = e->h, .ow = e->ow,
                    .oh = e->oh, .jx = jx, .jy = jy, .dt_ms = dtms, .reset = D.reset || !e->ffx};
    camera_planes(&f.near_z, &f.far_z, &f.fov_y);
    static int planes_logged;
    if (D.prev_ok && !planes_logged++)
        rt_log("fsr: the game's camera: near %.4g, far %.4g, vertical field of view %.1f degrees", (double)f.near_z,
               (double)f.far_z, (double)f.fov_y * 57.29578);
    if (!vk_ffx_dispatch(ex->cb, &e->ffx, &f)) {
        if (!vk_ffx_available()) D.failed = 1;   // (vk_ffx.c said why)
        return 0;
    }
    vk_ffx_ran();
    // MLB_FSR_MASKDEBUG=1 (test): the reactive mask in place of the picture, in red (0.9: FSR drops its history there)
    static int maskdebug = -1;
    if (maskdebug < 0) maskdebug = rt_knob("FSR_MASKDEBUG", "0");
    if (maskdebug && masked) {
        full_barrier(ex->cb);
        VkImageBlit bl = {.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .srcOffsets = {{0, 0, 0}, {(int32_t)e->w, (int32_t)e->h, 1}},
                          .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .dstOffsets = {{0, 0, 0}, {(int32_t)e->ow, (int32_t)e->oh, 1}}};
        vkCmdBlitImage(ex->cb, e->mask, VK_IMAGE_LAYOUT_GENERAL, e->out, VK_IMAGE_LAYOUT_GENERAL, 1, &bl,
                       VK_FILTER_NEAREST);
    }
    return 1;
}

int vk_dlaa_on(void) { return dl_active(); }

int vk_dlaa_scene(VkExec *ex, const VkTexImage *im, uint32_t pw, uint32_t ph, VkImageView *out) {
    if (!dl_active() || !D.armed || im->image != D.color.image) return 0;
    if (D.done) {   // a second composite draw of this frame
        if (!D.out_now) return 0;
        *out = D.out_now;
        return 1;
    }
    D.done = 1;
    uint32_t w = D.color.width, h = D.color.height;
    // the output at the composite's size; where the scene is as large or larger (DLAA), at the scene's own
    uint32_t ow = pw > w && ph > h ? pw : w, oh = pw > w && ph > h ? ph : h;
    VkImageView v = evaluate(ex, ow, oh);
    if (!v) {
        D.jit_ok = 0;   // fastball: nothing resolved this frame's jitter: the next scene is drawn without it
        return 0;
    }
    *out = D.out_now = v;
    return 1;
}

const char *vk_dlaa_name(void) { return use_fsr() ? "FSR" : "DLSS"; }

// The preset, read again when a setting changed (the menu); a different one recreates the features at the next run.
// fastball: with FSR, the version instead (MLB_FSR_VERSION: 2 FSR 4, 1 FSR 3.1); a change makes the contexts again.
static void preset_check(void) {
    unsigned v = cfg_version();
    if (v == D.cfg_seen) return;
    D.cfg_seen = v;
    int fsr = use_fsr(), p = fsr ? (vk_ffx_ml_wanted() ? 2 : 1) : preset_value();
    if (p == D.preset) return;
    if (D.evals) {
        if (fsr) rt_log("fsr: FSR %s from now on; the contexts are made again", p == 2 ? "4" : "3.1");
        else if (p) rt_log("dlss: preset %c in every mode; the features are created again", 'A' + p - 1);
        else rt_log("dlss: presets per mode; the features are created again");
    }
    D.preset = p, D.preset_dirty = 1, D.reset = 1;
}

// Each present: the preset, and the texture LOD bias for the scene DLSS scales up (NVIDIA's guide: log2 of the scene's
// share of the output), so the scene's material textures are sampled for the output's resolution.
// fastball: FSR's guide asks for one step more, log2(render / output) - 1 (-1.58 in Quality at 1.5x). Off or failed:
// no bias.
void vk_dlaa_frame(void) {
    float b = 0.0f;
    if (dl_active()) {
        preset_check();
        if (D.last && use_fsr()) b = (float)(log2((double)D.last->w / D.last->ow) - 1.0);
        else if (D.last && D.last->w < D.last->ow) b = (float)log2((double)D.last->w / D.last->ow);
    }
    if (b != D.bias) {
        D.bias = b;
        vk_sampler_dlss_bias(b);
        rt_log("%s: texture LOD bias %.2f", tag(), (double)b);
    }
}

// MLB has no FXAA of its own to switch (TotK's fxaa setting): nothing is skipped.
int vk_dlaa_skip_draw(VkExec *ex, const GfxShader *fs) {
    (void)ex, (void)fs;
    return 0;
}

// Per-object motion (TotK's vk_mvprev.c and the motion draws of its vk_exec_draw.c) is not ported: DLSS gets the
// camera's motion only.
int vk_dlaa_prev_camera(VkDescriptorBufferInfo *out, float jitter[2]) {
    (void)out, (void)jitter;
    return 0;
}
