# Update 2026-03-24

Small summary of today's changes:
- webcam bring-up path updated and stabilized around the `dual direct` RAM pipeline (`go_dual_direct.sh`, `tools/webcam/camera.py`, `tools/webcam/camerad.py`)
- BRIO source path switched to native `NV12` at `1280x720@20`
- `system/loggerd` / `encoderd` updated so explicit `cpu` and `vaapi` encoder selection works again, software HEVC works, and the current dual-direct runtime records both `fcamera.hevc` and `ecamera.hevc` across segments
- PC thumbnail generation remains disabled in `encoderd` because it was the main source of the short-road-recording failure on the webcam path
- `sunnypilot/modeld_v2` updated: fixed the PC/CL warp input path, removed the zeroed `Tensor.from_blob(...)` behavior, and optimized `warp.py` so preprocess is no longer the main runtime bottleneck
- `modeld` now produces `modelV2` and `cameraOdometry` again, and the current road-camera projection has been validated with the repo OpenCV overlay path
- launcher/runtime defaults updated to keep `ORT_OPENVINO_FALLBACK_CPU=0`; this was verified not to be the source of the residual drop pattern
- `scripts/bmw_i3_shadow_logger.py` updated repeatedly during the day and now logs the stock `54/59` families together with the raw FlexRay candidates that actually discriminate longitudinal state
- BMW i3 controller reverse path updated in `opendbc`: `carstate.py`, `carcontroller.py`, and `bmw_i3_flexray_custom_v3.dbc` now include the raw FlexRay long helpers (`46/49/55/56/63/93`) needed to close the longitudinal state-machine data path offline
- longitudinal reverse/data path is therefore closed much more tightly than before, but `openpilotLongitudinalControl` is still intentionally left disabled until the real TX builder is moved from shadow logic into the live controller


![](docs/assets/Gemini_Generated_Image_en6pmeen6pmeen6p.jpg)

## Dev Branch Delta From `sunnypilot/sunnypilot`

This `dev` branch starts from upstream `sunnypilot/sunnypilot` and adds only the changes needed to bring up the Intel PC + BRIO webcam + Pico FlexRay runtime with the smallest practical delta.
