# SUNNYPILOT for BMW i3
FlexRay-CAN (Intel PC/OpenVINO Build)

![](docs/assets/Gemini_Generated_Image_en6pmeen6pmeen6p.jpg)

## Dev Branch Delta From `sunnypilot/sunnypilot`

This `dev` branch starts from upstream `sunnypilot/sunnypilot` and adds only the changes needed to bring up the Intel PC + BRIO webcam + Pico FlexRay runtime with the smallest practical delta.

## What Was Imported And Adapted

1. Added a dedicated PC launcher:
   - [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - keeps PC bring-up separate from upstream [`go.sh`](/home/gericho/sunnypilot/go.sh)
   - exports only the runtime env needed for webcam, model, encoder and manager startup

2. Imported the webcam runtime from the fork into a contained area:
   - [`tools/webcam/camera.py`](/home/gericho/sunnypilot/tools/webcam/camera.py)
   - [`tools/webcam/camerad.py`](/home/gericho/sunnypilot/tools/webcam/camerad.py)
   - [`tools/webcam/README.md`](/home/gericho/sunnypilot/tools/webcam/README.md)

3. Added PC camera geometry support without hardcoding device-camera assumptions into the launcher:
   - [`common/transformations/camera.py`](/home/gericho/sunnypilot/common/transformations/camera.py)
   - PC runtime can now derive `fcam` and `ecam` from env such as:
     - `ROAD_W`, `ROAD_H`
     - `ROAD_HFOV_DEG` or `ROAD_FOCAL_PIXELS`
     - `WIDE_HFOV_DEG` or `WIDE_FOCAL_PIXELS`

4. Added the minimum Panda/FlexRay transport block required for the real hardware rig:
   - [`.gitmodules`](/home/gericho/sunnypilot/.gitmodules)
   - [panda](/home/gericho/sunnypilot/panda)
   - [opendbc_repo](/home/gericho/sunnypilot/opendbc_repo)
   - [selfdrive/pandad](/home/gericho/sunnypilot/selfdrive/pandad)
   - this is the minimum structural change needed so upstream `dev` can talk to the Pico FlexRay hardware

5. Built and enabled the external `pandad` runtime used by the Pico/FlexRay path:
   - [`selfdrive/pandad`](/home/gericho/sunnypilot/selfdrive/pandad)
   - [`SConstruct`](/home/gericho/sunnypilot/SConstruct)
   - the build side was adjusted only as much as needed to compile the imported `pandad`

6. Fixed the PC UI crash blocker with the smallest viable patch:
   - [`selfdrive/ui/layouts/sidebar.py`](/home/gericho/sunnypilot/selfdrive/ui/layouts/sidebar.py)
   - upstream PC UI was passing float dimensions to texture creation on this machine; the patch only normalizes the texture dimensions to integers

7. Kept the webcam path on the custom dynamic exposure controller:
   - [`tools/webcam/camera.py`](/home/gericho/sunnypilot/tools/webcam/camera.py)
   - active runtime profile on PC uses:
     - custom dynamic exposure enabled
     - dynamic gain disabled
     - BRIO FoV preset through Logitech/UVC handling

8. Enabled `modeld_v2` on PC with ONNX Runtime + OpenVINO instead of the lagging stock tinygrad path:
   - [`sunnypilot/modeld_v2/modeld.py`](/home/gericho/sunnypilot/sunnypilot/modeld_v2/modeld.py)
   - [`sunnypilot/modeld_v2/runners/ort_helpers.py`](/home/gericho/sunnypilot/sunnypilot/modeld_v2/runners/ort_helpers.py)
   - [`sunnypilot/models/runners/onnx/onnx_runner.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/onnx/onnx_runner.py)
   - [`sunnypilot/models/runners/helpers.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/helpers.py)
   - [`sunnypilot/models/helpers.py`](/home/gericho/sunnypilot/sunnypilot/models/helpers.py)

9. Wired the runner selection so the manager actually launches the intended model process:
   - `FORCE_MODEL_RUNNER=tinygrad` now correctly maps to the `modeld_tinygrad` process selection
   - `USE_ONNX=1` now switches the runner factory from tinygrad runner classes to the ONNX/OpenVINO runner classes

10. Added stock-model fallback for `modeld_v2` so PC bring-up does not depend on a pre-populated `ModelManager_ActiveBundle`:
   - [`sunnypilot/models/runners/model_runner.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/model_runner.py)
   - [`sunnypilot/models/pc_compat.py`](/home/gericho/sunnypilot/sunnypilot/models/pc_compat.py)
   - if there is no active model bundle, the PC path falls back to stock:
     - `driving_vision.onnx`
     - `driving_policy.onnx`
     - stock metadata files from [`selfdrive/modeld/models`](/home/gericho/sunnypilot/selfdrive/modeld/models)

11. Added compatibility glue so legacy `modeld_v2` call sites can drive the ONNX runner without a broad refactor:
   - [`sunnypilot/models/runners/onnx/onnx_runner.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/onnx/onnx_runner.py)
   - the runner now accepts both:
     - the new `imgs_cl, numpy_inputs, frames` style
     - the existing `modeld_v2` tinygrad-style call path

12. Kept the tinygrad warp path on CL for PC so the OpenVINO runner does not crash on JIT input-device mismatches:
   - [`sunnypilot/modeld_v2/modeld.py`](/home/gericho/sunnypilot/sunnypilot/modeld_v2/modeld.py)
   - the PC path explicitly resets tinygrad runtime device selection and keeps warp execution on `CL`

13. Reduced false startup failures in `selfdrived` for the PC webcam rig:
   - [`selfdrive/selfdrived/selfdrived.py`](/home/gericho/sunnypilot/selfdrive/selfdrived/selfdrived.py)
   - longer init timeout for PC webcam bring-up
   - camera/sensor/gps packet expectations trimmed to what the PC rig actually provides
   - guard added so missing `gpsLocation` does not crash `selfdrived`

14. Extracted PC-specific logic into dedicated helper modules to keep future upstream merges simpler:
   - [`sunnypilot/pc_runtime/helpers.py`](/home/gericho/sunnypilot/sunnypilot/pc_runtime/helpers.py)
   - [`sunnypilot/pc_runtime/__init__.py`](/home/gericho/sunnypilot/sunnypilot/pc_runtime/__init__.py)
   - [`sunnypilot/models/pc_compat.py`](/home/gericho/sunnypilot/sunnypilot/models/pc_compat.py)
   - these helpers now hold:
     - PC tinygrad/OpenCL device setup
     - selfdrived packet policy for PC webcam mode
     - stock split-model fallback for PC/OpenVINO bring-up
     - forced runner selection helper

## Current Runtime Direction

The current `dev` branch is intentionally focused on these goals:

1. keep `master` untouched
2. keep the PC runtime in separate files where possible
3. keep the delta against `sunnypilot/sunnypilot` understandable and reviewable
4. make future merges from upstream easier than they would be with a direct port of the old branch state

## Notes

1. The PC path is using:
   - BRIO webcam runtime
   - Pico FlexRay transport
   - `modeld_v2` with ONNX Runtime + OpenVINO

2. The README above is a branch-specific engineering summary for `dev`.
   - It is not claiming that every imported piece is finalized or production-ready.
   - It documents what was actually brought over and adapted to make this branch run on the target PC rig.

## Force Audit: Keep / Remove / Make Optional

This section lists the current `dev` branch changes by whether they should be kept as structural work, removed to get closer to upstream stock behavior, or made optional behind runtime configuration.

### Keep

1. [`tools/webcam/camera.py`](/home/gericho/sunnypilot/tools/webcam/camera.py)
   - required for the PC webcam runtime that does not exist upstream in a usable form for this rig

2. [`tools/webcam/camerad.py`](/home/gericho/sunnypilot/tools/webcam/camerad.py)
   - required to publish the BRIO camera feed into the runtime on this PC rig

3. [`common/transformations/camera.py`](/home/gericho/sunnypilot/common/transformations/camera.py)
   - should stay because PC runtime needs explicit camera geometry support instead of upstream device defaults

4. [`.gitmodules`](/home/gericho/sunnypilot/.gitmodules)
5. [panda](/home/gericho/sunnypilot/panda)
6. [opendbc_repo](/home/gericho/sunnypilot/opendbc_repo)
7. [selfdrive/pandad](/home/gericho/sunnypilot/selfdrive/pandad)
   - these are structural dependencies for the Pico FlexRay hardware path, not temporary forcing knobs

8. [`SConstruct`](/home/gericho/sunnypilot/SConstruct)
   - keep only the minimum build compatibility needed for the imported `pandad` path

9. [`selfdrive/ui/layouts/sidebar.py`](/home/gericho/sunnypilot/selfdrive/ui/layouts/sidebar.py)
   - keep as a PC compatibility fix unless upstream resolves the same crash on this platform

10. [`sunnypilot/pc_runtime/helpers.py`](/home/gericho/sunnypilot/sunnypilot/pc_runtime/helpers.py)
11. [`sunnypilot/pc_runtime/__init__.py`](/home/gericho/sunnypilot/sunnypilot/pc_runtime/__init__.py)
12. [`sunnypilot/models/pc_compat.py`](/home/gericho/sunnypilot/sunnypilot/models/pc_compat.py)
   - keep because they isolate PC-specific behavior from shared upstream files

### Remove If The Goal Is "Stay Stock"

1. `FORCE_MODEL_RUNNER=tinygrad` in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - this explicitly overrides normal model-runner selection

2. `USE_ONNX=1` and `ORT_BACKEND=openvino` in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - these explicitly force the OpenVINO path instead of leaving selection to the upstream default behavior

3. `DEV=CL` in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - this is a direct device/runtime force

4. `ROAD_HFOV_DEG=60` and `WIDE_HFOV_DEG=58.08` in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - these are geometry forcing knobs in the launcher

5. `ROAD_W=640`, `ROAD_H=360`, `ROAD_FPS=20`, `ROAD_FOURCC=MJPG` in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - these are explicit runtime-camera forcing choices

6. all `WEBCAM_DYNAMIC_*` knobs in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - they force the custom exposure controller behavior instead of leaving the camera path closer to stock defaults

7. `WEBCAM_BRIO_FOV=65` in [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
   - this is a hardware preset force

### Better As Optional

1. [`selfdrive/selfdrived/selfdrived.py`](/home/gericho/sunnypilot/selfdrive/selfdrived/selfdrived.py)
   - current PC webcam logic reduces expected sensors and extends init timeout
   - useful for PC bring-up, but should ideally be active only behind a dedicated PC mode

2. [`sunnypilot/modeld_v2/modeld.py`](/home/gericho/sunnypilot/sunnypilot/modeld_v2/modeld.py)
   - current PC behavior forces tinygrad/OpenCL device setup for warp stability
   - keep the code path, but make it clearly conditional and isolated to PC runtime

3. [`sunnypilot/models/helpers.py`](/home/gericho/sunnypilot/sunnypilot/models/helpers.py)
   - forced runner selection is useful for bring-up and benchmarking
   - should remain optional, not the default expectation

4. [`sunnypilot/models/runners/helpers.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/helpers.py)
   - ONNX runner selection via `USE_ONNX` is valid for PC, but should remain an explicit opt-in path

5. [`sunnypilot/models/runners/model_runner.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/model_runner.py)
   - stock split-model fallback is useful for PC bring-up without a model manager bundle
   - should be treated as a compatibility fallback, not as a hidden default for all environments

6. [`sunnypilot/models/runners/onnx/onnx_runner.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/onnx/onnx_runner.py)
   - the backward-compatible legacy call handling should remain only as long as `modeld_v2` still uses the old call pattern

### Summary

If the target is a strictly stock-like system, the main forcing surface is:
- [`go_pc_webcam.sh`](/home/gericho/sunnypilot/go_pc_webcam.sh)
- [`sunnypilot/models/helpers.py`](/home/gericho/sunnypilot/sunnypilot/models/helpers.py)
- [`sunnypilot/models/runners/helpers.py`](/home/gericho/sunnypilot/sunnypilot/models/runners/helpers.py)
- [`selfdrive/selfdrived/selfdrived.py`](/home/gericho/sunnypilot/selfdrive/selfdrived/selfdrived.py)
- [`sunnypilot/modeld_v2/modeld.py`](/home/gericho/sunnypilot/sunnypilot/modeld_v2/modeld.py)

If the target is a working PC rig, most of the structural pieces should stay, but the launcher-level forcing should be reviewed first.
