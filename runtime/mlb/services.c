// Horizon services the runtime core does not provide (ipc.c rt_service_handler). Command ids and layouts per
// Switchbrew; our own implementation.
//
// lm: the SDK's log manager. nn::lm::Initialize (from nninitInitializeSdkModule in SDK 19.3.11) opens it, and every
// NN_LOG / SDK log line arrives as a log packet; the text goes to our log as "[lm] ...".
#include <stdio.h>
#include <string.h>

#include "host.h"
#include "ipc.h"
#include "platform/platform.h"
#include "cfg.h"
#include "packages.h"
#include "prompts.h"

void gfx_capture_arm(long ahead);   // runtime/gfx/gfx_stubs.c

static int memmem_lite(const char *h, int n, const char *needle) {
    int m = (int)strlen(needle);
    for (int i = 0; i + m <= n; i++)
        if (!memcmp(h + i, needle, (size_t)m)) return 1;
    return 0;
}

// ---- lm: ILogService / ILogger
// A log packet: a 0x18-byte header (process id, thread id, flags, level, verbosity, payload size), then chunks of
// ULEB128 key, ULEB128 size, data. Key 2 is the text, 4 the file, 5 the function, 3 the line number.
enum { LM_TEXT = 2, LM_LINE = 3, LM_FILE = 4, LM_FUNCTION = 5, LM_MODULE = 6, LM_THREAD = 7 };

static uint64_t uleb(const uint8_t **p, const uint8_t *end) {
    uint64_t v = 0;
    for (int shift = 0; *p < end && shift < 64; shift += 7) {
        uint8_t b = *(*p)++;
        v |= (uint64_t)(b & 0x7f) << shift;
        if (!(b & 0x80)) break;
    }
    return v;
}

static void lm_packet(const uint8_t *d, uint64_t n) {
    if (n < 0x18) return;
    uint32_t payload;
    memcpy(&payload, d + 0x14, 4);
    uint8_t level = d[0x11];
    const uint8_t *p = d + 0x18, *end = d + (0x18 + (uint64_t)payload <= n ? 0x18 + payload : n);
    const char *text = NULL, *file = NULL, *fn = NULL;
    int text_n = 0, file_n = 0, fn_n = 0;
    while (p < end) {
        uint64_t key = uleb(&p, end), size = uleb(&p, end);
        if (size > (uint64_t)(end - p)) break;
        if (key == LM_TEXT) text = (const char *)p, text_n = (int)size;
        else if (key == LM_FILE) file = (const char *)p, file_n = (int)size;
        else if (key == LM_FUNCTION) fn = (const char *)p, fn_n = (int)size;
        p += size;
    }
    if (!text) return;
    while (text_n > 0 && (text[text_n - 1] == '\n' || text[text_n - 1] == '\r' || !text[text_n - 1])) text_n--;
    hid_game_log(text, text_n);   // mlbts-native: the screens the game enters switch MLB_PAD_MAP=auto
    if (memmem_lite(text, text_n, "===GAME ENTERED===")) {   // MLB_DRAWLOG=game: one frame's capture in the match
        const char *dl = cfg_get("MLB_DRAWLOG");
        if (dl && !strcmp(dl, "game")) gfx_capture_arm(600);
    }
    if (file && (rt_trace & RT_TRACE_IPC))
        rt_logf("[lm %u] %.*s (%.*s %.*s)\n", level, text_n, text, file_n, file, fn_n, fn ? fn : "");
    else
        rt_logf("[lm %u] %.*s\n", level, text_n, text);
}

static void lm_logger_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    (void)rs;
    switch (rq->cmd) {
    case 0: {   // Log(buffer 0x21)
        const IpcBuffer *b = rq->na && rq->a[0].size ? &rq->a[0] : rq->nx ? &rq->x[0] : NULL;
        if (b && b->size) lm_packet(ipc_guest(b->addr, b->size), b->size);
        return;
    }
    case 1: return;   // SetDestination(u32)
    default: ipc_unimplemented(s, rq);
    }
}

static void lm_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // OpenLogger(pid) -> ILogger
        rs->move[rs->nmove++] = ipc_session_new("lm:ILogger", lm_logger_handler, NULL, NULL);
        return;
    default: ipc_unimplemented(s, rq);
    }
}

// ---- apm: performance mode. The game runs as docked ("boost" configuration 0x00020003 is the docked default).
#define APM_CONFIG_DOCKED 0x00020003u

static void apm_session_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: return;   // SetPerformanceConfiguration(mode, config)
    case 1: {         // GetPerformanceConfiguration(mode) -> config
        uint32_t c = APM_CONFIG_DOCKED;
        IPC_OUT(rs, c);
        return;
    }
    case 2: return;   // SetCpuOverclockEnabled(bool)
    default: ipc_unimplemented(s, rq);
    }
}

static void apm_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // OpenSession -> ISession
        rs->move[rs->nmove++] = ipc_session_new("apm:ISession", apm_session_handler, NULL, NULL);
        return;
    case 1: {   // GetPerformanceMode -> 1 (boost / docked)
        uint32_t mode = 1;
        IPC_OUT(rs, mode);
        return;
    }
    case 6: {   // IsCpuOverclockEnabled
        uint8_t no = 0;
        IPC_OUT(rs, no);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// ---- ectx:aw: error context writer for applications (nn::err::InitializeContextWriterApi, SDK init). The error
// contexts an application attaches to its error reports go nowhere: there is no error report to attach them to.
static void ectx_registrar_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: {   // Complete(result, buffer 5) -> u32
        uint32_t v = 0;
        if (rt_trace & RT_TRACE_IPC) rt_log("ectx: context completed for result %#x", IPC_ARG(rq, uint32_t, 0));
        IPC_OUT(rs, v);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

static void ectx_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // CreateContextRegistrar -> IContextRegistrar
        rs->move[rs->nmove++] = ipc_session_new("ectx:IContextRegistrar", ectx_registrar_handler, NULL, NULL);
        return;
    default: ipc_unimplemented(s, rq);
    }
}

// ---- pctl: parental controls (nn::pctl::detail::ipc::InitializeIpcSessionIfNeeded, SDK init). No restrictions are
// set, no smart device is paired and the play timer is off, so every check passes.
static uint32_t pctl_event_copy(uint32_t *w) {
    if (!*w) *w = kern_event_new();
    return kern_event_readable(*w);
}

static void pctl_service_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static uint32_t suspension, unlinked;
    uint8_t no = 0;
    switch (rq->cmd) {
    case 1: return;      // Initialize
    case 1001: return;   // CheckFreeCommunicationPermission: permitted
    case 1013: return;   // ConfirmStereoVisionPermission: permitted
    case 1017: return;   // EndFreeCommunication
    case 1018: return;   // IsFreeCommunicationAvailable: available (a restriction would be a failing result)
    case 1031:           // IsRestrictionEnabled -> bool
    case 1403:           // IsPairingActive -> bool
    case 1453:           // IsPlayTimerEnabled -> bool
    case 1455:           // IsRestrictedByPlayTimer -> bool
        IPC_OUT(rs, no);
        return;
    case 1451: case 1452: return;   // StartPlayTimer, StopPlayTimer
    case 1457: rs->copy[rs->ncopy++] = pctl_event_copy(&suspension); return;   // GetPlayTimerEventToRequestSuspension
    case 1473: rs->copy[rs->ncopy++] = pctl_event_copy(&unlinked); return;     // GetUnlinkedEvent
    default: ipc_unimplemented(s, rq);
    }
}

static void pctl_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: case 1:   // CreateService(u64, pid), CreateServiceWithoutInitialize(u64, pid) -> IParentalControlService
        rs->move[rs->nmove++] = ipc_session_new("pctl:IParentalControlService", pctl_service_handler, NULL, NULL);
        return;
    default: ipc_unimplemented(s, rq);
    }
}

// ---- nifm:u: the network interface manager. Offline: no network is ever available. Only the commands MLB was seen
// to use are served; the rest stop with a named fatal.
// IRequest: a request for a network connection. Offline it never leaves the Free state (nn::nifm::RequestState 1:
// not on hold, not accepted), whether submitted or not, and its two events never fire.
static uint32_t nifm_event(uint32_t *w) {
    if (!*w) *w = kern_event_new();
    return kern_event_readable(*w);
}

static void nifm_request_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static uint32_t ev_state, ev_other;
    switch (rq->cmd) {
    case 0: {   // GetRequestState -> u32: 1 Free; with offline packages (packages.c) 3 Accepted, a network is there
        uint32_t state = packages_on() ? 3 : 1;
        IPC_OUT(rs, state);
        return;
    }
    case 1:     // GetResult: why there is no connection. nifm (module 110) description 1111, network communication
                // disabled, as with networking switched off [H: the code from yuzu's behaviour, not checked on a console]
        rs->result = packages_on() ? 0 : 0x8AE6Eu;
        return;
    case 2:     // GetSystemEventReadableHandles -> two copy handles
        rs->copy[rs->ncopy++] = nifm_event(&ev_state);
        rs->copy[rs->ncopy++] = nifm_event(&ev_other);
        return;
    case 3: return;   // Cancel
    case 4:           // Submit. With offline packages the request is accepted at once: its state event fires
        if (packages_on()) {
            nifm_event(&ev_state);
            kern_event_signal(ev_state);
        }
        return;
    case 6: case 8: case 10: case 11: case 12: case 13: case 14: case 15: case 16: case 17: case 23:
        return;   // SetRequirementPreset, SetPriority, SetRejectable, SetConnectionConfirmationOption, SetPersistent,
                  // SetInstant, SetSustainable, SetRawPriority, SetGreedy, SetSharable, SetKeptInSleep
    default:
        if (!packages_on()) {
            ipc_unimplemented(s, rq);
            return;
        }
        rt_log("packages: nifm:IRequest command %u answered empty", rq->cmd);
        uint64_t zero = 0;
        IPC_OUT(rs, zero);
    }
}

static void nifm_general_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 4:   // CreateRequest(s32 requirement preset) -> IRequest
        rs->move[rs->nmove++] = ipc_session_new("nifm:IRequest", nifm_request_handler, NULL, NULL);
        return;
    case 12:  // GetCurrentIpAddress -> u32 (network byte order). Only with offline packages: this PC
        if (packages_on()) {
            uint32_t ip = 0x0100007Fu;   // 127.0.0.1
            IPC_OUT(rs, ip);
            return;
        }
        ipc_unimplemented(s, rq);
        return;
    default:
        if (!packages_on()) {
            ipc_unimplemented(s, rq);
            return;
        }
        if (rq->cmd == 1) {   // GetClientId -> buffer 0x1A (u32 client id), in the B or C buffer
            const IpcBuffer *o = rq->nb && rq->b[0].size ? &rq->b[0] : rq->nc && rq->c[0].size ? &rq->c[0] : NULL;
            if (o && o->size >= 4) {
                uint32_t id = 1;
                memcpy(ipc_guest(o->addr, o->size), &id, 4);
            }
            return;
        }
        if (rq->cmd == 21 || rq->cmd == 22) {   // IsAny{Internet,Foreground}RequestAccepted -> bool: yes
            uint8_t yes = 1;
            IPC_OUT(rs, yes);
            return;
        }
        rt_log("packages: nifm:IGeneralService command %u answered empty", rq->cmd);
        uint64_t zero = 0;
        IPC_OUT(rs, zero);
    }
}

static void nifm_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 4: case 5:   // CreateGeneralServiceOld, CreateGeneralService(u64, pid) -> IGeneralService
        rs->move[rs->nmove++] = ipc_session_new("nifm:IGeneralService", nifm_general_handler, NULL, NULL);
        return;
    default: ipc_unimplemented(s, rq);
    }
}

// ---- bsd:u: BSD sockets (nn::socket::Initialize). Offline: the client registers; sockets are not served yet.
static void bsd_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: {   // RegisterClient(LibraryConfigData, u64 pid, u64 transfer memory size, copy handle, pid) -> s32
        int32_t ret = 0;
        IPC_OUT(rs, ret);
        return;
    }
    case 1: return;   // StartMonitoring(u64 pid, pid)
    default: ipc_unimplemented(s, rq);
    }
}

// ---- ssl: TLS for the online modes (nn::ssl::Initialize). Offline: the service starts; contexts are not served.
static void ssl_context_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    (void)rs;
    ipc_unimplemented(s, rq);
}

static void ssl_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // CreateContext(u32 ssl version, u64, pid) -> ISslContext
        rs->move[rs->nmove++] = ipc_session_new("ssl:ISslContext", ssl_context_handler, NULL, NULL);
        return;
    case 5: return;   // SetInterfaceVersion(u32)
    default: ipc_unimplemented(s, rq);
    }
}

// ---- csrng: cryptographically random bytes (nn::crypto::GenerateCryptographicallyRandomBytes), from the OS
static void csrng_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    (void)rs;
    switch (rq->cmd) {
    case 0: {   // GenerateRandomBytes(buffer 6 out)
        const IpcBuffer *b = rq->nb && rq->b[0].size ? &rq->b[0] : NULL;
        if (!b) rt_fatal("csrng: GenerateRandomBytes without an output buffer");
        if (!plat_random(ipc_guest(b->addr, b->size), b->size)) rt_fatal("csrng: no random bytes from the system");
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// ---- ngc:u: the profanity filter (nn::ngc::ProfanityFilter). There is no word list on this host: no text is flagged.
static void ngc_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: {   // GetContentVersion -> u32
        uint32_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 1: {   // Check(u32 regions, ProfanityFilterOption, buffer 5 text) -> u32 mask of the regions that flag it
        uint32_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    // Mask(u32 regions, ProfanityFilterOption, buffer 5 text in) -> (u32 masked words, buffer 6 text out).
    // nn::ngc::ProfanityFilter::MaskProfanityWordsInText (sdk+0x3e8bd0) calls it through the proxy's vtable slot 0x30
    // and copies the out buffer back over the player's text, so the text goes back unchanged. MLB filters the names
    // typed in Road to the Show's player editor this way (a friend's 0.1.1 log: "Enter Last Name" -> crash).
    case 2: {
        const IpcBuffer *in = rq->na ? &rq->a[0] : NULL, *out = rq->nb ? &rq->b[0] : NULL;
        if (!in || !out || !out->size) rt_fatal("ngc: Mask without its text buffers");
        uint64_t n = in->size < out->size ? in->size : out->size;
        char *dst = ipc_guest(out->addr, out->size);
        if (n) memcpy(dst, ipc_guest(in->addr, n), n);
        dst[n < out->size ? n : out->size - 1] = 0;
        uint32_t masked = 0;
        IPC_OUT(rs, masked);
        return;
    }
    case 3: return;   // Reload
    default: ipc_unimplemented(s, rq);
    }
}

// ---- set: nn::settings for applications (ISettingsServer). The language is MLB_LANGUAGE, as am's GetDesiredLanguage
// answers; the region is America. nn::ngc's profanity filter asks for it (GetLanguageSetting, sdk+0x3e9780) when the
// player confirms a typed name.
static uint64_t set_language_code(void) {
    char code[8] = {0};
    const char *lang = cfg_value("MLB_LANGUAGE");
    if (strlen(lang) >= sizeof code) rt_fatal("set: MLB_LANGUAGE=%s is not a language code", lang);
    memcpy(code, lang, strlen(lang));
    uint64_t v;
    memcpy(&v, code, sizeof v);
    return v;
}

static void set_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: {   // GetLanguageCode -> u64
        uint64_t v = set_language_code();
        IPC_OUT(rs, v);
        return;
    }
    case 1: case 5: {   // GetAvailableLanguageCodes (buffer 0xA) / GetAvailableLanguageCodes2 (buffer 6) -> s32 count
        const IpcBuffer *b = rq->cmd == 1 ? (rq->nc ? &rq->c[0] : NULL) : (rq->nb ? &rq->b[0] : NULL);
        int32_t n = 0;
        if (b && b->size >= 8) {
            uint64_t v = set_language_code();
            memcpy(ipc_guest(b->addr, 8), &v, 8);
            n = 1;
        }
        IPC_OUT(rs, n);
        return;
    }
    case 3: case 6: {   // GetAvailableLanguageCodeCount(2) -> s32
        int32_t n = 1;
        IPC_OUT(rs, n);
        return;
    }
    case 4: {   // GetRegionCode -> s32: 1 = America
        int32_t v = 1;
        IPC_OUT(rs, v);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// ---- friend:u: friends (online). The service creator hands out sessions; their commands are served as MLB uses them.
static void friend_service_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    // Offline nothing reaches here. With offline packages (packages.c) the game's online code runs: answer as an
    // account with no friends.
    static uint32_t ev;
    if (!packages_on()) {
        ipc_unimplemented(s, rq);
        return;
    }
    int32_t zero = 0;
    switch (rq->cmd) {
    case 0:   // GetCompletionEvent -> copy handle
        rs->copy[rs->ncopy++] = nifm_event(&ev);
        return;
    case 10100: case 10101: case 10400: case 20101:   // friend / blocked list ids and counts: none
        IPC_OUT(rs, zero);
        break;
    case 1: case 10102: case 10120: case 10121: case 10600: case 10601: case 10610: case 20401: case 30830:
        break;    // Cancel, UpdateFriendInfo, IsFriendListCacheAvailable, EnsureFriendListAvailable,
                  // Declare{Open,Close}OnlinePlaySession, UpdateUserPresence, SyncBlockedUserList, ClearPlayLog
    default:
        rt_log("packages: friend:IFriendService command %u answered empty", rq->cmd);
        IPC_OUT(rs, zero);
        break;
    }
    nifm_event(&ev);
    kern_event_signal(ev);   // the asynchronous ones are done at once
}

// INotificationService: the friend notifications of one user (requests, presence). Offline none arrive: the event is
// never signalled and the queue is always empty.
#define FRIEND_R_QUEUE_EMPTY 0x1E79u   // friends (module 121) description 15 [H: from Ryujinx's ResultCode]
static void friend_notification_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static uint32_t ev;
    switch (rq->cmd) {
    case 0:   // GetEvent -> copy handle
        rs->copy[rs->ncopy++] = nifm_event(&ev);
        return;
    case 1: return;   // Clear
    case 2:           // Pop -> SizedNotificationInfo
        rs->result = FRIEND_R_QUEUE_EMPTY;
        return;
    default: ipc_unimplemented(s, rq);
    }
}

static void friend_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // CreateFriendService -> IFriendService
        rs->move[rs->nmove++] = ipc_session_new("friend:IFriendService", friend_service_handler, NULL, NULL);
        return;
    case 1:   // CreateNotificationService(Uid) -> INotificationService
        rs->move[rs->nmove++] = ipc_session_new("friend:INotificationService", friend_notification_handler, NULL, NULL);
        return;
    default: ipc_unimplemented(s, rq);
    }
}

// ---- nim:eca: the eShop access server (nn::ec). Online only; the server object is handed out and its commands
// are served as MLB uses them.
// IShopServiceAccessServer: 1.0.20 asks the eShop for the game's consumables list
// (/v1/applications/{applicationId}/consumables) when the game modes menu opens (main+0x152e844):
// nn::ec::ShopServiceAccessor::Initialize, then Request, Wait, GetSize and Get. 1.0.15 never did. Offline there is no
// shop: CreateAccessorInterface fails with nifm's "network communication disabled" (as nifm GetResult above), which
// the SDK's ShopServiceAccessServer::ToResult passes through unchanged (only nim results are mapped; nim 0 aborts), and
// the game takes its own failure path: "nn::ec::ShopServiceAccessor::Initialize failed : 110-1111" at a log level
// that never reaches lm, and no list [C, disassembly; 1.0.20 smoke run to a match, 2026-11-15].
static void eca_server_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: {   // CreateAccessorInterface(u8 shop service) -> IShopServiceAccessor
        static int said;
        if (!said++) rt_log("nim: the game asks the eShop for its consumables; offline, refused (110-1111)");
        rs->result = 0x8AE6Eu;
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

static void eca_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // CreateServerInterface(pid, copy transfer memory, u64 size) -> IShopServiceAccessServer
    case 5:   // the form SDK 19.3.11's Proxy::CreateServerInterface sends (24 bytes, copy transfer memory) [C]
        rs->move[rs->nmove++] = ipc_session_new("nim:IShopServiceAccessServer", eca_server_handler, NULL, NULL);
        return;
    case 4: {   // (u64, u32) -> bool. SDK 19.3.11's ShopServiceAccessServer::Proxy::Initialize reconnects to nim:eca
                // when it reads true and keeps its session when false [C, disassembly]; the name is not known.
        uint8_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// ---- nsd:u: network service discovery settings. A retail console's are the production environment "lp1"
// (nn::oe::ServerEnvironmentType 1, Lp). Offline nothing connects to the names it resolves.
#define NSD_ENVIRONMENT "lp1"
static const IpcBuffer *nsd_in(const IpcRequest *rq) {    // AutoSelect in (0x15): A or X
    return rq->na && rq->a[0].size ? &rq->a[0] : rq->nx && rq->x[0].size ? &rq->x[0] : NULL;
}
static const IpcBuffer *nsd_out(const IpcRequest *rq) {   // AutoSelect out (0x16): B or C
    return rq->nb && rq->b[0].size ? &rq->b[0] : rq->nc && rq->c[0].size ? &rq->c[0] : NULL;
}

static void nsd_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 11: {   // GetEnvironmentIdentifier -> buffer 0x16 (8 bytes)
        const IpcBuffer *o = nsd_out(rq);
        if (!o) rt_fatal("nsd: GetEnvironmentIdentifier without an output buffer");
        char *d = ipc_guest(o->addr, o->size);
        memset(d, 0, o->size);
        memcpy(d, NSD_ENVIRONMENT, o->size < sizeof NSD_ENVIRONMENT ? o->size : sizeof NSD_ENVIRONMENT);
        return;
    }
    case 21: {   // ResolveEx(buffer 0x15 Fqdn) -> (Result, buffer 0x16 Fqdn): '%' stands for the environment
        const IpcBuffer *i = nsd_in(rq), *o = nsd_out(rq);
        if (!i || !o) rt_fatal("nsd: ResolveEx without its buffers");
        const char *src = ipc_guest(i->addr, i->size);
        char out[0x100] = {0};
        size_t n = 0;
        for (size_t k = 0; k < i->size && src[k] && n + 4 < sizeof out; k++) {
            if (src[k] == '%') memcpy(out + n, NSD_ENVIRONMENT, 3), n += 3;
            else out[n++] = src[k];
        }
        memcpy(ipc_guest(o->addr, o->size), out, o->size < sizeof out ? o->size : sizeof out);
        if (rt_trace & RT_TRACE_IPC) rt_log("nsd: ResolveEx %s", out);
        uint32_t inner = 0;
        IPC_OUT(rs, inner);
        return;
    }
    case 100: {   // GetApplicationServerEnvironmentType -> u8
        uint8_t v = 1;   // Lp
        IPC_OUT(rs, v);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// ---- audin:u: audio input (the microphone, for voice chat). No input device is offered: every list is empty, so the
// SDK never opens one.
static void audin_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: case 2: case 4: {   // ListAudioIns, ListAudioInsAuto, ListAudioInsAutoFiltered -> u32 count
        uint32_t n = 0;
        IPC_OUT(rs, n);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// nn::nifm::HandleNetworkRequestErrorResult(): on the console it shows the network error applet and reports whether
// the user got a connection; MLB's caller keeps only bit 0 of w0 (main+0x1515f2c) [C, disassembly]. Offline nothing
// can resolve it and no applet exists here: false, without the applet (whose IRequest GetAppletInfo the SDK would ask).
static void ov_nifm_handle_error(Cpu *c) { ret_x(c, 0); }
HOST_OVERRIDE("_ZN2nn4nifm31HandleNetworkRequestErrorResultEv", ov_nifm_handle_error);

// ---- table
void am_applet_oe_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs);   // am.c
void aoc_u_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs);          // aoc.c
void time_u_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs);         // time.c

static const struct { const char *name; IpcHandler handler; } services[] = {
    {"lm", lm_handler},
    {"apm", apm_handler},
    {"appletOE", am_applet_oe_handler},
    {"aoc:u", aoc_u_handler},
    {"ectx:aw", ectx_handler},
    {"pctl", pctl_handler},
    {"time:u", time_u_handler},
    {"nifm:u", nifm_handler},
    {"bsd:u", bsd_handler},
    {"ssl", ssl_handler},
    {"csrng", csrng_handler},
    {"ngc:u", ngc_handler},
    {"set", set_handler},
    {"friend:u", friend_handler},
    {"nim:eca", eca_handler},
    {"nsd:u", nsd_handler},
    {"audin:u", audin_handler},
};

IpcHandler rt_service_handler(const char *name, const char **stable_name) {
    for (unsigned i = 0; i < sizeof services / sizeof *services; i++)
        if (!strcmp(services[i].name, name)) {
            *stable_name = services[i].name;
            return services[i].handler;
        }
    return NULL;
}
