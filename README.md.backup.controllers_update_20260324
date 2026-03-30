# Update 2026-03-24

Small summary of today's changes:
- restored and kept the `dual direct` RAM path as the active webcam bring-up path
- switched the BRIO source path to native `NV12` at `1280x720@20`
- fixed the `encoderd` software HEVC path and re-enabled working explicit encoder selection from the launcher (`cpu` or `vaapi`, no fallback for explicit modes)
- fixed the `modeld_v2` warp input path on PC/CL by replacing the zeroing `Tensor.from_blob(...)` path with explicit tensor copy-in
- optimized the `warp.py` hot path so the preprocess is no longer the main runtime bottleneck and `modeld` now produces `modelV2` and `cameraOdometry` again
- verified the current `dual direct` runtime writes both `fcamera.hevc` and `ecamera.hevc` across segments, with `roadEncodeIdx` and `wideRoadEncodeIdx` progressing correctly
- kept PC thumbnail generation disabled in `encoderd` because it was the main source of the short `road` recording failure on the webcam path
- disabled `ORT_OPENVINO_FALLBACK_CPU` in the launcher and verified it does not change the observed drop pattern
- validated the current road-camera projection with the repo OpenCV overlay path: the model path is inside frame and geometrically plausible on `fcamera`


![](docs/assets/Gemini_Generated_Image_en6pmeen6pmeen6p.jpg)

## Dev Branch Delta From `sunnypilot/sunnypilot`

This `dev` branch starts from upstream `sunnypilot/sunnypilot` and adds only the changes needed to bring up the Intel PC + BRIO webcam + Pico FlexRay runtime with the smallest practical delta.
