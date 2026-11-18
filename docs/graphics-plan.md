# Graphics plan: NVN on Vulkan

How `mlb.exe` gets from the game's first `nvdrv` request to presented frames. Written 2026-11-08, when the boot
stops at `sm: service "nvdrv"` (docs/runtime-port.md, boot step 13). Tags: **[C]** confirmed against the 1.0.15
binaries or this machine, **[H]** hypothesis.

## What MLB asks for

- **Bring-up imports of `main` [C]:** `nv::SetGraphicsAllocator`, `nv::InitializeGraphics`, `nn::vi::Initialize`,
  `OpenDefaultDisplay`, `CreateLayer`, `GetNativeWindow`, `nvnBootstrapLoader`, and `nvnPrivate0`. This is TotK's
  set, minus `nv::SetGraphicsDevtoolsAllocator` and `nn::vi::GetDisplayVsyncEvent`, plus `nvnPrivate0` (unknown so
  far). The `nvdrv` request comes from the SDK's own `nv::InitializeGraphics`, reached because nothing overrides it
  yet.
- **NVN API [C]:** MLB's NVN proc-name table has 536 names. 534 of them are also in TotK 1.2.1's table
  (`runtime/nvn_procs.inc`). MLB adds `nvnBootstrapLoader` and `nvnPrivate0`, and lacks three NVX interop procs
  (`nvnSyncGetNvRmSyncNVX`, `nvnSyncInitializeFromNvRmSyncNVX`, `nvnTextureGetNvRmSurfaceNVX`). The table is the
  whole API the driver exposes, not proof that MLB calls each proc.
- **Shaders [C]:** the FXB banks hold NVN GPU programs with a 0x30-byte header (magic `0x12345678`), a 0x50-byte
  Maxwell SPH, then SASS (docs/recon-report.md §5a). That is the layout TotK's shader client expects (`gfx_shader.c`:
  graphics code starts at code+0x30). The 0x880-byte control section TotK hashes and sends with the code is
  **[H]** the same for MLB's NVN 19.3.11; to be confirmed on the first `nvnProgramSetShaders`.
- **Textures [H]:** TX12 files are decoded by the game's own code into NVN textures, so the back end sees ordinary
  NVN formats. Which ones (BCn, ASTC) is still open.
- **GPU [C]:** RTX 3060 Ti, driver 610.88, Vulkan 1.4.341. It has `VK_EXT_external_memory_host`,
  `VK_EXT_graphics_pipeline_library`, `VK_EXT_transform_feedback`, `VK_EXT_custom_border_color`,
  `VK_EXT_extended_dynamic_state3`, `VK_EXT_vertex_input_dynamic_state`, `VK_EXT_robustness2` and dynamic rendering.
  It has no `textureCompressionASTC_LDR`, so ASTC goes through TotK's compute decoder (`vk_astc.c`).

## Approach: TotK's graphics stack, trimmed

TotK Recomp (MIT) has a working NVN to Vulkan path on Windows. Its NVN front end is MacNativeGames' (MIT); its Vulkan
1.3 back end and Ryujinx-based shader translator are its own. MLB uses the same NVN API on the same Maxwell GPU, so
we reuse it instead of writing one. Astral Chain Recomp and Power Moon Recomp were compared in the recon report;
TotK's is the most complete Windows/Vulkan path of the three.

Layers, all vendored with attribution and `fastball` markers on changes:

| Layer | TotK files | Notes |
|---|---|---|
| Bring-up overrides | `ov_gfx.c` | `nv::*`, `nn::vi::*`, `nvnBootstrapLoader`; add `nvnPrivate0` once known |
| NVN front end | `nvn.h`, `nvn_obj.h`, `nvn_api*.c`, `nvn_ext.c`, `nvn_tex.c`, `nvn_procs.c/.inc`, `nvn_hmap.h`, `nvn_pool_index.h` | records command buffers; nothing reaches the GPU before `QueueSubmitCommands` |
| Vulkan back end | `vk_device.c`, `vk_memory.c`, `vk_texture.c`, `vk_exec*.c`, `vk_pipeline.c`, `vk_sync.c`, `vk_backend.c`, `vk_rec.c`, `vk_usnap.c`, `vk_formats.c`, `vk_deswizzle.c`, `vk_caps.c`, `vk_color.c`, `vk_astc.c`, `tex_astc.c`, `vk_vma.cpp` | replays recorded NVN commands into Vulkan; pools imported as host memory |
| Present and window | `gfx_present.c`, `gfx_window_win.c`, `gfx_null.c` | Win32 window, swapchain, frame pacing |
| Shaders | `gfx_shader.c` + `tools/xlate` (Ryujinx 1.3.2 + TotK patches, .NET NativeAOT) | out-of-process translator, disk cache |

**Not ported (TotK-specific):**
- resolution patch sets;
- DLAA and motion vectors (`vk_dlaa.c`, `vk_mv*`); DLSS came back on 2026-11-13 with MLB's own frame and camera
  motion, see below (TotK's per-object motion is still not ported);
- HDR (`vk_hdr.c`); FSR (`vk_fsr.c`) came back on 2026-11-13, see below;
- contact shadows;
- the ImGui settings menu (back since 2026-11-13 with MLB's own pages, see below);
- TotK's movie decoder;
- frame dumps and the flight recorder (until needed);
- the shader prewarm list, which is built from TotK's captured shaders.

These pieces sit behind headers that get stubs, so they can come back later as options.

**MLB-specific additions, later:**
- an ahead-of-time shader pass over the FXB banks (all 4,505 unique graphics programs are on disk);
- the compute bank layout;
- whatever `nvnPrivate0` turns out to be.

## Toolchain additions

- Vulkan headers: Khronos Vulkan-Headers (Apache-2.0), with the loader `vulkan-1.dll` that the driver installed.
  The import library comes from the Vulkan SDK, or from the headers' DLL exports with `llvm-dlltool`.
- Vulkan Memory Allocator: one header (MIT); `vk_vma.cpp` compiles with clang++ against the MSVC STL from VS 2022,
  which is installed.
- Shader translator: `.NET SDK 10.0.400` is installed and VS 2022 provides the NativeAOT linker. Built from TotK's
  `tools/vendor/ryujinx` with `tools/xlate/patches`, output under `work/` (it is built from MIT sources, not game
  data, but it stays out of git like every build output).

## Steps

1. **G0 toolchain:** Vulkan headers and import library, VMA, the translator built to `work/xlate/`.
2. **G1 bring-up:** `ov_gfx.c` and the NVN proc table (`nvn_procs.c`, with every proc that is not implemented yet
   stopping with its name). Expected result: the boot passes `nv::InitializeGraphics` and the first
   `nvnBootstrapLoader`, then stops at the first NVN proc. That gives the list of procs MLB really calls in order.
3. **G2 front end and back end:** vendor the NVN front end and the Vulkan back end, stub the TotK-only features,
   build. TotK's probes (`--probe-nvn`, `--probe-vkexec`, `--probe-shader`) come along and must pass on this machine.
4. **G3 shaders:** the shader client and translator. First check: the control section and code of MLB's first
   programs translate (log the stage, sizes and translator answer).
5. **G4 first present:** window, swapchain, `nvnQueuePresentTexture`. Done when the window shows the game's first
   frame, whatever it is (clear colour, logo, loading screen).
6. **G5 correctness pass:** render targets and formats MLB uses, texture formats from TX12, the Maxwell behaviour in
   TotK's `docs/maxwell.md`; then the FXB ahead-of-time shader pass.

Each step ends with a run, a log, and a commit; the boot progress in docs/runtime-port.md moves with it.

## Status (2026-11-08)

- **G0 ✔** `tools/fetch_deps.py` (Vulkan-Headers 1.4.363, VMA 3.4.0, `vulkan-1.lib` from the driver's loader exports)
  and `tools/build_xlate.py` (NativeAOT, 11 s). Two of TotK's 15 translator patches are left out: 0010 (soft PCSS
  sun shadows on every 2D-array shadow compare with an explicit LOD) and 0011 (a shadow filter spread factor). They
  change the picture on purpose for TotK, and are not Maxwell behaviour. The support buffer fields they add sit
  after every field the remaining patches use.
- **G3 ✔ (offline)** `tools/shader_smoke.py`: 66 of 66 vertex/fragment programs from 12 FXB banks translate to
  SPIR-V **[C]**.
- **G1, G2 ✔** The whole stack builds with clang (MSVC target) and lld. The boot passes `nv::InitializeGraphics`
  and `nvnBootstrapLoader` and records command buffers.
- **G4 (2026-11-09)** The status above first claimed a presented frame, but `main.c` had the null back end
  hard-coded, so Vulkan never ran. With `MLB_GPU=vulkan` (now the default) the window, swapchain and translator
  (`work/xlate/`, which gfx_shader.c now looks for instead of TotK's `build/xlate/`) run, and the game presents at
  60 fps. Every draw was skipped at first: MLB's programs hold **one stage each** **[C]** and are bound per stage
  (`nvnCommandBufferBindProgram`'s stage mask), while TotK's back end took the last bound program as the whole
  pipeline. `vk_exec_draw.c` now keeps a program per stage and hands draws a combined program (one per distinct set,
  with its own serial), and dispatches the compute stage's program.
- **G5** open: the presented frames are black while the intro movie should play. MLB binds textures and samplers
  through separate handles and writes movie frames with `nvnTextureWriteTexels`; both are next to check.

## Settings menu and antialiasing (2026-11-13)

- **Menu.** F1, or Back and Start together on the pad, opens TotK's Dear ImGui menu (`runtime/gfx/ui/`), drawn over
  the game in the present's command buffer. Pages: Graphics (antialiasing, colour), Display (fullscreen, window size,
  presentation, aspect) and Controls (face-button layout, rumble). Changes apply at once and are written into
  `mlb.cfg` (`cfg_save`: a `MLB_X=` line is updated in place, a missing one added under a heading; comments stay).
  While it is open the game keeps running and `hid.c` gives it an idle controller. `MLB_MENU_TEST=<frame>[:<tab>]`
  opens it at a frame (with `MLB_SHOT`, a picture of it).
- **Menu, second round (2026-11-13).** Pages as TotK's, less its TotK-only rows: Graphics (antialiasing, texture
  filtering, colour), Display (window, presentation, aspect, graphics card, performance overlay), Game (frame queue,
  running out of focus, play time), Sound (volume), Controls (face buttons, vibration and its strength, per-stick dead
  zones with the stick's live deflection), Advanced (TotK's troubleshooting switches that MLB reads, open log folder,
  copy system info, reset all). "Restart now" appears once a setting read at start changed. F10 cycles TotK's
  performance overlay (`perfmon.c`; off costs one branch per present). Not offered: TotK's speaker setting (MLB's
  `audout` always folds 5.1 to stereo), the frame limiter, motion and mouse rows (nothing here reads them), key
  rebinding (hid.c has a fixed table).
- **Internal resolution (`MLB_RENDER_SCALE`, 2026-11-13).** The scene's size is not computed: f_70005a5368 returns entry
  min(level, 4) of a table in main's read-only data (pointer at `0x7002283d80`, table at `0x7001d818a0`): 960x540,
  1280x720, 1366x768, **1440x810** (the TV's level 3), 1600x900 **[C]** (traced with a size log on
  `nvnTextureBuilderSetSize2D`: three 1440x810 targets made by f_70005a4b88, called from f_70005a4634). The output
  table beside it holds 1280x720 and 1920x1080. `runtime/mlb/resolution.c` scales every entry by the chosen
  percentage of 1080p before the guest starts (it checks the bytes first). 150 % (2880x1620) runs at 60 fps on the
  title screen; **200 % crashes** at about frame 1400 with a null write in f_7001267d20 (a game allocation that failed,
  most likely a fixed graphics heap, as TotK's DynamicTextureAllocator **[H]**), so the menu stops at 150 %.
- **FSR 1 (`MLB_UPSCALER=fsr`, off by default; `MLB_SHARPNESS`).** TotK's `vk_fsr.c` scales the picture up on the present
  when the window is larger than 1080p, and `vk_fsr_scene` scales MLB's 1440x810 scene up to the composite's 1080p
  pass right after FXAA; the composite then samples it in the scene's place (`vk_dlaa_swap_img/view`, TotK's DLSS
  hook, held for that one draw). At 100 % and above there is nothing to scale up.
- **Antialiasing (`MLB_AA=fxaa`, default; `off`).** MLB renders its 3D scene into one 1440x810 B10G11R11 image
  (`0x154ea0000`) without any antialiasing, draws the HUD into a separate 1920x1080 layer, and one full-screen draw
  (fragment shader `daf10a59`, `1d3e4d6b` on some menus) tone-maps and scales the scene and lays the HUD over it
  **[C]** (drawlogs of 2026-11-10). `vk_exec_draw.c aa_before_draw` recognises that draw and `vk_aa.c` runs FXAA
  (`runtime/shaders/fxaa.comp`, our own) on the scene in place first, so the HUD stays sharp. Brightness is compared
  in stops, as the scene is linear HDR before the game's exposure. `MLB_AA_STRENGTH` (0..100) sets the sub-pixel
  blending. Shaders compile with `tools/build_shaders.py` (glslang) into committed `*_spv.h` headers.
- **NVIDIA DLSS / DLAA (`MLB_DLSS`, off by default; `MLB_DLSS_PRESET`; 2026-11-13).** `vk_dlaa.c` keeps TotK's NGX
  half (the driver's `_nvngx.dll` loaded at run time, no SDK code) and adds MLB's frame. MLB is a forward renderer: a
  pass with one B10G11R11 colour target and a D24S8 depth target of the same size is the scene and arms the frame
  **[C]** (drawlogs and RenderDoc captures of 2026-11-10/11). At the composite draw (`aa_before_draw`, where FXAA and
  FSR run) DLSS reads that pair and writes its picture at 1080p (DLAA: at the scene's own size), which the composite
  samples in the scene's place, so the HUD is never jittered nor touched. The scene's draws get a Halton sub-pixel
  viewport jitter. Camera: every scene vertex shader computes `gl_Position = c3[0]*x + c3[1]*y + c3[2]*z + c3[3]*w`
  (RenderDoc, frame 18520 event 4746) **[C]**, so the first 64 bytes of vertex bank c3 are the view-projection; the block
  most of a frame's depth-tested scene draws bind is the camera (173 of 174 draws in a frame of play). Motion vectors:
  `shaders/dlss_mv.comp` reprojects depth through last frame's view-projection times the inverse of this frame's
  (double precision on the CPU); a turn of more than ~10 degrees or a 10 % field-of-view change counts as a camera cut
  and resets DLSS's history. Players and the ball get the camera's motion only. The mode sets the scene size through
  `resolution.c` (DLAA 1920x1080, Quality the game's own 1440x810: 75 %, not NVIDIA's 67 %; Balanced 1114x626,
  Performance 960x540, Ultra Performance 640x360) when the driver has NGX and `nvngx_dlss.dll` (NVIDIA's, v310.9.1 as TotK's setup pins it, not in git) is
  next to `mlb.exe`; restart to change it. Test knobs: `MLB_DLSS_MVDEBUG=1` (vectors instead of the picture),
  `MLB_DLSS_MV=0`, `MLB_DLSS_JITTER=0`, `MLB_DLSS_TIMES=1` (GPU time every 600 frames).
