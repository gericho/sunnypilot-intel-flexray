# Update 2026-03-24

Small summary of today's changes:
- restored and kept the `dual direct` RAM path as the active webcam bring-up path
- switched the BRIO source path to native `NV12` at `1280x720@20`
- fixed the `encoderd` software HEVC path and re-enabled working explicit encoder selection from the launcher (`cpu` or `vaapi`, no fallback for explicit modes)
- fixed the `modeld_v2` warp input path on PC/CL by replacing the zeroing `Tensor.from_blob(...)` path with explicit tensor copy-in
- verified that offline warp output is no longer all zeros; the remaining issue is live runtime throughput/dropped model evals, not black warp output
- disabled `ORT_OPENVINO_FALLBACK_CPU` in the launcher and verified it does not change the live drop pattern; the remaining bottleneck is still runtime throughput, not an OpenVINO CPU fallback


![](docs/assets/Gemini_Generated_Image_en6pmeen6pmeen6p.jpg)

## Dev Branch Delta From `sunnypilot/sunnypilot`

This `dev` branch starts from upstream `sunnypilot/sunnypilot` and adds only the changes needed to bring up the Intel PC + BRIO webcam + Pico FlexRay runtime with the smallest practical delta.
