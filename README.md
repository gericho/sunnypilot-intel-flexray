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
