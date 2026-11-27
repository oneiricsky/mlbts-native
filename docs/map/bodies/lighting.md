# Stadium lighting and animation, MLB The Show 26 (Switch) 1.0.20, `main` base 0x7000000000

Read-only analysis of the stadium lighting and the player animation in `main` 1.0.20 (base 0x7000000000):

| Block | Range |
|---|---|
| lighting | 0x70012c0000-0x7001300000 |
| `LocoManager` cluster | 0x700140e900-0x7001437e00 |
| `KineCore` | just below it, 0x7001340000-0x70013b0000 |

Addresses are 1.0.20 (`f_<addr>` in `work/gen`), and each fact was read in the generated C at the quoted `file:line` or in the binary's strings and symbols.

Tags: [C] string, symbol or code read; [I] strong pattern; [H] guess. Where a row's string is [C] but the role is an inference the tag says `C/I`, which the tables write [C/I].

## Summary

| # | Topic | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 | Plain words | two buffers; index at `+0xd38` | A stadium's light changes with the time of day, and redrawing the light for the whole stadium is too slow to do between pitches, so the game keeps two copies of the lighting ("buffers"): it shows one and quietly paints the other for the next time of day, a slice per frame, then swaps them. The manager below is the bookkeeping for that, and the "bake" is the quiet painting. | [C] |
| 2 | Manager getter | `0x70012c54ec`; global `0x70045a9dc0`; one 0x101e40-byte block; built by `0x70012c56e0` | `0x70012c54ec` is the stadium-lighting manager getter: a lazy singleton at `[0x70045a9dc0]`, one 0x101e40-byte zeroed block, built by `0x70012c56e0`; 173 callers, so nearly everything that lights a scene goes through it. | [C] |
| 3 | Two results per buffer | **two lighting results** ("buffers"), index at `+0xd38`; `+0x101400+4*i`; `+0x674+4*i` | The manager keeps **two lighting results** ("buffers", index at `+0xd38`) and, per buffer, two floats: the clock time it was baked from at `+0x101400+4*i` and the requested time at `+0x674+4*i` (both in hours). | [C] |
| 4 | Request gate | `0x70012d0fcc`; `+0xc43`; scene object of type 120; dirty byte `+0xc2d`; `0x70012d1e04` | A request (`0x70012d0fcc`) is gated on the manager's "stadium lighting in use" test (`+0xc43` or a scene object of type 120) and on a *dirty* byte `+0xc2d`; it then calls `0x70012d1e04`, the switch-or-bake decision. | [C] |
| 5 | Switch or bake | `0x70012d1e04`; flag word `+0xd3c` = `0xef01`; `0x70019fb800` | `0x70012d1e04` compares the wanted hour with both buffers: equal to the spare -> **instant buffer flip, no bake**; otherwise it writes the spare's times, sets flag word `+0xd3c` = `0xef01`, and broadcasts the new hour to the stadium props (`0x70019fb800`). | [C] |
| 6 | Background bake | `0x70012d20a0`; `0x7000d52680`; `clock/3600`; `+0xd3c` = `0xec01` | `0x70012d20a0` starts the *background* bake after a play: it ticks the game clock (`0x7000d52680`), stores `clock/3600` h and the requested hour into the spare, and sets `+0xd3c` = `0xec01`. | [C] |
| 7 | Frame job | `0x70012e0150`; 28-entry jump table `0x7001da572e`; counter `+0x10`; stops at 29 | `0x70012e0150` is the frame job: it does the per-frame lighting render and, while `+0xd3c` != 0, runs bake stages. A 28-entry jump table at `0x7001da572e` picks the stage from the counter at `+0x10`; it stops at 29. | [C] |
| 8 | Brake bit 9 | flag bit 9 (`0x200`); stages 7 and 8; graphics job group 2; bit 8 | Flag bit 9 (`0x200`) is the brake: only stages 7 and 8 run without it; with it set, each stage kicks graphics job group 2 and spin-waits, so one call finishes the whole bake. Bit 8 flips buffers at the end. | [C] |
| 9 | Clock | `*[0x700227e460] / 3600.0f`; `0x7000d52680`; `0x7000d529c0`; packed HHMM | The hour comes from the game clock: `*[0x700227e460] / 3600.0f`; `0x7000d52680` advances it and `0x7000d529c0` rebuilds seconds-of-day from a packed HHMM value. | [C] |
| 10 | Animation location | `KineCore`/`AnimWrap`/`Kinematics` at 0x7001340000-0x70013b0000; 0x7001500000+; 0x7001400000 | The animation core is **not** in 0x7001400000-0x7001548000: `KineCore`/`AnimWrap`/`Kinematics` sit at 0x7001340000-0x70013b0000, and 0x7001500000+ is the online-services client. 0x7001400000 holds `LocoManager`. | [C] |
| 11 | `LocoManager` | transition builders ("start/end/turn trans"); the "ring" containers; throttle ("walk-to-jog"); idles; current-motion query | `LocoManager` owns the locomotion state machine: transition builders ("start/end/turn trans"), the "ring" motion containers, throttle ("walk-to-jog"), idles, and the current-motion query it hands to Kinematics. The animation half is the player's motion state machine (walking, turning, idling, catching), which hands clip choices to the game's skeleton system. | [C] |

## Bake lifecycle

What one step is.

| Step | Function | Evidence | What it does | Tag |
|---|---|---|---|---|
| 1 Request | `0x70012d0fcc` | "same scenario" and nothing dirty/forced; `+0xc2d`; `0x70012d1e04(manager, force, s0, s1)` | If the game state says "same scenario" and nothing is dirty/forced, return; else tick the clock when needed, clear `+0xc2d`, and call `0x70012d1e04(manager, force, s0, s1)`. | [C] |
| 2 Decide | `0x70012d1e04` | `s9` = wanted hour (`[manager+0x670]`, or the `s1` argument when >= 0), clamped to 14.5 h when the current view object's type is 48; `s8` = that, or 13.0 h if the (always-true) predicate fails | Compare with the two `+0x101400` slots: current -> nothing; spare -> flip `+0xd38` and `+0xd3c` = 0; neither -> **bake**: write `[+0x674+4*spare]` = requested, `[+0x101400+4*spare]` = wanted, `+0xd3c` = `0xef01`, reset `+0x10` = 0, and tail-call `0x70019fb800` (light-rig event) unless a bake was already running. | [C] |
| 3 Step | `0x70012e0150` (only caller `0x700000b140`, a MainSystem render-job vtable slot) | stages 1..28 from the jump table; named scratch targets (`ScratchZBuffer`, `CloudCastShadows2018`, `StadiumShadowmapEnergy`, `CRadialInwardBlurX`, `phgrassshadow`, ...) | Each stage renders into its named scratch targets, then `+0x10` advances (`counter >= 25 -> 29`, else `counter+1`). | [C] |
| 4 GPU wait | `f_70005a1300(2)` then `f_70005a1a90()` | flag bit 9; spin-wait whose log string is `hang in kick %u`; command buffer `0x700054aab8`, `0x70005f6190`, `0x700054b114` | With flag bit 9, kick graphics job group 2 and spin-wait; the kick is bracketed by a command buffer: `0x700054aab8`, `0x70005f6190`, `0x700054b114`. | [C] |
| 5 Finish | counter == 29 | `+0x288` = 1, `[manager+0x10]` = 0, `[x25+0x7c0]` = 1; flags bit 8 or 9 | If flags bit 8 or 9 is set it flips `+0xd38`, sets `[0x700229fdb80]` = 1.0f, bumps `[0x700229d620]` and `[0x7002284890]`, toggles the scene object's `+0x1320` bool and clears `+0xd3c`; otherwise `+0xd3c` = **2** ("baked, not shown yet"). | [C] |
| 6 Show later | `+0xd3c` = 2 | the next unforced request; spare holds the wanted hour | The next unforced request finds the spare holding the wanted hour and takes the instant-flip path from step 2. | [C] |

## Lighting functions

| Address | Role | Evidence | Tag |
|---|---|---|---|
| 0x70012c54ec | Lighting-manager getter (lazy 0x101e40 alloc) | global `0x70045a9dc0`; `x2 = 0x1e40 \| 0x100000` -> `f_700055a820`; `f_7001c1fb70` memset; `f_70012c56e0` | [C] |
| 0x70012c56e0 | Manager constructor (sub-objects, 15 callers) | callees `f_70012e3b10` ("LightingEnvironment"), `f_70012c5e9c`, `f_7001268e08`; `[x19+0xd38] = 0` | [C] |
| 0x70012c4e50 | Lighting-mode/parameter block init | strings "kLightingMode_Normal", "kLightingMode_Pips", "kLightingMode_FirstLightmapBake"; stores to `[0x70045ac9fc+..]` | [C] |
| 0x70012c62e0 | Sunrise/sunset solver | strings "SNU NEVER RISES HERE!", "SNU NEVER SETS HERE!"; clamps `0x41700000` (15.0f), `0x41900000` (18.0f) | [C/I] |
| 0x70012c66f0 | Depth-only / bent-AO bake passes | strings "BakeDepthOnly", "BakeBentDao", "UseShadowMap" | [C] |
| 0x70012c7ed4 | Predicate: stadium lighting in use | `LD8([x0+0xc43])`; else `[x0+8]` and `[x8+0xb8] == 0x78` | [C] |
| 0x70012c7f04 | Exposure weighting profiles | strings "$(PLATFORM)/lighting/ExposureWeightingBase" ... "FaceRecog" | [C] |
| 0x70012c9440 | LightingProxy load/apply per location | strings "lightingproxy main", "LightingProxy milb_locker_room", "HomeDugout" | [C] |
| 0x70012cb3c0 | Baked-lighting locals loader | string "$(WORLD_PLATFORM)/stadiums/Nowhere/BAKEDLIGHTING_ENVIRONMENT_LOCALS" | [C] |
| 0x70012cc470 | HDRI probes + exposure buffers | strings "m_pExposureBuffer1", "m_pExposureBuffer2", "$(WORLD_PLATFORM)/Lighting/HDRIProbes/%s_specular.$(EXT_WORLD_TEX)" | [C] |
| 0x70012cf660 | Season-based sun path (lat/long) | "SeasonBasedMode :", "UNSET LATITUDE LONGITUDE FOR STADIUM %d!! Tell Pinzy or PHager" | [C] |
| 0x70012d0fcc | Per-frame lighting request/gate | `LD8([x0+0xc43])`; `[x9+0xb8] == 0x78`; `LD8([x0+0xc2d])`; calls `f_7000d52680`, `f_70012d1e04` | [C] |
| 0x70012d1558 | Mark lighting dirty | `{ uint64_t ea = x0 + 0xc2dull; ST8(ea, (uint32_t)x8); }` with `x8 = 1` | [C] |
| 0x70012d1dd0 | Read both bake times of the active buffer | `x9 = 0x101400`; `VSET(0, LD32([x8+x9]))` -> out1; `VSET(0, LD32([x8+0x674]))` -> out2 | [C] |
| 0x70012d1e04 | Switch vs bake decision; writes 0xef01 | `ST32([x19+0xd3c], 0xef01)`; `[x8+0x674] = s9`, `[x8+0x101400] = s8`; tail `f_70019fb800` | [C] |
| 0x70012d20a0 | Start background bake (0xec01) | `f_7000d52680(1)`; `s0 = *[0x700227e460]`; `FOP_DIV` by `0x45610000` (3600.0f); `ST32([x19+0xd3c], 0xec01)` | [C] |
| 0x70012e0150 | Frame lighting setup + bake stages | jump table `0x7001da572e`; `ldr w8,[x19,#0x10]; cmp w8,#0x1d; b.ne #0x12e062c` | [C] |
| 0x70012e1880 | Lighting render job ("Method_RenderJob") | string "Method_RenderJob" | [C] |
| 0x70012dc7f0 | Stage 1 helper: scratch depth | string "ScratchZBuffer" | [C] |
| 0x70012dd8c8 | Stage 8: cloud-cast shadows | strings "CloudCastShadows2018", "ScratchZB1024" | [C] |
| 0x70012ddc40 | Stage 7: stadium shadow-map energy | strings "StadiumShadowmapEnergy", "TempIDLLum8", "CBlurX" | [C] |
| 0x70012de560 | Stage 11: radial inward blur | strings "CRadialInwardBlurX", "temp1024A", "temp1024B" | [C] |
| 0x70012dfad0 | Stages 22-25: grass/dirt shadows | strings "phgrassshadow", "phdirtedge" | [C] |
| 0x70012daee8 | Night-probe texture load | "CROSS/Stadiums/Lighting/%s_NightProbe.dds" | [C] |
| 0x70012dbc30 | Grow border lighting | strings "GrowBorderLighting", "phmoundColor.culling=true" | [C] |
| 0x70012d5bd0 | PS4Lighting per-frame TOD update (2897 L, 27 callers) | "HELP! DEMO MODE BROKEN HERE PS4Lighting if m_bTODemoEnabled" | [C] |
| 0x70012d9590 | SkyOnly lighting reset | string "SkyOnly"; `ST64` of `0x40a0000000000000` (2048.0) at `0x70045a9c1c` | [C] |
| 0x70012d9690 | ObjectLightingStructure node alloc | "IDL: NodeAllopcated to 0x%p, index: %d", "ObjectLightingStructure" | [C] |
| 0x70012d9900 | ObjectLightingStructure node free | "IDL: deleting node 0x%p, index: %d" | [C] |
| 0x70012e64c0 | Season date decoder | "S_decode ==> Please fix the year: %d [1950-2050]" | [C] |
| 0x700128d2a0 | Indirect-light probe task | nearby strings "IRTSample: %d (%d) Texel:%d, subsample %d. st[%d", "AtlasIrradiance", "DrawInstancedProbes" | [C] |
| 0x70019fb800 | Light-rig event broadcast (tail-called by 1e04) | tail `return f_70019fb800(c)` with s0 = new hour; "Method_Broadcaster" neighbours | [C] |
| 0x70019fb880 | Stadium light-rig prop; sets `+0xc3c` | `[x0+0xc3c] = 1` after `f_70012c54ec`; calls `f_7001a3bf20` | [C] |
| 0x7001a3bf20 | Field foot-candles light computation | string "FieldFootCandles" | [C] |
| 0x7000d52680 | Game clock tick / minute event | reads `[0x700227e470]` rate and `*[0x700227e460]`; `f_70005e6b40(0xa8, &minute)` | [C/I] |
| 0x7000d529c0 | Seconds-of-day from packed HHMM | `*[0x700227e468] = (h*60+m)*60` using `0x42700000` (60.0f); `1264.0f` fallback | [C] |
| 0x700076ce78 | Class-table lookup by type id | `cmp x0,#0xd9; ... 0x700218a028 + x0*0x50 + 4` | [C] |
| 0x7001a3c270 | Predicate that always returns 1 | `x0 = (uint32_t)(0x1ull); c->x[0] = x0; return;` -> 13.0/14.5 h fallbacks unreachable | [C] |
| 0x7001a40510 | Current view-object getter | `[0x70047827e8]`; `[x8+0x70] & 1 ? x8 : 0` | [C] |
| 0x70005a1a90 | Graphics-job spin-wait (bit-9 GPU wait) | `(void)(fsub32(&F, x0, x19)); if (fc_sub32(&F, CC_GE)) { goto L_70005a1b54; }`; log "hang in kick %u" | [C] |

## Animation functions

| Address | Role | Evidence | Tag |
|---|---|---|---|
| 0x700141a424 | LocoManager turn transition | "LocoManager turn trans"; reads `[x21+0x104]` count / `[x21+0xc0]` array | [C] |
| 0x700141b090 | LocoManager start transition (1871 L, 8 callers) | "LocoManager start trans", "Breakdown"; 29 indirect calls | [C] |
| 0x70014206e8 | End transition / compressed loco motion | "LocoManager end trans", "Error building compressed loco motion for %s!  Should always find a solution." | [C] |
| 0x7001423410 | End transition (1694 L, 9 callers) | "LocoManager end trans" | [C] |
| 0x7001422220 | Loco throttle | "LocoManager throttle" | [C] |
| 0x70014326a0 | Throttle object (13 callers) | string "Throttle" | [C] |
| 0x700142a900 | Walk-to-jog transition | string "walk-to-jog" | [C] |
| 0x7001427248 | Loco idle | string "Loco manager idle" | [C] |
| 0x700142ae2c | Current motion + skinning params | "Loco Manager current motion", "Throttle", "GlobalSkinningParams" | [C] |
| 0x700142b8fc | Current-motion query (1113 L) | "LocoManager current motion", "placeholder standing idle" | [C] |
| 0x70014229a0 | Catcher-to-popup transition | string "Catcher to popup" | [C] |
| 0x7001436950 | Time-to-location for a ring | "GetTimeToLoc ring"; `FOP_SQRT` of `[+0x190]`/`[+0x198]` deltas | [C] |
| 0x700140e908 | Catch-loco ring constructor (21 callers) | "Catch Loco Ring"; `c->x[2] = 0xc363` class tag | [C] |
| 0x7001409660 | Stopped-pickup idle | string "Stopped pickup idle" | [C] |
| 0x70013af7fc | KineCore::CoreAnimationState::SetupNewAnimation | "KineCore::CoreAnimationState::SetupNewAnimation: Invalid animation! State dump follows:" | [C] |
| 0x70013a8250 | AnimWrap::InitByMem (bind an anim's bones) | "ERROR: In AnimWrap::InitByMem() ... we allocated %d bones from a prev anim" | [C] |
| 0x7001383e80 | Kinematics::Update (vtable slot 8) | "Kinematics::Update() - UPDATING UNINITIALIZED KINEMATICS"; in vtable 0x70021cfbc0 slot 8 | [C] |
| 0x7001385220 | Kinematics::UpdateSkeletonOnly | "Kinematics::UpdateSkeletonOnly() - UPDATING UNINITIALIZED KINEMATICS" | [C] |
| 0x7000d4e560 | Kinematics::LoadAnimBin | string "Kinematics::LoadAnimBin (%p)" | [C] |
| 0x700136bbc0 | BatterStreamerAlt::CheckMaxMoveSize | "BatterStreamerAlt::CheckMaxMoveSize", "MAX_MOVE_SLOT_SI" | [C] |

## Open questions

| Topic | Evidence | What is open | Tag |
|---|---|---|---|
| Stage contents | jump table `0x7001da572e` (stage order); callee names (the passes); `MLB_DRAWLOG`/RenderDoc on a bake frame | No stage was traced to its render targets, textures or shaders; `MLB_DRAWLOG`/RenderDoc on a bake frame would settle it. | [H] |
| The buffer objects | `+0x1011c0`/`+0x1011c8` are the two buffer slots (`x25` plus `(1-2*buffer) ? 8 : 0`); `+0x1011c0+0x6d8/0x6e0/0x7c0/0x254` are touched | Nothing here says what a buffer *contains* (render-target set, irradiance cube, shadow atlas) or how big it is; only the two time arrays are proven. | [H] |
| Per-frame bake granularity | 29-slot counter predicts 29 calls; `docs/walkup-freeze.md` measured about 50 frames (0.9-1.2 s) for a background bake; counter update (`csinc`, `0x12e09f8`) and the two bit-9 gates (`0x12e0668 tbz w8,#1 -> 0x12e141c`, `0x12e0a30 tbz w8,#9 -> 0x12e0ca4`) are read | Which frames run which stage was not traced, so do not treat "one step a frame" as proven. | [H] |
| Flag bits | bit 0 = bake active, bit 1 = "baked, not shown" (`+0xd3c` = 2), bit 8 = flip on finish, bit 9 = blocking; bit 2 (`\|= 4`, `0x70012e0c70`) and the bytes `+0xc3c/-c3d/-c3e` | Bit 2 and those bytes are only located, not explained. | [I] |
| Other manager fields | `+0x288` (bake-complete), `+0x10` (stage), `+0x14`, `+0x464`, `+0x101408` (last wanted hour), `+0x101d30` (int fed to `0x700076ce78`), `+0xb60/+0xb64` are seen used | Their full meaning is not known. | [H] |
| Clock ABI | `0x7000d52680` reads a rate at `0x700227e470` and the clock at `0x700227e460`; `0x7000d529c0` writes a *different* pointer `0x700227e468` | The relation between the two floats is unproven, and the `1264.0f` branch in `0x7000d529c0` is unexplained. | [H] |
| Predicates are stubs here | `0x7001a3c270` returns constant 1 in 1.0.20, so the 13.0 h default and the 14.5 h clamp in `0x70012d1e04` are unreachable | What they were for, and whether a build variant changes it, is unknown. | [C/I] |
| LocoManager layout | the objects these functions drive have `+0xc0` (pointer array), `+0x104` (count), `+0x30`, `+0x9c` (type 6 checks), `+0x190/+0x198` (2-D position), `+0x574` flags | Which of those is the manager and which is the player/actor was not separated; the manager's constructor and vtable were not found. | [H] |
| Clip/blend math | `KineCore::CoreAnimationState::SetupNewAnimation` (0x70013af7fc) and `AnimWrap::InitByMem` (0x70013a8250) are the entry points; the actual clip sampling/blend graph (`BlendGraphDb::Unpack`, 0x70003cc110; `AnimBlock report`, 0x700134af00; `KineCore_MT`, 0x70013ad320) was not read | The clip sampling and blend graph itself is unread. | [H] |
| Probe cluster | only `0x700128d2a0` is listed; its neighbours 0x700128c16c ("AtlasIrradiance"), 0x700128df40 ("IRTSample: ...") and 0x700128e7b8 ("DrawInstancedProbes") were matched by string only | Their bodies were not read, so their roles are guesses. | [H] |
| Ranges | 0x7001500000-0x7001548000 is Ollsc/socket/OpenSSL code ("olClient", "Socket", "ShopServiceAccessor", "OpenSSL"), not animation; 0x7001440000+ is the engine object/stream layer; the animation and lighting work is in the 0x70012c0000-0x7001300000 lighting block and the `LocoManager` cluster 0x700140e900-0x7001437e00, plus `KineCore` just below at 0x7001340000-0x70013b0000 | The ranges named in the task map onto these blocks, not onto the 0x7001400000-0x7001548000 band. | [C] |
| Not in the table, named only by a caller or stage link (role is a guess) | `0x70012e4374`, `0x70012dcf74`, `0x70012dd350`, `0x70012df3f8`, `0x7001426410`, `0x7001413da0`, `0x7001408888`, `0x7001427a4c` | Each is named only by a caller or a stage link, so its role is a guess. | [H] |
