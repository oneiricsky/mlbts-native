// nn::swkbd by symbol override: text entry for the game, through a window of the host (swkbd_win.c). Adapted from TotK
// Recomp runtime/swkbd.c @ ae30a61 (MIT, LICENSE.totk-recomp), itself after MacNativeGames games/totk/runtime/
// swkbd_host.c @ b75be8cf (MIT): the ShowKeyboardArg offsets, the UTF-8/UTF-16 conversions, the disabled-key filter and
// the result codes. The inline keyboard part is our own.
//
// fastball: on the console both keyboards are a library applet. The SDK waits for ISelfController's "library applet
// launchable" event before it starts one, which am.c never signalled: the game froze for good on its "Keyboard" screen
// (entered from the RTTS player search; the last presented frame came right after "Entering screen:
// [Keyboard->Keyboard (0)]", with no IPC sent). This port has no applets, so every swkbd function main imports is
// replaced here and the SDK's own never runs.
//
// MLB's keyboard wrapper is a state machine at main+0xf020 (object fields +0x368 InlineKeyboard *, +0x14a the decided
// text, +0x24c max length, +0x254 flags, +0x398/+0x39c state). Flag bit 8 picks the path:
//   - clear: nn::swkbd::ShowKeyboard (main+0xf2a0), blocking, UTF-16 out; result 0x29f = cancelled.
//   - set: nn::swkbd::InlineKeyboard, which the game drives once a frame with Calc() and answers through callbacks:
//     FinishedInitialize main+0xf434 (calls Appear), ChangedStringUtf8 main+0xf6d0, MovedCursorUtf8 main+0xf7b0,
//     DecidedEnterUtf8 main+0xf890 (copies the text, state 3), DecidedCancel main+0xfa0c (state 4), FinishedKeyboard
//     main+0xf674. Here the first Calc after Initialize calls FinishedInitialize; the Calc after Appear opens the host
//     window and calls ChangedString + DecidedEnter, or DecidedCancel. The argument layouts (UTF-8 text, its length
//     in bytes at +0x7d4, cursor at +0x7e0 / +0x7d8) are the ones those callbacks read. The keyboard image the game
//     would draw stays empty (transparent).
//
// The window blocks the guest thread that called (as ShowKeyboard does on the Switch); the thread gives its virtual
// core up meanwhile and the game reads an idle controller (input_block). Settings:
//   SWKBD_ANSWER=<text>|<cancel>|<initial>   answer without a window (scripted runs); <initial> keeps the starting text
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "platform/platform.h"
#include "swkbd.h"

// KeyboardConfig, then the work buffer {pointer, size}. Offsets confirmed in SDK 19.3.11 (sdk SetHeaderTextUtf8 writes
// +0x24, SetGuideTextUtf8 +0x1a8, SetInitialTextUtf8 +0x3c0/+0x3c4 and reads the buffer at +0x518; main+0xf244 stores
// the buffer at +0x518 and the max length at +0x3ac).
enum {
    KB_TYPE = 0x00, KB_DISABLED = 0x1c, KB_HEADER = 0x24, KB_SUB = 0xa6, KB_GUIDE = 0x1a8, KB_MAX_LEN = 0x3ac,
    KB_MIN_LEN = 0x3b0, KB_PASSWORD = 0x3b4, KB_UTF8 = 0x3bd, KB_INIT_OFF = 0x3c0, KB_INIT_LEN = 0x3c4,
    ARG_WORK = 0x518, ARG_WORK_SIZE = 0x520, KB_TYPE_NUMPAD = 1, SWKBD_CANCELED = 0x29f,
};
// AppearArg as main+0xf4f4 fills it: type +0x00, disabled keys +0x1c, max length +0x20, min length +0x24.
enum { AP_TYPE = 0x00, AP_DISABLED = 0x1c, AP_MAX_LEN = 0x20, AP_MIN_LEN = 0x24 };
// The callbacks' UTF-8 arguments: the text (NUL-terminated), its length in bytes, then the cursor fields.
enum { CB_TEXT_MAX = 0x7d4, CB_LEN = 0x7d4, CB_MOVED_CURSOR = 0x7d8, CB_DIC_START = 0x7d8, CB_DIC_END = 0x7dc,
       CB_CHANGED_CURSOR = 0x7e0, CB_ARG_SIZE = 0x800 };
#define IMAGE_W 1280
#define IMAGE_H 720

static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static uint64_t rd64(const uint8_t *p) { uint64_t v; memcpy(&v, p, 8); return v; }
static void wr32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static size_t u16_len(const uint16_t *s, size_t max) { size_t n = 0; while (n < max && s[n]) n++; return n; }

size_t swkbd_utf16_to_utf8(const uint16_t *s, size_t n, char *out, size_t cap) {
    size_t o = 0;
    if (!cap) return 0;
    for (size_t i = 0; i < n; i++) {
        uint32_t c = s[i];
        if (c >= 0xd800 && c < 0xdc00 && i + 1 < n && s[i + 1] >= 0xdc00 && s[i + 1] < 0xe000)
            c = 0x10000 + ((c - 0xd800) << 10) + (s[++i] - 0xdc00);
        else if (c >= 0xd800 && c < 0xe000) c = 0xfffd;
        char b[4];
        size_t k;
        if (c < 0x80) { b[0] = (char)c; k = 1; }
        else if (c < 0x800) { b[0] = (char)(0xc0 | c >> 6); b[1] = (char)(0x80 | (c & 0x3f)); k = 2; }
        else if (c < 0x10000) { b[0] = (char)(0xe0 | c >> 12); b[1] = (char)(0x80 | ((c >> 6) & 0x3f)); b[2] = (char)(0x80 | (c & 0x3f)); k = 3; }
        else { b[0] = (char)(0xf0 | c >> 18); b[1] = (char)(0x80 | ((c >> 12) & 0x3f)); b[2] = (char)(0x80 | ((c >> 6) & 0x3f)); b[3] = (char)(0x80 | (c & 0x3f)); k = 4; }
        if (o + k + 1 > cap) break;
        memcpy(out + o, b, k);
        o += k;
    }
    out[o] = 0;
    return o;
}

size_t swkbd_utf8_to_utf16(const char *s, uint16_t *out, size_t cap) {
    const unsigned char *p = (const unsigned char *)s;
    size_t n = 0;
    while (*p) {
        uint32_t c;
        int k;
        if (*p < 0x80) { c = *p; k = 0; }
        else if ((*p & 0xe0) == 0xc0) { c = *p & 0x1f; k = 1; }
        else if ((*p & 0xf0) == 0xe0) { c = *p & 0x0f; k = 2; }
        else if ((*p & 0xf8) == 0xf0) { c = *p & 0x07; k = 3; }
        else { c = 0xfffd; k = 0; }
        p++;
        for (int i = 0; i < k; i++, p++) {
            if ((*p & 0xc0) != 0x80) { c = 0xfffd; break; }
            c = c << 6 | (*p & 0x3f);
        }
        if (c > 0x10ffff || (c >= 0xd800 && c < 0xe000)) c = 0xfffd;
        if (c >= 0x10000) {
            if (n + 2 > cap) break;
            out[n++] = (uint16_t)(0xd800 + ((c - 0x10000) >> 10));
            out[n++] = (uint16_t)(0xdc00 + ((c - 0x10000) & 0x3ff));
        } else {
            if (n + 1 > cap) break;
            out[n++] = (uint16_t)c;
        }
    }
    return n;
}

int swkbd_allowed(uint16_t c, uint32_t disabled, int digits_only) {
    int digit = c >= '0' && c <= '9';
    if (digits_only && !digit) return 0;
    if (c < 0x20 || c == 0x7f) return 0;
    if ((disabled & 1u << 1 && c == ' ') || (disabled & 1u << 2 && c == '@') || (disabled & 1u << 3 && c == '%')) return 0;
    if ((disabled & 1u << 4 && c == '/') || (disabled & 1u << 5 && c == '\\') || (disabled & 1u << 6 && digit)) return 0;
    return 1;
}

// Drop disallowed characters and keep at most max units without splitting a surrogate pair.
static size_t clean(uint16_t *t, size_t n, size_t max, uint32_t disabled, int digits_only) {
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        int pair = t[i] >= 0xd800 && t[i] < 0xdc00 && i + 1 < n;
        size_t k = pair ? 2 : 1;
        if (!pair && !swkbd_allowed(t[i], disabled, digits_only)) continue;
        if (o + k > max) break;
        t[o++] = t[i];
        if (pair) t[o++] = t[++i];
    }
    return o;
}

static int clamp_len(int32_t max_len) { return max_len <= 0 || max_len > KB_LIMIT ? KB_LIMIT : max_len; }

// One text entry at a time (the applet is modal too). Runs the window, or answers from SWKBD_ANSWER. The answer is
// cleaned to the request's rules; shorter than min_len counts as cancelled. Returns 1 with the text in u (*n units).
static PlatMutex one = PLAT_MUTEX_INIT;
static int entry(const SwkbdRequest *req, uint16_t *u, size_t cap, size_t *n, int *scripted) {
    const char *forced = cfg_get("SWKBD_ANSWER");
    int confirmed;
    *n = 0;
    *scripted = forced && *forced;
    if (*scripted) {
        confirmed = strcmp(forced, "<cancel>") != 0;
        if (!strcmp(forced, "<initial>")) *n = u16_len(req->initial, KB_LIMIT), memcpy(u, req->initial, *n * 2);
        else if (confirmed) *n = swkbd_utf8_to_utf16(forced, u, cap);
    } else {
        int away = kern_core_away();
        input_block(1);
        confirmed = text_entry_run(req, u, cap, n);
        input_block(0);
        kern_core_back(&away);
    }
    *n = confirmed ? clean(u, *n, (size_t)req->max_len, req->disabled, req->numeric) : 0;
    if (confirmed && (int)*n < req->min_len) confirmed = 0, *n = 0;
    return confirmed;
}

static void log_entry(const char *how, const SwkbdRequest *req, const uint16_t *u, size_t n, int confirmed, int scripted) {
    char prompt[0x101 * 3 + 1], shown[KB_LIMIT * 3 + 1];
    swkbd_utf16_to_utf8(req->prompt, u16_len(req->prompt, 0x100), prompt, sizeof prompt);
    swkbd_utf16_to_utf8(u, n, shown, sizeof shown);
    if (req->password) snprintf(shown, sizeof shown, "(password, %zu units, not logged)", n);
    rt_log("swkbd: %s \"%s\" (%d-%d units, disabled keys %#x%s)%s -> %s%s%s", how, prompt, req->min_len, req->max_len,
           req->disabled, req->numeric ? ", digits" : "", scripted ? " [SWKBD_ANSWER]" : "",
           confirmed ? "\"" : "cancelled", confirmed ? shown : "", confirmed ? "\"" : "");
}

// ---- nn::swkbd::ShowKeyboard
static void request_from(const uint8_t *arg, SwkbdRequest *r) {
    memset(r, 0, sizeof *r);
    r->max_len = clamp_len((int32_t)rd32(arg + KB_MAX_LEN));
    int32_t min_len = (int32_t)rd32(arg + KB_MIN_LEN);
    r->min_len = min_len < 0 ? 0 : min_len > r->max_len ? r->max_len : min_len;
    r->password = rd32(arg + KB_PASSWORD) != 0;
    r->numeric = rd32(arg + KB_TYPE) == KB_TYPE_NUMPAD;
    r->disabled = rd32(arg + KB_DISABLED);
    static const struct { int off; size_t max; } texts[] = {{KB_HEADER, 0x40}, {KB_GUIDE, 0x100}, {KB_SUB, 0x80}};
    for (size_t i = 0; i < 3 && !r->prompt[0]; i++) {
        const uint16_t *t = (const uint16_t *)(arg + texts[i].off);
        size_t n = u16_len(t, texts[i].max);
        memcpy(r->prompt, t, n * 2);
        r->prompt[n] = 0;
    }
    uint64_t work = rd64(arg + ARG_WORK), work_size = rd64(arg + ARG_WORK_SIZE);
    int32_t init_off = (int32_t)rd32(arg + KB_INIT_OFF), init_len = (int32_t)rd32(arg + KB_INIT_LEN);
    size_t n = 0;
    if (init_len > 0 && work && init_off >= 0 && (uint64_t)init_off + (uint64_t)init_len * 2 <= work_size) {
        const uint16_t *t = (const uint16_t *)(uintptr_t)(work + (uint64_t)init_off);
        n = u16_len(t, (size_t)(init_len > KB_LIMIT ? KB_LIMIT : init_len));
        memcpy(r->initial, t, n * 2);
    }
    n = clean(r->initial, n, (size_t)r->max_len, r->disabled, r->numeric);
    r->initial[n] = 0;
}

// Result ShowKeyboard(String *out, const ShowKeyboardArg &arg); String = {pointer, byte size}
static void ov_show_keyboard(Cpu *c) {
    uint64_t *str = arg_p(c, 0);
    const uint8_t *arg = arg_p(c, 1);
    char lr[96];
    if (!str || !arg) rt_fatal("nn::swkbd::ShowKeyboard from %s: null argument", ldr_describe(c->x[30] - 4, lr, sizeof lr));
    static SwkbdRequest req;
    static uint16_t u[KB_LIMIT * 2 + 1];
    size_t n;
    int scripted;
    plat_mutex_lock(&one);
    request_from(arg, &req);
    int utf8 = arg[KB_UTF8] != 0;
    int confirmed = entry(&req, u, KB_LIMIT * 2, &n, &scripted);
    uint64_t buf = str[0], size = str[1];
    if (buf && size) {
        if (utf8) swkbd_utf16_to_utf8(u, n, (char *)(uintptr_t)buf, size);
        else {
            size_t units = size / 2;   // one kept for the terminator
            if (units) {
                size_t k = n;
                if (k > units - 1) { k = units - 1; if (k && u[k - 1] >= 0xd800 && u[k - 1] < 0xdc00) k--; }
                memcpy((void *)(uintptr_t)buf, u, k * 2);
                ((uint16_t *)(uintptr_t)buf)[k] = 0;
            }
        }
    }
    char how[128];
    snprintf(how, sizeof how, "ShowKeyboard from %s (%s out):", ldr_describe(c->x[30] - 4, lr, sizeof lr),
             utf8 ? "UTF-8" : "UTF-16");
    log_entry(how, &req, u, n, confirmed, scripted);
    plat_mutex_unlock(&one);
    ret_x(c, confirmed ? 0 : SWKBD_CANCELED);
}

// ---- nn::swkbd::InlineKeyboard
// One inline keyboard at a time (MLB has one). Its calls come from the game's UI thread.
enum { IK_OFF, IK_INITIALIZED, IK_WAIT_APPEAR, IK_APPEARED, IK_DONE };
static struct {
    uint64_t kb;   // the game's InlineKeyboard object, untouched (its constructor and destructor do nothing here)
    int phase;
    uint64_t on_init, on_finished, on_changed, on_moved, on_enter, on_cancel;
    uint16_t text[KB_LIMIT + 1];   // SetInputText
    SwkbdRequest req;              // Appear
    uint64_t image_cleared;        // the image buffer last cleared (GetImage)
} ik;
static uint8_t *ik_arg;   // a callback's argument, in guest memory (CB_ARG_SIZE bytes)

static void ov_ik_nop(Cpu *c) { (void)c; }   // InlineKeyboard(), ~InlineKeyboard(), SetUtf8Mode, SetCursorPos

// size_t GetRequiredWorkBufferSize(): the SDK's work buffer is never used here
static void ov_ik_work_size(Cpu *c) { ret_x(c, 0x1000); }

// void Initialize(void *work)
static void ov_ik_initialize(Cpu *c) {
    memset(&ik, 0, sizeof ik);
    ik.kb = c->x[0];
    ik.phase = IK_INITIALIZED;
    if (!ik_arg) ik_arg = mem_kernel_alloc(CB_ARG_SIZE, 16);
}

static void ov_ik_finalize(Cpu *c) { (void)c; ik.phase = IK_OFF; ik.image_cleared = 0; }

static void ov_ik_cb_init(Cpu *c) { ik.on_init = c->x[1]; }
static void ov_ik_cb_finished(Cpu *c) { ik.on_finished = c->x[1]; }
static void ov_ik_cb_changed(Cpu *c) { ik.on_changed = c->x[1]; }
static void ov_ik_cb_moved(Cpu *c) { ik.on_moved = c->x[1]; }
static void ov_ik_cb_enter(Cpu *c) { ik.on_enter = c->x[1]; }
static void ov_ik_cb_cancel(Cpu *c) { ik.on_cancel = c->x[1]; }

// InputText is 0x3f4 bytes (main+0xf4a0 clears that much); both its setter and its reader are here, so it holds the
// text as UTF-16, NUL-terminated (501 units = 0x3ea bytes).
// void InputText::SetUtf8(const char *)
static void ov_input_text_set(Cpu *c) {
    uint16_t *t = arg_p(c, 0);
    const char *s = arg_p(c, 1);
    if (!t) return;
    size_t n = s ? swkbd_utf8_to_utf16(s, t, KB_LIMIT) : 0;
    t[n] = 0;
}

// void SetInputText(const InputText &)
static void ov_ik_set_input_text(Cpu *c) {
    const uint16_t *t = arg_p(c, 1);
    size_t n = t ? u16_len(t, KB_LIMIT) : 0;
    if (n) memcpy(ik.text, t, n * 2);
    ik.text[n] = 0;
}

// void Appear(const AppearArg &)
static void ov_ik_appear(Cpu *c) {
    const uint8_t *a = arg_p(c, 1);
    SwkbdRequest *r = &ik.req;
    memset(r, 0, sizeof *r);
    r->max_len = KB_LIMIT;
    if (a) {
        r->max_len = clamp_len((int32_t)rd32(a + AP_MAX_LEN));
        int32_t min_len = (int32_t)rd32(a + AP_MIN_LEN);
        r->min_len = min_len < 0 ? 0 : min_len > r->max_len ? r->max_len : min_len;
        r->numeric = rd32(a + AP_TYPE) == KB_TYPE_NUMPAD;
        r->disabled = rd32(a + AP_DISABLED);
    }
    size_t n = u16_len(ik.text, KB_LIMIT);
    memcpy(r->initial, ik.text, n * 2);
    n = clean(r->initial, n, (size_t)r->max_len, r->disabled, r->numeric);
    r->initial[n] = 0;
    if (ik.phase != IK_OFF) ik.phase = IK_APPEARED;
}

// The callbacks' argument: the text as UTF-8 and its length in bytes; cursor fields after it.
static uint64_t cb_arg(const uint16_t *u, size_t n, int changed) {
    memset(ik_arg, 0, CB_ARG_SIZE);
    size_t len = swkbd_utf16_to_utf8(u, n, (char *)ik_arg, CB_TEXT_MAX);
    wr32(ik_arg + CB_LEN, (uint32_t)len);
    if (changed) {
        wr32(ik_arg + CB_DIC_START, 0);
        wr32(ik_arg + CB_DIC_END, 0);
        wr32(ik_arg + CB_CHANGED_CURSOR, (uint32_t)len);
    } else wr32(ik_arg + CB_MOVED_CURSOR, (uint32_t)len);
    return (uint64_t)(uintptr_t)ik_arg;
}

// void Calc(): the game's once-a-frame update of the keyboard
static void ov_ik_calc(Cpu *c) {
    if (ik.phase == IK_INITIALIZED) {
        ik.phase = IK_WAIT_APPEAR;
        if (ik.on_init) rt_call(c, ik.on_init, 0);   // main+0xf434: sets the text up and calls Appear
        return;
    }
    if (ik.phase != IK_APPEARED) return;   // the game drew one frame of its keyboard screen since Appear
    ik.phase = IK_DONE;
    static uint16_t u[KB_LIMIT * 2 + 1];
    size_t n;
    int scripted;
    plat_mutex_lock(&one);
    int confirmed = entry(&ik.req, u, KB_LIMIT * 2, &n, &scripted);
    log_entry("inline keyboard:", &ik.req, u, n, confirmed, scripted);
    plat_mutex_unlock(&one);
    if (confirmed) {
        if (ik.on_changed) rt_call(c, ik.on_changed, 1, cb_arg(u, n, 1));
        if (ik.on_enter) rt_call(c, ik.on_enter, 1, cb_arg(u, n, 0));
    } else if (ik.on_cancel) rt_call(c, ik.on_cancel, 0);
}

// void GetImageMemoryRequirement(size_t *size, size_t *alignment): one RGBA screen, as the applet's image
static void ov_ik_image_req(Cpu *c) {
    uint64_t *size = arg_p(c, 1), *align = arg_p(c, 2);
    if (size) *size = (uint64_t)IMAGE_W * IMAGE_H * 4;
    if (align) *align = 0x1000;
}

// bool GetImage(void *buffer, size_t size): the keyboard is the host window, so its image is empty (cleared once)
static void ov_ik_get_image(Cpu *c) {
    uint64_t buf = c->x[1], size = c->x[2];
    if (buf && size && buf != ik.image_cleared) {
        memset((void *)(uintptr_t)buf, 0, size);
        ik.image_cleared = buf;
    }
    ret_x(c, 0);
}

// void GetWindowSize(int *width, int *height) const
static void ov_ik_window_size(Cpu *c) {
    int32_t *w = arg_p(c, 1), *h = arg_p(c, 2);
    if (w) *w = IMAGE_W;
    if (h) *h = IMAGE_H;
}

HOST_OVERRIDE("_ZN2nn5swkbd12ShowKeyboardEPNS0_6StringERKNS0_15ShowKeyboardArgE", ov_show_keyboard);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboardC1Ev", ov_ik_nop);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboardD1Ev", ov_ik_nop);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard25GetRequiredWorkBufferSizeEv", ov_ik_work_size);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard10InitializeEPv", ov_ik_initialize);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard8FinalizeEv", ov_ik_finalize);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard29SetFinishedInitializeCallbackEPFvvE", ov_ik_cb_init);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard27SetFinishedKeyboardCallbackEPFvvE", ov_ik_cb_finished);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard28SetChangedStringCallbackUtf8EPFvPKNS0_20ChangedStringArgUtf8EE",
              ov_ik_cb_changed);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard26SetMovedCursorCallbackUtf8EPFvPKNS0_18MovedCursorArgUtf8EE",
              ov_ik_cb_moved);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard27SetDecidedEnterCallbackUtf8EPFvPKNS0_19DecidedEnterArgUtf8EE",
              ov_ik_cb_enter);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard24SetDecidedCancelCallbackEPFvvE", ov_ik_cb_cancel);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard11SetUtf8ModeEb", ov_ik_nop);
HOST_OVERRIDE("_ZN2nn5swkbd9InputText7SetUtf8EPKc", ov_input_text_set);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard12SetInputTextERKNS0_9InputTextE", ov_ik_set_input_text);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard12SetCursorPosEi", ov_ik_nop);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard6AppearERKNS0_9AppearArgE", ov_ik_appear);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard4CalcEv", ov_ik_calc);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard25GetImageMemoryRequirementEPmS2_", ov_ik_image_req);
HOST_OVERRIDE("_ZN2nn5swkbd14InlineKeyboard8GetImageEPvm", ov_ik_get_image);
HOST_OVERRIDE("_ZNK2nn5swkbd14InlineKeyboard13GetWindowSizeEPiS2_", ov_ik_window_size);
