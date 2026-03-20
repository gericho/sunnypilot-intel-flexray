#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path

import cereal.messaging as messaging
from openpilot.common.params import Params

POLL_S = 0.05
LAT_PHASE_THRESHOLDS = {
  60: 112.083,
  24: 80.833,
  8: 149.5,
}


def latest(sock):
  msgs = messaging.drain_sock(sock, wait_for_one=False)
  return msgs[-1] if msgs else None


def ema(prev, value, alpha=0.25):
  if value is None:
    return prev
  if prev is None:
    return float(value)
  return (1.0 - alpha) * float(prev) + alpha * float(value)


def infer_long_intent(gas_pct, brake_pct):
  gas_pct = 0.0 if gas_pct is None else float(gas_pct)
  brake_pct = 0.0 if brake_pct is None else float(brake_pct)
  if gas_pct < 0.02 and brake_pct < 0.02:
    return "neutral", 0.0
  if gas_pct > brake_pct + 0.05:
    return "positive", min(1.0, gas_pct)
  if brake_pct > gas_pct + 0.03:
    return "negative", min(1.0, brake_pct)
  return "blended", min(1.0, abs(gas_pct - brake_pct) + max(gas_pct, brake_pct) * 0.5)


def mode_from_state(gate, state):
  if gate is None or state is None:
    return "UNKNOWN"
  if gate == 643 and state == 35041:
    return "OFF"
  if gate == 3584 and state == 16610:
    return "ACC_ARMED"
  if gate in (640, 656) and state == 24802:
    return "MANAGED"
  if state == 26850:
    return "TRANSITION"
  return "UNKNOWN"


def infer_lat_direction(phase, b1):
  thr = LAT_PHASE_THRESHOLDS.get(phase)
  if thr is None or b1 is None:
    return "unknown", "none"
  if phase == 60:
    return ("right", "high") if b1 > thr else ("left", "high")
  if phase in (24, 8):
    return ("right", "medium") if b1 > thr else ("left", "medium")
  return "unknown", "none"


def infer_lat_mag(phase, b1):
  thr = LAT_PHASE_THRESHOLDS.get(phase)
  if thr is None or b1 is None:
    return 0.0, "none"
  if phase == 60:
    return min(1.0, abs(float(b1) - thr) / 110.0), "high"
  if phase == 24:
    return min(1.0, abs(float(b1) - thr) / 135.0), "low"
  if phase == 8:
    return min(1.0, abs(float(b1) - thr) / 90.0), "low"
  return 0.0, "none"


def current_route_name(params: Params):
  v = params.get("CurrentRoute")
  if not v:
    return None
  if isinstance(v, bytes):
    return v.decode("utf-8", errors="ignore")
  return str(v)


def current_segment_dir(root: Path, route_name: str):
  candidates = []
  prefix = f"{route_name}--"
  for p in root.glob(f"{route_name}--*"):
    if not p.is_dir():
      continue
    try:
      seg = int(p.name.split("--")[-1])
    except ValueError:
      continue
    candidates.append((seg, p))
  if not candidates:
    return None
  candidates.sort(key=lambda x: x[0])
  return candidates[-1][1]


def resolve_output_path(params: Params, root: Path, fallback: Path):
  route_name = current_route_name(params)
  if route_name is None:
    return fallback
  seg_dir = current_segment_dir(root, route_name)
  if seg_dir is None:
    return fallback
  out_dir = seg_dir / "bmw_i3_shadow"
  out_dir.mkdir(parents=True, exist_ok=True)
  return out_dir / "rlog.jsonl"


def open_output(current_file, current_path, new_path: Path):
  if current_path == new_path and current_file is not None:
    return current_file, current_path
  if current_file is not None:
    current_file.close()
  new_path.parent.mkdir(parents=True, exist_ok=True)
  return new_path.open("a", buffering=1), new_path


def main() -> None:
  parser = argparse.ArgumentParser(description="BMW i3 background shadow logger")
  parser.add_argument("--addr", default="127.0.0.1")
  parser.add_argument("--out", required=True)
  parser.add_argument("--interval", type=float, default=0.2)
  parser.add_argument("--root", default=os.path.expanduser("~/.comma/media/0/realdata"))
  args = parser.parse_args()

  if args.addr != "127.0.0.1":
    messaging.reset_context()

  params = Params()
  root = Path(args.root)
  fallback_path = Path(args.out)
  fallback_path.parent.mkdir(parents=True, exist_ok=True)

  carstate_sock = messaging.sub_sock("carState", addr=args.addr, conflate=True)
  panda_sock = messaging.sub_sock("pandaStates", addr=args.addr, conflate=True)
  can_sock = messaging.sub_sock("can", addr=args.addr, conflate=True)
  controlsstate_sock = messaging.sub_sock("controlsState", addr=args.addr, conflate=True)
  carcontrol_sock = messaging.sub_sock("carControl", addr=args.addr, conflate=True)
  longplan_sock = messaging.sub_sock("longitudinalPlan", addr=args.addr, conflate=True)
  longplan_sp_sock = messaging.sub_sock("longitudinalPlanSP", addr=args.addr, conflate=True)
  carcontrol_sp_sock = messaging.sub_sock("carControlSP", addr=args.addr, conflate=True)

  cs = None
  controls_state = None
  car_control = None
  long_plan = None
  long_plan_sp = None
  car_control_sp = None
  panda_count = 0
  gas217_word23 = None
  brake538_b0 = None
  brake239_word23 = None
  brake239_word56 = None
  turn502_raw = None
  cruise415_raw = None
  blink274_raw = None
  seatbelt435_raw = None
  seatbelt663_raw = None
  door481_raw = None
  steer770_raw = None
  fr0_72 = None
  fr0_96 = None
  fr0_131 = None
  fr0_135 = None
  fr1_54 = None
  fr1_59 = None
  fr1_97 = None
  fr1_112 = None
  fr1_116 = None
  fr1_275 = None
  gas_ema = None
  brake_ema = None
  last_write = 0.0
  out_file = None
  out_path = None

  try:
    while True:
      m = latest(carstate_sock)
      if m is not None:
        cs = m.carState

      m = latest(panda_sock)
      if m is not None:
        panda_count = len(m.pandaStates)

      m = latest(controlsstate_sock)
      if m is not None:
        controls_state = m.controlsState

      m = latest(carcontrol_sock)
      if m is not None:
        car_control = m.carControl

      m = latest(longplan_sock)
      if m is not None:
        long_plan = m.longitudinalPlan

      m = latest(longplan_sp_sock)
      if m is not None:
        long_plan_sp = m.longitudinalPlanSP

      m = latest(carcontrol_sp_sock)
      if m is not None:
        car_control_sp = m.carControlSP

      can_msgs = messaging.drain_sock(can_sock, wait_for_one=False)
      if can_msgs:
        for pkt in can_msgs:
          for msg in pkt.can:
            dat = bytes(msg.dat)
            if msg.src == 2 and msg.address == 217 and len(dat) >= 4:
              gas217_word23 = dat[2] | (dat[3] << 8)
            elif msg.src == 2 and msg.address == 538 and len(dat) >= 1:
              brake538_b0 = dat[0]
            elif msg.src == 2 and msg.address == 239 and len(dat) >= 7:
              brake239_word23 = dat[2] | (dat[3] << 8)
              brake239_word56 = dat[5] | (dat[6] << 8)
            elif msg.src == 2 and msg.address == 502 and len(dat) >= 2:
              turn502_raw = dat[0] | (dat[1] << 8)
            elif msg.src == 2 and msg.address == 415 and len(dat) >= 2:
              cruise415_raw = dat.hex()
            elif msg.src == 2 and msg.address == 274 and len(dat) >= 2:
              blink274_raw = dat.hex()
            elif msg.src == 2 and msg.address == 435 and len(dat) >= 5:
              seatbelt435_raw = dat.hex()
            elif msg.src == 2 and msg.address == 663 and len(dat) >= 3:
              seatbelt663_raw = dat.hex()
            elif msg.src == 2 and msg.address == 481 and len(dat) >= 3:
              door481_raw = dat.hex()
            elif msg.src == 2 and msg.address == 770 and len(dat) >= 2:
              steer770_raw = dat.hex()
            elif msg.src == 0 and msg.address == 72 and len(dat) >= 9:
              fr0_72 = dat.hex()
            elif msg.src == 0 and msg.address == 96 and len(dat) >= 9:
              fr0_96 = dat.hex()
            elif msg.src == 0 and msg.address == 131 and len(dat) >= 9:
              fr0_131 = dat.hex()
            elif msg.src == 0 and msg.address == 135 and len(dat) >= 9:
              fr0_135 = dat.hex()
            elif msg.src == 1 and msg.address == 54 and len(dat) >= 9:
              fr1_54 = dat.hex()
            elif msg.src == 1 and msg.address == 59 and len(dat) >= 9:
              fr1_59 = dat.hex()
            elif msg.src == 1 and msg.address == 97 and len(dat) >= 9:
              fr1_97 = dat.hex()
            elif msg.src == 1 and msg.address == 112 and len(dat) >= 9:
              fr1_112 = dat.hex()
            elif msg.src == 1 and msg.address == 116 and len(dat) >= 9:
              fr1_116 = dat.hex()
            elif msg.src == 1 and msg.address == 275 and len(dat) >= 9:
              fr1_275 = dat.hex()

      now = time.monotonic()
      if now - last_write < args.interval:
        time.sleep(POLL_S)
        continue

      active_out = resolve_output_path(params, root, fallback_path)
      out_file, out_path = open_output(out_file, out_path, active_out)

      gas217_value = None if gas217_word23 is None else min(4000, max(0, gas217_word23 - 4096))
      gas217_pct = None if gas217_value is None else gas217_value / 4000.0
      brake239_delta = None if brake239_word56 is None else max(0, 32000 - brake239_word56)
      brake239_pct = None if brake239_delta is None else min(1.0, brake239_delta / 2060.0)

      gas_ema = ema(gas_ema, gas217_pct)
      brake_ema = ema(brake_ema, brake239_pct)
      long_mode, long_conf = infer_long_intent(gas_ema, brake_ema)

      lat_phase = None
      lat_b1 = None
      lat_b2 = None
      lat_b3 = None
      if fr0_96 is not None:
        d = bytes.fromhex(fr0_96)
        lat_phase, lat_b1, lat_b2, lat_b3 = d[0], d[1], d[2], d[3]
      lat_dir, lat_dir_conf = infer_lat_direction(lat_phase, lat_b1)
      lat_mag, lat_mag_conf = infer_lat_mag(lat_phase, lat_b1)
      lat_helper_active = None
      if fr1_112 is not None:
        d112 = bytes.fromhex(fr1_112)
        lat_helper_active = (d112[5] & 0x20) == 0 if len(d112) > 5 else None
      gate131 = None
      state135 = None
      if fr0_131 is not None:
        d131 = bytes.fromhex(fr0_131)
        if len(d131) > 6:
          gate131 = d131[5] | (d131[6] << 8)
      if fr0_135 is not None:
        d135 = bytes.fromhex(fr0_135)
        if len(d135) > 6:
          state135 = d135[5] | (d135[6] << 8)
      acc_mode = mode_from_state(gate131, state135)
      acc_active = acc_mode in ("ACC_ARMED", "MANAGED")
      lat_active = (acc_mode == "MANAGED") and bool(lat_helper_active)
      tja_active = lat_active

      row = {
        "ts_wall": time.time(),
        "ts_mono": now,
        "route_out": str(out_path),
        "panda_count": panda_count,
        "gas217_word23": gas217_word23,
        "gas217_value": gas217_value,
        "gas217_pct": gas217_pct,
        "gas217_pct_ema": gas_ema,
        "brake538_b0": brake538_b0,
        "brake239_word23": brake239_word23,
        "brake239_word56": brake239_word56,
        "brake239_delta": brake239_delta,
        "brake239_pct": brake239_pct,
        "brake239_pct_ema": brake_ema,
        "turn502_raw": turn502_raw,
        "cruise415_raw": cruise415_raw,
        "blink274_raw": blink274_raw,
        "seatbelt435_raw": seatbelt435_raw,
        "seatbelt663_raw": seatbelt663_raw,
        "door481_raw": door481_raw,
        "steer770_raw": steer770_raw,
        "stock_long_intent": long_mode,
        "stock_long_intent_confidence": long_conf,
        "stock_acc_gate131": gate131,
        "stock_acc_state135": state135,
        "stock_acc_mode": acc_mode,
        "stock_acc_active": acc_active,
        "stock_tja_active": tja_active,
        "stock_lat_helper_active": lat_helper_active,
        "stock_lat_active": lat_active,
        "stock_lat_phase": lat_phase,
        "stock_lat_b1": lat_b1,
        "stock_lat_b2": lat_b2,
        "stock_lat_b3": lat_b3,
        "stock_lat_direction": lat_dir,
        "stock_lat_direction_confidence": lat_dir_conf,
        "stock_lat_magnitude": lat_mag,
        "stock_lat_magnitude_confidence": lat_mag_conf,
        "fr0_72": fr0_72,
        "fr0_96": fr0_96,
        "fr0_131": fr0_131,
        "fr0_135": fr0_135,
        "fr1_54": fr1_54,
        "fr1_59": fr1_59,
        "fr1_97": fr1_97,
        "fr1_112": fr1_112,
        "fr1_116": fr1_116,
        "fr1_275": fr1_275,
      }
      if controls_state is not None:
        row.update({
          "op_long_control_state": str(controls_state.longControlState),
          "op_up_accel_cmd": float(controls_state.upAccelCmd),
          "op_ui_accel_cmd": float(controls_state.uiAccelCmd),
          "op_uf_accel_cmd": float(controls_state.ufAccelCmd),
          "op_curvature": float(controls_state.curvature),
          "op_desired_curvature": float(controls_state.desiredCurvature),
          "op_force_decel": bool(controls_state.forceDecel),
        })
        lat_state = controls_state.lateralControlState.which()
        row["op_lat_control_state"] = lat_state
        if lat_state == "angleState":
          s = controls_state.lateralControlState.angleState
          row.update({
            "op_lat_active": bool(s.active),
            "op_lat_output": float(s.output),
            "op_lat_saturated": bool(s.saturated),
            "op_lat_steering_angle_deg": float(s.steeringAngleDeg),
            "op_lat_steering_angle_desired_deg": float(s.steeringAngleDesiredDeg),
          })
        elif lat_state == "torqueState":
          s = controls_state.lateralControlState.torqueState
          row.update({
            "op_lat_active": bool(s.active),
            "op_lat_output": float(s.output),
            "op_lat_saturated": bool(s.saturated),
            "op_lat_error": float(s.error),
            "op_lat_error_rate": float(s.errorRate),
            "op_lat_actual_lateral_accel": float(s.actualLateralAccel),
            "op_lat_desired_lateral_accel": float(s.desiredLateralAccel),
            "op_lat_desired_lateral_jerk": float(s.desiredLateralJerk),
          })
        elif lat_state == "pidState":
          s = controls_state.lateralControlState.pidState
          row.update({
            "op_lat_active": bool(s.active),
            "op_lat_output": float(s.output),
            "op_lat_saturated": bool(s.saturated),
            "op_lat_steering_angle_deg": float(s.steeringAngleDeg),
            "op_lat_steering_angle_desired_deg": float(s.steeringAngleDesiredDeg),
            "op_lat_p": float(s.p),
            "op_lat_i": float(s.i),
            "op_lat_f": float(s.f),
          })
      if car_control is not None:
        row.update({
          "op_enabled": bool(car_control.enabled),
          "op_lat_enabled": bool(car_control.latActive),
          "op_long_enabled": bool(car_control.longActive),
          "op_left_blinker_cmd": bool(car_control.leftBlinker),
          "op_right_blinker_cmd": bool(car_control.rightBlinker),
          "op_current_curvature": float(car_control.currentCurvature),
          "op_actuators_torque": float(car_control.actuators.torque),
          "op_actuators_steering_angle_deg": float(car_control.actuators.steeringAngleDeg),
          "op_actuators_curvature": float(car_control.actuators.curvature),
          "op_actuators_accel": float(car_control.actuators.accel),
          "op_actuators_speed": float(car_control.actuators.speed),
          "op_actuators_long_state": str(car_control.actuators.longControlState),
          "op_actuators_gas": float(car_control.actuators.gas),
          "op_actuators_brake": float(car_control.actuators.brake),
        })
      if long_plan is not None:
        row.update({
          "op_long_has_lead": bool(long_plan.hasLead),
          "op_long_fcw": bool(long_plan.fcw),
          "op_long_plan_source": str(long_plan.longitudinalPlanSource),
          "op_long_a_target": float(long_plan.aTarget),
          "op_long_should_stop": bool(long_plan.shouldStop),
          "op_long_allow_throttle": bool(long_plan.allowThrottle),
          "op_long_allow_brake": bool(long_plan.allowBrake),
        })
      if long_plan_sp is not None:
        row.update({
          "op_sp_long_source": str(long_plan_sp.longitudinalPlanSource),
          "op_sp_v_target": float(long_plan_sp.vTarget),
          "op_sp_a_target": float(long_plan_sp.aTarget),
          "op_sp_dec_enabled": bool(long_plan_sp.dec.enabled),
          "op_sp_dec_active": bool(long_plan_sp.dec.active),
          "op_sp_dec_state": str(long_plan_sp.dec.state),
          "op_sp_scc_vision_enabled": bool(long_plan_sp.smartCruiseControl.vision.enabled),
          "op_sp_scc_vision_active": bool(long_plan_sp.smartCruiseControl.vision.active),
          "op_sp_scc_vision_state": str(long_plan_sp.smartCruiseControl.vision.state),
          "op_sp_scc_vision_v_target": float(long_plan_sp.smartCruiseControl.vision.vTarget),
          "op_sp_scc_vision_a_target": float(long_plan_sp.smartCruiseControl.vision.aTarget),
          "op_sp_scc_map_enabled": bool(long_plan_sp.smartCruiseControl.map.enabled),
          "op_sp_scc_map_active": bool(long_plan_sp.smartCruiseControl.map.active),
          "op_sp_scc_map_state": str(long_plan_sp.smartCruiseControl.map.state),
          "op_sp_scc_map_v_target": float(long_plan_sp.smartCruiseControl.map.vTarget),
          "op_sp_scc_map_a_target": float(long_plan_sp.smartCruiseControl.map.aTarget),
          "op_sp_speed_limit_active": bool(long_plan_sp.speedLimit.assist.active),
          "op_sp_speed_limit_state": str(long_plan_sp.speedLimit.assist.state),
          "op_sp_speed_limit_v_target": float(long_plan_sp.speedLimit.assist.vTarget),
          "op_sp_speed_limit_a_target": float(long_plan_sp.speedLimit.assist.aTarget),
        })
      if car_control_sp is not None:
        row.update({
          "op_sp_mads_enabled": bool(car_control_sp.mads.enabled),
          "op_sp_mads_active": bool(car_control_sp.mads.active),
          "op_sp_mads_available": bool(car_control_sp.mads.available),
          "op_sp_mads_state": str(car_control_sp.mads.state),
          "op_sp_icbm_state": str(car_control_sp.intelligentCruiseButtonManagement.state),
          "op_sp_icbm_send_button": str(car_control_sp.intelligentCruiseButtonManagement.sendButton),
          "op_sp_icbm_v_target": float(car_control_sp.intelligentCruiseButtonManagement.vTarget),
        })
      if cs is not None:
        row.update({
          "gear": str(cs.gearShifter),
          "vEgo": float(cs.vEgo),
          "vEgoRaw": float(cs.vEgoRaw),
          "vEgoCluster": float(cs.vEgoCluster),
          "aEgo": float(cs.aEgo),
          "steeringAngleDeg": float(cs.steeringAngleDeg),
          "steeringTorque": float(cs.steeringTorque),
          "steeringPressed": bool(cs.steeringPressed),
          "yawRate": float(cs.yawRate),
          "wheelSpeedFL": float(cs.wheelSpeeds.fl),
          "wheelSpeedFR": float(cs.wheelSpeeds.fr),
          "wheelSpeedRL": float(cs.wheelSpeeds.rl),
          "wheelSpeedRR": float(cs.wheelSpeeds.rr),
          "leftBlinker": bool(cs.leftBlinker),
          "rightBlinker": bool(cs.rightBlinker),
          "seatbeltUnlatched": bool(cs.seatbeltUnlatched),
          "doorOpen": bool(cs.doorOpen),
          "gasPressed": bool(cs.gasPressed),
          "brakePressed": bool(cs.brakePressed),
          "cruiseAvailable": bool(cs.cruiseState.available),
          "cruiseEnabled": bool(cs.cruiseState.enabled),
          "cruiseStandstill": bool(cs.cruiseState.standstill),
          "standstill": bool(cs.standstill),
        })

      out_file.write(json.dumps(row, separators=(",", ":")) + "\n")
      last_write = now
      time.sleep(POLL_S)
  finally:
    if out_file is not None:
      out_file.close()


if __name__ == "__main__":
  main()
