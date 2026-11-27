# MLB The Show 26 (1.0.20), audio map: stream engine, Scream DSP, PXP commentary

Read-only analysis of `main` (base `0x7000000000`), game version 1.0.20: no repo file was edited and the game was not run.

| Source | Detail |
|---|---|
| Index | `tools/map_find.py` and the `sdk` symbol index |
| Code | the generated C in `work/gen/main/`; `tools/disasm.py` / capstone on the shipped ARM64 |
| Strings | the string blobs in `work/build/game/exefs/main` |
| Run log | the existing `work/build/logs/mlb.log` |
| `tools/fnxref.py` | every string a function references, in code order; this ties a log line to the state store that follows it |
| `tools/strdump.py` | the C string at a guest address |

The module carries Sony's Scream / 989snd engine statically, with full PS3-era source paths in its strings (`C:/MLBPS3/SRC/TnT_Audio/SCREAM/...`, `.../NCA/trunk/project/external/wws_gattaca/...`), so most SCREAM functions can be named from the file and message they embed.

Tags: [C] string, symbol, or code read; [I] strong pattern; [H] guess.

## Summary

| Topic | Evidence | Tag |
|---|---|---|
| Mix output | The game mixes in software (Scream), hands 48 kHz 6-channel PCM16 to `audout:u` in 256-frame buffers, and the port reports a single 6-channel session plus one 2-channel session. | [C] |
| Submission point | A `DeviceOut` thread (`0x70018cfd10` → open `0x70018cff0c` → pump `0x70018d00e0`) drains a PCM ring (`0x700153b740` / `0x700153b95c`) into `nn::audio::AppendAudioOutBuffer`. | [C] |
| Stream engine | The game's own per-slot stream engine (`0x70003dde10`): a 7-state machine over 0x4f0-byte slots with states IDLE, WAITING_FOR_HANDLE, QUEUING, BUFFERING, PLAYING, CHECK_FOR_IDLE and WAITING_TO_ISSUE_STOP; music, PA, umpire and commentary are all such streams, started by name through the `SKAT_*` sound categories. | [C] |
| Fading | Not a separate mixer path: a "manual fade" either issues a stop (state 6) or calls Scream's `snd_AutoGain` (`0x7001aa3ba0`). | [C] |
| Commentary ("PXP") | A per-pack object with a 129-entry vtable of play-event handlers; a handler copies an **event name string** (`PitchGetsAwayResult`, `PickoffStealResult`, `IntentionalWalk`, …) and calls vtable slot 9 (`+0x48`) with it, and the engine resolves that name to a sound in the pack's bank (`Audio\PXP.TBL/.MRK/.CTL/.SKX`), whose playlist picks a line and rejects ones in the recent history. | [C] |
| Variants | Three full copies of the PXP engine and five `PlayByPlay*` pack names exist, so the game ships several commentary variants ("TV", "MiLB", "PG", "Griffey", "RF_RF") compiled separately. | [C] |

## Audio output

Where the mix is submitted (confirmed): one thread opens and feeds the audio device.

| Step | Address | What it does | Tag |
|---|---|---|---|
| Output thread | `0x70018cfd10` | 124 generated lines, vtable `0x7002255ba0` slot 2. Lists the device (`nn::audio::ListAudioOuts`, PLT `0x7001c21d80`), calls `0x70018cff0c`, starts it (`StartAudioOut`, PLT `0x7001c21d90`) and then calls the pump `0x70018d00e0` in a loop. Its string pool holds `'DeviceOut'` (the device name the port hands back). | [C] |
| Open session | `0x70018cff0c` | 133 lines. Calls `nn::audio::InitializeAudioOutParameter` then `nn::audio::OpenAudioOut` (PLT `0x7001c21dd0`) with the name at `ctx+0x50`; on failure it sleeps 1 ms and retries. After success it reads `GetAudioOutSampleRate` (PLT `0x7001c21d50`) and `GetAudioOutSampleFormat` (PLT `0x7001c21d60`) to derive the per-buffer byte count. | [C] |
| Submission loop | `0x70018d00e0` | 116 lines. First drains every released buffer (`GetReleasedAudioOutBuffer`, PLT `0x7001c21df0`) until NULL, then for each of three buffer slots at `ctx+0x2b8`, `ctx+0x2e0`, `ctx+0x308` does: `ContainsAudioOutBuffer` → `GetAudioOutBufferDataSize` / `GetAudioOutBufferDataPointer` → `0x700153b740` → if enough, `0x700153b95c` → `AppendAudioOutBuffer` (PLT `0x7001c21e20`); then `GetAudioOutState` and `StartAudioOut` when it reads state 1. | [C] |
| Ring: bytes available | `0x700153b740` | Bytes available in the PCM ring, vtable `0x7002207800` slot 3; compared with the audout buffer size before appending. | [C] |
| Ring: copy out | `0x700153b95c` | Copies out of the ring into the audout buffer, vtable slot 7; called `(ring, dataPointer, dataSize)` and then `AppendAudioOutBuffer`. | [C] |
| SDK clients | `0x7004de73d0`, `0x7004de7c10` | The same two PLT stubs land in the SDK clients: `0x7004de73d0` `nn::audio::OpenAudioOut`, `0x7004de7c10` `nn::audio::AppendAudioOutBuffer`. | [C] |

The port's own log confirms the format and the one-stream claim [C, `work/build/logs/mlb.log`]:

| # | Log line (verbatim) | Tag |
|---|---|---|
| 1 | `[host] audout: OpenAudioOut -> session 1, 48000 Hz, 6 channels, PCM16` | [C] |
| 2 | `[host] audout: first buffer appended: tag 0x1c0f9f120, 3072 bytes at 0x1c10fa000, offset 0, 256 frames, 1 queued` | [C] |
| 3 | `[host] audout: session started (48000 Hz, 6 channels, 8 buffers queued)` | [C] |
| 4 | `[host] audout: OpenAudioOut -> session 2, 48000 Hz, 2 channels, PCM16` | [C] |
| 5 | `[host] audout: session started (48000 Hz, 2 channels, 0 buffers queued)` | [C] |

What the numbers say:

| Fact | Reading | Tag |
|---|---|---|
| Frame size | 3072 bytes / 256 frames = 12 bytes per frame = 6 channels × 16 bit, i.e. 5.1 PCM16 at 48 kHz. | [C] |
| Session count | Only one 6-channel session exists; the 2-channel one starts with no buffers queued. | [C] |
| Which session is the mix | Because there is exactly one `OpenAudioOut` call site in `main` (`0x70018cff0c`) and it is reached once per `DeviceOut` instance, I read the 6-channel instance as the game mix and the 2-channel instance as the headset/voice-chat feed; the code cluster around `0x70018ce000` to `0x70018d2000` is the headset library (`'Headset Thread'`, `'Microphone Thread'`, `LocalTalker`, `RemoteTalker`). | [I] |
| Mix producer | Not pinned in code. The consumer side is proven (the ring read at `0x700153b95c`), but the producer that writes the summed 5.1 PCM into that ring is not identified; see "What is not mapped". | |

The buffering state machine. `0x70003dde10` is the game's stream state machine, not the audout ring [C].

| Step | Address | What it does | Evidence | Tag |
|---|---|---|---|---|
| Read state | `0x70003dde10` | Reads `state = *(u32*)(ctx->slots + idx*0x4f0)`, returns if `state > 6`, and dispatches through a byte jump table. | Jump table at `0x7001d7d780` (verified: 7 bytes, targets below). | [C] |
| Read a state number | `0x70003ddf80`, `0x70003ddf90` | State numbers were read from the store that follows each log call. | At `0x70003ddf80` the string `'%010d, Moving to STATE BUFFERING\n'` is logged and `0x70003ddf90` does `mov w8, #3; str w8, [x20]`. | [C] |

| State | Name | Jump target | Evidence | Tag |
|---|---|---|---|---|
| 0 | IDLE | `0x70003dde9c` | `'%010d, Moving to STATE_IDLE\n'` then `str wzr, [x20]` at `0x70003de17c` | [C] |
| 1 | WAITING_FOR_HANDLE | `0x70003dde44` | `'%010d, Moving to STATE_WAITING_FOR_HANDLE\n'` then `mov w8, #1` at `0x70003de6e8` | [C] |
| 2 | QUEUING | `0x70003ddec4` | `'%010d, Moving to STATE_QUEUING\n'` then `mov w8, #2; str w8,[x20]` at `0x70003de464` | [C] |
| 3 | BUFFERING | `0x70003ddf9c` | `'%010d, Moving to STATE BUFFERING\n'` then `mov w8, #3` at `0x70003ddf90` | [C] |
| 4 | PLAYING | `0x70003ddffc` | `'%010d, Starting user1, going to STATE_PLAYING\n'` then `mov w8, #4` at `0x70003de348` | [C] |
| 5 | CHECK_FOR_IDLE | `0x70003de138` | `'%010d, Moving to STATE_CHECK_FOR_IDLE\n'` then `mov w8, #5` at `0x70003de6bc` | [C] |
| 6 | WAITING_TO_ISSUE_STOP | `0x70003de184` | `'%010d, Manual stop: Moving to STATE_WAITING_TO_ISSUE_STOP\n'` then `mov w8, #6` at `0x70003de4bc` | [C] |

Full state strings quoted from the binary (`fnxref` on `0x70003dde10`, `0x70003df214`, `0x70003df384`, `0x70003de940`, `0x70003dea10`) [C]:

| # | State log string | Tag |
|---|---|---|
| 1 | `'%010d, Starting initial stream, going to STATE_WAITING_FOR_HANDLE\n'` | [C] |
| 2 | `'%010d, Moving to STATE_QUEUING\n'` | [C] |
| 3 | `'%010d, Queuing additional fragment\n'` | [C] |
| 4 | `'%010d, Queing additional fragment on the fly\n'` | [C] |
| 5 | `'%010d, Moving to STATE BUFFERING\n'` | [C] |
| 6 | `'%010d, Buffering complete\n'` | [C] |
| 7 | `'%010d, Releasing stream (continuing)\n'` | [C] |
| 8 | `'%010d, Moving to STATE_PLAYING\n'` | [C] |
| 9 | `'%010d, Starting user1, going to STATE_PLAYING\n'` | [C] |
| 10 | `'%010d, Starting timer, going to STATE_PLAYING\n'` | [C] |
| 11 | `'%010d, Starting unhandled type, going to STATE_PLAYING\n'` | [C] |
| 12 | `'%010d, Preloading stream during user1\n'` | [C] |
| 13 | `'%010d, User1 Complete\n'` | [C] |
| 14 | `'%010d, Timer Complete\n'` | [C] |
| 15 | `'%010d, Received stream handle\n'` | [C] |
| 16 | `'%010d, Staying at STATE_PLAYING until user, timer, or unknown data completes.\n'` | [C] |
| 17 | `'%010d, 989snd failed to start stream!\n'` | [C] |
| 18 | `'Audio is running out of stream handles. Please alert!\n'` | [C] |
| 19 | `'%010d, 989snd queued stream ok, but returned a different handle!\n'` | [C] |
| 20 | `'%010d, Accepting new handle!\n'` | [C] |
| 21 | `'%010d, Sound finished\n'` | [C] |
| 22 | `'%010d, Moving to STATE_CHECK_FOR_IDLE\n'` | [C] |
| 23 | `'%010d, playFragment failed, going to CHECK_FOR_IDLE\n'` | [C] |
| 24 | `'%010d, Manual Stop: Issuing stop request to audio system.\n'` | [C] |
| 25 | `'%010d, Manual Stop: Moving to STATE_IDLE\n'` | [C] |
| 26 | `'%010d, Manual stop: Moving to STATE_WAITING_TO_ISSUE_STOP\n'` | [C] |
| 27 | `'%010d, Manual fade: Issuing fade request to audio system.\n'` | [C] |
| 28 | `'%010d, Manual fade: Moving to STATE_WAITING_TO_ISSUE_STOP\n'` | [C] |

Slot layout read from the code [C]:

| Offset | Field | Tag |
|---|---|---|
| `+0x0` | state | [C] |
| `+0x4b8` / `+0x4bc` | queued / total fragment pair | [C] |
| `+0x4c0` | a "buffering started" byte | [C] |
| `+0x4c4` / `+0x4cc` | handle and "no handle" sentinel `-1` | [C] |
| `+0x4d4` | a flag that selects the fade path over the stop path | [C] |
| `+0x4d8` | cleared on fade | [C] |
| `+0x4e0` | the stop-pending byte on the manager object | [C] |

## Music and fades

The music path is the same stream engine plus a bank and a catalogue layer [C].

| Address | Lines / callers | What it does | Strings | Tag |
|---|---|---|---|---|
| `0x70003d263c` | | Loads a jukebox bank: formats the two strings and calls the Scream bank load `0x7001aa2990` (unload/load bank). | `'Jukebox_%02d'`, `'Audio\%s.bnk'` | [C] |
| `0x70003d45b0` | 4 callers | The jukebox song catalogue. | `'Music Genre'`, `'Jukebox Song'` | [C] |
| `0x70003d4170` | | Reads the per-song metadata fields. | `'SONG_NAME'`, `'ALBUM_NAME'`, `'ARTIST_NAME'`, `'LABEL_NAME'`, `'GENRE_NAME'`, `'LENGTH_STR'` | [C] |
| `0x70003d2ca4` | 445 lines, 6 callers | The music/PA director: it chooses banks, references the boost/boot strings, and calls the stream helpers `0x70003dfee4` / `0x70003dff38` / `0x70003dffac`. | `'PA Music Boost'`, `'WELCOME_BOOT'`, `'Jukebox_%02d'` | [C] |
| `0x70003e8520` | | Streams the front-end jukebox. | `'Mobile Song Buffer'`, `'Jukebox_%02d'` | [C] |
| `0x70003e70fc` | | Plays a sound by symbolic name, the same name-keyed style the commentary uses. | `'MUS_RTTS_Awards'`, `'QUEST_BB_INTRO'`, `'STOP_ALL_SCENE_MUSIC'` | [C] |
| `0x70003f4e04` | | A *playlist gate*: it refuses a playlist for camera/logic reasons and logs each reason (12 such strings). | `'Could not play playlist because the batter isn't right-handed'`, `'...because we aren't focused on first base'` | [C] |

Selection itself is inside Scream [C]: a sound is a list of grains (playlist items), `PlaylistProcessor` walks them and `PlaylistSection` picks the next stream, rejecting repeats.

| Address | Function | Message it logs | Tag |
|---|---|---|---|
| `0x7001ad5610` | `PlaylistProcessor::AddPlaylistItem` | `'PlaylistProcessor::AddPlaylistItem(): Cannot add a %s grain before a Start Stream Playlist grain.'` | [C] |
| `0x7001ad5e98` | `PlaylistProcessor::Start` | `'PlaylistProcessor::Start(): Cannot find starting marker or section '%s' in playlist '%s'.'` | [C] |
| `0x7001ad69c4` | `PlaylistSection` rejecting a stream | `'(%d) PlaylistSection '%s' rejecting stream '%s' because it is in the global history.'` | [C] |
| `0x7001ad59f0` | | `'(%d) Playlist Loop End grain in playlist '%s' has no matching Playlist Loop Start!'` | [C] |
| `0x7001ae097c` | `TransitionMgr::BeginPlaylistDefinition` | `'TransitionMgr::BeginPlaylistDefinition(): Cannot begin playlist definition for '%s' at this time.'` | [C] |
| `0x7001ae0a48` | `TransitionMgr::AddPlaylistItem` | `'TransitionMgr::AddPlaylistItem(): Cannot add %s (grain #%d) in Sound '%s'.'` | [C] |
| `0x7001ab6110` | `snd_TestStreamPlaylist` | `'snd_TestStreamPlaylist(): More than %d unique active playlists found!'` | [C] |

Grain kinds named by the binary [C]:

| Grain kind | Tag |
|---|---|
| `'Start Stream Playlist'` | [C] |
| `'Playlist Configuration'` | [C] |
| `'End Playlist Definition'` | [C] |
| `'Stop Stream Playlist'` | [C] |
| `'Playlist Section'` | [C] |
| `'Playlist Marker'` | [C] |
| `'Playlist Loop Start'` | [C] |
| `'Playlist Loop End'` | [C] |
| `'Playlist Delay'` | [C] |
| `'Goto Playlist Marker'` | [C] |
| `'Playlist Selector'` | [C] |

Fade. `0x70003df4b8` (95 lines, 48 callers) is the shared "manual fade this slot" entry. It resets the slot (`+0x4cc = -1`, `+0x4bc = +0x4b8`, `+0x4d8 = 0`) and then takes one of two branches [C]:

| Branch | Address | What it does | Strings | Tag |
|---|---|---|---|---|
| Live handle | `0x70003df4b8` → `0x7001aa3ba0` | Loads the word at `+0x4c4` into `x0`, sets `x1 = 1`, `v0 = 0, v1 = 8, v2 = 0`, logs the fade request, and calls Scream `snd_AutoGain` (`0x7001aa3ba0`, whose own string is `'snd_AutoGain'`) as `(slot+0x4c4, 1, 0.0f, 8, 0)`: the ramp is issued on the voice, not on a mix bus. | `'%010d, Manual fade: Issuing fade request to audio system.\n'` | [C] |
| No live handle | `0x70003df4b8` | Otherwise it logs the fade-pending line, stores state **6**, sets the stop-pending byte at `[manager+0x4e0] = 1`, and returns 0. | `'%010d, Manual fade: Moving to STATE_WAITING_TO_ISSUE_STOP\n'` | [C] |
| Hard stop sibling | `0x70003ddcb4`, `0x70003ddaf0` | `0x70003ddcb4` (83 lines, 50 callers) issues the stop request; `0x70003ddaf0` drives the state machine directly. | `'%010d, Manual Stop: Issuing stop request to audio system.\n'` | [C] |
| Conclusion | | A fade is a gain ramp on the 989snd voice followed by the same stop handshake; there is no separate mix-level fade bus. | | [C] |

## Commentary events

The PXP path.

Dispatch is by vtable slot, not by string, but the event name is passed as data [C]. The commentary engine is one class with a **129-entry vtable**; each play event is a virtual method.

| Function | Address | Slot | Evidence | Tag |
|---|---|---|---|---|
| `DoIntroLineupLeadInPXP`, pack 1 | `0x7000f64f94` | 31 of 129, vtable `0x70021e07d8` | Identified "in vtable 0x70021e07d8 slot 31 of 129"; string `'DoIntroLineupLeadInPXP'`. | [C] |
| `DoIntroLineupLeadInPXP`, pack 2 | `0x7000fad928` | 31 of 129, vtable `0x70021e0bf0` | Identified "in vtable 0x70021e0bf0 slot 31 of 129", i.e. the same slot in two adjacent vtables (`0x70021e0bf0 - 0x70021e07d8 = 0x418` = 131 slots of 8 bytes), two instantiations. | [C] |
| `PxPHitResultFoul` | `0x7000f846a8` | 61 of 129, vtable `0x70021e07d8` | `'[PxPHitResultFoul: Cleared Event Buffer]'`, `'[PxPHitResultFoul: Stop]'`. | [C] |
| Walk handler | `0x7000f76770` | 16 of 129, vtable `0x70021e07d8` | `'[Walk: Clear Script Phrases]'`, `'IntentionalWalk'`. | [C] |

The event name is the selector. In `DoPickoffResultPXP` (`0x7000e37630`) the string order is `'BaseResultHandler'`, `'PitchGetsAwayResult'`, `'[Cleared Conversation Follow Ups]\n'`, `'DoPickoffResultPXP'`, `'PickoffStealResult'` [C]. Immediately after the `PitchGetsAwayResult` reference the code is [C]:

| Address | Instruction | Note |
|---|---|---|
| `0xe37a10` | `adrp x1, #0x1c43000` | |
| `0xe37a14` | `add x1, x1, #0x36d` | "PitchGetsAwayResult" |
| `0xe37a18` | `add x0, sp, #0x330` | |
| `0xe37a1c` | `mov w2, #0xff` | |
| `0xe37a20` | `bl #0x1c1fbe0` | plt strncpy |
| `0xe37a2c` | `fmov s0, #0.50000000` | |
| `0xe37a30` | `add x1, sp, #0x330` | x1 = the copied event name |
| `0xe37a34` | `mov x0, x19` | x0 = the commentary engine |
| `0xe37a38` | `mov w2, wzr` | |
| `0xe37a3c` | `ldr x8, [x8, #0x48]` | vtable slot 9 |
| `0xe37a40` | `blr x8` | the call with the event name |
| `0xe37a44` | `ldr x0, [x19, #0x18]` | engine+0x18 holds the sound-system pointer |

| Step | What it does | Tag |
|---|---|---|
| Name buffer | The handler builds the event name in a 256-byte stack buffer and calls **vtable slot 9 (`+0x48`) with `(engine, name, 0, 0.5f)`**. | [C] |
| Engine field | `0x18` off the engine holds the sound-system pointer that the next instructions load (`ldr x0, [x19, #0x18]` at `0xe37a44`). | [C] |
| Bank | The engine then resolves that name against its pack's bank; the bank loader object references `'Audio\PXP.MRK'`, `'Audio\PXP.TBL'`, `'Audio\PXP.CTL'`, `'Audio\PXP.SKX'` (`0x7000ab7fa8`, vtable `0x70021a37d0` slot 10 of 11), i.e. markers, table, playlist control and sample bank. | [C] |
| Pick | The sound's playlist section picks the line, skipping anything in the global history (`0x7001ad69c4`). | [C] |
| Resolution | The name→bank-entry resolution happens inside the runtime-filled vtable slot, so that one hop is a strong pattern, not a code read. | [I] |

Conversation bookkeeping around the pick [C]:

| String | Where | What it does | Tag |
|---|---|---|---|
| `'[Cleared Conversation Follow Ups]\n'` | many handlers, and the helper `0x7000e42b9c` (11 callers) | Clears the event's follow-up phrases. | [C] |
| `'[Next Action Fade: Fade Event]'` | handlers | Fade bookkeeping for the next action. | [C] |
| `'[Chatter Registered By Tsunami]'` | the PXP engine bodies | Chatter registration trace. | [C] |
| `'[KillConversation: '` / `'[KillConversation: Cleared Event Buffer]'` | `0x7000e4ae90` | Kills a commentary conversation. | [C] |
| `'[<Event>: Cleared Event Buffer]'` / `'[<Event>: Stop]'` / `'[<Event>: Clear Script Phrases]'` | per handler | The phrase set for an event is therefore a *script* of phrases that the handler clears when the event is superseded. | [C] |

Several commentary packs ship side by side [C]:

| Item | Pack / string | Address | Tag |
|---|---|---|---|
| Pack name | `'PlayByPlay'` | `0x7000ffa2b4` | [C] |
| Pack name | `'PlayByPlayMiLB'` | `0x7000fad808` | [C] |
| Pack name | `'PlayByPlay_PG'` | `0x7000ff98e8` | [C] |
| Pack name | `'PlayByPlay_Griffey'` | `0x7000f64320` | [C] |
| Pack name | `'PlayByPlay_RF_RF'` | `0x7000f64e84` | [C] |
| `PXP_RF` bank | `'PXP_RF'` bank and its own save file `'PXP_RF_SAVE.BIN'` | `0x7000f92c08`, `0x7000f93a94` | [C] |
| Engine body, copy 1 | 1415 lines | `0x7000e472cc` | [C] |
| Engine body, copy 2 | 7517 lines | `0x7000fd9d44` | [C] |
| Engine body, copy 3 | 8574 lines | `0x700102b87c` | [C] |
| Shared strings | `'[Pitcher Intro: Clear Script Phrases]'` and `'[DefensiveLineup: Clear Script Phrases]'` each appear in more than one of those copies, which is what a separately-compiled variant looks like. | | [C] |

End to end (each hop is [C] at the address given):

| Hop | Address | Tag |
|---|---|---|
| Play event handler | | [C] |
| vtable `+0x48` with the event name | | [C] |
| PXP bank sound | | [C] |
| Playlist section picks a line | | [C] |
| Game stream start | `0x70003d95f0` | [C] |
| SKAT play, which fills `SndFileParams` and satisfies `SndFileInterface` (open/seek/read/close) for `snd_stream.cpp` (`0x7001b30a90`) | `0x70003e0960` | [C] |
| 989snd/Scream voice | | [C] |
| Master mix | | [C] |
| `DeviceOut` pump | `0x70018d00e0` | [C] |
| `AppendAudioOutBuffer` | | [C] |

## Function table

| Address | Function | Evidence | Tag |
|---|---|---|---|
| `0x70018cfd10` | audout output thread: list device, open, start, pump | vtable `0x7002255ba0` slot 2; calls `ListAudioOuts`/`StartAudioOut`/`0x70018cff0c`; string `'DeviceOut'` | [C] |
| `0x70018cff0c` | opens the audout session, derives buffer size | `nn::audio::OpenAudioOut` (PLT `0x7001c21dd0`) after `InitializeAudioOutParameter`; on error calls the delay helper with `0xf4240` and retries | [C] |
| `0x70018d00e0` | submits mixed PCM to audout, 3 buffer slots per pass | `GetReleasedAudioOutBuffer`, `ContainsAudioOutBuffer`, `AppendAudioOutBuffer` (PLT `0x7001c21e20`), `GetAudioOutState`, `StartAudioOut` | [C] |
| `0x700153b740` | PCM ring: bytes available | ring vtable `0x7002207800` slot 3; compared with the audout buffer size before appending | [C] |
| `0x700153b95c` | PCM ring: copy out into the audout buffer | ring vtable slot 7; called `(ring, dataPointer, dataSize)` then `AppendAudioOutBuffer` | [C] |
| `0x7001c21dd0` | `main` PLT stub: `nn::audio::OpenAudioOut` | `plt_targets`: `_ZN2nn5audio12OpenAudioOutEPNS0_8AudioOutEPKcRKNS0_17AudioOutParameterE` | [C] |
| `0x7001c21e20` | `main` PLT stub: `nn::audio::AppendAudioOutBuffer` | `plt_targets`: `_ZN2nn5audio20AppendAudioOutBufferEPNS0_8AudioOutEPNS0_14AudioOutBufferE` | [C] |
| `0x7004de73d0` | SDK client: `nn::audio::OpenAudioOut` | `sdk` symbol; port log `audout: OpenAudioOut -> session 1, 48000 Hz, 6 channels, PCM16` | [C] |
| `0x7004de7c10` | SDK client: `nn::audio::AppendAudioOutBuffer` | `sdk` symbol; port log `3072 bytes ... 256 frames` | [C] |
| `0x70003dde10` | per-slot stream state machine, 7 states | `ldr w9,[slot]; cmp w9,#6; b.hi` return; jump table `0x7001d7d780` → `0x70003dde9c/dde44/ddec4/ddf9c/ddffc/de138/de184` | [C] |
| `0x70003ddaf0` | manual stop that drives the state machine | `'%010d, Manual stop: Moving to STATE_WAITING_TO_ISSUE_STOP\n'`; calls `0x70003dde10` and `0x70003ddcb4` | [C] |
| `0x70003ddcb4` | manual stop: issue stop request (50 callers) | `'%010d, Manual Stop: Issuing stop request to audio system.\n'` | [C] |
| `0x70003df4b8` | manual fade of one stream slot (48 callers) | `'%010d, Manual fade: Issuing fade request to audio system.\n'` then `snd_AutoGain`; else state 6 and `strb 1,[mgr+0x4e0]` | [C] |
| `0x70003df214` | waiting-for-handle substate; handle adoption | `'%010d, Received stream handle\n'`, `'Audio is running out of stream handles. Please alert!\n'` | [C] |
| `0x70003df384` | start of a queued stream, handle mismatch check | `'%010d, 989snd queued stream ok, but returned a different handle!\n'`, `'%010d, Accepting new handle!\n'` | [C] |
| `0x70003de940` | buffering complete → PLAYING | `'%010d, Buffering complete\n'`, `'%010d, Releasing stream (continuing)\n'`, `'%010d, Moving to STATE_PLAYING\n'` | [C] |
| `0x70003dea10` | stream finished → CHECK_FOR_IDLE | `'%010d, Sound finished\n'`, `'%010d, Moving to STATE_CHECK_FOR_IDLE\n'` | [C] |
| `0x70003e1ac4` | per-fragment play attempt inside the QUEUING loop | called once per fragment at `0x70003ddef4`; its returned bit selects `'playFragment failed, going to CHECK_FOR_IDLE'` | [I] |
| `0x70003d95f0` | starts a stream slot from a caller request (237 lines, 20 callers) | called from `DoPickoffResultPXP` (`0x7000e37630`) and from the fade site; all callees via vtables | [I] |
| `0x70003dead0` | builds a `'%s%d.%s'` key and starts a stream sound | string `'%s%d.%s'`; calls `0x70003e0960` | [I] |
| `0x70003e0960` | starts a streaming sound: fills `SndFileParams`, starts the 989snd stream | calls `0x7001b32320`/`0x7001b30a90` (`snd_stream.cpp`); strings `'SKAT_Umpire_Distance'`, `'SKAT_Yells_Distance'`, `'By Group'` | [C] |
| `0x70003d3d50` | SKAT category lookup (56 callers) | 13 lines, 2 trap sites; called by `SKAT_Music`, `SKAT_PXP`, Mobile Song Buffer; calls `0x70003e2800` | [C] |
| `0x70003e2400` | `SKAT_Music` category | string `'SKAT_Music'` | [C] |
| `0x70003e57d0` | `SKAT_PXP` category (commentary) | string `'SKAT_PXP'`; 3 callers | [C] |
| `0x70003e8974` | SKAT named parameter setter (game state → mix) | `'Excitement'`, `'Attendance'`, `'Rain Intensity'`, `'COTW_Level_2'` | [C] |
| `0x70003e5d00` | registers the external Scream handler; per-category distance params | string `'ExternalScreamHandler'`, `'SKAT_Umpire_Distance'` | [C] |
| `0x70003e70fc` | plays a sound by symbolic name | `'MUS_RTTS_Awards'`, `'QUEST_BB_INTRO'`, `'STOP_ALL_SCENE_MUSIC'` | [C] |
| `0x70003d263c` | loads a jukebox bank | formats `'Jukebox_%02d'` and `'Audio\%s.bnk'`; calls `0x7001aa2990` (unload/load bank) | [C] |
| `0x70003d2ca4` | music / PA director (445 lines, 6 callers) | `'PA Music Boost'`, `'WELCOME_BOOT'`, `'Jukebox_%02d'`; calls `0x70003dfee4`, `0x70003dff38`, `0x70003dffac` | [C] |
| `0x70003d45b0` | jukebox song catalogue | `'Music Genre'`, `'Jukebox Song'`; 4 callers | [C] |
| `0x70003d4170` | per-song metadata fields | `'SONG_NAME'`, `'ALBUM_NAME'`, `'ARTIST_NAME'`, `'LABEL_NAME'`, `'GENRE_NAME'`, `'LENGTH_STR'` | [C] |
| `0x70003e8520` | streams the front-end jukebox | `'Mobile Song Buffer'`, `'Jukebox_%02d'` | [C] |
| `0x70003f4e04` | playlist gate: refuses a playlist by camera / handedness | `'Could not play playlist because the batter isn't right-handed'`, `'...we aren't focused on first base'` (12 strings) | [C] |
| `0x7001aa3ba0` | `snd_AutoGain`, the fade request | string `'snd_AutoGain'`; called by `0x70003df4b8` as `(slot+0x4c4, 1, 0.0f, 8, 0)` | [C] |
| `0x7001ab6110` | `snd_TestStreamPlaylist`: reports active playlists and streams | `'snd_TestStreamPlaylist(): More than %d unique active playlists found!'` | [C] |
| `0x7001ad5610` | `PlaylistProcessor::AddPlaylistItem` | `'PlaylistProcessor::AddPlaylistItem(): Cannot add a %s grain before a Start Stream Playlist grain.'` | [C] |
| `0x7001ad5e98` | `PlaylistProcessor::Start` | `'PlaylistProcessor::Start(): Cannot find starting marker or section '%s' in playlist '%s'.'` | [C] |
| `0x7001ad69c4` | `PlaylistSection` rejects a recently used stream | `'(%d) PlaylistSection '%s' rejecting stream '%s' because it is in the global history.'` | [C] |
| `0x7001b0b090` | `snd_SynthAllocSubmixVoice` | `'snd_SynthAllocSubmixVoice(): WARNING: No mono submix voices to allocate! Did you set ScreamSynthPara...'` | [C] |
| `0x7001b2e9a0` | `SndStream` handle validation (`snd_stream.cpp`) | `'%s(%d) : ERROR non SndStream handle 0x%08X passe...'`, `'snd_stream.cpp'` | [C] |
| `0x7001b30a90` | validates `SndFileParams`, requires `SndFileInterface` | `'ERROR SndFileInterface missing m_pFileOpen !'`, `'%s(%d) : Invalid SndFileParams.'` | [C] |
| `0x7001b841a0` | DSP graph: patch load / apply (3976 lines) | `'Unsupported patch version %d, expected patch version %d'`, path `.../wws_gattaca/dsp/src/processors/processors_graph.c` | [C] |
| `0x7001b8ba30` | DSP graph message dispatch | `'Unrecognised graph message %d\n'`, `'Invalid message size for kGraphMsgSetParam'` | [C] |
| `0x7001b8bfb0` | DSP graph output node | embedded path `.../dsp/src/processors/processor_output.cpp`, string `'%s: 0x%08x'` | [C] |
| `0x7001b91190` | DSP graph input node | embedded path `.../dsp/src/processors/processor_input.cpp` | [C] |
| `0x7001b944e0` | filter factory (`wws_dsp_flt.cpp`) | `'Filter type not implemented\n'` | [C] |
| `0x7001b91230` | DSP frame processing (1078 lines) | asserts from `dsp_frame.h`, `dsp_processors.h`, `dsp_dly.h`, `dsp_heap.h` in one body | [C] |
| `0x7000e37630` | `DoPickoffResultPXP` commentary handler (1444 lines) | strings `'BaseResultHandler'`, `'PitchGetsAwayResult'`, `'PickoffStealResult'`; calls vtable `+0x48` with the name | [C] |
| `0x7000f846a8` | `PxPHitResultFoul` handler | vtable `0x70021e07d8` slot 61 of 129; `'[PxPHitResultFoul: Cleared Event Buffer]'`, `'[PxPHitResultFoul: Stop]'` | [C] |
| `0x7000f64f94` | `DoIntroLineupLeadInPXP`, pack 1 | vtable `0x70021e07d8` slot 31 of 129; string `'DoIntroLineupLeadInPXP'` | [C] |
| `0x7000fad928` | `DoIntroLineupLeadInPXP`, pack 2 | vtable `0x70021e0bf0` slot 31 of 129; string `'DoIntroLineupLeadInPXP'` | [C] |
| `0x7000f76770` | Walk / `IntentionalWalk` handler | vtable `0x70021e07d8` slot 16 of 129; `'[Walk: Clear Script Phrases]'`, `'IntentionalWalk'` | [C] |
| `0x7000e472cc` | PXP engine body, copy 1 | `'[Chatter Registered By Tsunami]'`, `'[Next Action Fade: Fade Event]'`, per-event `Cleared Event Buffer` pairs | [C] |
| `0x7000fd9d44` | PXP engine body, copy 2 | `'[Chatter Registered By Tsunami]'`; 7517 lines | [C] |
| `0x700102b87c` | PXP engine body, copy 3 | `'[Chatter Registered By Tsunami]'`; 8574 lines | [C] |
| `0x7000ab7fa8` | PXP bank object: table, markers, playlist, samples | `'Audio\PXP.MRK'`, `'Audio\PXP.TBL'`, `'Audio\PXP.CTL'`, `'Audio\PXP.SKX'`; vtable `0x70021a37d0` slot 10 of 11 | [C] |
| `0x7000f92c08` | `PXP_RF` bank object | `'Audio\PXP_RF.mrk'`, `'Audio\PXP_RF.tbl'`, `'Audio\PXP_RF.ctl'`, `'Audio\PXP_RF.skx'` | [C] |
| `0x7000f93a94` | `PXP_RF` save data / reload | `'PXP_RF_SAVE.BIN'`, `'ReloadSaveData'` | [C] |
| `0x7000e4ae90` | kills a commentary conversation | `'[KillConversation: '`, `'[KillConversation: Cleared Event Buffer]'` | [C] |
| `0x7000fad808` | commentary pack `PlayByPlayMiLB` | string `'PlayByPlayMiLB'` | [C] |

## Open questions

| # | Not mapped | What is known | Next step | Tag |
|---|---|---|---|---|
| 1 | The mix producer | The consumer side of the PCM ring is proven (`0x700153b740`/`0x700153b95c` read into the audout buffer), but I did not find the function that writes the summed 5.1 PCM into that ring, so "where the mix is produced" stops at "inside Scream's master/submix path" (`snd_SynthAllocSubmixVoice` `0x7001b0b090` and the DSP graph are the visible evidence). | A write-watchpoint on the ring during a run, or `MLB_FNTRACE` over the Scream range. | |
| 2 | Which audout session carries what | The 6-channel/2-channel split is inferred from channel counts and from the headset code cluster around `0x70018ce000`; no run was traced, so "6ch = game mix, 2ch = voice chat" is [I], not [C]. | | [I] |
| 3 | The target of commentary vtable slot 9 (`+0x48`) | The call with the event name is proven at `0xe37a40`, but the slot is filled at runtime, so the resolving function (name → bank entry) is not identified statically; same for the other 128 slots of `0x70021e07d8` and `0x70021e0bf0`. | | |
| 4 | Pack identity and count | Five `PlayByPlay*` names and three engine-body copies are confirmed, but which pack a given vtable instance points at is not established, and the earlier reading call at `0x7000f64e84` (`'PlayByPlay_RF_RF'`) is not tied to a specific team or mode. | | |
| 5 | Thread ownership and clock | Which thread ticks the stream state machine and Scream's render is not established; `0x70003dde10` is called from two sites and the audio threads visible here (`0x70018cfd10`) are the last hop only. | | |
| 6 | DSP graph content | Processor nodes are identified only by embedded source paths (`processor_input.cpp`, `processor_output.cpp`, `processor_delay.cpp`, `processor_lfo.cpp`, `processor_envelope*.cpp`, `processor_oscillator.cpp`, `processor_saturator.cpp`, `processor_param_eq.cpp`, `processor_trigger_filter.cpp`, `processor_hex_wave.cpp`, `wws_dsp_flt.cpp`); the patch/preset file format and which graph the game builds are not mapped. | | |
| 7 | Method caveat | `tools/map_find.py str` attributes a string to every function whose pool references it, and can over-attribute when a large string blob is shared. Example found and discarded here: `0x7000590ce0` looks like `snd_SynthAllocSubmixVoice` from the `str` search but its own strings are a ZLS/bank-transition loader. Row evidence above therefore comes from `fnxref.py` (per-function, in code order) or from the function's own message, not from `str` alone. | | |
| 8 | No runtime cross-check | Nothing here was confirmed by a run, an audio capture, or a breakpoint; the only runtime artefact used is the existing `work/build/logs/mlb.log`. | | |
| 9 | Quotation kept whole | The prose original breaks one sentence across a line, so a line-by-line quote scan reads the fragment " stops at " on its own; the chain is one phrase and is kept whole in row 1. | | |
