# Update 2026-04-07

Small summary of the latest changes:
- BMW i3 stock-TJA state detection was re-derived from raw `src0` FlexRay using route `00000401--75b081dc8a--0..1` as the clean reference instead of continuing to rely on the older broad `acc_family` / `authority_like` heuristics
- the new strict `401` managed-window rule is intentionally minimal and route-grounded:
  - `96.byte3 == 0xE0`
  - `135.byte7 == 0x32`
- on route `00000401--75b081dc8a--0..1` this isolates the stock steering-managed window as:
  - entry at `01:01.054`
  - exit at `01:44.446`
- representative raw packets at the managed boundaries are:
  - entry:
    - `96 = 00b1f4e0ffffffffff`
    - `135 = 18ccf72628e2603206`
  - exit:
    - `96 = 08d4f221ffffffffff`
    - `135 = 38c9f72228e2603206`
- a second managed family was then identified on route `00000006--e6a3e58043--0..4`; it is not `401`-like, but it is internally coherent and carries the same SAS command structure through a different state family:
  - `96.byte3 == 0x21`
  - `135[3:9] == 20e0e240e201` for `21.500 -> 86.446`
  - `135[3:9] == 20e0e2408202` for `199.708 -> 241.887` and `279.485 -> 301.148`
- wide-angle windows inside `00000006` confirmed that the large stock steering events live inside these `96...21` / `135...e201|8202` families rather than inside the stricter `401` family
- full `src0` SAS scanning on the `401` managed window was widened beyond the usual known candidates and showed that:
  - `72` behaves like envelope/phase, not the real command payload
  - `96` remains the best primary SAS command candidate
  - `264` is the strongest support/helper candidate outside `96`
  - `135`, `267`, `269`, and `131` behave like state/gate helpers rather than the main steering-request payload
- the current best practical model for stock lateral command is therefore:
  - `96.byte0` = phase
  - `96.byte1` / `96.byte2` = phase-local command payload
  - `264` = support/intensity-like helper
- with that result, the active draft TX path was simplified:
  - live runtime no longer builds or injects `72`
  - `carstate.py` now treats `96` as the active SAS-side lateral command/template source
  - `carcontroller.py` now emits a stock-like `96` payload draft by copying the live `96` family and only nudging the phase-local command bytes (`b1`, and `b2` when support medians exist)
  - the Pico injector was switched from `60 -> 72` to `60 -> 96` and now replaces the full 9-byte `96` payload without trying to apply the old `72` E2E patch logic
- current conclusion:
  - `401` is the cleanest strict reference for `managed` stock steering
  - `06` expands the search space with a second valid managed family at much larger steering angles
  - the main remaining reverse task is no longer “which frame carries the command?”, but “how to calibrate `96` phase-local payloads into a cleaner OEM-like steering request across managed families”

# Update 2026-04-06

Small summary of the latest changes:
- BMW i3 steering-angle reverse work was tightened against the `dynm` BMW SP2018 reference one frame at a time instead of continuing with mixed FlexRay proxies
- the local i3 port was confirmed already aligned with `dynm` on:
  - `46 wheel_speed`
  - `49 steer_torque`
  - including the same demux rule on frame `49` (`cycle/mux == 0`)
- the main remaining mismatch was the EPS angle source:
  - `dynm` uses `BO_ 51 EPS_Angle`
  - the local i3 port had still been using `56` as primary and `44` as fallback
- a route with a taped steering-wheel marker (`0000003f--9f8cebeeb7--0/1`) was used to validate the temporal structure of frame `51`
- after replay inspection and user-confirmed wheel motion order, frame `51` was accepted as the new primary FlexRay EPS angle source for the i3 port:
  - same decode model as `dynm`
  - `cycle/mux == 0`
  - `raw16 = u16le(bytes 3:4)`
  - `angle_deg = raw * 0.0439453125 - 1440.0`
- further cleanup against the `dynm` reference tightened the runtime set of active FlexRay signals:
  - frame `40` was promoted from `DRIVE_STATE_EXPERIMENTAL` to production `DRIVE_STATE`
  - frame `55` was kept as the only production vehicle-speed source
  - frame `46` was removed from the active runtime path after route-wide comparison on `0000003d--4035c308e0--0..2` showed that it does not track frame `55` closely enough on the i3
- the UI/cluster speed path was also aligned with live behavior:
  - `vEgoRaw` now comes only from frame `55`
  - `vEgoCluster` keeps a `+1 km/h` offset because the cluster consistently reads about `1 km/h` higher than the raw FlexRay vehicle-speed value
- `opendbc/dbc/bmw_i3_flexray_custom_v3.dbc` now exposes:
  - `BO_ 51 EPS_ANGLE`
  - `EPS_STEERING_ANGLE_BMW`
- `opendbc/car/bmw_i3/carstate.py` now uses frame `51` as the only production FlexRay `steeringAngleDeg` source when PT-CAN steering is absent
- former FlexRay angle candidates remain only as debug/support:
  - `56` secondary debug/support
  - `44` legacy debug only
- frame `56` was re-checked as a possible yaw-rate source, but live replay on the latest route showed that the currently decoded value is not physically plausible enough to publish into openpilot:
  - it remains available in the DBC and raw helper fields
  - but it is no longer forwarded to `CarState.yawRate`
- current conclusion:
  - the i3 port is now aligned with the `dynm` reference on the active production steering signals that matter most: `40`, `49`, `51`, and `55`
  - the next remaining question is behavioral validation of this `51` feedback inside live lateral control, not DBC alignment

# Update 2026-04-06

# Update 2026-04-07

Small summary of today's changes:
- BMW i3 lateral TX bring-up was finalized around the `96` path instead of the old `72` path:
  - `opendbc/car/bmw_i3/carcontroller.py` now emits only frame `96`
  - the temporary hard clamp was removed again after bench/runtime verification
  - `opendbc/dbc/bmw_i3_flexray_custom_v3.dbc` no longer carries the old `BO_72`
- Pico injector and diagnostics were cleaned up to match the `96`-only runtime:
  - `pico-flexray/src/flexray_injector_rules.h` now contains only the active `0x3c -> 0x60` trigger rule
  - firmware/runtime counters were renamed to `target96_cache_count` / `override96_pop_hit_count`
  - the Pico firmware was rebuilt and reflashed after the cleanup
- replay/webcam/runtime support was tightened:
  - replay camera lookup was fixed so segment changes no longer reuse the wrong video frame
  - `go_dual_direct.sh` gained a persistent optional `ENABLE_DRIVER_CAM` toggle via `~/.config/sunnypilot/go_dual_direct.env`
  - the extra driver camera can now be disabled cleanly without leaving route-recording residue behind
- the `no panda` regression was traced to a same-day change in `scripts/bmw_i3_shadow_logger.py`:
  - direct USB access to the Pico from the shadow logger caused `LIBUSB_ERROR_BUSY`
  - this blocked `pandad` from claiming the device and produced the false on-screen `no panda`
  - the shadow logger no longer opens the Pico directly
- Pico injector counters are now sourced the right way:
  - `selfdrive/pandad/pandad.cc` reads injector diagnostics from the Pico
  - those diagnostics are published onto `customReservedRawData0`
  - `scripts/bmw_i3_shadow_logger.py` subscribes to that channel and writes the `fw_*` fields into `bmw_i3_shadow/rlog.jsonl`
- current `96` conclusion after checking all afternoon routes with real `sendcan 96` traffic:
  - the host-side `96` packets are consistently `10` bytes long with `base=1`
  - `pandad` converts them into the exact `[crc][9-byte slice]` form expected by `injector_submit_override()`
  - so the `96` transport format is correct; any remaining lateral issue is downstream of CRC/length/base validity

# Update 2026-04-06

Small summary of the latest changes:
- BMW i3 lateral reverse work moved from “is anything transmitted?” to a stricter semantic comparison across all useful replays: desktop TJA route `00000016--8c7aacbbbc--0..4`, recent live routes `3a/3b/3c/3d/3e`, Pico injector counters, and the final bus payload after template overlay
- comparison against the BMW FlexRay implementations from the `dynm` and `smnogar` repos confirmed that their `72` builders are SP2018-style direct-angle packets, while the i3 `72` remains phase-local and stock-orbit-like; the reusable part was the injector architecture, not the packet semantics
- the main residual bug was identified as a **phase mismatch** between the host-generated `72` and the cached stock `72` template that the Pico actually injected:
  - transport was already good (`submit/accept/fire` all moved)
  - but host `72.byte0` phase matched the stock template phase in only a small minority of replayed injections
  - because the i3 command nibble is phase-local, this meant semantically valid nibble choices were being applied to the wrong template phase on-bus
- `opendbc/car/bmw_i3/carcontroller.py` was updated so the host lateral command predicts the **next** usable stock control phase (`+4`) and computes the nibble against that predicted command phase, while keeping the command bounded and sign-aware around the stock nibble
- `pico-flexray/src/flexray_fowarder_with_injector.c` was updated so frame `72` overrides carry the expected phase byte and are only consumed when the cached stock template phase matches exactly; this fixes semantic desynchronization without changing trigger cadence, DMA flow, or FlexRay timing behavior
- replay-backed simulation of the new policy shows the right direction:
  - exact phase matching with the old host phase would have yielded only a handful of valid fires
  - exact phase matching with the new `+4` host phase yields a healthy number of phase-correct injections across the key replay set
- current conclusion:
  - the remaining BMW i3 lateral bottleneck is no longer generic transport or engagement
  - it was narrowed to phase-correct semantic injection of `72`, and the current code now reflects that model

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
