// From TotK Recomp runtime/vk_fsr.c @ ae30a61 (MIT, Copyright (c) 2026 Valiantsin Dzerakh); the shaders and their
// headers (runtime/shaders/fsr_*.comp, ffx/) and fsr_*_spv.h too. fastball: MLB's scene upscale below
// (vk_fsr_scene), and MLB_ keys.
//
// AMD FidelityFX Super Resolution 1 on the present path (gfx_present.c present_image): when the window is larger than
// the game's output, EASU scales the game's crop rectangle to the swapchain size and RCAS sharpens it, in place of the
// bilinear vkCmdBlitImage. TOTK_UPSCALER=fsr|bilinear picks it, TOTK_SHARPNESS (0..100, 0 = no RCAS pass) sets RCAS;
// both apply at the next frame.
//
// Per frame: EASU reads the source through a view of its own format (the same colour conversion the blit does) and
// writes an RGBA16F image of the picture's size on the swapchain (all of it, or the part between black bars,
// gfx_window.c fit_rect); RCAS reads that and writes a second one; a 1:1 blit converts the result into its place in
// the swapchain image, which the caller left in TRANSFER_DST. The shaders (runtime/shaders/fsr_*.comp)
// compute AMD's constants from the push constants. Cost: two compute passes over the swapchain size and one copy per
// present; nothing on the game's draws.
//
// The source view of slot s is destroyed when slot s records again: present_image has waited for that slot's fence.
// The two intermediate images are shared by all slots; each frame's first barrier orders it after the previous
// frame's reads (one queue, so the barrier covers earlier submissions).
#include "vk.h"

#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "fsr_easu_spv.h"
#include "fsr_rcas_spv.h"
#include "host.h"
#include "platform/platform.h"

#define SLOTS 8

static struct {
    int tried, ok;
    PFN_vkCmdPushDescriptorSetKHR push;
    VkDescriptorSetLayout dsl;
    VkPipelineLayout layout;
    VkPipeline easu, rcas;
    VkSampler sampler;
    VkImage img[2];                // EASU output, RCAS output
    VmaAllocation alloc[2];
    VkImageView view[2];
    uint32_t w, h;                 // their size
    VkImageView src_view[SLOTS];   // the source view each slot's last frame read
    int logged;
} F;

static VkPipeline make_pipeline(VkCtx *c, const uint32_t *code, size_t size) {
    VkShaderModuleCreateInfo mi = {.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .codeSize = size, .pCode = code};
    VkShaderModule m = VK_NULL_HANDLE;
    if (vkCreateShaderModule(c->device, &mi, NULL, &m) != VK_SUCCESS) return VK_NULL_HANDLE;
    VkComputePipelineCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
                                      .stage = {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                                                .stage = VK_SHADER_STAGE_COMPUTE_BIT, .module = m, .pName = "main"},
                                      .layout = F.layout};
    VkPipeline p = VK_NULL_HANDLE;
    if (vkCreateComputePipelines(c->device, VK_NULL_HANDLE, 1, &ci, NULL, &p) != VK_SUCCESS) p = VK_NULL_HANDLE;
    vkDestroyShaderModule(c->device, m, NULL);
    return p;
}

static int init(VkCtx *c) {
    F.tried = 1;
    F.push = (PFN_vkCmdPushDescriptorSetKHR)vkGetDeviceProcAddr(c->device, "vkCmdPushDescriptorSetKHR");
    if (!F.push) {
        rt_log("vk: FSR off: no VK_KHR_push_descriptor; the present scales bilinearly");
        return 0;
    }
    VkDescriptorSetLayoutBinding b[2] = {
        {.binding = 0, .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .descriptorCount = 1,
         .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT},
        {.binding = 1, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .descriptorCount = 1,
         .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT}};
    VkDescriptorSetLayoutCreateInfo dci = {.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
                                           .flags = VK_DESCRIPTOR_SET_LAYOUT_CREATE_PUSH_DESCRIPTOR_BIT_KHR,
                                           .bindingCount = 2, .pBindings = b};
    VkPushConstantRange pr = {VK_SHADER_STAGE_COMPUTE_BIT, 0, 32};
    VkPipelineLayoutCreateInfo li = {.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, .setLayoutCount = 1,
                                     .pSetLayouts = &F.dsl, .pushConstantRangeCount = 1, .pPushConstantRanges = &pr};
    VkSamplerCreateInfo si = {.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO, .magFilter = VK_FILTER_LINEAR,
                              .minFilter = VK_FILTER_LINEAR, .mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST,
                              .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                              .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                              .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE, .maxLod = 0};
    if (vkCreateDescriptorSetLayout(c->device, &dci, NULL, &F.dsl) != VK_SUCCESS ||
        vkCreatePipelineLayout(c->device, &li, NULL, &F.layout) != VK_SUCCESS ||
        vkCreateSampler(c->device, &si, NULL, &F.sampler) != VK_SUCCESS ||
        !(F.easu = make_pipeline(c, fsr_easu_spv, sizeof fsr_easu_spv)) ||
        !(F.rcas = make_pipeline(c, fsr_rcas_spv, sizeof fsr_rcas_spv))) {
        rt_log("vk: FSR off: its pipelines could not be created; the present scales bilinearly");
        return 0;
    }
    rt_log("vk: FSR 1 (EASU + RCAS) ready for the present");
    return F.ok = 1;
}

static void free_images(VkCtx *c) {
    for (int i = 0; i < 2; i++) {
        if (F.view[i]) vkDestroyImageView(c->device, F.view[i], NULL);
        if (F.img[i]) vmaDestroyImage(c->vma, F.img[i], F.alloc[i]);
        F.view[i] = VK_NULL_HANDLE;
        F.img[i] = VK_NULL_HANDLE;
    }
    F.w = F.h = 0;
}

static int ensure_images(VkCtx *c, uint32_t w, uint32_t h) {
    if (F.img[0] && F.w == w && F.h == h) return 1;
    // A swapchain size change: earlier presents may still read the old images. vkDeviceWaitIdle needs every queue
    // externally synchronized, so it holds the queue lock like a submission.
    vk_queue_lock();
    vkDeviceWaitIdle(c->device);
    vk_queue_unlock();
    free_images(c);
    for (int i = 0; i < 2; i++) {
        VkImageCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                                .format = VK_FORMAT_R16G16B16A16_SFLOAT, .extent = {w, h, 1}, .mipLevels = 1,
                                .arrayLayers = 1, .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                                .usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_SAMPLED_BIT |
                                         VK_IMAGE_USAGE_TRANSFER_SRC_BIT};
        VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE};
        if (vmaCreateImage(c->vma, &ci, &ai, &F.img[i], &F.alloc[i], NULL) != VK_SUCCESS) {
            F.img[i] = VK_NULL_HANDLE;
            free_images(c);
            return 0;
        }
        VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = F.img[i],
                                    .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = VK_FORMAT_R16G16B16A16_SFLOAT,
                                    .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
        if (vkCreateImageView(c->device, &vi, NULL, &F.view[i]) != VK_SUCCESS) {
            F.view[i] = VK_NULL_HANDLE;
            free_images(c);
            return 0;
        }
    }
    F.w = w;
    F.h = h;
    return 1;
}

static void barrier(VkCommandBuffer cb, VkImage img, VkImageLayout from, VkImageLayout to, VkPipelineStageFlags2 ss,
                    VkAccessFlags2 sa, VkPipelineStageFlags2 ds, VkAccessFlags2 da) {
    VkImageMemoryBarrier2 b = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2, .srcStageMask = ss, .srcAccessMask = sa,
                               .dstStageMask = ds, .dstAccessMask = da, .oldLayout = from, .newLayout = to,
                               .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                               .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .image = img,
                               .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    VkDependencyInfo d = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .imageMemoryBarrierCount = 1,
                          .pImageMemoryBarriers = &b};
    vkCmdPipelineBarrier2(cb, &d);
}

static void bind_pass(VkCommandBuffer cb, VkPipeline p, VkImageView in, VkImageView out, const float pc[8]) {
    VkDescriptorImageInfo ii = {F.sampler, in, VK_IMAGE_LAYOUT_GENERAL}, oi = {VK_NULL_HANDLE, out, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet w[2] = {
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = 0, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .pImageInfo = &ii},
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = 1, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .pImageInfo = &oi}};
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, p);
    rec_push(F.push, cb, VK_PIPELINE_BIND_POINT_COMPUTE, F.layout, 0, 2, w);
    vkCmdPushConstants(cb, F.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, 32, pc);
}

int vk_fsr_record(VkCommandBuffer cb, unsigned slot, VkImage src, VkFormat fmt, int sw, int sh, const int crop[4],
                  VkImage dst, const int out[4]) {
    int cw = crop[2], ch = crop[3];
    uint32_t dw = (uint32_t)out[2], dh = (uint32_t)out[3];
    if (strcmp(cfg_value("TOTK_UPSCALER"), "fsr") || (dw <= (uint32_t)cw && dh <= (uint32_t)ch) || !fmt) return 0;
    VkCtx *c = vk_ctx();
    if (!F.tried) init(c);
    if (!F.ok || !ensure_images(c, dw, dh)) return 0;
    slot %= SLOTS;
    if (F.src_view[slot]) vkDestroyImageView(c->device, F.src_view[slot], NULL);
    VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = src,
                                .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = fmt,
                                .components = {VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY,
                                               VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_ONE},
                                .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    if (vkCreateImageView(c->device, &vi, NULL, &F.src_view[slot]) != VK_SUCCESS) {
        F.src_view[slot] = VK_NULL_HANDLE;
        return 0;
    }
    int sharp = cfg_int("TOTK_SHARPNESS");
    if (sharp < 0) sharp = 0;
    if (sharp > 100) sharp = 100;
    if (!F.logged) {
        F.logged = 1;
        rt_log("vk: FSR upscales %dx%d to %ux%u (sharpness %d)", cw, ch, dw, dh, sharp);
    }
    const VkPipelineStageFlags2 CS = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT, XF = VK_PIPELINE_STAGE_2_TRANSFER_BIT;
    // the game's writes to the source become visible to the compute read; the earlier frame's reads of the
    // intermediates finish before this frame writes them
    barrier(cb, src, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
            VK_ACCESS_2_MEMORY_WRITE_BIT, CS, VK_ACCESS_2_SHADER_SAMPLED_READ_BIT);
    for (int i = 0; i < 2; i++)
        barrier(cb, F.img[i], VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_GENERAL, CS | XF, 0, CS,
                VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT | VK_ACCESS_2_SHADER_SAMPLED_READ_BIT);
    uint32_t gx = (dw + 15) / 16, gy = (dh + 15) / 16;
    float easu[8] = {(float)cw, (float)ch, (float)sw, (float)sh, (float)dw, (float)dh, (float)crop[0], (float)crop[1]};
    bind_pass(cb, F.easu, F.src_view[slot], F.view[0], easu);
    vkCmdDispatch(cb, gx, gy, 1);
    int last = 0;
    if (sharp > 0) {
        barrier(cb, F.img[0], VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, CS, VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT,
                CS, VK_ACCESS_2_SHADER_SAMPLED_READ_BIT);
        float rcas[8] = {(float)dw, (float)dh, (float)(100 - sharp) / 50.0f, 0, 0, 0, 0, 0};
        bind_pass(cb, F.rcas, F.view[0], F.view[1], rcas);
        vkCmdDispatch(cb, gx, gy, 1);
        last = 1;
    }
    barrier(cb, F.img[last], VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, CS, VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT,
            XF, VK_ACCESS_2_TRANSFER_READ_BIT);
    // later submissions that write the source wait for the compute read
    barrier(cb, src, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, CS, 0, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT, 0);
    VkImageBlit region = {.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .srcOffsets = {{0, 0, 0}, {(int)dw, (int)dh, 1}},
                          .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .dstOffsets = {{out[0], out[1], 0}, {out[0] + (int)dw, out[1] + (int)dh, 1}}};
    vkCmdBlitImage(cb, F.img[last], VK_IMAGE_LAYOUT_GENERAL, dst, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region,
                   VK_FILTER_NEAREST);
    return 1;
}

// ---- fastball: FSR 1 on MLB's 3D scene (MLB_UPSCALER=fsr, the settings menu's Graphics tab)
//
// MLB renders its 3D scene at 1440x810 (resolution.c) and its final full-screen draw (fragment shader daf10a59,
// vk_exec_draw.c aa_before_draw) stretches it to 1920x1080 with a plain bilinear sample while laying the HUD over it.
// With FSR on, EASU scales the scene to the size of that draw's pass first (and RCAS sharpens it), and the draw samples
// the result in the scene's place: tex_info swaps the scene's view for vk_dlaa_swap_view in passes larger than the
// scene, the hook TotK Recomp's DLSS path uses for the same job. The draw samples with normalised coordinates, so the
// larger image needs nothing else. When the scene is as large as the pass or larger (MLB_RENDER_SCALE 100 and above),
// nothing is scaled up and this does nothing.
//
// The scene is linear HDR before the game's tone mapping. EASU only interpolates within the four nearest texels'
// range (its deringing clamp), so its results stay within the scene's own values; RCAS is limited the same way.
// Per frame: two compute passes over the output size, a fraction of a millisecond at 1080p. The work images live as
// long as the sizes stay; replaced ones, and the source view of a replaced scene image, go once the submission that
// used them is done.
typedef struct { VkImage img[2]; VmaAllocation alloc[2]; VkImageView view[2]; VkImageView src; } SceneSet;

static struct {
    SceneSet *cur;
    VkImage src_img;                  // the scene image cur->src views
    VkFormat fmt;
    uint32_t sw, sh, dw, dh;
    uint64_t done_fence;              // once per submission
    VkImage done_image;
    VkImageView done_view;
    int logged;
} S;

static void scene_set_free(void *arg) {   // completion thread, or release
    SceneSet *s = arg;
    VkCtx *c = vk_ctx();
    for (int i = 0; i < 2; i++) {
        if (s->view[i]) vkDestroyImageView(c->device, s->view[i], NULL);
        if (s->img[i]) vmaDestroyImage(c->vma, s->img[i], s->alloc[i]);
    }
    if (s->src) vkDestroyImageView(c->device, s->src, NULL);
    free(s);
}

static SceneSet *scene_set_make(VkCtx *c, VkImage src, VkFormat fmt, uint32_t dw, uint32_t dh) {
    SceneSet *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    for (int i = 0; i < 2; i++) {
        VkImageCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                                .format = VK_FORMAT_R16G16B16A16_SFLOAT, .extent = {dw, dh, 1}, .mipLevels = 1,
                                .arrayLayers = 1, .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                                .usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_SAMPLED_BIT};
        VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE};
        if (vmaCreateImage(c->vma, &ci, &ai, &s->img[i], &s->alloc[i], NULL) != VK_SUCCESS) {
            s->img[i] = VK_NULL_HANDLE;
            scene_set_free(s);
            return NULL;
        }
        VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = s->img[i],
                                    .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = VK_FORMAT_R16G16B16A16_SFLOAT,
                                    .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
        if (vkCreateImageView(c->device, &vi, NULL, &s->view[i]) != VK_SUCCESS) {
            s->view[i] = VK_NULL_HANDLE;
            scene_set_free(s);
            return NULL;
        }
    }
    VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = src,
                                .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = fmt,
                                .components = {VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY,
                                               VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_ONE},
                                .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    if (vkCreateImageView(c->device, &vi, NULL, &s->src) != VK_SUCCESS) {
        s->src = VK_NULL_HANDLE;
        scene_set_free(s);
        return NULL;
    }
    return s;
}

int vk_fsr_scene_on(void) { return !strcmp(cfg_value("MLB_UPSCALER"), "fsr"); }

int vk_fsr_scene(VkCommandBuffer cb, uint64_t fence, VkImage scene, VkFormat fmt, uint32_t sw, uint32_t sh, uint32_t dw,
                 uint32_t dh, VkImageView *out) {
    if (!vk_fsr_scene_on() || dw <= sw + 1 || dh <= sh + 1 || !sw || !sh) return 0;
    VkCtx *c = vk_ctx();
    if (!F.tried) init(c);
    if (!F.ok) return 0;
    if (fence == S.done_fence && scene == S.done_image && S.done_view) {   // a second composite in this submission
        *out = S.done_view;
        return 1;
    }
    if (!S.cur || S.src_img != scene || S.fmt != fmt || S.sw != sw || S.sh != sh || S.dw != dw || S.dh != dh) {
        if (S.cur) vk_completion_add(fence, scene_set_free, S.cur);   // this submission may still use them
        S.cur = scene_set_make(c, scene, fmt, dw, dh);
        S.done_view = VK_NULL_HANDLE;
        if (!S.cur) {
            rt_log("vk: FSR scene: no memory for the %ux%u images; the game scales the scene itself", dw, dh);
            return 0;
        }
        S.src_img = scene, S.fmt = fmt, S.sw = sw, S.sh = sh, S.dw = dw, S.dh = dh;
        for (int i = 0; i < 2; i++)
            barrier(cb, S.cur->img[i], VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_GENERAL, VK_PIPELINE_STAGE_2_NONE, 0,
                    VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT, VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT);
    }
    int sharp = cfg_int("MLB_SHARPNESS");
    sharp = sharp < 0 ? 0 : sharp > 100 ? 100 : sharp;
    if (!S.logged) {
        S.logged = 1;
        rt_log("vk: FSR upscales the %ux%u 3D scene to %ux%u before the game's final draw (sharpness %d)", sw, sh, dw, dh,
               sharp);
    }
    const VkPipelineStageFlags2 CS = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT, ALL = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT;
    // the caller ended the pass behind a full barrier: the scene's writes are done. The previous frame's reads of the
    // work images finish before this frame writes them.
    for (int i = 0; i < 2; i++)
        barrier(cb, S.cur->img[i], VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, ALL, 0, CS,
                VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT | VK_ACCESS_2_SHADER_SAMPLED_READ_BIT);
    uint32_t gx = (dw + 15) / 16, gy = (dh + 15) / 16;
    float easu[8] = {(float)sw, (float)sh, (float)sw, (float)sh, (float)dw, (float)dh, 0, 0};
    bind_pass(cb, F.easu, S.cur->src, S.cur->view[0], easu);
    vkCmdDispatch(cb, gx, gy, 1);
    int last = 0;
    if (sharp > 0) {
        barrier(cb, S.cur->img[0], VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, CS,
                VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT, CS, VK_ACCESS_2_SHADER_SAMPLED_READ_BIT);
        float rcas[8] = {(float)dw, (float)dh, (float)(100 - sharp) / 50.0f, 0, 0, 0, 0, 0};
        bind_pass(cb, F.rcas, S.cur->view[0], S.cur->view[1], rcas);
        vkCmdDispatch(cb, gx, gy, 1);
        last = 1;
    }
    // the game's draw samples the result; later writers of the scene wait for the compute read
    barrier(cb, S.cur->img[last], VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, CS,
            VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT, ALL, VK_ACCESS_2_MEMORY_READ_BIT);
    barrier(cb, scene, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_GENERAL, CS, 0, ALL, 0);
    S.done_fence = fence, S.done_image = scene, S.done_view = S.cur->view[last];
    *out = S.done_view;
    return 1;
}

void vk_fsr_release(void) {
    VkCtx *c = vk_ctx();
    if (!c || !F.tried) return;
    if (S.cur) scene_set_free(S.cur);
    memset(&S, 0, sizeof S);
    free_images(c);
    for (int i = 0; i < SLOTS; i++)
        if (F.src_view[i]) vkDestroyImageView(c->device, F.src_view[i], NULL);
    if (F.easu) vkDestroyPipeline(c->device, F.easu, NULL);
    if (F.rcas) vkDestroyPipeline(c->device, F.rcas, NULL);
    if (F.sampler) vkDestroySampler(c->device, F.sampler, NULL);
    if (F.layout) vkDestroyPipelineLayout(c->device, F.layout, NULL);
    if (F.dsl) vkDestroyDescriptorSetLayout(c->device, F.dsl, NULL);
    memset(&F, 0, sizeof F);
}
