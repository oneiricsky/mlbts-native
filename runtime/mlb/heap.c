// fastball (diagnostic): how full the game's malloc heap is, every 30 s with MLB_TRACE=perf.
// Issue #17 (0.1.4, 1.0.20): after 5-6 hours of play the SDK aborted in operator new under std::string::resize: the
// SDK's libc++ allocates through malloc, and main's malloc is nn::init's nn::mem::StandardAllocator over the whole heap
// less 32 MiB (nninitStartup, main+0x5b1a84 in 1.0.20), so that heap had run out. These lines show whether it shrinks
// over a session and whether it is used up or only cut into pieces (free against the largest block).
// What they found: the game's own pools take all but 136 MiB of it at boot, and every match start left a 2.1 MiB
// block of JSON text ("ClassRestrictions") and about 1,000 small strings behind: the loader bound sdk's operator new to
// sdk's own (malloc) while the game freed through its own operator delete (loader.c resolve). Since that fix a match
// start adds no malloc block.
// The allocator is the object malloc passes to StandardAllocator::Allocate: malloc's adrp x0 / add x0 pair (1.0.15 and
// 1.0.20 alike). Off, it costs one test per presented frame.
// MLB_HEAP_CENSUS=1 also walks the live blocks (StandardAllocator::WalkAllocatedBlocks) and logs the kinds that grew
// since the last line: a kind is the block size and its first word when that points into main (a C++ object's vtable).
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "kernel.h"

#define INTERVAL_NS 30000000000ull

static uint64_t allocator(void) {
    uint64_t m = ldr_symbol("malloc");
    if (!m || !mem_guest_readable(m, 0x24)) return 0;
    const uint32_t *w = (const uint32_t *)(uintptr_t)m;
    // malloc: stp; mov; adrp x8; ldr x8 (initialized?); cbz; mov x1, x0; adrp x0, page; add x0, x0, #off; bl Allocate
    uint32_t adrp = w[6], add = w[7];
    if ((adrp & 0x9F00001Fu) != 0x90000000u || (add & 0xFFC003FFu) != 0x91000000u) return 0;
    int64_t imm = (int64_t)((((adrp >> 5) & 0x7FFFF) << 2) | ((adrp >> 29) & 3)) << 12;
    if (imm & (1ll << 32)) imm -= 1ll << 33;
    return ((m + 24) & ~0xFFFull) + (uint64_t)imm + ((add >> 10) & 0xFFF);
}

// ---- census: kind -> live blocks, open addressing
#define SLOTS (1u << 18)
typedef struct { uint64_t size, tag; uint32_t n, prev; } Kind;
static Kind *kinds;
static uint64_t main_lo, main_hi, blocks, bytes, lost;
static uint64_t walk_cb_addr;
// blocks of BIG bytes or more (the game's own pools are the larger ones): those of a kind that grew are described
#define BIG (256u << 10)
#define MAX_BIG 512
static struct { uint64_t addr, size; } big[MAX_BIG];
static uint32_t nbig;

static void walk_cb(Cpu *c) {   // int (void *block, size_t size, void *user): nonzero goes on
    uint64_t a = c->x[0], size = c->x[1], tag = 0;
    if (mem_guest_readable(a, 8)) {
        uint64_t v = *(const uint64_t *)(uintptr_t)a;
        if (v >= main_lo && v < main_hi) tag = v - main_lo;
    }
    blocks++, bytes += size;
    if (size >= BIG && nbig < MAX_BIG) big[nbig].addr = a, big[nbig++].size = size;
    uint64_t h = (size * 0x9E3779B97F4A7C15ull) ^ (tag * 0xC2B2AE3D27D4EB4Full);
    for (uint32_t i = 0, s = (uint32_t)(h >> 40) & (SLOTS - 1); i < 64; i++, s = (s + 1) & (SLOTS - 1)) {
        Kind *k = &kinds[s];
        if (!k->n && !k->prev && !k->size) *k = (Kind){size, tag, 0, 0};
        if (k->size == size && k->tag == tag) {
            k->n++;
            ret_x(c, 1);
            return;
        }
    }
    lost++;
    ret_x(c, 1);
}

static int by_growth(const void *x, const void *y) {
    const Kind *a = x, *b = y;
    int64_t ga = ((int64_t)a->n - a->prev) * (int64_t)a->size, gb = ((int64_t)b->n - b->prev) * (int64_t)b->size;
    return ga < gb ? 1 : ga > gb ? -1 : 0;
}

static void census(Cpu *c, uint64_t obj, uint64_t walk_fn) {
    if (!kinds && !(kinds = calloc(SLOTS, sizeof *kinds))) return;
    for (uint32_t i = 0; i < SLOTS; i++) kinds[i].prev = kinds[i].n, kinds[i].n = 0;
    uint64_t prev_blocks = blocks, prev_bytes = bytes;
    blocks = bytes = lost = 0;
    nbig = 0;
    rt_call(c, walk_fn, 3, obj, walk_cb_addr, (uint64_t)0);
    rt_log("heap: census %llu blocks %.1f MiB (%+lld blocks, %+.2f MiB since the last)%s", (unsigned long long)blocks,
           bytes / 1048576.0, (long long)(blocks - prev_blocks), ((double)bytes - (double)prev_bytes) / 1048576.0,
           lost ? " (some kinds not counted: table full)" : "");
    static Kind top[24];
    uint32_t ntop = 0;
    for (uint32_t i = 0; i < SLOTS; i++) {   // the 24 largest growths in bytes
        Kind *k = &kinds[i];
        if (k->n <= k->prev) continue;
        if (ntop < 24) top[ntop++] = *k;
        else if (by_growth(k, &top[23]) < 0) top[23] = *k;
        else continue;
        qsort(top, ntop, sizeof *top, by_growth);
    }
    for (uint32_t i = 0; i < ntop; i++)
        rt_log("heap:   size %llu first word %s%llx: %u -> %u (%+.1f KiB)", (unsigned long long)top[i].size,
               top[i].tag ? "main+0x" : "", (unsigned long long)top[i].tag, top[i].prev, top[i].n,
               ((double)top[i].n - top[i].prev) * top[i].size / 1024.0);
    // the large blocks of kinds that grew: where they are, a guest thread whose stack it is, the first bytes
    for (uint32_t i = 0; i < ntop; i++) {
        if (top[i].size < BIG || top[i].size > (64u << 20)) continue;
        for (uint32_t j = 0; j < nbig; j++) {
            if (big[j].size != top[i].size) continue;
            char who[400], head[100];
            if (!kern_threads_with_stack_in(big[j].addr, big[j].addr + big[j].size, who, sizeof who))
                snprintf(who, sizeof who, "no thread's stack");
            int k = 0;
            const uint8_t *p = (const uint8_t *)(uintptr_t)big[j].addr;
            for (int b = 0; b < 32 && mem_guest_readable(big[j].addr + b, 1); b++)
                k += snprintf(head + k, sizeof head - k, "%02x", p[b]);
            rt_log("heap:     block %#llx size %llu: %s; starts %s", (unsigned long long)big[j].addr,
                   (unsigned long long)big[j].size, who, head);
        }
    }
}

void mlb_heap_init(void) {   // boot.c, before hostfn_seal
    walk_cb_addr = hostfn_register("<heap census walk>", walk_cb);
}

void mlb_heap_tick(Cpu *c) {
    if (!(rt_trace & RT_TRACE_PERF)) return;
    static uint64_t next, obj, free_fn, largest_fn, walk_fn, min_free = UINT64_MAX;
    static int state;   // 0 unresolved, 1 on, 2 not found
    uint64_t now = kern_now_ns();
    if (state == 2 || now < next) return;
    next = now + INTERVAL_NS;
    if (!state) {
        obj = allocator();
        free_fn = ldr_symbol("_ZNK2nn3mem17StandardAllocator16GetTotalFreeSizeEv");
        largest_fn = ldr_symbol("_ZNK2nn3mem17StandardAllocator18GetAllocatableSizeEv");
        if (cfg_bool("HEAP_CENSUS")) walk_fn = ldr_symbol("_ZNK2nn3mem17StandardAllocator19WalkAllocatedBlocksEPFiPvmS2_ES2_");
        const RtLoaded *m = ldr_module(0);
        main_lo = m->base, main_hi = m->base + m->size;
        state = obj && free_fn && largest_fn ? 1 : 2;
        if (state == 2) {
            rt_log("heap: malloc's allocator not found; no heap lines");
            return;
        }
    }
    uint64_t f = rt_call(c, free_fn, 1, obj), big = rt_call(c, largest_fn, 1, obj);
    if (f < min_free) min_free = f;
    rt_log("heap: malloc free %.1f MiB (lowest %.1f), largest block %.1f MiB, at %.1f min", f / 1048576.0,
           min_free / 1048576.0, big / 1048576.0, (now - rt_guest_start_ns) / 6e10);
    if (walk_fn) census(c, obj, walk_fn);
}
