// fastball, our own: antialiasing of MLB's 3D scene (MLB_AA=fxaa, the default; MLB_AA=off; the menu's Graphics
// page). MLB draws its 3D scene into one HDR image (1440x810, B10G11R11 float, at 0x154ea0000 in every capture so far:
// gameplay, menus, RTTS) with no antialiasing, lays its HUD into a separate 1920x1080 image, and one full-screen draw
// then tone-maps the scene, scales it to 1080p and puts the HUD over it (fragment shader daf10a59; 1d3e4d6b on some
// menu screens). vk_exec_draw.c aa_before_draw recognises that draw and calls vk_aa_record first, so the scene is
// smoothed in place before the game reads it: edges lose their stair steps and the HUD's text stays sharp.
//
// One compute pass (shaders/fxaa.comp, our own FXAA): a copy of the scene in, the result out, copied back over the
// scene. The copies keep the game's images untouched apart from the final copy (no views or storage use of them, and
// no layout change: they stay GENERAL). At 1440x810 both copies and the pass take a small fraction of a millisecond.
// The two work images live as long as the scene keeps its size and format; replaced ones are freed once the
// submission that used them is done.
#include "vk.h"

#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "fxaa_spv.h"
#include "host.h"
#include "platform/platform.h"

typedef struct { VkImage img; VmaAllocation alloc; VkImageView view; } AaImage;
typedef struct { AaImage in, out; } AaPair;

static struct {
    int tried, ok;
    PFN_vkCmdPushDescriptorSetKHR push;
    VkDescriptorSetLayout dsl;
    VkPipelineLayout layout;
    VkPipeline pipe;
    VkSampler sampler;
    AaPair *cur;                       // the work images for (fmt, w, h)
    VkFormat fmt;
    uint32_t w, h;
    VkFormat bad_fmt;                  // a format the device cannot write from a shader: never tried again
    uint64_t done_fence;               // the submission the scene was last smoothed in (once per submission)
    VkImage done_image;
    volatile uint64_t applied_ns;      // plat_now_ns of the last smoothing, for vk_aa_status
    unsigned seen;                     // cfg_version the settings were read at
    int on;
    float subpix;
} A = {.seen = ~0u};

static int init(VkCtx *c) {
    A.tried = 1;
    A.push = (PFN_vkCmdPushDescriptorSetKHR)vkGetDeviceProcAddr(c->device, "vkCmdPushDescriptorSetKHR");
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
                                     .pSetLayouts = &A.dsl, .pushConstantRangeCount = 1, .pPushConstantRanges = &pr};
    VkSamplerCreateInfo si = {.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO, .magFilter = VK_FILTER_LINEAR,
                              .minFilter = VK_FILTER_LINEAR, .mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST,
                              .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                              .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                              .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE, .maxLod = 0};
    VkShaderModuleCreateInfo mi = {.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .codeSize = sizeof fxaa_spv,
                                   .pCode = fxaa_spv};
    VkShaderModule m = VK_NULL_HANDLE;
    if (!A.push || vkCreateDescriptorSetLayout(c->device, &dci, NULL, &A.dsl) != VK_SUCCESS ||
        vkCreatePipelineLayout(c->device, &li, NULL, &A.layout) != VK_SUCCESS ||
        vkCreateSampler(c->device, &si, NULL, &A.sampler) != VK_SUCCESS ||
        vkCreateShaderModule(c->device, &mi, NULL, &m) != VK_SUCCESS) {
        rt_log("vk_aa: antialiasing off: its pipeline could not be created");
        return 0;
    }
    VkComputePipelineCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
                                      .stage = {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                                                .stage = VK_SHADER_STAGE_COMPUTE_BIT, .module = m, .pName = "main"},
                                      .layout = A.layout};
    VkResult r = vkCreateComputePipelines(c->device, VK_NULL_HANDLE, 1, &ci, NULL, &A.pipe);
    vkDestroyShaderModule(c->device, m, NULL);
    if (r != VK_SUCCESS) {
        rt_log("vk_aa: antialiasing off: its pipeline could not be created");
        return 0;
    }
    rt_log("vk_aa: FXAA ready");
    return A.ok = 1;
}

static void free_image(VkCtx *c, AaImage *i) {
    if (i->view) vkDestroyImageView(c->device, i->view, NULL);
    if (i->img) vmaDestroyImage(c->vma, i->img, i->alloc);
    memset(i, 0, sizeof *i);
}

static void free_pair(void *arg) {   // completion thread, once the last submission that used them is done
    AaPair *p = arg;
    VkCtx *c = vk_ctx();
    free_image(c, &p->in);
    free_image(c, &p->out);
    free(p);
}

static int make_image(VkCtx *c, AaImage *i, VkFormat fmt, uint32_t w, uint32_t h, VkImageUsageFlags usage) {
    VkImageCreateInfo ii = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D, .format = fmt,
                            .extent = {w, h, 1}, .mipLevels = 1, .arrayLayers = 1, .samples = VK_SAMPLE_COUNT_1_BIT,
                            .tiling = VK_IMAGE_TILING_OPTIMAL, .usage = usage};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE};
    if (vmaCreateImage(c->vma, &ii, &ai, &i->img, &i->alloc, NULL) != VK_SUCCESS) {
        i->img = VK_NULL_HANDLE;
        return 0;
    }
    VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = i->img,
                                .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = fmt,
                                .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    if (vkCreateImageView(c->device, &vi, NULL, &i->view) != VK_SUCCESS) {
        i->view = VK_NULL_HANDLE;
        free_image(c, i);
        return 0;
    }
    return 1;
}

static void image_barrier(VkCommandBuffer cb, VkImage img, VkImageLayout from) {
    VkImageMemoryBarrier2 b = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
                               .srcStageMask = VK_PIPELINE_STAGE_2_NONE, .dstStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                               .dstAccessMask = VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT,
                               .oldLayout = from, .newLayout = VK_IMAGE_LAYOUT_GENERAL,
                               .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                               .image = img, .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    VkDependencyInfo d = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .imageMemoryBarrierCount = 1,
                          .pImageMemoryBarriers = &b};
    vkCmdPipelineBarrier2(cb, &d);
}

static void memory_barrier(VkCommandBuffer cb, VkPipelineStageFlags2 ss, VkAccessFlags2 sa, VkPipelineStageFlags2 ds,
                           VkAccessFlags2 da) {
    VkMemoryBarrier2 mb = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER_2, .srcStageMask = ss, .srcAccessMask = sa,
                           .dstStageMask = ds, .dstAccessMask = da};
    VkDependencyInfo d = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .memoryBarrierCount = 1, .pMemoryBarriers = &mb};
    vkCmdPipelineBarrier2(cb, &d);
}

// The work images for this scene; new ones (made GENERAL in cb) when its size or format changed. 0: none.
static int ensure_images(VkCtx *c, VkCommandBuffer cb, uint64_t fence, VkFormat fmt, uint32_t w, uint32_t h) {
    if (A.cur && A.fmt == fmt && A.w == w && A.h == h) return 1;
    if (fmt == A.bad_fmt) return 0;
    VkFormatProperties fp;
    vkGetPhysicalDeviceFormatProperties(c->phys, fmt, &fp);
    VkFormatFeatureFlags need = VK_FORMAT_FEATURE_STORAGE_IMAGE_BIT | VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT;
    if ((fp.optimalTilingFeatures & need) != need) {
        A.bad_fmt = fmt;
        rt_log("vk_aa: the scene's format %d cannot be written by a shader on this GPU: no antialiasing for it", fmt);
        return 0;
    }
    if (A.cur) vk_completion_add(fence, free_pair, A.cur);   // this submission may still use them; freed after it
    A.cur = NULL;
    AaPair *p = calloc(1, sizeof *p);
    if (!p) return 0;
    if (!make_image(c, &p->in, fmt, w, h, VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT) ||
        !make_image(c, &p->out, fmt, w, h, VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT)) {
        free_pair(p);
        rt_log("vk_aa: no memory for the %ux%u work images", w, h);
        return 0;
    }
    image_barrier(cb, p->in.img, VK_IMAGE_LAYOUT_UNDEFINED);
    image_barrier(cb, p->out.img, VK_IMAGE_LAYOUT_UNDEFINED);
    A.cur = p, A.fmt = fmt, A.w = w, A.h = h;
    rt_log("vk_aa: smoothing a %ux%u scene (format %d)", w, h, fmt);
    return 1;
}

static void read_settings(void) {
    unsigned v = cfg_version();
    if (v == A.seen) return;
    A.seen = v;
    A.on = !strcmp(cfg_value("MLB_AA"), "fxaa");
    A.subpix = (float)cfg_double("MLB_AA_STRENGTH") / 100.0f;
}

int vk_aa_on(void) {
    read_settings();
    return A.on;
}

int vk_aa_record(VkCommandBuffer cb, uint64_t fence, VkImage scene, VkFormat fmt, uint32_t w, uint32_t h) {
    if (!A.on || (A.tried && !A.ok) || !w || !h) return 0;
    // A second composite of the same scene in one submission. Keyed by the submission, not the present counter: with
    // the asynchronous replay the next frame can be recorded before the counter moves.
    if (fence == A.done_fence && scene == A.done_image) return 0;
    VkCtx *c = vk_ctx();
    if (!A.tried && !init(c)) return 0;
    if (!ensure_images(c, cb, fence, fmt, w, h)) return 0;
    A.done_fence = fence, A.done_image = scene;
    AaPair *p = A.cur;
    // The caller ended the pass behind a full barrier: the scene's writes are done and the previous frame's use of the
    // work images too (submission order, one queue).
    VkImageCopy region = {.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, .extent = {w, h, 1}};
    vkCmdCopyImage(cb, scene, VK_IMAGE_LAYOUT_GENERAL, p->in.img, VK_IMAGE_LAYOUT_GENERAL, 1, &region);
    memory_barrier(cb, VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT,
                   VK_ACCESS_2_SHADER_SAMPLED_READ_BIT | VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT);
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, A.pipe);
    VkDescriptorImageInfo src = {A.sampler, p->in.view, VK_IMAGE_LAYOUT_GENERAL};
    VkDescriptorImageInfo dst = {VK_NULL_HANDLE, p->out.view, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet wr[2] = {
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = 0, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .pImageInfo = &src},
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstBinding = 1, .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .pImageInfo = &dst}};
    // through the recorder (vk_rec.h) like the vkCmd* calls around it: a direct call would reach the command buffer
    // ahead of them, or race the recorder thread that owns it
    rec_push(A.push, cb, VK_PIPELINE_BIND_POINT_COMPUTE, A.layout, 0, 2, wr);
    struct { float rcp[2]; int32_t size[2]; float subpix, threshold, pad[2]; } pc = {
        {1.0f / (float)w, 1.0f / (float)h}, {(int32_t)w, (int32_t)h}, A.subpix,
        0.3f,   // stops: about 23 % brighter or darker than a neighbour, FXAA's usual edge threshold
        {0, 0}};
    vkCmdPushConstants(cb, A.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    vkCmdDispatch(cb, (w + 7) / 8, (h + 7) / 8, 1);
    memory_barrier(cb, VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT, VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT,
                   VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_READ_BIT);
    vkCmdCopyImage(cb, p->out.img, VK_IMAGE_LAYOUT_GENERAL, scene, VK_IMAGE_LAYOUT_GENERAL, 1, &region);
    // the composite draw and anything later read or overwrite the scene after the copy
    memory_barrier(cb, VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                   VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT);
    __atomic_store_n(&A.applied_ns, plat_now_ns(), __ATOMIC_RELAXED);
    return 1;
}

// For the menu: 0 off, 1 smoothing (a scene in the last 2 seconds), 2 on but no 3D scene lately (loading
// screens, video), 3 the device cannot run it.
int vk_aa_status(void) {
    read_settings();
    if (!A.on) return 0;
    if ((A.tried && !A.ok) || (A.bad_fmt && A.bad_fmt == A.fmt)) return 3;
    uint64_t a = __atomic_load_n(&A.applied_ns, __ATOMIC_RELAXED);
    return a && plat_now_ns() - a < 2000000000ull ? 1 : 2;
}

void vk_aa_release(void) {   // before the device goes away
    VkCtx *c = vk_ctx();
    if (!c || !A.tried) return;
    if (A.cur) free_pair(A.cur);
    A.cur = NULL;
    if (A.pipe) vkDestroyPipeline(c->device, A.pipe, NULL);
    if (A.layout) vkDestroyPipelineLayout(c->device, A.layout, NULL);
    if (A.dsl) vkDestroyDescriptorSetLayout(c->device, A.dsl, NULL);
    if (A.sampler) vkDestroySampler(c->device, A.sampler, NULL);
    A.pipe = VK_NULL_HANDLE, A.layout = VK_NULL_HANDLE, A.dsl = VK_NULL_HANDLE, A.sampler = VK_NULL_HANDLE;
    A.tried = A.ok = 0;
}
