# Update 2026-04-05

Small summary of the latest changes:
- BMW i3 FlexRay-only bring-up was tightened around the real bus split: SAS-side stock lateral frames (`60/72/96`) are parsed from `src0`, while vehicle-side helper frames (including the steering-wheel helper families on `97/112/116`) stay on `src1`
- this closes the key lateral parsing bug found on route `0000002a--e7362cf0b9`: openpilot was already engaged and sending frame `72`, but the builder was reading `phase=0` from the wrong bus and was therefore transmitting an all-zero `72` payload
- after the parser fix, offline replay now shows a stock-like `72` stream instead of `010000...` null frames; representative replay payloads are now in the family `011bfff2ffffffffffe0ffffffffffffff`, `011ffff4ffffffffffe0ffffffffffffff`, `0123fff4ffffffffffe0ffffffffffffff`
- the same fix also holds on the latest real route replay (`0000002e--a1698ed7e7--4`): `selfdriveState`, `carControl`, and `sendcan` all go active in replay, and `72` alternates between plausible `control` and `zero` branches instead of staying null
- `opendbc/car/bmw_i3/carstate.py` was refined again so stock ACC/TJA helper states only use the clean reference states (`OFF = 643/35041`, `ACC = 3584/16610`, `MANAGED = 640/24802`) as button-state candidates; intermediate stock states are now treated as context only
- current conclusion:
  - software-side lateral bring-up is now closed through `sendcan`
  - the real remaining on-car question is no longer “is openpilot sending anything?”, but whether the generated `72` is accepted end-to-end by the Pico + FlexRay + BDC chain on the live bus

# Update 2026-04-03

Small summary of the latest changes:
- BMW i3 PC FlexRay bring-up refined around the SAS-side `60 -> 72` model instead of treating lateral as a generic analog payload
- `opendbc/car/bmw_i3/carstate.py` now keeps `cruiseState.available` from stock helpers but forces `cruiseState.enabled = False` for the `pcmCruise = False` button-based PC port, removing the persistent `cruiseMismatch` failure mode
- `selfdrive/selfdrived/selfdrived.py` now ignores `noGps` on the PC webcam runtime; this setup has no GPS attached and should not be blocked by the standard on-road GPS gate
- BMW i3 fingerprint coverage was expanded again to include the new `src1-only` startup variant observed in recent realdata logs
- `opendbc/car/bmw_i3/carcontroller.py` and `carstate.py` were tightened around the current FlexRay lateral bring-up model:
  - `60/72` phase alignment is tracked explicitly
  - modern TJA-like context is accepted beyond the old narrow `135` family gate
  - lateral TX debug/readiness fields now reflect the actual gate used before sending `72`
- local status memory for the current i3 lateral/FlexRay bring-up was saved in `notes/bmw_i3_lateral_status_2026-04-03.md`
- current conclusion from recent routes: the stock SAS `60/72` stream is coherent, but in the routes inspected so far openpilot had still not reached a true `enabled/latActive` state, so lateral TX was not yet genuinely exercised on-bus

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
