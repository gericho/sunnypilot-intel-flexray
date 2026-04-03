# BMW i3 Lateral Status - 2026-04-03

## Current Architecture Model

- MITM is mounted between SAS and BDC.
- Current working model:
  - `src0 / 0x3c (60)` and `src0 / 0x48 (72)` are SAS -> BDC upstream control path.
  - `src1 / 0x44 (68)` is downstream/actuation-side and is treated as feedback/proxy, not as an injected command.
- Therefore openpilot must emulate SAS, not BDC/EPS.

## Key Signal Conclusions

- `72` is not a simple analog angle field.
- `72` behaves like a discrete phase-indexed command/state machine.
- Practical working extraction:
  - `phase = byte0 >> 1`
  - `nibble = byte2 & 0x0F`
- `60.byte0 == 72.byte0` is a strong invariant in valid SAS-side traffic.

## EPS Angle Proxy

- Best FlexRay proxy for CAN `770` found on old TJA route with CAN:
  - `src1 / 0x44 / s12le@105`
- Nickname:
  - `EPS_ANGLE_PROXY_44`
- Old-route fit vs `770_raw`:
  - `770_raw ~= 2.361 * EPS_ANGLE_PROXY_44 + 32844`
  - lag roughly `35-40 ms`

## Route Findings

- `00000402--59a94efa08`
  - old reference route with CAN `770`
  - used to build initial `(phase,nibble)` table from real steering feedback

- `backup routes 31`
  - `00000007--f518197f2b`: real TJA route
  - `00000006--e6a3e58043`: also valid TJA-like route in later segments
  - `00000008--6154aab5fe`: mostly ACC-family
  - `00000009--05041e7132`: mostly ACC-family

- `00000010--5d583d0f8e`
  - OP was never enabled
  - blocker was mainly `cruiseMismatch`
  - fixed later by changing i3 `cruiseState.enabled`

- `00000016--8c7aacbbbc`
  - TJA-clean pieces exist on bus
  - `src0/60`, `src0/72`, `src0/96`, `src0/131`, `src0/135` all present
  - but OP never engaged
  - after `cruiseMismatch` fix, dominant blocker became `noGps`

## Important Code Changes Already Made

- `opendbc_repo/opendbc/car/bmw_i3/carstate.py`
  - broadened modern `stock_tja_active`
  - `cruiseState.available` still reflects stock availability
  - `cruiseState.enabled = False` for this flexray-only button-based port
  - reason: with `pcmCruise=False`, mirroring stock ACC active caused permanent `cruiseMismatch`

- `selfdrive/selfdrived/selfdrived.py`
  - `noGps` is now ignored on PC webcam runtime:
    - gated with `not is_pc_webcam_runtime()`

- `opendbc_repo/opendbc/car/bmw_i3/carcontroller.py`
  - lateral TX only happens when:
    - `CC.latActive`
    - `lat_tx_ready`
  - therefore if OP is not enabled, no lateral TX is sent at all

- `opendbc_repo/opendbc/car/bmw_i3/fingerprints.py`
  - added extra i3 fingerprint variants
  - latest fix covered a `src1-only` startup variant

## Important Practical Conclusion

- So far, in the routes inspected after bring-up:
  - `selfdriveState.enabled = 0`
  - `carControl.latActive = 0`
- Therefore:
  - openpilot has not yet truly transmitted lateral control on the bus in those runs
  - the immediate blocker was engagement/runtime gating, not the final 72 DBC semantics

## Firmware / Pico Status

- Pico FlexRay firmware path has been tested in multiple forms before.
- But current route evidence says the more immediate truth is:
  - OP was not yet active
  - so the lateral `72` path was not actually exercised in normal runtime driving logs

## Next Step

1. Reboot runtime with current fixes.
2. Record a short route.
3. Check:
   - `selfdriveState.enabled`
   - `carControl.latActive`
   - whether `noGps` is gone
4. Only if `latActive` becomes `1`, investigate:
   - whether `72` is actually emitted in `sendcan`
   - whether Pico receives and forwards/injects it

