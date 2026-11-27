#!/usr/bin/env python3
"""Put a recorder for 0x7000d42f20 into the generated C, so a live match writes down each call for the offline replay.

    python -I tools/guestfn_capture.py on  [--gen work/gen_cheats] [--out work/scratch/guestfn/live.bin]
    ninja -f work/<build>/build.ninja            # then run a match with that build
    python -I tools/guestfn_capture.py off       # restore the generated C, and build again
    python -I tools/guestfn_test.py --replay work/scratch/guestfn/live.bin

The recorder only reads game memory. It changes ignored generated files (a .orig copy is kept) and is never part of a
normal build. A call is written once: repeats with the same input and answer are skipped.
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTION = 'f_7000d42f20'

RECORDER = r'''
#include <stdio.h>
#include "@HEADER@"
typedef struct { Cpu *c; uint64_t rules, entry, out; GfRecord r; int live; } GfCall;
static uint64_t gf_ptr(uint64_t a) { return a ? *(const uint64_t *)(uintptr_t)a : 0; }
static void gf_runner(GfRecord *r, uint64_t team, int32_t id) {
    if (id < 0 || id >= GF_IDS || r->runners >= GF_RUNNERS) return;
    for (uint32_t i = 0; i < r->runners; i++)
        if (r->run[i].id == id) return;
    GfRunner *g = &r->run[r->runners++];
    g->id = id;
    uint64_t player = gf_ptr(team + 0x18 + 8 * (uint64_t)id);
    uint64_t slot = player ? gf_ptr(player + 0x10) : 0;
    uint64_t info = slot ? gf_ptr(slot + 0x158) : 0, move = slot ? gf_ptr(slot + 0x160) : 0;
    uint64_t state = move ? gf_ptr(move + 8) : 0;
    if (!info || !move || !state) return;
    g->ok = 1;
    memcpy(&g->info_id, (const void *)(uintptr_t)(info + 0x40), 4);
    memcpy(&g->state, (const void *)(uintptr_t)(state + 0x170), 4);
    memcpy(&g->pos, (const void *)(uintptr_t)(move + 0x124), 4);
}
static void gf_begin(GfCall *k, Cpu *c) {
    memset(k, 0, sizeof *k);
    k->c = c, k->rules = c->x[0], k->entry = c->x[1], k->out = c->x[3];
    uint64_t teams = gf_ptr(0x7003aeb728ull), a = gf_ptr(teams ? teams + 0x18 : 0), b = gf_ptr(teams ? teams + 0x20 : 0);
    if (!k->rules || k->entry < k->rules || k->entry - k->rules + 0x9c > GF_RULES || !a || !b) return;
    GfRecord *r = &k->r;
    r->magic = GF_MAGIC, r->w2 = (uint32_t)c->x[2], r->has_out = k->out != 0, r->entry_off = (uint32_t)(k->entry - k->rules);
    r->batting = *(const uint8_t *)(uintptr_t)(b + 0x124);
    memcpy(r->rules, (const void *)(uintptr_t)k->rules, GF_RULES);
    uint64_t team = r->batting == 0 ? b : a;
    static const int k_ids[] = {0x148, 0x1d0};
    for (int i = 0; i < 4; i++) {
        int32_t id;
        memcpy(&id, r->rules + r->entry_off + 0x48 + 4 * i, 4), gf_runner(r, team, id);
        for (int l = 0; l < 2; l++) memcpy(&id, r->rules + k_ids[l] + 4 * i, 4), gf_runner(r, team, id);
        memcpy(&id, r->rules + 0x18c + 0x10 * i, 4), gf_runner(r, team, id);
    }
    if (k->out) memcpy(&r->out_before, (const void *)(uintptr_t)k->out, 4);
    k->live = 1;
}
static void gf_end(GfCall *k) {
    if (!k->live) return;
    GfRecord *r = &k->r;
    r->result = (int32_t)(uint32_t)k->c->x[0];
    if (k->out) memcpy(&r->out_after, (const void *)(uintptr_t)k->out, 4);
    memcpy(&r->base_after, (const void *)(uintptr_t)(k->entry + 0x6c), 4);
    static uint64_t seen[1 << 15];
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < sizeof *r; i++) h = (h ^ ((const uint8_t *)r)[i]) * 1099511628211ull;
    for (unsigned n = 0, at = (unsigned)h & 0x7fff; n < 0x8000; n++, at = (at + 1) & 0x7fff) {
        if (seen[at] == h) return;
        if (!seen[at]) { seen[at] = h; break; }
    }
    FILE *f = fopen("@OUT@", "ab");
    if (!f) return;
    fwrite(r, sizeof *r, 1, f);
    fclose(f);
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['on', 'off'])
    ap.add_argument('--gen', default='work/gen_cheats')
    ap.add_argument('--out', default='work/scratch/guestfn/live.bin')
    args = ap.parse_args()

    head = f'\nvoid {FUNCTION}(Cpu *c) {{\n'
    if args.mode == 'off':
        for orig in (ROOT / args.gen).glob('main/*.c.guestfn-orig'):
            path = orig.with_name(orig.name[:-len('.guestfn-orig')])
            shutil.move(orig, path)
            path.touch()
            print('restored', path.name)
        return
    for path in sorted((ROOT / args.gen).glob('main/*.c')):
        text = path.read_bytes().decode()
        if head not in text:
            continue
        orig = path.with_name(path.name + '.guestfn-orig')
        if orig.exists():
            sys.exit('already on')
        shutil.copy2(path, orig)
        out = (ROOT / args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)
        code = RECORDER.replace('@HEADER@', (ROOT / 'tools' / 'guestfn_record.h').as_posix())
        code = code.replace('@OUT@', out.as_posix())
        first = '#include "simd.h"\n'
        text = text.replace(first, first + code, 1)
        text = text.replace(head, head + '    __attribute__((cleanup(gf_end))) GfCall gf_call;\n'
                                         '    gf_begin(&gf_call, c);\n', 1)
        path.write_bytes(text.encode())
        print('recorder in', path.name, '->', out)
        return
    sys.exit(f'{FUNCTION} not found under {args.gen}')


if __name__ == '__main__':
    main()
