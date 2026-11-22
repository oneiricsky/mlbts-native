// Transfers of the Vulkan op-stream replay: buffer and texture copies, texture
// clears, event signals, counter reports and conditional rendering. vk_exec.c calls vk_exec_op_xfer for these ops.
//
// Buffers are guest memory: vk_mem_resolve maps an address to the VkBuffer behind its pool, textures are the vk_texture.c images
// (linear texel layout, GENERAL layout; block-linear storage is only converted when a mirrored texture is uploaded). So a
// copy is one Vulkan transfer command and the pitch of a buffer side comes from the payload (OP_COPY_STRIDE or the
// tight row). Every copy ends the open pass and starts with a full barrier. Destinations: an image is marked
// GPU-written at record time; a CPU-visible buffer range is reported to vk_gpu_written once the GPU is done (write
// watch does not see GPU writes, textures stored there re-upload).
//
// Events and counters are CPU-visible side effects. Their values go into guest memory on the completion thread through
// vk_completion_add, in submit order, as gfx_null.c does: event WRITE / ADD, counter {0, timestamp} for every type but
// samples passed. A timestamp report puts 0 in the counter word: TOTK gates its clears on two such words being unequal.
//
// Samples passed (NVN_COUNTER_TYPE_SAMPLES_PASSED) is a running count on the queue: RESET_COUNTER zeroes it, every
// draw after it adds the samples that passed the depth and stencil tests, REPORT_COUNTER writes the running value.
// TOTK resets and reports it 3 to 8 times a frame in the field and its CPU reads the results back (f_70010c3298); a 0
// there culls what the query tested. The replay counts with Vulkan occlusion queries ("occlusion counts" below).
//
// Conditional rendering is a CPU-side skip, not VK_EXT_conditional_rendering: the extension compares one 32-bit word
// with zero, NVN compares the counter words at addr and addr + 16. The condition is evaluated when the op is recorded
// from guest memory; a counter reported by an earlier submission that is not done yet counts as 0 if it is a timestamp,
// as unknown if it is samples passed. An unknown count renders: the report usually sits in the command buffer being
// recorded, so its value cannot be waited for, and the word in memory still holds an older query's count. Rendering
// costs at most the work the condition would have saved (MacNativeGames nvn_mtl.m decides the same); in the field
// TOTK conditions only on timestamp reports. The condition sets VkExec.render_disabled, which vk_exec.c honours for
// clears and vk_exec_draw.c for draws and dispatches. A condition that cannot be read (address outside every pool)
// renders.
// Copies and CLEAR_TEX are not conditional (as in MacNativeGames, nvn_mtl.m).
//
// The copy semantics (region and layer arithmetic, row and image strides, whole-level clears, copy / blit / resolve
// choice) follow MacNativeGames games/totk/third_party/d2r_gfx/gfx/nvn/nvn_mtl.m:10080-10368, 10618-10642, 1700-1725
// (https://github.com/ly05010419/MacNativeGames @ b75be8cfa704df3701e86130c8ced268e79d6b11, MIT, Copyright (c) 2026
// jhaizhou) and LAS Recomp runtime/nvn/vulkan/exec.c:3045-3235 (https://github.com/peiikai/LASRecomp @
// da35b83a9611d046a9a681aae668d7085954d37f, MIT, Copyright (c) 2026 Peiikai).
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"
#include "nvn_api.h"
#include "nvn_tex.h"
#include "tex.h"
#include "vk.h"
#include "vk_exec.h"

enum { W_FORMAT, W_REGION, W_BUFFER, W_OVERLAP, W_COPY, W_CLEAR, W_QUERY, W_COUNT };

static void warn_once(int key, const char *fmt, ...) {
    static volatile int32_t seen[W_COUNT];
    if (__atomic_exchange_n(&seen[key], 1, __ATOMIC_RELAXED)) return;
    char msg[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    rt_log("vk: %s (logged once)", msg);
}

static uint32_t max1(uint32_t v) { return v ? v : 1; }
int vk_watch_hit(uint64_t a, uint64_t n);   // vk_texture.c (fastball diagnosis)

// ---- completion callbacks (completion thread)

typedef struct { uint64_t addr, size; } Range;

static void guest_written_cb(void *arg) {
    Range *r = arg;
    vk_gpu_written(r->addr, r->size);
    free(r);
}

// The GPU wrote [addr, addr+size) of CPU-visible memory: tell the texture cache once the fence is reached.
static void note_gpu_write(VkExec *ex, uint64_t addr, uint64_t size) {
    vk_usnap_drop(addr, size);
    vk_exec_ub_foreign(ex, addr, size);
    if (nvn_gpu_only(addr)) return;
    Range *r = malloc(sizeof *r);
    if (!r) rt_fatal("vk: out of memory");
    *r = (Range){addr, size};
    vk_mem_gpu_pending(addr, size);
    vk_completion_add(ex->fence, guest_written_cb, r);
}

typedef struct { volatile uint32_t *val; uint32_t mode, value; uint64_t fence; } EventWrite;

// fastball diagnosis (MLB_TRACE=perf): per event word, the timeline value of its newest signal, when the replay
// recorded it and when its write was applied, for gfx_event_story. At each batter walk-up of 1.0.20 the game's main
// thread spins in its GPU wait (f_70005a1a90 polls nvnEventGetValue until the count it signalled is reached) for
// about half a second while the replay and the GPU look idle half of that time. The replay thread fills an entry, the
// completion thread (or the poll) marks it applied; read racily by the polling thread.
#define EVS_N 64
static struct { volatile uint32_t *val; volatile uint64_t fence, rec_ns, applied_ns, applied_fence; } evs[EVS_N];
static int evs_find(const volatile uint32_t *val, int add) {
    unsigned s = (unsigned)(((uintptr_t)val >> 2) * 0x9E3779B1u) % EVS_N;
    for (int k = 0; k < EVS_N; k++, s = (s + 1) % EVS_N) {
        if (evs[s].val == val) return (int)s;
        if (!evs[s].val) {
            if (!add) return -1;
            evs[s].val = (volatile uint32_t *)val;
            return (int)s;
        }
    }
    return -1;
}
static void evs_recorded(const volatile uint32_t *val, uint64_t fence) {
    if (!(rt_trace & RT_TRACE_PERF)) return;
    int s = evs_find(val, 1);
    if (s >= 0) evs[s].fence = fence, evs[s].rec_ns = kern_now_ns();
}
static void evs_applied(const volatile uint32_t *val, uint64_t fence) {
    if (!(rt_trace & RT_TRACE_PERF)) return;
    int s = evs_find(val, 0);
    if (s >= 0) evs[s].applied_fence = fence, evs[s].applied_ns = kern_now_ns();
}
void gfx_fence_story(uint64_t v, uint64_t t0, char *b, size_t n);   // vk_backend.c
// One line for a long wait on the event word val that began at t0 (nvn_api_core.c): its newest signal, that signal's
// submission (queued, replayed), and the timeline with the completion queue.
void gfx_event_story(const volatile uint32_t *val, uint64_t t0, char *b, size_t n) {
    char fs[400], cs[300];
    vk_completion_story(cs, sizeof cs);
    int s = evs_find(val, 0);
    if (s < 0) {
        snprintf(b, n, "no signal of it replayed yet; %s", cs);
        return;
    }
    uint64_t f = evs[s].fence, af = evs[s].applied_fence;
    double ms = 1e-6;
    gfx_fence_story(f, t0, fs, sizeof fs);
    snprintf(b, n, "newest signal: value %llu, recorded %+.1f ms; last applied: value %llu at %+.1f ms (from the wait's "
             "start); %s; %s", (unsigned long long)f, ((double)evs[s].rec_ns - (double)t0) * ms, (unsigned long long)af,
             af ? ((double)evs[s].applied_ns - (double)t0) * ms : 0.0, fs, cs);
}

// fastball diagnosis (MLB_TRACE=perf): the game's GPU waits in bursts. Each batter walk-up of 1.0.20 is about 50
// waits in a row (submit, wait for the event, submit the next), each under 30 ms, about 10 ms apiece, with the replay
// thread idle about 60 % of the time. nvn_api_core.c calls this when a thread's poll of an event word ends (the value
// moved on or another event was polled): t0 the first poll at the old value, t1 now, polls how many. Waits closer than
// 50 ms to the last one form a burst; a burst that waited 100 ms or more gets one line: per wait, from its start, when
// the submission whose signal ended it was queued for the replay, replayed, submitted, seen reached by the completion
// thread and applied, and when the game saw it. The replay of those submissions is also split into its phases
// (vk_sync_phase_times: before the submit, recording, upload flush, mirror prologue, queue submit, tail), which says
// where the port's share of each wait goes. Per thread (the main thread's are the ones that matter).
int gfx_fence_times(uint64_t v, uint64_t *enq, uint64_t *rs, uint64_t *re);   // vk_backend.c
static _Thread_local struct {
    uint64_t start, last_end, n, waited, timed, ptimed, omin, omax, h0_first, h0_last, nsame;
    double s[7], p[7];
} EB;
static void eb_flush(void) {
    if (EB.n && EB.waited >= 100000000ull) {
        double k = EB.timed ? 1e-6 / (double)EB.timed : 0;
        double pk = EB.ptimed ? 1e-6 / (double)EB.ptimed : 0;
        double po = EB.ptimed ? 1.0 / (double)EB.ptimed : 0;
        double span = (double)(EB.last_end - EB.start);
        rt_log("nvn: game GPU wait burst: %llu waits over %.1f ms (%.1f ms waiting, the game ran %.2f ms between waits); "
               "per wait from its start (%llu timed): queued %+.2f, replay start %+.2f, end %+.2f, submitted %+.2f, "
               "GPU reached (seen) %+.2f, applied %+.2f, seen by the game %+.2f ms; the replay split (%llu timed): "
               "before submit %+.2f (drain, textures, lock), record %+.2f of %.0f commands (%llu to %llu; %llu of %llu "
               "submissions the same first buffer as the one before), upload flush %+.2f, prologue %+.2f (shadow, "
               "mirror), queue submit %+.2f, tail %+.2f ms (frame %llu)",
               (unsigned long long)EB.n, span / 1e6, EB.waited / 1e6, (span - (double)EB.waited) / 1e6 / (double)EB.n,
               (unsigned long long)EB.timed, EB.s[0] * k, EB.s[1] * k, EB.s[2] * k, EB.s[3] * k, EB.s[4] * k,
               EB.s[5] * k, EB.s[6] * k, (unsigned long long)EB.ptimed, EB.p[0] * pk, EB.p[1] * pk, EB.p[6] * po,
               (unsigned long long)EB.omin, (unsigned long long)EB.omax, (unsigned long long)EB.nsame,
               (unsigned long long)EB.ptimed, EB.p[2] * pk, EB.p[3] * pk, EB.p[4] * pk, EB.p[5] * pk,
               (unsigned long long)gfx_counters.frames);
    }
    memset(&EB, 0, sizeof EB);
}
void gfx_event_wait_end(const volatile uint32_t *val, uint64_t t0, uint64_t t1, uint64_t polls) {
    if (EB.n && (t0 > EB.last_end + 50000000ull || t1 > EB.start + 1000000000ull)) eb_flush();
    if (polls < 2) return;   // found at once: not a wait
    if (!EB.n) EB.start = t0;
    EB.n++, EB.waited += t1 - t0, EB.last_end = t1;
    int s = evs_find(val, 0);
    if (s < 0) return;
    uint64_t f = evs[s].applied_fence, app = evs[s].applied_ns, enq, rs, re, sub, seen, beg, rec, fl, pro;
    uint32_t ops = 0;
    if (!f || app < t0 || !gfx_fence_times(f, &enq, &rs, &re) || !vk_sync_value_times(f, &sub, &seen) || !rs || !re ||
        !seen)
        return;
    double d[7] = {(double)enq - (double)t0, (double)rs - (double)t0, (double)re - (double)t0, (double)sub - (double)t0,
                   (double)seen - (double)t0, (double)app - (double)t0, (double)t1 - (double)t0};
    for (int i = 0; i < 7; i++) EB.s[i] += d[i];
    EB.timed++;
    if (vk_sync_phase_times(f, &beg, &rec, &fl, &pro, &ops) && beg >= rs && rec >= beg && fl >= rec && pro >= fl &&
        sub >= pro && re >= sub) {
        double p[7] = {(double)beg - (double)rs, (double)rec - (double)beg, (double)fl - (double)rec,
                       (double)pro - (double)fl, (double)sub - (double)pro, (double)re - (double)sub, (double)ops};
        for (int i = 0; i < 7; i++) EB.p[i] += p[i];
        uint64_t h0 = vk_sync_submit_h0(f);
        if (!EB.ptimed) EB.omin = EB.omax = ops, EB.h0_first = h0;
        if (ops < EB.omin) EB.omin = ops;
        if (ops > EB.omax) EB.omax = ops;
        if (h0 && h0 == EB.h0_last) EB.nsame++;
        EB.h0_last = h0;
        EB.ptimed++;
    }
}

static void event_cb(void *arg) {
    EventWrite *e = arg;
    if (e->mode == NVN_EVENT_SIGNAL_MODE_ADD) __atomic_fetch_add(e->val, e->value, __ATOMIC_RELEASE);
    else __atomic_store_n(e->val, e->value, __ATOMIC_RELEASE);
    evs_applied(e->val, e->fence);
    free(e);
}

// NVNcounterData = {counter, timestamp}; timestamps are Tegra 19.2 MHz ticks (the base of GetSystemTick).
static void write_counter(uint64_t addr, uint64_t counter) {
    uint64_t rec[2] = {counter, (uint64_t)((unsigned __int128)kern_now_ns() * 12 / 625)};
    memcpy((void *)(uintptr_t)addr, rec, sizeof rec);
}

// fastball experiment (MLB_OQ_FORCE=1; off by default): samples-passed reports
// write at least 1 << 20, and the other non-timestamp counters 1 << 20, instead of the count (or 0).
static int oq_force = -1;
static int oq_force_on(void) {
    if (oq_force < 0) {
        const char *e = cfg_get("MLB_OQ_FORCE");
        oq_force = e && *e && strcmp(e, "0");   // off unless MLB_OQ_FORCE=1 (did not bring the RTTS room's lights back)
        rt_log("vk: counters: %s", oq_force ? "EXPERIMENT: samples-passed and statistics reports forced to at least 1<<20 "
                                              "(MLB_OQ_FORCE=1)" : "as counted");
    }
    return oq_force;
}

typedef struct { uint64_t addr; uint32_t type; } CounterWrite;
static void counter_cb(void *arg) {
    CounterWrite *c = arg;
    int stat = c->type != NVN_COUNTER_TYPE_TIMESTAMP && c->type != NVN_COUNTER_TYPE_TIMESTAMP_TOP;
    write_counter(c->addr, stat && oq_force_on() ? 1u << 20 : 0);
    free(c);
}

// Reports queued by the replay that the GPU has not finished. The condition of RENDER_COND reads a timestamp one as 0
// and a samples-passed one as unknown.
#define PENDING 256
static struct { uint64_t addr, fence; int unknown; } pending[PENDING];
static unsigned pending_head;

// ---- occlusion counts (samples passed)
//
// After a SAMPLES_PASSED reset, the first draw of a pass begins an occlusion query (precise when the device has
// occlusionQueryPrecise); the query ends with the pass, or at the next report or reset of the counter, and the next
// draw begins another. A Vulkan query begun inside a render pass must end inside it. TOTK always resets, draws the
// tested proxies, reports, so counting stops at a report and restarts at the next reset: queries cover only the draws
// between the two, not every pass of the frame. Once the game reports twice without a reset in between, counting stays
// on for good (cumulative NVN semantics; that one report misses the draws since the previous one). The queries closed since the last
// report or reset form a segment, handed to the completion thread with that report or reset: in submit order it sums
// the segment's results into the running count (a reset drops the sum and zeroes the count) and writes the count of a
// report into guest memory. Slots come from one ring; the completion thread reads and host-resets them
// (hostQueryReset, Vulkan 1.2), so the replay records no reset commands. A full ring (no slot read back yet) leaves the
// draw uncounted and the segment's count at least 1, as does a query still unavailable after its fence. Without hostQueryReset the counts stay 0.
#define OQ_N 4096
#define LOG_ONCE(...) do { static volatile char once_; if (!__atomic_exchange_n(&once_, 1, __ATOMIC_RELAXED)) rt_log(__VA_ARGS__); } while (0)
static VkQueryPool oq_pool;
static int oq_state;                     // 0 not set up, 1 counting available, -1 unavailable
static VkQueryControlFlags oq_flags;
static volatile uint8_t oq_busy[OQ_N];   // from begin until the completion thread read and reset the slot
static uint32_t oq_next;                 // replay: next ring slot
static int oq_counting;                  // replay: draws are counted (a reset since the last report, or oq_keep)
static int oq_reported;                  // replay: a samples-passed report since the last reset
static int oq_keep;                      // replay: the game reported twice without a reset: count every draw
static int oq_open = -1;                 // replay: the slot whose query is active in the open pass
static uint32_t *oq_seg;                 // replay: slots closed since the last report or reset
static uint32_t oq_nseg, oq_capseg;
static int oq_lost;                      // replay: the segment missed a draw (ring full)
static uint64_t oq_count;                // completion thread: samples since the last reset

typedef struct { uint64_t addr; int reset, lost; uint32_t n; uint32_t q[]; } OqSegment;

static int oq_ready(void) {
    if (oq_state) return oq_state > 0;
    VkCtx *v = vk_ctx();
    // vk_device.c enables every feature the device reports, so supported means enabled.
    VkPhysicalDeviceVulkan12Features f12 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
    VkPhysicalDeviceFeatures2 f2 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &f12};
    vkGetPhysicalDeviceFeatures2(v->phys, &f2);
    oq_state = -1;
    if (!f12.hostQueryReset) {
        rt_log("vk: no hostQueryReset: samples-passed counters report 0");
        return 0;
    }
    VkQueryPoolCreateInfo qi = {.sType = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO, .queryType = VK_QUERY_TYPE_OCCLUSION,
                                .queryCount = OQ_N};
    VkResult r = vkCreateQueryPool(v->device, &qi, NULL, &oq_pool);
    if (r != VK_SUCCESS) {
        rt_log("vk: occlusion query pool creation failed (%d): samples-passed counters report 0", (int)r);
        return 0;
    }
    vkResetQueryPool(v->device, oq_pool, 0, OQ_N);
    oq_flags = f2.features.occlusionQueryPrecise ? VK_QUERY_CONTROL_PRECISE_BIT : 0;
    oq_state = 1;
    return 1;
}

static void oq_close(VkExec *ex) {
    if (oq_open < 0) return;
    vkCmdEndQuery(ex->cb, oq_pool, (uint32_t)oq_open);
    ex->recorded++;
    if (oq_nseg == oq_capseg) {
        oq_capseg = oq_capseg ? oq_capseg * 2 : 64;
        oq_seg = realloc(oq_seg, sizeof *oq_seg * oq_capseg);
        if (!oq_seg) rt_fatal("vk: out of memory");
    }
    oq_seg[oq_nseg++] = (uint32_t)oq_open;
    oq_open = -1;
}

void vk_exec_oq_draw(VkExec *ex) {
    if (!oq_counting || oq_open >= 0) return;
    uint32_t q = oq_next % OQ_N;
    if (__atomic_load_n(&oq_busy[q], __ATOMIC_ACQUIRE)) {
        warn_once(W_QUERY, "occlusion query ring full: draws left uncounted");
        oq_lost = 1;
        return;
    }
    oq_busy[q] = 1;
    oq_next++;
    vkCmdBeginQuery(ex->cb, oq_pool, q, oq_flags);
    ex->recorded++;
    oq_open = (int)q;
}

void vk_exec_oq_pass_end(VkExec *ex) { oq_close(ex); }

int vk_exec_oq_active(void) { return oq_open >= 0; }

void vk_exec_xfer_shutdown(void) {
    if (oq_state > 0) vkDestroyQueryPool(vk_ctx()->device, oq_pool, NULL);
    oq_pool = VK_NULL_HANDLE, oq_state = 0, oq_next = 0, oq_counting = oq_reported = oq_keep = 0, oq_open = -1;
    oq_nseg = 0, oq_lost = 0, oq_count = 0;
    memset((void *)oq_busy, 0, sizeof oq_busy);
}

static void oq_cb(void *arg) {
    OqSegment *s = arg;
    VkDevice dev = vk_ctx()->device;
    uint64_t sum = 0, v[64 * 2];
    for (uint32_t i = 0; i < s->n;) {
        uint32_t j = i + 1;
        while (j < s->n && j - i < 64 && s->q[j] == s->q[j - 1] + 1) j++;
        // The fence has passed, so a query that is still unavailable will not become available: waiting would block the
        // completion thread, and with it every later callback, for good. It counts as visible (one sample).
        VkResult r = vkGetQueryPoolResults(dev, oq_pool, s->q[i], j - i, sizeof v, v, 2 * sizeof v[0],
                                           VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WITH_AVAILABILITY_BIT);
        if (r != VK_SUCCESS && r != VK_NOT_READY) {
            vk_device_fault_report(r);
            rt_fatal("vk: occlusion query results failed (%d)", (int)r);
        }
        vkResetQueryPool(dev, oq_pool, s->q[i], j - i);
        for (uint32_t k = i; k < j; k++) {
            if (v[2 * (k - i) + 1]) sum += v[2 * (k - i)];
            else {
                sum += 1;
                LOG_ONCE("vk: occlusion query slot %u not available after its fence, counted as visible", s->q[k]);
            }
            __atomic_store_n(&oq_busy[s->q[k]], 0, __ATOMIC_RELEASE);
        }
        i = j;
    }
    if (s->reset) oq_count = 0;
    else {
        oq_count += sum;
        if (s->lost && !oq_count) oq_count = 1;
        static volatile int32_t n_logged;
        if (plat_inc32(&n_logged) <= 300)   // fastball diagnosis
            rt_log("counter: samples passed report %#llx: %llu (queries %u%s)", (unsigned long long)s->addr,
                   (unsigned long long)oq_count, s->n, s->lost ? ", some uncounted" : "");
        if (s->addr) write_counter(s->addr, oq_force_on() && oq_count < (1u << 20) ? 1u << 20 : oq_count);
    }
    free(s);
}

// Hands the segment to the completion thread with a report (addr; 0: no CPU-visible memory) or a reset.
static void oq_segment(VkExec *ex, uint64_t addr, int reset) {
    oq_close(ex);
    OqSegment *s = malloc(sizeof *s + sizeof *s->q * oq_nseg);
    if (!s) rt_fatal("vk: out of memory");
    s->addr = addr, s->reset = reset, s->lost = oq_lost, s->n = oq_nseg;
    memcpy(s->q, oq_seg, sizeof *s->q * oq_nseg);
    oq_nseg = 0, oq_lost = 0;
    vk_completion_add(ex->fence, oq_cb, s);
}

static void reset_counter(VkExec *ex, const p_reset_counter *p) {
    if (p->type != NVN_COUNTER_TYPE_SAMPLES_PASSED || !oq_ready()) return;
    oq_segment(ex, 0, 1);
    oq_counting = 1, oq_reported = 0;
}

// A samples-passed report: the segment goes with it (addr 0: no CPU-visible memory) and counting stops until the next
// reset, unless reports came without resets before.
static void oq_report(VkExec *ex, uint64_t addr) {
    oq_segment(ex, addr, 0);
    if (oq_reported && !oq_keep) {
        oq_keep = 1;
        rt_log("vk: samples passed reported twice without a reset: counting every draw from now on");
    }
    oq_reported = 1;
    if (!oq_keep) oq_counting = 0;
}

// fastball: an event signal takes effect where it is in the command stream. NVN writes the event when the GPU gets
// there; the replay wrote it when the whole submission completed (vk_completion_add), and MLB's main thread spins on
// nvnEventGetValue for such an event (f_70005a1310: 400,000-670,000 nvnSyncWait and GetValue calls a frame in the draft
// cutscene), so it waited for the submission's end, the completion thread and the replay queue: 45-55 fps with the
// GPU at 15-17 ms. Now, after a full barrier at the signal's place, the GPU writes the signal's sequence number into a
// host-visible buffer, and nvnEventGetValue (gfx_event_poll) applies every signal the GPU has reached, in order. The
// completion callback stays as the backstop; each signal is applied once (an ADD event must not count twice).
// MLB_EVENT_GPU=0: at completion only, as before.
#define EV_N 1024
typedef struct { volatile uint32_t *val; uint32_t mode, value, seq; volatile int32_t done; uint64_t fence; } EvRec;
static EvRec ev_rec[EV_N];
static uint32_t ev_next = 1, ev_lo = 1;   // the next sequence number (replay thread); the lowest not known applied (poll)
static volatile uint32_t ev_pub = 1;       // sequence numbers below it are recorded
static volatile int32_t ev_pending;
static VkBuffer ev_buf;
static VmaAllocation ev_alloc;
static volatile uint32_t *ev_map;
static int ev_state;                       // 0 not tried, 1 on, -1 off
static PlatMutex ev_lock = PLAT_MUTEX_INIT;
static uint64_t ev_n_gpu, ev_n_poll, ev_n_cb, ev_n_fallback;

static void ev_apply(EvRec *r) {
    if (__atomic_exchange_n(&r->done, 1, __ATOMIC_ACQ_REL)) return;
    if (r->mode == NVN_EVENT_SIGNAL_MODE_ADD) __atomic_fetch_add(r->val, r->value, __ATOMIC_RELEASE);
    else __atomic_store_n(r->val, r->value, __ATOMIC_RELEASE);
    evs_applied(r->val, r->fence);
    __atomic_sub_fetch(&ev_pending, 1, __ATOMIC_RELEASE);
}
static void ev_cb(void *arg) {   // the submission completed: every signal in it has been reached
    uint64_t k = (uint64_t)(uintptr_t)arg;
    uint32_t s = (uint32_t)k;
    plat_mutex_lock(&ev_lock);
    // earlier signals first (one per submission order); the poll may have applied them already. Bounded by sequence
    // order: when the poll already moved ev_lo past s, the loop must not run on to signals the GPU has not reached
    // (an unbounded i != s + 1 applied every recorded signal early, the game reused memory the GPU still read, and
    // the device was lost in the draft cutscene).
    uint32_t pub = __atomic_load_n(&ev_pub, __ATOMIC_ACQUIRE);
    for (uint32_t i = ev_lo; (int32_t)(s - i) >= 0 && i != pub; i++) {
        EvRec *r = &ev_rec[i % EV_N];
        if (r->seq == i && !r->done) ev_apply(r), ev_n_cb++;
    }
    while (ev_lo != __atomic_load_n(&ev_pub, __ATOMIC_ACQUIRE) &&
           (ev_rec[ev_lo % EV_N].seq != ev_lo || ev_rec[ev_lo % EV_N].done))
        ev_lo++;
    plat_mutex_unlock(&ev_lock);
}
void gfx_event_poll(void) {
    if (!__atomic_load_n(&ev_pending, __ATOMIC_ACQUIRE)) return;
    plat_mutex_lock(&ev_lock);
    uint32_t pub = __atomic_load_n(&ev_pub, __ATOMIC_ACQUIRE);
    for (uint32_t i = ev_lo; i != pub; i++) {
        EvRec *r = &ev_rec[i % EV_N];
        if (r->seq != i) {   // its slot was reused, which only happens once it was applied
            if (i == ev_lo) ev_lo++;
            continue;
        }
        if (!r->done) {
            if (__atomic_load_n(&ev_map[i % EV_N], __ATOMIC_ACQUIRE) != i) break;   // the GPU is not there yet
            ev_apply(r), ev_n_poll++;
        }
        if (i == ev_lo) ev_lo++;
    }
    plat_mutex_unlock(&ev_lock);
}
static int ev_init(void) {
    if (ev_state) return ev_state > 0;
    // Off by default: with it on the draft cutscene lost the device twice (GPU page faults, a 3-4 s hang) at its start.
    // MLB_EVENT_GPU=1 turns it on for testing.
    const char *e = cfg_get("MLB_EVENT_GPU");
    ev_state = -1;
    if (e && strcmp(e, "0")) {
        VkCtx *c = vk_ctx();
        VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = EV_N * 4,
                                 .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
        VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
                                      .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT,
                                      .requiredFlags = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT};
        VmaAllocationInfo info;
        if (vmaCreateBuffer(c->vma, &bi, &ai, &ev_buf, &ev_alloc, &info) == VK_SUCCESS && info.pMappedData) {
            ev_map = info.pMappedData;
            memset((void *)ev_map, 0, EV_N * 4);
            ev_state = 1;
        }
    }
    rt_log("vk: event signals %s", ev_state > 0 ? "take effect where the GPU reaches them (MLB_EVENT_GPU=1, experimental)"
                                                : "take effect when their submission completes (MLB_EVENT_GPU=1: where the GPU reaches them)");
    return ev_state > 0;
}

static void signal_event(VkExec *ex, const p_signal_event *p) {
    uint32_t s = ev_next;
    EvRec *r = &ev_rec[s % EV_N];
    evs_recorded(p->val, ex->fence);
    if (!ev_init() || (r->seq && !r->done)) {   // off, or the slot's previous signal still pending: at completion
        EventWrite *e = malloc(sizeof *e);
        if (!e) rt_fatal("vk: out of memory");
        *e = (EventWrite){p->val, p->mode, p->value, ex->fence};
        vk_completion_add(ex->fence, event_cb, e);
        if (ev_state > 0) ev_n_fallback++;
        return;
    }
    ev_next = s + 1 ? s + 1 : 1;
    plat_mutex_lock(&ev_lock);
    *r = (EvRec){p->val, p->mode, p->value, s, 0, ex->fence};
    plat_mutex_unlock(&ev_lock);
    __atomic_add_fetch(&ev_pending, 1, __ATOMIC_RELEASE);
    vk_exec_barrier(ex);   // ends the pass; the work before the signal is done before the write below
    vkCmdFillBuffer(ex->cb, ev_buf, (VkDeviceSize)(s % EV_N) * 4, 4, s);
    VkMemoryBarrier2 mb = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER_2, .srcStageMask = VK_PIPELINE_STAGE_2_COPY_BIT,
                           .srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT, .dstStageMask = VK_PIPELINE_STAGE_2_HOST_BIT,
                           .dstAccessMask = VK_ACCESS_2_HOST_READ_BIT};
    VkDependencyInfo di = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .memoryBarrierCount = 1, .pMemoryBarriers = &mb};
    vkCmdPipelineBarrier2(ex->cb, &di);
    ex->recorded += 2;
    __atomic_store_n(&ev_pub, ev_next, __ATOMIC_RELEASE);
    vk_completion_add(ex->fence, ev_cb, (void *)(uintptr_t)s);
    ev_n_gpu++;
    static uint64_t last_frame;
    uint64_t fr = __atomic_load_n(&gfx_counters.frames, __ATOMIC_RELAXED);
    if ((rt_trace & RT_TRACE_PERF) && fr >= last_frame + 600) {
        rt_log("perf: frame %llu: event signals %llu: applied by the poll %llu, by completion %llu; at completion only "
               "(slot busy) %llu", (unsigned long long)fr, (unsigned long long)ev_n_gpu, (unsigned long long)ev_n_poll,
               (unsigned long long)ev_n_cb, (unsigned long long)ev_n_fallback);
        ev_n_gpu = ev_n_poll = ev_n_cb = ev_n_fallback = 0, last_frame = fr;
    }
}

static void report_counter(VkExec *ex, const p_report_counter *p) {
    {   // fastball diagnosis: the game's counter reports by type
        static uint64_t by_type[18], total;
        by_type[p->type < 17 ? p->type : 17]++;
        static volatile int32_t n_logged;
        if (plat_inc32(&n_logged) <= 60)
            rt_log("counter: report type %u at %#llx%s", (unsigned)p->type, (unsigned long long)p->addr,
                   nvn_gpu_only(p->addr) ? " (GPU-only pool)" : "");
        if (++total % 5000 == 0) {
            char line[400];
            int o = snprintf(line, sizeof line, "counter: %llu reports by type:", (unsigned long long)total);
            for (int t = 0; t < 18; t++)
                if (by_type[t]) o += snprintf(line + o, sizeof line - o, " %d:%llu", t, (unsigned long long)by_type[t]);
            rt_log("%s", line);
        }
    }
    int samples = p->type == NVN_COUNTER_TYPE_SAMPLES_PASSED && oq_ready();
    if (nvn_gpu_only(p->addr)) {   // CPU-invisible pool: no host memory behind it
        if (samples) oq_report(ex, 0);
        return;
    }
    VkMemSpan m;
    if (!vk_mem_resolve(p->addr, sizeof(NVNcounterData), &m))
        rt_fatal("vk: counter report at %#llx is in no memory pool", (unsigned long long)p->addr);
    vk_mem_count(m.cls, VK_MUSE_GPU_WRITE, sizeof(NVNcounterData));
    if (samples) oq_report(ex, p->addr);
    else {
        CounterWrite *a = malloc(sizeof *a);
        if (!a) rt_fatal("vk: out of memory");
        *a = (CounterWrite){p->addr, (uint32_t)p->type};
        vk_completion_add(ex->fence, counter_cb, a);
    }
    pending[pending_head++ % PENDING] = (typeof(pending[0])){p->addr, ex->fence, samples};
}

// ---- conditional rendering

// 1: *v read, 0: not readable, 2: a samples-passed report not done yet (unknown)
static int counter_word(uint64_t addr, uint64_t *v) {
    uint64_t done = vk_sync_fence_done();
    for (unsigned k = 1; k <= PENDING; k++) {   // newest first: the last report to addr decides
        unsigned i = (pending_head - k) % PENDING;
        if (pending[i].addr == addr && pending[i].fence > done) return *v = 0, pending[i].unknown ? 2 : 1;
    }
    VkMemSpan m;
    if (nvn_gpu_only(addr) || !vk_mem_resolve(addr, sizeof *v, &m)) return 0;
    memcpy(v, (const void *)(uintptr_t)addr, sizeof *v);
    vk_mem_count(m.cls, VK_MUSE_CPU_READ, sizeof *v);
    return 1;
}

static int cond_enabled(const p_render_cond *c) {
    uint64_t x, y;
    int rx = counter_word(c->addr, &x), ry = counter_word(c->addr + 16, &y);
    if (!rx || !ry) {
        warn_once(W_BUFFER, "conditional render counters at %#llx are not readable: rendering", (unsigned long long)c->addr);
        return 1;
    }
    if (rx == 2 || ry == 2) return 1;   // a samples-passed count not done yet
    return c->mode == 0 ? x == y : x != y;
}

// ---- textures

typedef struct {
    const VkTexImage *img;
    VkImageAspectFlags aspect;
    uint32_t level, layer0;
    int bpb, bw, bh;
    int32_t x, y, z;           // region origin
    uint32_t w, h, nz;         // region extent; nz: slices (3D) or layers
} Sub;

// Resolves tex, its view and a copy region to image coordinates. 0 (warned) when the copy cannot be replayed.
static int sub_resolve(const tex_t *t, const view_t *v, int has_v, const NVNcopyRegion *r, int defaults_to_level,
                       Sub *s) {
    memset(s, 0, sizeof *s);
    if (!t) return 0;
    TexVkFormat f;
    if (!tex_vk_format(t->d.format, &f) || f.vk != f.ideal || f.expand_rgb || f.astc_bw) {
        warn_once(W_FORMAT, "copy of format %#x texture (decoded or expanded on upload): skipped", t->d.format);
        return 0;
    }
    s->bpb = nvn_fmt_bpb(t->d.format, &s->bw, &s->bh);
    s->img = vk_texture_get(t);
    if (!s->img || !s->bpb) {
        warn_once(W_FORMAT, "copy of format %#x texture without an image: skipped", t->d.format);
        return 0;
    }
    const VkTexImage *img = s->img;
    if (img->aspect & VK_IMAGE_ASPECT_COLOR_BIT) s->aspect = VK_IMAGE_ASPECT_COLOR_BIT;
    else if (img->aspect == VK_IMAGE_ASPECT_DEPTH_BIT) s->aspect = VK_IMAGE_ASPECT_DEPTH_BIT;
    else {
        warn_once(W_FORMAT, "copy of depth-stencil format %#x texture: skipped", t->d.format);
        return 0;
    }
    s->level = has_v && v->set_levels ? v->base_level : 0;
    s->layer0 = has_v && v->set_layers ? v->min_layer : 0;
    uint32_t lw = max1(img->width >> s->level), lh = max1(img->height >> s->level);
    int k = img->scale > 1 ? img->scale : 1;   // a larger shadow map: the game's region in its texels
    s->x = r->xoffset * k, s->y = r->yoffset * k, s->z = r->zoffset;
    s->nz = r->depth > 0 ? (uint32_t)r->depth : 1;
    s->w = r->width > 0 ? (uint32_t)r->width * k : defaults_to_level ? (s->x < (int32_t)lw ? lw - (uint32_t)s->x : 0) : 0;
    s->h = r->height > 0 ? (uint32_t)r->height * k : defaults_to_level ? (s->y < (int32_t)lh ? lh - (uint32_t)s->y : 0) : 0;
    int is3d = img->type == VK_IMAGE_TYPE_3D;
    uint32_t layers = is3d ? 1 : (uint32_t)s->z + s->nz, first = is3d ? 0 : s->layer0;
    if (s->level >= img->levels || s->x < 0 || s->y < 0 || s->z < 0 || !s->w || !s->h ||
        (uint64_t)s->x + s->w > lw || (uint64_t)s->y + s->h > lh || first + layers > img->layers ||
        (is3d && (uint64_t)s->z + s->nz > max1(img->depth >> s->level))) {
        warn_once(W_REGION, "copy region %d,%d,%d %ux%ux%u outside level %u of a %ux%u texture: skipped", s->x, s->y,
                  s->z, s->w, s->h, s->nz, s->level, img->width, img->height);
        return 0;
    }
    return 1;
}

static VkImageSubresourceLayers sub_layers(const Sub *s) {
    int is3d = s->img->type == VK_IMAGE_TYPE_3D;
    return (VkImageSubresourceLayers){s->aspect, s->level, is3d ? 0 : s->layer0 + (uint32_t)s->z, is3d ? 1 : s->nz};
}

static VkOffset3D sub_offset(const Sub *s) {
    return (VkOffset3D){s->x, s->y, s->img->type == VK_IMAGE_TYPE_3D ? s->z : 0};
}

static VkExtent3D sub_extent(const Sub *s) {
    return (VkExtent3D){s->w, s->h, s->img->type == VK_IMAGE_TYPE_3D ? s->nz : 1};
}

// Buffer side of a texture <-> buffer copy: bytes covered, pitches, Vulkan buffer span (a VRAM mirror when the pool
// has one).
static int buffer_side(const VkExec *ex, const Sub *s, uint64_t addr, uint64_t *size, VkBufferImageCopy *c,
                       VkMemSpan *span) {
    uint32_t wb = (s->w + (uint32_t)s->bw - 1) / (uint32_t)s->bw, hb = (s->h + (uint32_t)s->bh - 1) / (uint32_t)s->bh;
    uint64_t row = ex->copy_stride > 0 ? (uint64_t)ex->copy_stride : (uint64_t)wb * (uint64_t)s->bpb;
    if (row % (uint64_t)s->bpb || row < (uint64_t)wb * (uint64_t)s->bpb) {
        warn_once(W_REGION, "buffer copy row stride %llu does not fit %u blocks of %d bytes: skipped",
                  (unsigned long long)row, wb, s->bpb);
        return 0;
    }
    uint64_t img = row * hb;
    *size = img * (s->nz - 1) + row * (hb - 1) + (uint64_t)wb * (uint64_t)s->bpb;
    VkMemSpan m;
    if (!addr || !vk_mem_resolve(addr, *size, &m) || m.avail < *size) {
        warn_once(W_BUFFER, "texture copy buffer %#llx (%llu bytes) is not one backed span: skipped",
                  (unsigned long long)addr, (unsigned long long)*size);
        return 0;
    }
    VK_MEM_PICK(m);
    *span = m;
    *c = (VkBufferImageCopy){.bufferOffset = m.offset, .bufferRowLength = (uint32_t)(row / (uint64_t)s->bpb) * (uint32_t)s->bw,
                             .bufferImageHeight = hb * (uint32_t)s->bh, .imageSubresource = sub_layers(s),
                             .imageOffset = sub_offset(s), .imageExtent = sub_extent(s)};
    return 1;
}

static void copy_buffer_image(VkExec *ex, const p_copy_b2t *p, int to_image) {
    Sub s;
    int dl_near = vk_drawlog_near();
    if (dl_near)   // fastball diagnosis
        rt_log("drawlog%s copy%s buffer %#llx %s texture %#llx fmt %#x %ux%u, region %d,%d %dx%d",
               dl_near > 1 ? (dl_near == 2 ? "+1" : "+2") : "", to_image ? "b2t" : "t2b", (unsigned long long)p->src,
               to_image ? "->" : "<-", (unsigned long long)(uintptr_t)p->tex->mem, (unsigned)p->tex->d.format,
               p->tex->d.width, p->tex->d.height, p->r.xoffset, p->r.yoffset, p->r.width, p->r.height);
    if (!sub_resolve(p->tex, &p->view, p->has_view, &p->r, 1, &s)) return;
    if (s.img->scale > 1) {   // the buffer holds the game's texel count, the image more
        warn_once(W_REGION, "buffer copy of a shadow map enlarged by TOTK_SHADOW_SCALE: skipped");
        return;
    }
    uint64_t size;
    VkBufferImageCopy c;
    VkMemSpan m;
    if (!buffer_side(ex, &s, p->src, &size, &c, &m)) return;
    vk_mem_count(m.cls, to_image ? VK_MUSE_COPY_SRC : VK_MUSE_GPU_WRITE, size);
    vk_exec_pass_end(ex);
    vk_exec_barrier(ex);
    if (to_image) vkCmdCopyBufferToImage(ex->cb, m.buffer, s.img->image, VK_IMAGE_LAYOUT_GENERAL, 1, &c);
    else vkCmdCopyImageToBuffer(ex->cb, s.img->image, VK_IMAGE_LAYOUT_GENERAL, m.buffer, 1, &c);
    ex->recorded++;
    if (to_image && vk_watch_hit((uint64_t)(uintptr_t)p->tex->mem, p->tex->L.size)) {   // fastball diagnosis
        uint64_t nz = 0;
        VkMemSpan cm;
        if (vk_mem_resolve(p->src, size, &cm))
            for (uint64_t b = 0; b < size; b++) nz += ((const uint8_t *)(uintptr_t)p->src)[b] != 0;
        rt_log("watch: buffer %#llx (+%#llx, %llu bytes non-zero in guest memory) copied to %#llx fmt %#x level %u layer %u "
               "%d,%d %ux%u", (unsigned long long)p->src, (unsigned long long)size, (unsigned long long)nz,
               (unsigned long long)(uintptr_t)p->tex->mem, (unsigned)p->tex->d.format, s.level, s.layer0, s.x, s.y, s.w, s.h);
    }
    if (to_image) vk_texture_gpu_written(p->tex);
    else vk_mem_gpu_wrote(&m, size), note_gpu_write(ex, p->src, size);
}

int vk_watch_hit(uint64_t a, uint64_t n);   // vk_texture.c (fastball diagnosis)
static void copy_t2t(VkExec *ex, const p_copy_t2t *p) {
    Sub s, d;
    int dl_near = vk_drawlog_near();
    if (dl_near)   // fastball diagnosis: drawlog frame and the two after it
        rt_log("drawlog%s copytex %#llx fmt %#x %ux%u s%d level %u -> %#llx fmt %#x %ux%u s%d level %u, region %d,%d %dx%d -> "
               "%d,%d %dx%d flags %#x", dl_near > 1 ? (dl_near == 2 ? "+1" : "+2") : "",
               (unsigned long long)(uintptr_t)p->src->mem, (unsigned)p->src->d.format, p->src->d.width, p->src->d.height,
               p->src->d.samples, p->has_sv && p->sv.set_levels ? p->sv.base_level : 0,
               (unsigned long long)(uintptr_t)p->dst->mem, (unsigned)p->dst->d.format, p->dst->d.width, p->dst->d.height,
               p->dst->d.samples, p->has_dv && p->dv.set_levels ? p->dv.base_level : 0, p->sr.xoffset, p->sr.yoffset,
               p->sr.width, p->sr.height, p->dr.xoffset, p->dr.yoffset, p->dr.width, p->dr.height, p->flags);
    if (!sub_resolve(p->src, &p->sv, p->has_sv, &p->sr, 1, &s)) {
        if (dl_near) rt_log("drawlog   copytex: source has no image or region: skipped");
        return;
    }
    if (!sub_resolve(p->dst, &p->dv, p->has_dv, &p->dr, 1, &d)) {
        if (dl_near) rt_log("drawlog   copytex: destination has no image or region: skipped");
        return;
    }
    if (dl_near)
        rt_log("drawlog   copytex images: src %p vk fmt %d %u samples, dst %p vk fmt %d %u samples", (void *)s.img->image,
               (int)s.img->format, s.img->samples, (void *)d.img->image, (int)d.img->format, d.img->samples);
    d.nz = s.nz;
    int same_size = s.w == d.w && s.h == d.h;
    int same_format = s.img->format == d.img->format;
    if (s.img->samples != d.img->samples && !(s.img->samples > 1 && d.img->samples == 1 && same_size && same_format)) {
        warn_once(W_COPY, "texture copy between %u and %u samples: skipped", s.img->samples, d.img->samples);
        return;
    }
    if (s.aspect != d.aspect || (s.aspect != VK_IMAGE_ASPECT_COLOR_BIT && !same_format)) {
        warn_once(W_COPY, "texture copy between formats %#x and %#x: skipped", p->src->d.format, p->dst->d.format);
        return;
    }
    VkImageSubresourceLayers sl = sub_layers(&s), dl = sub_layers(&d);
    if (vk_watch_hit((uint64_t)(uintptr_t)p->src->mem, p->src->L.size) ||
        vk_watch_hit((uint64_t)(uintptr_t)p->dst->mem, p->dst->L.size))   // fastball diagnosis
        rt_log("watch: copy %#llx fmt %#x level %u layers %u+%u %d,%d %ux%u -> %#llx fmt %#x level %u layers %u+%u %d,%d "
               "%ux%u (%s%s)", (unsigned long long)(uintptr_t)p->src->mem, (unsigned)p->src->d.format, sl.mipLevel,
               sl.baseArrayLayer, sl.layerCount, s.x, s.y, s.w, s.h, (unsigned long long)(uintptr_t)p->dst->mem,
               (unsigned)p->dst->d.format, dl.mipLevel, dl.baseArrayLayer, dl.layerCount, d.x, d.y, d.w, d.h,
               s.img->samples > 1 && d.img->samples == 1 ? "resolve" : same_size && same_format ? "copy" : "blit",
               (p->flags & NVN_COPY_FLAGS_LINEAR_FILTER_BIT) ? ", linear" : "");
    vk_exec_pass_end(ex);
    vk_exec_barrier(ex);
    if (s.img->samples > 1 && d.img->samples == 1) {
        VkImageResolve rv = {sl, sub_offset(&s), dl, sub_offset(&d), sub_extent(&s)};
        vkCmdResolveImage(ex->cb, s.img->image, VK_IMAGE_LAYOUT_GENERAL, d.img->image, VK_IMAGE_LAYOUT_GENERAL, 1, &rv);
    } else if (same_size && same_format) {
        VkImageCopy cp = {sl, sub_offset(&s), dl, sub_offset(&d), sub_extent(&s)};
        vkCmdCopyImage(ex->cb, s.img->image, VK_IMAGE_LAYOUT_GENERAL, d.img->image, VK_IMAGE_LAYOUT_GENERAL, 1, &cp);
    } else {   // scaled or converting copy: nearest, or linear when asked for (colour only)
        int is3d = s.img->type == VK_IMAGE_TYPE_3D;
        VkImageBlit bl = {.srcSubresource = sl, .dstSubresource = dl};
        bl.srcOffsets[0] = sub_offset(&s);
        bl.srcOffsets[1] = (VkOffset3D){s.x + (int32_t)s.w, s.y + (int32_t)s.h, is3d ? s.z + (int32_t)s.nz : 1};
        bl.dstOffsets[0] = sub_offset(&d);
        bl.dstOffsets[1] = (VkOffset3D){d.x + (int32_t)d.w, d.y + (int32_t)d.h, is3d ? d.z + (int32_t)d.nz : 1};
        int linear = (p->flags & NVN_COPY_FLAGS_LINEAR_FILTER_BIT) && s.aspect == VK_IMAGE_ASPECT_COLOR_BIT;
        vkCmdBlitImage(ex->cb, s.img->image, VK_IMAGE_LAYOUT_GENERAL, d.img->image, VK_IMAGE_LAYOUT_GENERAL, 1, &bl,
                       linear ? VK_FILTER_LINEAR : VK_FILTER_NEAREST);
    }
    ex->recorded++;
    vk_texture_gpu_written(p->dst);
}

// ---- buffer to buffer

static void copy_b2b(VkExec *ex, const p_copy_b2b *p) {
    if (vk_drawlog_now())   // fastball: drawlog frame
        rt_log("drawlog copybuf %#llx -> %#llx +%#llx", (unsigned long long)p->src, (unsigned long long)p->dst,
               (unsigned long long)p->size);
    {
        int vk_watch_hit(uint64_t a, uint64_t n);   // vk_texture.c (fastball diagnosis)
        if (vk_watch_hit(p->dst, p->size))
            rt_log("watch: buffer copy %#llx -> %#llx +%#llx", (unsigned long long)p->src, (unsigned long long)p->dst,
                   (unsigned long long)p->size);
    }
    uint64_t src = p->src, dst = p->dst, left = p->size;
    int started = 0;
    while (left) {
        VkMemSpan s, d;
        if (!vk_mem_resolve(src, 1, &s) || !vk_mem_resolve(dst, 1, &d)) {
            warn_once(W_BUFFER, "buffer copy %#llx -> %#llx (%llu bytes) leaves backed memory: rest skipped",
                      (unsigned long long)p->src, (unsigned long long)p->dst, (unsigned long long)p->size);
            break;
        }
        uint64_t n = left < s.avail ? left : s.avail;
        if (n > d.avail) n = d.avail;
        VK_MEM_PICK(s);
        VK_MEM_PICK(d);
        if (s.buffer == d.buffer && s.offset < d.offset + n && d.offset < s.offset + n) {
            warn_once(W_OVERLAP, "buffer copy %#llx -> %#llx overlaps within one buffer: skipped",
                      (unsigned long long)p->src, (unsigned long long)p->dst);
            break;
        }
        if (!started) vk_exec_pass_end(ex), vk_exec_barrier(ex), started = 1;
        VkBufferCopy bc = {s.offset, d.offset, n};
        vkCmdCopyBuffer(ex->cb, s.buffer, d.buffer, 1, &bc);
        vk_mem_gpu_wrote(&d, n);
        ex->recorded++;
        vk_mem_count(s.cls, VK_MUSE_COPY_SRC, n);
        vk_mem_count(d.cls, VK_MUSE_GPU_WRITE, n);
        src += n, dst += n, left -= n;
    }
    if (started) note_gpu_write(ex, p->dst, p->size - left);
}

// ---- buffer fills (ClearBuffer, and ReportValue as a 4-byte one): vkCmdFillBuffer in GPU order after a full
// barrier, so the value lands after earlier work, as NVN's semaphore release does; CPU-visible ranges go to
// vk_guest_written at the fence, as copies do. Works in CPU-invisible pools.

static void clear_buf(VkExec *ex, const p_clear_buf *p) {
    if (vk_drawlog_now())   // fastball: drawlog frame
        rt_log("drawlog clearbuf %#llx +%#llx value %#x", (unsigned long long)p->addr, (unsigned long long)p->size,
               (unsigned)p->value);
    if ((p->addr | p->size) & 3) {
        warn_once(W_BUFFER, "buffer fill at %#llx of %llu bytes is not 4-byte aligned: skipped", (unsigned long long)p->addr,
                  (unsigned long long)p->size);
        return;
    }
    uint64_t dst = p->addr, left = p->size;
    int started = 0;
    while (left) {
        VkMemSpan d;
        if (!vk_mem_resolve(dst, 1, &d) || d.offset % 4) {
            warn_once(W_BUFFER, "buffer fill at %#llx (%llu bytes) leaves backed memory: rest skipped",
                      (unsigned long long)p->addr, (unsigned long long)p->size);
            break;
        }
        uint64_t n = left < d.avail ? left : d.avail & ~3ull;
        if (!n) break;
        if (!started) vk_exec_pass_end(ex), vk_exec_barrier(ex), started = 1;
        VK_MEM_PICK(d);
        vkCmdFillBuffer(ex->cb, d.buffer, d.offset, n, p->value);
        vk_mem_gpu_wrote(&d, n);
        ex->recorded++;
        vk_mem_count(d.cls, VK_MUSE_GPU_WRITE, n);
        dst += n, left -= n;
    }
    if (started) note_gpu_write(ex, p->addr, p->size - left);
}

// ---- texture clears

static int int_format(VkFormat f) {
    switch (f) {
    case VK_FORMAT_R8_UINT: case VK_FORMAT_R8G8_UINT: case VK_FORMAT_R8G8B8A8_UINT: case VK_FORMAT_R8_SINT:
    case VK_FORMAT_R8G8_SINT: case VK_FORMAT_R8G8B8A8_SINT: case VK_FORMAT_R16_UINT: case VK_FORMAT_R16G16_UINT:
    case VK_FORMAT_R16G16B16A16_UINT: case VK_FORMAT_R16_SINT: case VK_FORMAT_R16G16_SINT:
    case VK_FORMAT_R16G16B16A16_SINT: case VK_FORMAT_R32_UINT: case VK_FORMAT_R32G32_UINT:
    case VK_FORMAT_R32G32B32A32_UINT: case VK_FORMAT_R32_SINT: case VK_FORMAT_R32G32_SINT:
    case VK_FORMAT_R32G32B32A32_SINT: case VK_FORMAT_A2B10G10R10_UINT_PACK32:
        return 1;
    default: return 0;
    }
}

// Whole levels only (vkCmdClear*Image has no rectangle); partial regions, channel masks and a view that reinterprets
// the format are skipped (MacNativeGames does not replay them either, nvn_mtl.m).
static void clear_tex(VkExec *ex, const p_clear_tex *p) {
    const tex_t *t = p->tex;
    if (!t) return;
    Sub s;
    if (!sub_resolve(t, &p->view, p->has_view, &p->r, 1, &s)) return;
    const VkTexImage *img = s.img;
    int is3d = img->type == VK_IMAGE_TYPE_3D;
    uint32_t lw = max1(img->width >> s.level), lh = max1(img->height >> s.level);
    int reformat = p->has_view && p->view.set_format && p->view.format != t->d.format;
    if (s.x || s.y || s.w != lw || s.h != lh || (p->mask & 0xf) != 0xf || reformat ||
        (is3d && (s.z || s.nz != max1(img->depth >> s.level)))) {
        warn_once(W_CLEAR, "texture clear of region %d,%d %ux%u mask %#x (level %ux%u, view format change %d): skipped",
                  s.x, s.y, s.w, s.h, p->mask, lw, lh, reformat);
        return;
    }
    VkImageSubresourceRange rng = {img->aspect, s.level, 1, is3d ? 0 : s.layer0 + (uint32_t)s.z, is3d ? 1 : s.nz};
    if (img->aspect & VK_IMAGE_ASPECT_COLOR_BIT) {
        rng.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        VkClearColorValue cv;
        if (int_format(img->format) != (p->is_uint != 0)) {
            warn_once(W_CLEAR, "texture clear value kind (uint %d) does not match format %d: skipped", p->is_uint, (int)img->format);
            return;
        }
        memcpy(&cv, &p->c, sizeof cv);
        vk_exec_pass_end(ex);
        vk_exec_barrier(ex);
        vkCmdClearColorImage(ex->cb, img->image, VK_IMAGE_LAYOUT_GENERAL, &cv, 1, &rng);
    } else {
        int both = (img->aspect & VK_IMAGE_ASPECT_DEPTH_BIT) && (img->aspect & VK_IMAGE_ASPECT_STENCIL_BIT);
        VkClearDepthStencilValue dv = {0, 0};
        if (img->aspect & VK_IMAGE_ASPECT_DEPTH_BIT) dv.depth = p->c.f[0];
        if (img->aspect & VK_IMAGE_ASPECT_STENCIL_BIT) dv.stencil = both ? p->c.u[1] : p->c.u[0];
        vk_exec_pass_end(ex);
        vk_exec_barrier(ex);
        vkCmdClearDepthStencilImage(ex->cb, img->image, VK_IMAGE_LAYOUT_GENERAL, &dv, 1, &rng);
    }
    ex->recorded++;
    if (vk_watch_hit((uint64_t)(uintptr_t)t->mem, t->L.size))   // fastball diagnosis
        rt_log("watch: texture clear of %#llx fmt %#x to %g %g %g %g", (unsigned long long)(uintptr_t)t->mem,
               (unsigned)t->d.format, p->c.f[0], p->c.f[1], p->c.f[2], p->c.f[3]);
    vk_texture_gpu_written(t);
}

void vk_exec_op_xfer(VkExec *ex, uint32_t op, const void *payload) {
    if (op != OP_RENDER_ENABLE && op != OP_SIGNAL_EVENT) vk_contact_flush(ex);
    switch (op) {
    case OP_COPY_B2B: copy_b2b(ex, payload); break;
    case OP_COPY_B2T: copy_buffer_image(ex, payload, 1); break;
    case OP_COPY_T2B: copy_buffer_image(ex, payload, 0); break;   // p_copy_b2t: src holds the destination address
    case OP_COPY_T2T: copy_t2t(ex, payload); break;
    case OP_CLEAR_TEX: clear_tex(ex, payload); break;
    case OP_SIGNAL_EVENT: signal_event(ex, payload); break;
    case OP_REPORT_COUNTER: report_counter(ex, payload); break;
    case OP_RESET_COUNTER: reset_counter(ex, payload); break;
    case OP_CLEAR_BUF: clear_buf(ex, payload); break;
    case OP_RENDER_ENABLE: ex->render_disabled = !((const p_flag *)payload)->value; break;
    case OP_RENDER_COND:
        ex->render_cond = *(const p_render_cond *)payload;
        ex->has_render_cond = 1;
        ex->render_disabled = !cond_enabled(payload);
        break;
    default: rt_fatal("vk: op %s is not a transfer", nvn_op_name(op));
    }
}
