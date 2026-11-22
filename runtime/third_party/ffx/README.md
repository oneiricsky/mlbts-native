# AMD FSR API headers (FidelityFX SDK 2.4.0)

The public API headers of AMD's FSR SDK v2.4.0, revision `7539ae8b6568ad29ed78a753404351daf3b5cca7`, unmodified:
https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK/tree/7539ae8b6568ad29ed78a753404351daf3b5cca7/Kits/FidelityFX

- `api/include/ffx_api.h`, `api/include/ffx_api_types.h`, `api/include/vk/ffx_api_vk.h`
- `upscalers/include/ffx_upscale.h`

`LICENSE.md` is the SDK's `Kits/FidelityFX/docs/license.md` at that revision (the headers carry their own MIT notice).

`runtime/gfx/vk_ffx.c` compiles against them. The code itself, AMD's signed Vulkan runtime
(`amd_fidelityfx_loader_vk.dll`, `amd_fidelityfx_upscaler_vk.dll` from `Kits/FidelityFX/signedbin` at the same
revision), is loaded at run time from the folder of `mlb.exe` and is never committed: the setup downloads it
(`installer/steps.py`), and `tools/fetch_ffx.py` puts it into `work/build` for the dev tree.
