// fastball, our own: the render targets of the capture frame (gfx_stubs.c gfx_capture_arm: F12, MLB_DRAWLOG=game)
// as PNGs, <profile>/shot-<frame>-<n>-<w>x<h>-fmt<NVN format>.png, so a frame's intermediate pictures (an HDR scene,
// exposure targets, UI layers) can be looked at, not just the presented one. Each colour target is blitted into an
// RGBA8 image (the blit converts float and packed formats; values above 1 clamp), copied to a host buffer and written.
// It waits for the queue to go idle first: a diagnosis path, taken once per capture.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "host.h"
#include "nvn_api.h"
#include "nvn_obj.h"
#include "vk.h"

void rt_write_png(const char *path, const uint8_t *rgba, uint32_t w, uint32_t h);   // gfx_stubs.c

static int blit_src_ok(VkPhysicalDevice phys, VkFormat f) {
    VkFormatProperties p;
    vkGetPhysicalDeviceFormatProperties(phys, f, &p);
    return (p.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_SRC_BIT) != 0;
}

static void save_one(VkCtx *c, VkCommandPool pool, const VkTexImage *im, const char *path, uint32_t layer) {
    uint32_t w = im->width, h = im->height;
    VkImage tmp = VK_NULL_HANDLE;
    VmaAllocation tmp_a = NULL, buf_a = NULL;
    VkBuffer buf = VK_NULL_HANDLE;
    VkImageCreateInfo ii = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                            .format = VK_FORMAT_R8G8B8A8_UNORM, .extent = {w, h, 1}, .mipLevels = 1, .arrayLayers = 1,
                            .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                            .usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT};
    VmaAllocationCreateInfo ia = {.usage = VMA_MEMORY_USAGE_AUTO};
    VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = (VkDeviceSize)w * h * 4,
                             .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    VmaAllocationCreateInfo ba = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
                                  .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
    VmaAllocationInfo binfo;
    if (vmaCreateImage(c->vma, &ii, &ia, &tmp, &tmp_a, NULL) != VK_SUCCESS ||
        vmaCreateBuffer(c->vma, &bi, &ba, &buf, &buf_a, &binfo) != VK_SUCCESS || !binfo.pMappedData) {
        rt_log("capture: %s: no staging memory", path);
        goto done;
    }
    VkCommandBufferAllocateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                      .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    VkCommandBuffer cb;
    if (vkAllocateCommandBuffers(c->device, &ci, &cb) != VK_SUCCESS) goto done;
    VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                      .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    vkBeginCommandBuffer(cb, &begin);
    VkImageMemoryBarrier b0 = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
                               .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED, .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                               .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                               .image = tmp, .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &b0);
    VkImageBlit region = {.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, layer, 1},
                          .srcOffsets = {{0, 0, 0}, {(int32_t)w, (int32_t)h, 1}},
                          .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                          .dstOffsets = {{0, 0, 0}, {(int32_t)w, (int32_t)h, 1}}};
    vkCmdBlitImage(cb, im->image, VK_IMAGE_LAYOUT_GENERAL, tmp, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region,
                   VK_FILTER_NEAREST);
    VkImageMemoryBarrier b1 = b0;
    b1.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, b1.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    b1.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, b1.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &b1);
    VkBufferImageCopy copy = {.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, .imageExtent = {w, h, 1}};
    vkCmdCopyImageToBuffer(cb, tmp, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buf, 1, &copy);
    vkEndCommandBuffer(cb);
    VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
    vk_queue_lock();
    VkResult r = vkQueueSubmit(c->gfx_queue, 1, &si, VK_NULL_HANDLE);
    if (r == VK_SUCCESS) r = vkQueueWaitIdle(c->gfx_queue);
    vk_queue_unlock();
    vkFreeCommandBuffers(c->device, pool, 1, &cb);
    if (r != VK_SUCCESS) {
        rt_log("capture: %s: submit failed (%d)", path, (int)r);
        goto done;
    }
    vmaInvalidateAllocation(c->vma, buf_a, 0, VK_WHOLE_SIZE);
    uint8_t *px = binfo.pMappedData;
    for (uint64_t i = 3; i < (uint64_t)w * h * 4; i += 4) px[i] = 255;   // the picture, not its alpha
    rt_write_png(path, px, w, h);
    rt_log("capture: %s", path);
done:
    if (buf) vmaDestroyBuffer(c->vma, buf, buf_a);
    if (tmp) vmaDestroyImage(c->vma, tmp, tmp_a);
}

// The GPU's bytes of [addr, addr+n) (a mirror's device-local copy when the pool has one), copied through a host buffer.
// The queue must be idle (vk_drawq_report runs after vk_capture_targets). 0 when the range is not backed.
// Level 0 of a sampled image as the GPU holds it: byte sum and nonzero bytes (layout-independent, so comparable with the
// guest's tiled storage) over its packed size *bytes. Images stay in GENERAL. 0 when it could not be read.
int vk_capture_image_sum(const VkTexImage *im, uint64_t *sum, uint64_t *nz, uint64_t *bytes) {
    VkCtx *c = vk_ctx();
    if (!c || !im || !im->image || (im->aspect & ~VK_IMAGE_ASPECT_COLOR_BIT) || im->samples > 1) return 0;
    int bc8 = (im->format >= VK_FORMAT_BC1_RGB_UNORM_BLOCK && im->format <= VK_FORMAT_BC1_RGBA_SRGB_BLOCK) ||
              im->format == VK_FORMAT_BC4_UNORM_BLOCK || im->format == VK_FORMAT_BC4_SNORM_BLOCK;
    int bc = im->format >= VK_FORMAT_BC1_RGB_UNORM_BLOCK && im->format <= VK_FORMAT_BC7_SRGB_BLOCK;
    uint64_t n = bc ? (uint64_t)((im->width + 3) / 4) * ((im->height + 3) / 4) * (bc8 ? 8 : 16)
                    : (uint64_t)im->width * im->height * 16;   // uncompressed: an upper bound, the tail stays zero
    if (n > (64u << 20)) return 0;
    VkBuffer buf = VK_NULL_HANDLE;
    VmaAllocation ba = NULL;
    VmaAllocationInfo info;
    VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = n, .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
                                  .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
    if (vmaCreateBuffer(c->vma, &bi, &ai, &buf, &ba, &info) != VK_SUCCESS || !info.pMappedData) return 0;
    memset(info.pMappedData, 0, n);
    VkCommandPoolCreateInfo pi = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                  .flags = VK_COMMAND_POOL_CREATE_TRANSIENT_BIT, .queueFamilyIndex = c->gfx_family};
    VkCommandPool pool;
    int ok = 0;
    if (vkCreateCommandPool(c->device, &pi, NULL, &pool) == VK_SUCCESS) {
        VkCommandBufferAllocateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                          .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
        VkCommandBuffer cb;
        if (vkAllocateCommandBuffers(c->device, &ci, &cb) == VK_SUCCESS) {
            VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                              .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
            vkBeginCommandBuffer(cb, &begin);
            VkBufferImageCopy cp = {.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                                    .imageExtent = {im->width, im->height, 1}};
            vkCmdCopyImageToBuffer(cb, im->image, VK_IMAGE_LAYOUT_GENERAL, buf, 1, &cp);
            vkEndCommandBuffer(cb);
            VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
            vk_queue_lock();
            VkResult r = vkQueueSubmit(c->gfx_queue, 1, &si, VK_NULL_HANDLE);
            if (r == VK_SUCCESS) r = vkQueueWaitIdle(c->gfx_queue);
            vk_queue_unlock();
            if (r == VK_SUCCESS) {
                vmaInvalidateAllocation(c->vma, ba, 0, VK_WHOLE_SIZE);
                const uint8_t *b = info.pMappedData;
                uint64_t s = 0, z = 0;
                for (uint64_t i = 0; i < n; i++) s += b[i], z += b[i] != 0;
                *sum = s, *nz = z, *bytes = n;
                ok = 1;
            }
        }
        vkDestroyCommandPool(c->device, pool, NULL);
    }
    vmaDestroyBuffer(c->vma, buf, ba);
    return ok;
}

int vk_capture_read(uint64_t addr, void *out, uint32_t n) {
    VkCtx *c = vk_ctx();
    VkMemSpan sp;
    if (!c || !n || !vk_mem_resolve(addr, n, &sp)) return 0;
    VkBuffer buf = VK_NULL_HANDLE;
    VmaAllocation ba = NULL;
    VmaAllocationInfo info;
    VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = n, .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
                                  .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
    if (vmaCreateBuffer(c->vma, &bi, &ai, &buf, &ba, &info) != VK_SUCCESS || !info.pMappedData) return 0;
    VkCommandPoolCreateInfo pi = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                  .flags = VK_COMMAND_POOL_CREATE_TRANSIENT_BIT, .queueFamilyIndex = c->gfx_family};
    VkCommandPool pool;
    int ok = 0;
    if (vkCreateCommandPool(c->device, &pi, NULL, &pool) == VK_SUCCESS) {
        VkCommandBufferAllocateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                          .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
        VkCommandBuffer cb;
        if (vkAllocateCommandBuffers(c->device, &ci, &cb) == VK_SUCCESS) {
            VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                              .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
            vkBeginCommandBuffer(cb, &begin);
            VkBufferCopy cp = {sp.offset, 0, n};
            vkCmdCopyBuffer(cb, sp.buffer, buf, 1, &cp);
            vkEndCommandBuffer(cb);
            VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
            vk_queue_lock();
            VkResult r = vkQueueSubmit(c->gfx_queue, 1, &si, VK_NULL_HANDLE);
            if (r == VK_SUCCESS) r = vkQueueWaitIdle(c->gfx_queue);
            vk_queue_unlock();
            if (r == VK_SUCCESS) {
                vmaInvalidateAllocation(c->vma, ba, 0, VK_WHOLE_SIZE);
                memcpy(out, info.pMappedData, n);
                ok = 1;
            }
        }
        vkDestroyCommandPool(c->device, pool, NULL);
    }
    vmaDestroyBuffer(c->vma, buf, ba);
    return ok;
}

// fastball diagnosis: the newest texture object of each image the address watch saw created (vk_texture.c
// create_tex), saved with the capture frame's targets as shot-<2000000+frame>-*.png (vk_drawq_report).
static tex_t wt[24];
static int nwt;
void vk_watch_note_tex(const tex_t *t) {
    static int next_out;   // fastball: when full, the oldest goes (the newest scene's images are the ones saved)
    for (int i = 0; i < nwt; i++)
        if (wt[i].mem == t->mem && wt[i].d.format == t->d.format && wt[i].d.target == t->d.target) {
            wt[i] = *t;
            return;
        }
    if (nwt < 24) wt[nwt++] = *t;
    else wt[next_out++ % 24] = *t;
}
void vk_capture_targets(const tex_t *const *ts, int n, uint64_t frame);
void vk_watch_capture(uint64_t frame) {
    static uint64_t done_at;   // fastball: once per capture (vk_drawq_report and vk_exec_frame_log both call it)
    if (done_at && frame - done_at < 3) return;
    done_at = frame;
    const tex_t *p[24];
    for (int i = 0; i < nwt; i++) {
        p[i] = &wt[i];
        rt_log("watch: capture saves watched image %d: %#llx nvn fmt %#x %ux%ux%u target %d", i,
               (unsigned long long)(uintptr_t)wt[i].mem, (unsigned)wt[i].d.format, (unsigned)wt[i].d.width,
               (unsigned)wt[i].d.height, (unsigned)wt[i].d.depth, (int)wt[i].d.target);
    }
    if (nwt) vk_capture_targets(p, nwt, 2000000 + frame);
}

// fastball diagnosis (black heads): images the address watch keeps (vk_watch_keep) are saved as PNGs at the
// present of the frame WK_DELAY frames after the one that armed it, once per run.
enum { WK_DELAY = 30 };
enum { WK_N = 10 };
static tex_t wk[WK_N];
static int wk_set[WK_N], wk_done;
void vk_capture_targets(const tex_t *const *ts, int n, uint64_t frame);
static uint64_t wk_due;
void vk_watch_keep(const tex_t *t, int i, int arm) {
    if (wk_done || i < 0 || i >= WK_N) return;
    wk[i] = *t, wk_set[i] = 1;
    if (arm) wk_due = __atomic_load_n(&gfx_counters.frames, __ATOMIC_RELAXED) + WK_DELAY;
}
void vk_watch_frame(uint64_t frame) {
    if (wk_done || !wk_due || frame < wk_due) return;
    wk_done = 1;
    const tex_t *ts[WK_N];
    int n = 0;
    for (int i = 0; i < WK_N; i++)
        if (wk_set[i]) ts[n++] = &wk[i];
    rt_log("watch: saving %d kept image(s) at frame %llu", n, (unsigned long long)frame);
    vk_capture_targets(ts, n, frame);
}

// fastball: layer 0, level 0 of a D16 / D32 / X8_D24 depth image as a grayscale PNG, stretched from the smallest
// depth to the largest below 1 (a cleared 1.0 is white); the range goes to the log.
static void save_depth(VkCtx *c, VkCommandPool pool, const VkTexImage *im, const char *path) {
    uint32_t w = im->width, h = im->height, bpt;
    switch (im->format) {
    case VK_FORMAT_D16_UNORM: bpt = 2; break;
    case VK_FORMAT_D32_SFLOAT: case VK_FORMAT_X8_D24_UNORM_PACK32: case VK_FORMAT_D32_SFLOAT_S8_UINT:
    case VK_FORMAT_D24_UNORM_S8_UINT: bpt = 4; break;
    default: return;
    }
    VkBuffer buf;
    VmaAllocation ba;
    VmaAllocationInfo info;
    VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = (VkDeviceSize)w * h * bpt,
                             .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
                                  .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
    if (vmaCreateBuffer(c->vma, &bi, &ai, &buf, &ba, &info) != VK_SUCCESS) return;
    VkCommandBufferAllocateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                      .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    VkCommandBuffer cb;
    if (vkAllocateCommandBuffers(c->device, &ci, &cb) == VK_SUCCESS) {
        VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                          .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
        vkBeginCommandBuffer(cb, &begin);
        VkBufferImageCopy copy = {.imageSubresource = {VK_IMAGE_ASPECT_DEPTH_BIT, 0, 0, 1}, .imageExtent = {w, h, 1}};
        vkCmdCopyImageToBuffer(cb, im->image, VK_IMAGE_LAYOUT_GENERAL, buf, 1, &copy);
        vkEndCommandBuffer(cb);
        VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
        vk_queue_lock();
        VkResult r = vkQueueSubmit(c->gfx_queue, 1, &si, VK_NULL_HANDLE);
        if (r == VK_SUCCESS) r = vkQueueWaitIdle(c->gfx_queue);
        vk_queue_unlock();
        vkFreeCommandBuffers(c->device, pool, 1, &cb);
        uint8_t *px = r == VK_SUCCESS ? malloc((size_t)w * h * 4) : NULL;
        if (px) {
            vmaInvalidateAllocation(c->vma, ba, 0, VK_WHOLE_SIZE);
            const uint8_t *b = info.pMappedData;
            float lo = 1, hi = 0;
            uint64_t ones = 0;
            float *d = malloc((size_t)w * h * sizeof(float));
            if (d) {
                for (uint64_t i = 0; i < (uint64_t)w * h; i++) {
                    float v;
                    if (bpt == 2) v = (float)((const uint16_t *)b)[i] / 65535.0f;
                    else if (im->format == VK_FORMAT_D32_SFLOAT || im->format == VK_FORMAT_D32_SFLOAT_S8_UINT) memcpy(&v, b + 4 * i, 4);
                    else v = (float)(((const uint32_t *)b)[i] & 0xffffff) / 16777215.0f;
                    d[i] = v;
                    if (v >= 1.0f) ones++;
                    else { if (v < lo) lo = v; if (v > hi) hi = v; }
                }
                for (uint64_t i = 0; i < (uint64_t)w * h; i++) {
                    float v = d[i] >= 1.0f ? 1.0f : hi > lo ? (d[i] - lo) / (hi - lo) * 0.9f : 0.0f;
                    uint8_t g = (uint8_t)(v * 255.0f);
                    px[4 * i] = px[4 * i + 1] = px[4 * i + 2] = g, px[4 * i + 3] = 255;
                }
                free(d);
                rt_write_png(path, px, w, h);
                rt_log("capture: %s (depth %g..%g below 1, %llu of %u texels at 1)", path, lo, hi, (unsigned long long)ones, w * h);
            }
            free(px);
        }
    }
    vmaDestroyBuffer(c->vma, buf, ba);
}

static float half_to_float(uint16_t h) {
    uint32_t sg = h >> 15, e = h >> 10 & 31, m = h & 1023;
    float v = e == 0 ? m / 1024.0f / 16384.0f : e == 31 ? 65504.0f : (1.0f + m / 1024.0f) * ldexpf(1.0f, (int)e - 15);
    return sg ? -v : v;
}
static float uf(uint32_t bits, int mb) {   // unsigned 5-bit-exponent float with mb mantissa bits (B10G11R11)
    uint32_t e = bits >> mb & 31, m = bits & ((1u << mb) - 1);
    return e == 0 ? m / (float)(1u << mb) * ldexpf(1.0f, -14) : e == 31 ? 65504.0f : (1.0f + m / (float)(1u << mb)) * ldexpf(1.0f, (int)e - 15);
}
static int cmpf_cap(const void *a, const void *b) {
    float x = *(const float *)a, y = *(const float *)b;
    return x < y ? -1 : x > y;
}

// fastball: level 0 of an R11G11B10F or RGBA16F image decoded from its raw bits: value statistics of the brightest
// channel per texel to the log, and a PNG scaled so the 99th percentile is white (sRGB-encoded), no 8-bit blit first.
static void save_hdr_layer(VkCtx *c, VkCommandPool pool, const VkTexImage *im, const char *path, uint32_t layer);
static void save_hdr(VkCtx *c, VkCommandPool pool, const VkTexImage *im, const char *path) {
    uint32_t nl = im->type == VK_IMAGE_TYPE_3D ? (im->depth < 64 ? im->depth : 64) : im->layers < 8 ? im->layers : 8;
    for (uint32_t l = 0; l < nl; l++) {   // layers, or depth slices of a 3D image
        char p[1300];
        if (l) snprintf(p, sizeof p, "%.*s-layer%u.png", (int)(strlen(path) - 4), path, l);
        save_hdr_layer(c, pool, im, l ? p : path, l);
    }
}
static void save_hdr_layer(VkCtx *c, VkCommandPool pool, const VkTexImage *im, const char *path, uint32_t layer) {
    uint32_t w = im->width, h = im->height, bpt = im->format == VK_FORMAT_B10G11R11_UFLOAT_PACK32 ? 4 : 8;
    VkBuffer buf;
    VmaAllocation ba;
    VmaAllocationInfo info;
    VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = (VkDeviceSize)w * h * bpt,
                             .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
                                  .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
    if (vmaCreateBuffer(c->vma, &bi, &ai, &buf, &ba, &info) != VK_SUCCESS) return;
    VkCommandBufferAllocateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                      .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    VkCommandBuffer cb;
    if (vkAllocateCommandBuffers(c->device, &ci, &cb) == VK_SUCCESS) {
        VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                          .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
        vkBeginCommandBuffer(cb, &begin);
        int is3d = im->type == VK_IMAGE_TYPE_3D;
        VkBufferImageCopy copy = {.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, is3d ? 0 : layer, 1},
                                  .imageOffset = {0, 0, is3d ? (int32_t)layer : 0}, .imageExtent = {w, h, 1}};
        vkCmdCopyImageToBuffer(cb, im->image, VK_IMAGE_LAYOUT_GENERAL, buf, 1, &copy);
        vkEndCommandBuffer(cb);
        VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
        vk_queue_lock();
        VkResult r = vkQueueSubmit(c->gfx_queue, 1, &si, VK_NULL_HANDLE);
        if (r == VK_SUCCESS) r = vkQueueWaitIdle(c->gfx_queue);
        vk_queue_unlock();
        vkFreeCommandBuffers(c->device, pool, 1, &cb);
        uint64_t n = (uint64_t)w * h;
        float *rgb = r == VK_SUCCESS ? malloc(n * 3 * sizeof(float)) : NULL, *mx = rgb ? malloc(n * sizeof(float)) : NULL;
        uint8_t *px = mx ? malloc(n * 4) : NULL;
        if (px) {
            vmaInvalidateAllocation(c->vma, ba, 0, VK_WHOLE_SIZE);
            const uint8_t *b = info.pMappedData;
            uint64_t n_bad = 0, n_zero = 0;   // texels with an Inf/NaN colour channel; texels with all colour channels 0
            for (uint64_t i = 0; i < n; i++) {
                float v[3];
                int bad = 0;
                if (bpt == 4) {
                    uint32_t x;
                    memcpy(&x, b + 4 * i, 4);
                    bad = (x >> 6 & 31) == 31 || (x >> 17 & 31) == 31 || (x >> 27 & 31) == 31;
                    v[0] = uf(x & 0x7ff, 6), v[1] = uf(x >> 11 & 0x7ff, 6), v[2] = uf(x >> 22, 5);
                } else {
                    uint16_t x[4];
                    memcpy(x, b + 8 * i, 8);
                    for (int k = 0; k < 3; k++) {
                        bad |= (x[k] >> 10 & 31) == 31;
                        v[k] = half_to_float(x[k]);
                        if (v[k] != v[k] || v[k] > 65504.0f) v[k] = 65504.0f;
                        if (v[k] < -65504.0f) v[k] = -65504.0f;
                    }
                }
                n_bad += bad, n_zero += v[0] == 0 && v[1] == 0 && v[2] == 0;
                memcpy(rgb + 3 * i, v, sizeof v);
                mx[i] = v[0] > v[1] ? (v[0] > v[2] ? v[0] : v[2]) : (v[1] > v[2] ? v[1] : v[2]);
            }
            qsort(mx, n, sizeof(float), cmpf_cap);
            float p50 = mx[n / 2], p99 = mx[n * 99 / 100], top = mx[n - 1], scale = p99 > 0 ? 1.0f / p99 : 1.0f;
            uint64_t distinct = 1;
            for (uint64_t i = 1; i < n; i++) distinct += mx[i] != mx[i - 1];
            for (uint64_t i = 0; i < n; i++)
                for (int k = 0; k < 3; k++) {
                    float v = rgb[3 * i + k] * scale;
                    v = v <= 0 ? 0 : v >= 1 ? 1 : v < 0.0031308f ? v * 12.92f : 1.055f * powf(v, 1 / 2.4f) - 0.055f;
                    px[4 * i + k] = (uint8_t)(v * 255.0f + 0.5f);
                }
            for (uint64_t i = 0; i < n; i++) px[4 * i + 3] = 255;
            rt_write_png(path, px, w, h);
            rt_log("capture: %s (brightest channel: median %g, 99th percentile %g, max %g, min %g; %llu distinct values; "
                   "scaled x%g; %llu of %llu texels Inf/NaN, %llu black)", path, p50, p99, top, mx[0], (unsigned long long)distinct,
                   scale, (unsigned long long)n_bad, (unsigned long long)n, (unsigned long long)n_zero);
        }
        free(rgb), free(mx), free(px);
    }
    vmaDestroyBuffer(c->vma, buf, ba);
}

// fastball: a BC6H image's real values: each layer (up to 8) of level 0 blitted into an RGBA16F image (no clamp)
// and decoded by save_hdr_layer.
static void save_bc6h(VkCtx *c, VkCommandPool pool, const VkTexImage *im, const char *path) {
    uint32_t w = im->width, h = im->height, nl = im->layers < 8 ? im->layers : 8;
    VkImage tmp;
    VmaAllocation ta;
    VkImageCreateInfo ii = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                            .format = VK_FORMAT_R16G16B16A16_SFLOAT, .extent = {w, h, 1}, .mipLevels = 1, .arrayLayers = 1,
                            .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                            .usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT};
    VmaAllocationCreateInfo ia = {.usage = VMA_MEMORY_USAGE_AUTO};
    if (vmaCreateImage(c->vma, &ii, &ia, &tmp, &ta, NULL) != VK_SUCCESS) return;
    for (uint32_t l = 0; l < nl; l++) {
        VkCommandBufferAllocateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                          .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
        VkCommandBuffer cb;
        if (vkAllocateCommandBuffers(c->device, &ci, &cb) != VK_SUCCESS) break;
        VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                          .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
        vkBeginCommandBuffer(cb, &begin);
        VkImageMemoryBarrier b0 = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
                                   .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED, .newLayout = VK_IMAGE_LAYOUT_GENERAL,
                                   .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                                   .image = tmp, .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
        vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &b0);
        VkImageBlit region = {.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, l, 1},
                              .srcOffsets = {{0, 0, 0}, {(int32_t)w, (int32_t)h, 1}},
                              .dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                              .dstOffsets = {{0, 0, 0}, {(int32_t)w, (int32_t)h, 1}}};
        vkCmdBlitImage(cb, im->image, VK_IMAGE_LAYOUT_GENERAL, tmp, VK_IMAGE_LAYOUT_GENERAL, 1, &region, VK_FILTER_NEAREST);
        VkMemoryBarrier mb = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER, .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
                              .dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT};
        vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &mb, 0, NULL, 0, NULL);
        vkEndCommandBuffer(cb);
        VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
        vk_queue_lock();
        VkResult r = vkQueueSubmit(c->gfx_queue, 1, &si, VK_NULL_HANDLE);
        if (r == VK_SUCCESS) r = vkQueueWaitIdle(c->gfx_queue);
        vk_queue_unlock();
        vkFreeCommandBuffers(c->device, pool, 1, &cb);
        if (r != VK_SUCCESS) break;
        VkTexImage f = *im;
        f.image = tmp, f.format = VK_FORMAT_R16G16B16A16_SFLOAT, f.layers = 1, f.levels = 1;
        char lp[1300];
        snprintf(lp, sizeof lp, "%.*s-bc6h-layer%u.png", (int)(strlen(path) - 4), path, l);
        save_hdr_layer(c, pool, &f, lp, 0);
    }
    vmaDestroyImage(c->vma, tmp, ta);
}

void vk_capture_targets(const tex_t *const *ts, int n, uint64_t frame) {
    VkCtx *c = vk_ctx();
    if (!c || !n) return;
    VkCommandPoolCreateInfo pi = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                  .flags = VK_COMMAND_POOL_CREATE_TRANSIENT_BIT, .queueFamilyIndex = c->gfx_family};
    VkCommandPool pool;
    if (vkCreateCommandPool(c->device, &pi, NULL, &pool) != VK_SUCCESS) return;
    vk_queue_lock();
    vkQueueWaitIdle(c->gfx_queue);   // the frame's rendering is done
    vk_queue_unlock();
    for (int i = 0; i < n; i++) {
        const VkTexImage *im = ts[i] ? vk_texture_get(ts[i]) : NULL;
        if (im && im->image != VK_NULL_HANDLE && (im->aspect & VK_IMAGE_ASPECT_DEPTH_BIT) && im->samples == 1 &&
            im->type == VK_IMAGE_TYPE_2D) {
            char path[1200];
            snprintf(path, sizeof path, "%s/shot-%llu-%d-%ux%u-fmt%#x-depth.png", rt_config()->profile,
                     (unsigned long long)frame, i, im->width, im->height, (unsigned)ts[i]->d.format);
            save_depth(c, pool, im, path);
            continue;
        }
        if (im && im->image != VK_NULL_HANDLE && im->samples == 1 && im->type == VK_IMAGE_TYPE_2D &&
            (im->format == VK_FORMAT_BC6H_UFLOAT_BLOCK || im->format == VK_FORMAT_BC6H_SFLOAT_BLOCK)) {
            char hp[1200];
            snprintf(hp, sizeof hp, "%s/shot-%llu-%d-%ux%u-fmt%#x.png", rt_config()->profile, (unsigned long long)frame, i,
                     im->width, im->height, (unsigned)ts[i]->d.format);
            save_bc6h(c, pool, im, hp);
        }
        if (im && im->image != VK_NULL_HANDLE && im->samples == 1 &&
            (im->type == VK_IMAGE_TYPE_2D || im->type == VK_IMAGE_TYPE_3D) &&
            (im->format == VK_FORMAT_B10G11R11_UFLOAT_PACK32 || im->format == VK_FORMAT_R16G16B16A16_SFLOAT)) {
            char hp[1200];
            snprintf(hp, sizeof hp, "%s/shot-%llu-%d-%ux%u-fmt%#x-hdr.png", rt_config()->profile, (unsigned long long)frame,
                     i, im->width, im->height, (unsigned)ts[i]->d.format);
            save_hdr(c, pool, im, hp);
        }
        if (!im || im->image == VK_NULL_HANDLE || !(im->aspect & VK_IMAGE_ASPECT_COLOR_BIT) || im->samples > 1 ||
            im->type != VK_IMAGE_TYPE_2D || !blit_src_ok(c->phys, im->format))
            continue;
        uint32_t nl = im->layers < 8 ? im->layers : 8;
        for (uint32_t l = 0; l < nl; l++) {   // fastball: every layer (up to 8) of an array or cube
            char path[1200];
            if (l)
                snprintf(path, sizeof path, "%s/shot-%llu-%d-%ux%u-fmt%#x-layer%u.png", rt_config()->profile,
                         (unsigned long long)frame, i, im->width, im->height, (unsigned)ts[i]->d.format, l);
            else
                snprintf(path, sizeof path, "%s/shot-%llu-%d-%ux%u-fmt%#x.png", rt_config()->profile,
                         (unsigned long long)frame, i, im->width, im->height, (unsigned)ts[i]->d.format);
            save_one(c, pool, im, path, l);
        }
    }
    vkDestroyCommandPool(c->device, pool, NULL);
}
