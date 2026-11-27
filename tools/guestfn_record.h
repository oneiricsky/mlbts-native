// One recorded call of the error judge's "did a runner gain?" test (0x7000d42f20): what it was given and what it
// answered. Written by the recorder tools/guestfn_capture.py puts into the generated C, read by the replay in
// tools/guestfn_errorjudge.c. Only our own code; the records are game data and stay under work/.
#ifndef GUESTFN_RECORD_H
#define GUESTFN_RECORD_H
#include <stdint.h>

#define GF_MAGIC 0x31524647u   // "GFR1"
#define GF_RULES 0xe60         // the rules object up to and including the action count
#define GF_RUNNERS 16
#define GF_IDS 58              // ids the fake team object's table can hold

typedef struct {
    int32_t id, ok;            // ok: every pointer from the team's table to the figures was there
    int32_t info_id, state, pos;
} GfRunner;

typedef struct {
    uint32_t magic, w2, has_out, entry_off;
    uint32_t batting;          // team object B's batting-side byte
    uint32_t runners;
    GfRunner run[GF_RUNNERS];
    uint8_t rules[GF_RULES];   // before the call
    int32_t out_before;
    int32_t result, out_after, base_after;   // base_after: the batter's base in the entry, which the call may rewrite
} GfRecord;
#endif
