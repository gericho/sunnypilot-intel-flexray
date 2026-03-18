# SUNNYPILOT for BMW i3
FlexRay-CAN (Intel PC/OpenVINO Build)

> Disclaimer: this repository is under heavy development and must currently be considered `BROKEN`. It is not usable as a stable driving build.

![](docs/assets/Gemini_Generated_Image_en6pmeen6pmeen6p.jpg)

## 🤖 Technical Delta Summary
> **Status:** Work in progress. The Pico FlexRay + CAN transport path is currently working on the Czok V1 setup.

1. Added BMW i3 support in `opendbc` with a dedicated DBC and platform registration.
2. Integrated FlexRay-related Panda communication/safety changes and Cabana decoding support.
3. Added dual-endpoint Pico host support:
   - `pandad` reads `0x81` for FlexRay and `0x82` for CAN
   - Cabana live USB now reads both endpoints too
4. Enabled simultaneous logging of:
   - `src 0` = FlexRay ECU side
   - `src 1` = FlexRay vehicle side
   - `src 2` = external CAN on `CN13`
5. Enabled Intel hardware video encoding for PC testing (`hevc_vaapi` / `h264_vaapi`) with explicit runtime fallback paths.
6. Reworked FFmpeg encoder handling for NV12/VAAPI and added safer software fallback behavior for unsupported cases.
7. Aligned logger segmentation with runtime camera FPS (`ROAD_FPS`) to improve route/segment timing consistency.
8. Added dedicated qcamera tuning knobs (`QCAM_FPS`, `QCAM_BITRATE`) to reduce encoder/queue pressure on low-power CPUs.
9. Optimized the webcam pipeline with a raw NV12 fast path (`WEBCAM_RAW_NV12`) and camera FOURCC control from env.
10. Added robust webcam format handling (including YUYV fallback conversion) and runtime stage profiling output.
11. Switched webcam publish timing to monotonic nanosecond timestamps for improved playback/signal synchronization.
12. Switched the PC inference path to `modeld_tinygrad` with ONNX Runtime + OpenVINO on the Intel iGPU; OpenCL remains used only for vision transform/buffer handling and CL context setup, not as the primary inference backend.
13. Added PC runtime profiles and kept `qcamera` disabled by default to keep Cabana route handling deterministic on PC runs.
14. Added logger queue tuning for encoder bursts (`LOGGERD_ENCODER_QUEUE_LIMIT`) and increased default buffering in `loggerd` to prevent HEVC packet drops during segment rotation.
15. Tuned HEVC stability settings for PC capture: shorter GOP (keyframe cadence tied to `ROAD_FPS`) and reduced main-road bitrates (`ROAD_MAIN_BITRATE_LOW/HIGH`) to lower encoder pressure.
16. Fixed BMW i3 startup on PC runs:
   - `./go.sh` exposes dedicated runtime profiles (`can_soc_scan`, `log_only_stable`, `log_modeld`, `full_experimental`)
   - runtime fingerprinting matches `BMW_I3_EXPERIMENTAL` instead of falling back to `MOCK`
17. Fixed BMW i3 `carState` runtime compatibility for this fork's schema (`gasPressed` only, no direct `gas` field in `CarState`).
18. Added a simple live debug tool:
   - `scripts/bmw_i3_live_monitor.py`
   - prints `gear`, `blinkers`, `seatbelt`, `door`, `brake`, `gasPressed`, `cruiseState`, and mapped `buttonEvents`
19. Refined stock ACC reverse-engineering on modern BMW i3 routes:
   - primary longitudinal stock-state helpers are now `FlexRay 0/131` and `0/135`
   - `0/131` separates `OFF (643)`, `ACC base armed/ready (3584)`, and managed/following states (`640/656`)
   - `0/135` separates `OFF (35041)`, `ACC base armed/ready (16610)`, and managed/following assist state (`24802`)
   - `FlexRay 1/97` remains useful as a command/stalk transition frame, not as the stable ACC state
  - for stock longitudinal content, the current best candidates are:
     - `FlexRay 1/59` = strongest pedal/hold/coast-state candidate
     - `FlexRay 1/54` = best brake-blend / regen-support candidate
     - `FlexRay 1/44` and `1/43` = weaker secondary dynamic-state helpers
   - strongest long-TX-oriented helper fields currently are:
     - `1/59`
       - `LONG_TX_POWERTRAIN_WORD_B`
       - `LONG_TX_POWERTRAIN_WORD_C`
       - `LONG_TX_POWERTRAIN_BYTE_3`
       - `LONG_TX_POWERTRAIN_BYTE_5`
     - `1/54`
       - `LONG_TX_BRAKE_BLEND_WORD_B`
       - `LONG_TX_BRAKE_BLEND_WORD_C`
       - `LONG_TX_BRAKE_BLEND_BYTE_4`
       - `LONG_TX_BRAKE_BLEND_BYTE_6`
   - current interpretation:
     - `59` is the best proxy for stock longitudinal high-level powertrain request/content
     - `54` is the best proxy for stock brake-blend / regen execution
20. Promoted the strongest historical TJA lateral helpers from legacy routes `00000054` and `00000055`:
   - `FlexRay 24/112` = primary stock lateral/TJA helper
   - `FlexRay 23/116` = secondary stock lateral/TJA helper
   - `FlexRay 23/275` = lateral/TJA confirmation helper
   - the same payload families are also present on the modern interface in route `000000b3`, now exposed on `src 1`
21. Added first bit-level notes for stock lateral reverse-engineering:
   - `112.byte5 bit5` is the strongest manual/off vs assisted-steering discriminator
   - `116` confirms assisted-steering phase changes, but does not yet expose a single robust boolean bit
22. Refined stock longitudinal content reverse-engineering:
   - `59` remains the strongest stock pedal/hold/coast-state candidate
   - `54` remains the best brake-blend / regen-support candidate
   - for practical inspection, the most useful helper bytes are:
     - `59.byte3-5`
     - `54.byte3-6`
23. Added coarse offline stock longitudinal indices for route analysis:
   - `long_stock_mode`
     - anchor it from `FlexRay 0/131` + `0/135`
     - `OFF = 643 / 35041`
     - `ACC base = 3584 / 16610`
     - `managed/following = 640|656 / 24802`
   - `long_stock_powertrain_index`
     - derived offline from `FlexRay 1/59`
     - primarily follows `59.byte3-5`
     - low in clear human pedal windows
     - higher in stock-managed coast/following windows
   - `long_stock_brake_blend_index`
     - derived offline from `FlexRay 1/54`
     - primarily follows `54.byte3-6`
     - lower in stable manual/off windows
     - higher in stock-controlled coast/following and automatic decel windows
24. Refined longitudinal interpretation around strong automatic braking:
   - `FlexRay 1/59` should be treated as the best current proxy for stock longitudinal powertrain intent/state, not as a confirmed direct pedal-equivalent in physical units
   - `FlexRay 1/54` should be treated as the best current proxy for stock brake-blend / regen-support execution
   - in strong stock braking windows from historical TJA routes, both `59` and `54` move together:
     - `59` changes family away from its stable managed-following pattern
     - `54` changes even more strongly, especially on `byte3`, `byte4`, and `byte6`
   - current best interpretation is:
     - high-level stock longitudinal request is carried through the ADAS path
     - BDC/powertrain then translate it into regen and, when needed, mechanical braking
     - `59` and `54` are the best current observable proxies for those two branches
25. Closed the current best conservative longitudinal TX architecture:
   - `59` is the primary positive/coast branch
   - `54` is the primary negative / brake-blend branch
   - `59` is active mainly on even subcycles, with active-center words near `wB=32777`, `wC=32767`
   - `54` is active mainly on odd subcycles, with active-center words near `wB=65025`, `wC=7`
   - this is enough for conservative shadow/replay hints, but still not enough to claim a final physical TX payload or checksum/counter closure
26. Added route-driven conservative long replay helpers:
   - `scripts/build_bmw_i3_long_replay_hint.py` prints the per-second branch/parity/template to imitate from a route
   - `scripts/build_bmw_i3_long_shadow_sequence.py` writes a CSV shadow sequence with:
     - `131/135` gate/state
     - active branch `59/54`
     - observed phase
     - target parity and target `wB/wC` center
   - these tools are replay/shadow-only and deliberately do not transmit anything

## 👀 FlexRay MITM Mapping
- Group 1 uses `FR1` and `FR2`.
- `FR1` (`U5`) is the vehicle-side transceiver: `TXD GPIO28`, `TXEN GPIO27`, `RXD GPIO26`.
- `FR2` (`U8`) is the ECU-side transceiver: `TXD GPIO4`, `TXEN GPIO5`, `RXD GPIO6`.
- Group 2 uses `FR3` and `FR4`.
- `FR3` (`U9`) is the vehicle-side transceiver: `TXD GPIO10`, `TXEN GPIO9`, `RXD GPIO8`.
- `FR4` (`U10`) is the ECU-side transceiver: `TXD GPIO16`, `TXEN GPIO22`, `RXD GPIO21`.
- In the dual-channel firmware, `src 24` means `FR2 + FR4` and `src 23` means `FR2 + FR3`.

## Czok V1 Connector Mapping

- `CN4 / Flexray2 -> SAS / ECU side`
- `CN3 / Flexray1 -> BDC / vehicle side`
- `CN13 / CAN2 -> BMW i3 PT-CAN`

Current live bus mapping:

- `src 0` = FlexRay ECU side
- `src 1` = FlexRay vehicle side
- `src 2` = CAN (`CN13`)

## 📶 WiFi SOC Realtime Monitoring

Experimental.

Current best live SOC candidates on `src 2` (`CN13`) from parked charging captures are:

- primary candidate: `addr 1074`, `byte 4`, interpreted as `raw / 2`
  - equivalent raw byte values:
    - `0x83` -> `131 / 2 = 65.5`
    - `0x86` -> `134 / 2 = 67.0`
    - `0x8A` -> `138 / 2 = 69.0`

- secondary candidate: `addr 303`, `byte 2`, interpreted as `raw / 2`
  - this also tracks the same charging windows reasonably well, but is less consistent than `1074.byte4 / 2`

Practical note:

- when monitoring live over WiFi or route logs, check `1074.byte4 / 2` first
- keep `303.byte2 / 2` as the backup comparison signal
- a weaker alternate raw candidate also appeared on `addr 569`, `byte 2`, but it trends high relative to the user-reported SOC and is currently not preferred

## Pico Host Stack Notes

Matching host components:

- `selfdrive/pandad`
  - location in this tree: `selfdrive/pandad`
  - matching host-side fork: see the fork/branch that adds Pico dual-endpoint support
  - branch: `Czok-V1-can`

- `tools/cabana`
  - live USB mode now reads both Pico endpoints:
    - `0x81` for FlexRay
    - `0x82` for CAN
  - includes the FlexRay-oriented `Demux` UI ported from `dynm/openpilot` branch `cabana-flexray`
  - supports cycle-base views `1 / 2 / 4 / 8 / 16 / 32` for cyclic FlexRay frames whose first byte acts as a cycle index

This means:

- route replay from `rlog.zst` shows `0`, `1`, `2`
- live USB in Cabana also shows `0`, `1`, `2`

## BMW i3 Runtime Status

- Runtime fingerprint: `BMW_I3_EXPERIMENTAL`; `./go.sh` now defaults to `full_experimental` for onroad bring-up on this PC.
- Current tuned onroad path: `modeld_tinygrad` + `ONNX Runtime` + `OpenVINOExecutionProvider` on the Intel iGPU.
- Current tuned road-camera path: `ffmpeg` capture, `640x360`, `NV12`, `20 fps`.
- OpenCL is still used for the vision transform/buffer path before inference; inference itself is OpenVINO, not OpenCL.
- Confirmed parsed signals: `gear P/D/N/R`, `blinkers`, `seatbelt`, `driver door`, `gasPressed`, `brakePressed`, `cruiseState`, `SET`, `RES`, `ACC`, `TJA`.
- Vehicle speed now follows the BMW method: `FlexRay 55` primary, `FlexRay 46` fallback.
- Stock ACC/TJA state is anchored on `FlexRay 0/131` + `0/135`; `1/97` is command/stalk echo only.
- Best current stock longitudinal proxies: `FlexRay 1/59` = powertrain intent, `FlexRay 1/54` = brake-blend / regen support.
- Best current stock longitudinal TX architecture: `59` even-subcycle positive/coast branch, `54` odd-subcycle negative/brake-blend branch.
- Best current stock longitudinal replay basis: route-driven shadow sequence with `131/135` gating plus `59/54` branch/parity targets.
- Best current stock lateral RX helpers: `FlexRay 1/112` primary, `1/116` secondary, `1/275` confirmation.
- Best current stock lateral TX localization: `FlexRay 0/72` = envelope / phase / counter, `FlexRay 0/96` = payload candidate.
- `72` and `96` are localized, but the final lateral steer command is still not closed.
- Current profiling on this PC shows the dominant cost is vision inference latency, not webcam capture, color conversion, rotation, or CL-to-numpy copy.
- Shadow debug is available and read-only: `bmw_i3_shadow_acc` and `bmw_i3_shadow_long`.

## Tested Hardware
- CPU: Intel Core i5-7200U (4 vCPU, x86_64)
- Webcam(s): Logitech BRIO

## BMW i3 Shadow Debug
- Shadow lateral debug event:
  - `bmw_i3_shadow_acc`
- Shadow longitudinal debug event:
  - `bmw_i3_shadow_long`
- Both are read-only:
  - no real actuator output is transmitted
- Extract the latest shadow debug lines with:
  - `python scripts/extract_bmw_i3_shadow_logs.py`
- Or inspect a specific log file:
  - `python scripts/extract_bmw_i3_shadow_logs.py /home/gericho/.comma/log/swaglog.0000000000`
- Summarize a route second-by-second for `131/135`, `72/96`, and `59/54` with:
  - `python scripts/bmw_i3_replay_report.py /path/to/route-or-rlog`
  - omit the path to use the latest route automatically
- Compare shadow lateral logs against real `72/96` route data with:
  - `python scripts/compare_bmw_i3_shadow_lat.py /path/to/route --swaglog /path/to/swaglog`
- Compare shadow longitudinal logs against real `59/54` route data with:
  - `python scripts/compare_bmw_i3_shadow_long.py /path/to/route --swaglog /path/to/swaglog`
- Fit the current best conservative longitudinal branch centers from existing routes with:
  - `python scripts/fit_bmw_i3_long_branches.py`
- Sweep the previous day's routes and print only the ones that actually show ACC/TJA activity with:
  - `python scripts/summarize_bmw_i3_yesterday_routes.py`
- Build a conservative per-second long replay hint directly from a route with:
  - `python scripts/build_bmw_i3_long_replay_hint.py /path/to/route`
- Build a shadow-only CSV sequence for long replay from a route with:
  - `python scripts/build_bmw_i3_long_shadow_sequence.py /path/to/route`
- Replay a saved long shadow sequence without transmitting anything with:
  - `python scripts/replay_bmw_i3_long_shadow_sequence.py /path/to/bmw_i3_long_shadow_sequence.csv`
- Run both shadow-log extraction and replay summary together with:
  - `python scripts/bmw_i3_offline_bundle.py`

## Credits
- CzokNorris: FlexRay reverse-engineering groundwork and V1 board design reference, `https://oshwlab.com/czoknorris/v1board`
- Dynm: `pico-flexray` firmware foundation, related BMW FlexRay work, and Cabana FlexRay demux reference from branch `cabana-flexray`, `https://github.com/dynm/pico-flexray`
- smnogar: BMW openpilot/opendbc reference points used for signal naming and structural comparison
