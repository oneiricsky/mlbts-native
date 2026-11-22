// appletOE: the applet manager as an application sees it. Command ids and layouts per Switchbrew ("Applet Manager
// services"); our own implementation, with Power Moon Recomp's runtime/services/am.c (MIT) read for comparison.
//
// SDK 19.3.11's nn::oe::InitializeApplet -> nn::am::InitializeApplicationInterfaces opens appletOE, asks for an
// IApplicationProxy and then for its sub-interfaces. We present a docked console in focus: operation mode console,
// performance mode boost (as apm does), 1920x1080. A command not listed here stops with a named fatal
// (ipc_unimplemented); a command that only takes a setting is accepted and logged under MLB_TRACE=ipc.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "ipc.h"
#include "platform/platform.h"

#define AM_R_NO_MESSAGE 0x680u   // module 128 (am), description 3: ReceiveMessage on an empty queue
#define AM_R_NO_DATA 0x480u      // module 128, description 2: no launch parameter / channel data
#define AM_ARUID 1ull            // applet resource user id (TotK Recomp's choice; hid, audio, vi take it back)

enum { MSG_FOCUS_STATE_CHANGED = 15, MSG_OPERATION_MODE_CHANGED = 30, MSG_PERFORMANCE_MODE_CHANGED = 31 };

static void note(const IpcSession *s, const IpcRequest *rq, const char *what) {
    if (rt_trace & RT_TRACE_IPC) rt_log("am: %s cmd %u %s", s->name, rq->cmd, what);
}

// An event the client receives as a copy handle. Created on first use; signal() is for those am raises itself.
typedef struct { uint32_t w; } AmEvent;

static uint32_t event_copy(AmEvent *e) {
    if (!e->w) e->w = kern_event_new();
    return kern_event_readable(e->w);
}

#define COPY_EVENT(rs, e) ((rs)->copy[(rs)->ncopy++] = event_copy(e))

// ---- the applet message queue (ICommonStateGetter GetEventHandle / ReceiveMessage). Its event stays signalled
// while messages wait, as am does.
static PlatMutex msg_lock = PLAT_MUTEX_INIT;
static AmEvent msg_event;
static uint32_t msg_queue[16];
static unsigned msg_count;
static int msg_started;

static void msg_push(uint32_t m) {   // holding msg_lock
    if (msg_count == sizeof msg_queue / sizeof *msg_queue) rt_fatal("am: message queue full");
    msg_queue[msg_count++] = m;
    if (!msg_event.w) msg_event.w = kern_event_new();
    kern_event_signal(msg_event.w);
}

static void msg_start(void) {   // an application starts in focus: the SDK waits for FocusStateChanged
    plat_mutex_lock(&msg_lock);
    if (!msg_started) {
        msg_started = 1;
        msg_push(MSG_FOCUS_STATE_CHANGED);
    }
    plat_mutex_unlock(&msg_lock);
}

// ---- the window's focus (gfx_present.c calls these from the window thread; declared in gfx.h for TotK's
// ov_system.c). TOTK_ASSUME_FOCUS=1, the default, keeps the application in focus, as TotK and MacNativeGames do: a
// game told it lost focus pauses or mutes itself.
static int32_t focus_state = 1;

void oe_set_focus(int in_focus) { plat_xchg32(&focus_state, in_focus || cfg_bool("TOTK_ASSUME_FOCUS") ? 1 : 2); }

void oe_push_message(uint32_t message) {
    plat_mutex_lock(&msg_lock);
    msg_push(message);
    plat_mutex_unlock(&msg_lock);
}

static void common_state_getter(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static AmEvent sleep_lock, resolution_change, hdcp_change;
    switch (rq->cmd) {
    case 0:   // GetEventHandle
        plat_mutex_lock(&msg_lock);
        COPY_EVENT(rs, &msg_event);
        plat_mutex_unlock(&msg_lock);
        return;
    case 1: {   // ReceiveMessage -> u32
        plat_mutex_lock(&msg_lock);
        if (!msg_count) {
            plat_mutex_unlock(&msg_lock);
            rs->result = AM_R_NO_MESSAGE;
            return;
        }
        uint32_t m = msg_queue[0];
        memmove(msg_queue, msg_queue + 1, --msg_count * sizeof *msg_queue);
        if (!msg_count) kern_event_clear(msg_event.w);
        plat_mutex_unlock(&msg_lock);
        if (rt_trace & RT_TRACE_IPC) rt_log("am: message %u", m);
        IPC_OUT(rs, m);
        return;
    }
    case 3: case 4: return;   // AllowToEnterSleep, DisallowToEnterSleep
    case 5: {                 // GetOperationMode -> u8: 1 console (docked)
        uint8_t v = 1;
        IPC_OUT(rs, v);
        return;
    }
    case 6: {                 // GetPerformanceMode -> u32: 1 boost
        uint32_t v = 1;
        IPC_OUT(rs, v);
        return;
    }
    case 7: {                 // GetCradleStatus -> u8: 1 mounted
        uint8_t v = 1;
        IPC_OUT(rs, v);
        return;
    }
    case 8: {                 // GetBootMode -> u8: 0 normal
        uint8_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 9: {                 // GetCurrentFocusState -> u8: 1 in focus, 2 out of focus
        uint8_t v = (uint8_t)plat_cas32(&focus_state, 0, 0);
        IPC_OUT(rs, v);
        return;
    }
    case 10: case 11: return;   // RequestToAcquireSleepLock, ReleaseSleepLock
    case 13: COPY_EVENT(rs, &sleep_lock); return;   // GetAcquiredSleepLockEvent
    case 50: {                // IsVrModeEnabled -> bool
        uint8_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 60: {                // GetDefaultDisplayResolution -> s32 width, height
        int32_t wh[2] = {1920, 1080};
        IPC_OUT(rs, wh);
        return;
    }
    case 61: COPY_EVENT(rs, &resolution_change); return;   // GetDefaultDisplayResolutionChangeEvent
    case 62: {                // GetHdcpAuthenticationState -> s32: 1 authenticated
        int32_t v = 1;
        IPC_OUT(rs, v);
        return;
    }
    case 63: COPY_EVENT(rs, &hdcp_change); return;   // GetHdcpAuthenticationStateChangeEvent
    case 66: case 67: note(s, rq, "(cpu boost mode)"); return;   // SetCpuBoostMode(u32), CancelCpuBoostMode
    case 900: return;   // SetRequestExitToLibraryAppletAtExecuteNextProgramEnabled
    default: ipc_unimplemented(s, rq);
    }
}

static void self_controller(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static AmEvent launchable, suspended_tick;
    switch (rq->cmd) {
    case 0: rt_log("am: the application asked to exit"); fflush(NULL); exit(0);   // Exit
    case 1: case 2: return;   // LockExit, UnlockExit
    case 3: case 4: return;   // EnterFatalSection, LeaveFatalSection
    case 9:   // GetLibraryAppletLaunchableEvent: signalled, as Horizon does (and Ryujinx) for a foreground application.
        // fastball: left unsignalled, the SDK waited on it forever before starting a library applet (the game froze
        // at its keyboard screen). The keyboard is swkbd.c's now; another applet stops at ILibraryAppletCreator's
        // named fatal instead of hanging.
        COPY_EVENT(rs, &launchable);
        kern_event_signal(launchable.w);
        return;
    case 10:   // SetScreenShotPermission(u32)
    case 11:   // SetOperationModeChangedNotification(bool)
    case 12:   // SetPerformanceModeChangedNotification(bool)
    case 13:   // SetFocusHandlingMode(bool, bool, bool)
    case 14:   // SetRestartMessageEnabled(bool)
    case 16:   // SetOutOfFocusSuspendingEnabled(bool)
    case 19:   // SetAlbumImageOrientation(u32)
    case 62:   // SetIdleTimeDetectionExtension(u32)
    case 65:   // ReportUserIsActive
    case 68:   // SetAutoSleepDisabled(bool)
    case 100:  // SetAlbumImageTakenNotificationEnabled(bool)
        note(s, rq, "(setting accepted)");
        return;
    case 40: {   // CreateManagedDisplayLayer -> u64 layer id (vi opens it later)
        uint64_t layer = 1;
        IPC_OUT(rs, layer);
        return;
    }
    case 63: {   // GetIdleTimeDetectionExtension -> u32
        uint32_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 69: {   // IsAutoSleepDisabled -> bool
        uint8_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 90: {   // GetAccumulatedSuspendedTickValue -> u64
        uint64_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 91: COPY_EVENT(rs, &suspended_tick); return;   // GetAccumulatedSuspendedTickChangedEvent
    default: ipc_unimplemented(s, rq);
    }
}

static void window_controller(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 1: {   // GetAppletResourceUserId -> u64
        uint64_t v = AM_ARUID;
        IPC_OUT(rs, v);
        return;
    }
    case 10: return;   // AcquireForegroundRights
    default: ipc_unimplemented(s, rq);
    }
}

static void audio_controller(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: case 3: case 4: note(s, rq, "(volume)"); return;   // SetExpectedMasterVolume, ChangeMainApplet..., Transparent...
    case 1: case 2: {   // GetMainAppletExpectedMasterVolume, GetLibraryAppletExpectedMasterVolume -> f32
        float v = 1.0f;
        IPC_OUT(rs, v);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

// Interfaces the SDK opens during init but MLB has not used yet: every command stops with a named fatal.
static void unserved(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    (void)rs;
    ipc_unimplemented(s, rq);
}

// ---- IStorage / IStorageAccessor: launch parameters
typedef struct { uint8_t *data; uint64_t size; int32_t refs; } AmStorage;

static void storage_unref(void *p) {
    AmStorage *st = p;
    if (plat_dec32(&st->refs)) return;
    free(st->data);
    free(st);
}

static const IpcBuffer *in_buffer(const IpcRequest *rq) {   // buffer type 0x21: A, or X when A is empty
    return rq->na && rq->a[0].size ? &rq->a[0] : rq->nx ? &rq->x[0] : NULL;
}

static const IpcBuffer *out_buffer(const IpcRequest *rq) {   // buffer type 0x22: B, or C when B is empty
    return rq->nb && rq->b[0].size ? &rq->b[0] : rq->nc ? &rq->c[0] : NULL;
}

static void storage_accessor(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    AmStorage *st = s->state;
    switch (rq->cmd) {
    case 0: {   // GetSize -> s64
        int64_t n = (int64_t)st->size;
        IPC_OUT(rs, n);
        return;
    }
    case 10: case 11: {   // Write(s64 offset, buffer 0x21), Read(s64 offset, buffer 0x22)
        uint64_t off = IPC_ARG(rq, uint64_t, 0);
        const IpcBuffer *b = rq->cmd == 10 ? in_buffer(rq) : out_buffer(rq);
        if (!b) rt_fatal("am: IStorageAccessor cmd %u without a buffer", rq->cmd);
        if (off > st->size || b->size > st->size - off) {
            rs->result = 0x3C80u;   // am description 30, out of bounds (hypothesis: not checked against a console)
            return;
        }
        uint8_t *g = ipc_guest(b->addr, b->size);
        if (rq->cmd == 10) memcpy(st->data + off, g, b->size);
        else memcpy(g, st->data + off, b->size);
        return;
    }
    default: ipc_unimplemented(s, rq);
    }
}

static void storage(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    AmStorage *st = s->state;
    switch (rq->cmd) {
    case 0:   // Open -> IStorageAccessor
        plat_inc32(&st->refs);
        rs->move[rs->nmove++] = ipc_session_new("am:IStorageAccessor", storage_accessor, st, storage_unref);
        return;
    default: ipc_unimplemented(s, rq);
    }
}

static uint32_t storage_new(const void *data, uint64_t size) {
    AmStorage *st = calloc(1, sizeof *st);
    if (!st || !(st->data = calloc(1, size ? size : 1))) rt_fatal("am: storage allocation");
    memcpy(st->data, data, size);
    st->size = size;
    st->refs = 1;
    return ipc_session_new("am:IStorage", storage, st, storage_unref);
}

// ---- IApplicationFunctions
enum { LAUNCH_USER_CHANNEL = 1, LAUNCH_PRESELECTED_USER = 2 };
#define PRESELECTED_USER_MAGIC 0xC79497CAu

static void application_functions(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static int preselected_popped;
    static AmEvent gpu_error, friend_invitation, notification, health_warning;
    switch (rq->cmd) {
    case 1: {   // PopLaunchParameter(u32 kind) -> IStorage
        uint32_t kind = IPC_ARG(rq, uint32_t, 0);
        if (kind == LAUNCH_PRESELECTED_USER && !preselected_popped) {
            // The user qlaunch picked: magic, is_selected, Uid, padding (0x88 bytes).
            uint8_t p[0x88] = {0};
            uint32_t head[2] = {PRESELECTED_USER_MAGIC, 1};
            uint64_t uid[2];
            account_uid(uid);
            memcpy(p, head, 8);
            memcpy(p + 8, uid, 16);
            preselected_popped = 1;
            rs->move[rs->nmove++] = storage_new(p, sizeof p);
            return;
        }
        note(s, rq, kind == LAUNCH_PRESELECTED_USER ? "(preselected user, again: no data)" : "(no launch parameter)");
        rs->result = AM_R_NO_DATA;
        return;
    }
    case 20: {   // EnsureSaveData(Uid) -> u64 required size: 0, the host save directory needs no room
        uint64_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 21: {   // GetDesiredLanguage -> u64 LanguageCode. NACP supports AmericanEnglish only.
        char code[8] = {0};
        const char *lang = cfg_value("MLB_LANGUAGE");
        if (strlen(lang) >= sizeof code) rt_fatal("am: MLB_LANGUAGE=%s is not a language code", lang);
        memcpy(code, lang, strlen(lang));
        IPC_OUT(rs, code);
        return;
    }
    case 22: note(s, rq, "(terminate result)"); return;   // SetTerminateResult(u32)
    case 23: {   // GetDisplayVersion -> char[0x10]: the update's NACP display version
        char v[0x10] = {0};
        snprintf(v, sizeof v, "%s", rt_game_build);
        IPC_OUT(rs, v);
        return;
    }
    case 40: {   // NotifyRunning -> bool
        uint8_t v = 0;
        IPC_OUT(rs, v);
        return;
    }
    case 50: {   // GetPseudoDeviceId -> 16 bytes: derived from the local account, stable across runs
        uint64_t id[2];
        account_uid(id);
        id[0] ^= 0x6d6c627473ull;   // not the Uid itself
        IPC_OUT(rs, id);
        return;
    }
    case 66: case 67: note(s, rq, "(game play recording)"); return;   // InitializeGamePlayRecording, SetGamePlayRecordingState
    case 90: note(s, rq, "(crash report)"); return;                    // EnableApplicationCrashReport(bool)
    case 100: case 101: case 102: note(s, rq, "(copyright frame buffer)"); return;
    case 123: {   // GetPreviousProgramIndex -> s32: -1, not started by ExecuteProgram
        int32_t v = -1;
        IPC_OUT(rs, v);
        return;
    }
    case 130: COPY_EVENT(rs, &gpu_error); return;            // GetGpuErrorDetectedSystemEvent
    case 131: return;                                        // SetDelayTimeToAbortOnGpuError(u64)
    case 140: COPY_EVENT(rs, &friend_invitation); return;    // GetFriendInvitationStorageChannelEvent
    case 141: case 151: rs->result = AM_R_NO_DATA; return;  // TryPopFrom{FriendInvitation,Notification}StorageChannel
    case 150: COPY_EVENT(rs, &notification); return;         // GetNotificationStorageChannelEvent
    case 160: COPY_EVENT(rs, &health_warning); return;       // GetHealthWarningDisappearedSystemEvent
    default: ipc_unimplemented(s, rq);
    }
}

static void application_proxy(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static const struct { unsigned cmd; const char *name; IpcHandler h; } subs[] = {
        {0, "am:ICommonStateGetter", common_state_getter},
        {1, "am:ISelfController", self_controller},
        {2, "am:IWindowController", window_controller},
        {3, "am:IAudioController", audio_controller},
        {4, "am:IDisplayController", unserved},
        {10, "am:IProcessWindingController", unserved},
        {11, "am:ILibraryAppletCreator", unserved},
        {20, "am:IApplicationFunctions", application_functions},
        {1000, "am:IDebugFunctions", unserved},
    };
    for (unsigned i = 0; i < sizeof subs / sizeof *subs; i++)
        if (subs[i].cmd == rq->cmd) {
            rs->move[rs->nmove++] = ipc_session_new(subs[i].name, subs[i].h, NULL, NULL);
            return;
        }
    ipc_unimplemented(s, rq);
}

// IApplicationProxyService
void am_applet_oe_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    switch (rq->cmd) {
    case 0:   // OpenApplicationProxy(pid, u64 reserved, copy handle: current process) -> IApplicationProxy
        msg_start();
        rs->move[rs->nmove++] = ipc_session_new("am:IApplicationProxy", application_proxy, NULL, NULL);
        return;
    default: ipc_unimplemented(s, rq);
    }
}
