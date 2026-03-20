#!/usr/bin/env python3
import argparse
import time

import cereal.messaging as messaging
from cereal import car
from build_bmw_i3_lat_shadow_packer import build_phase_profiles, collect_labeled_samples, pack_lat96


BUTTON_ENUM = {v: k for k, v in car.CarState.ButtonEvent.Type.schema.enumerants.items()}
PHASE_PROFILES = None


def get_phase_profiles():
  global PHASE_PROFILES
  if PHASE_PROFILES is None:
    PHASE_PROFILES = build_phase_profiles(collect_labeled_samples())
  return PHASE_PROFILES


def button_name(btn_type: int) -> str:
  return BUTTON_ENUM.get(btn_type, f"unknown({btn_type})")


def fmt_bool(v: bool) -> str:
  return "1" if v else "0"


def infer_mag_norm_from_b1(phase: int, b1: int, direction: str) -> tuple[float, str]:
  profile = get_phase_profiles().get(phase)
  if profile is None or direction not in ("left", "right"):
    return 0.0, "none"
  ladder = profile.ladder_right if direction == "right" else profile.ladder_left
  if ladder:
    ordered = [triple[0] for triple in ladder]
    nearest_idx = min(range(len(ordered)), key=lambda i: abs(ordered[i] - b1))
    mag = nearest_idx / max(1, len(ordered) - 1)
    return float(mag), profile.magnitude_confidence
  return 0.0, profile.magnitude_confidence


def main() -> None:
  parser = argparse.ArgumentParser(description="Live BMW i3 carState monitor")
  parser.add_argument("--addr", default="127.0.0.1", help="messaging address")
  args = parser.parse_args()

  if args.addr != "127.0.0.1":
    messaging.reset_context()

  sm = messaging.SubMaster(["carState", "pandaStates", "can"], addr=args.addr)

  last_state = None
  last_heartbeat = 0.0
  last_print = 0.0
  gas217_raw16 = None
  gas217_word23 = None
  print("waiting for carState...", flush=True)
  while True:
    sm.update(100)
    now = time.monotonic()
    if now - last_heartbeat > 2.0:
      print(
        f"[{time.strftime('%H:%M:%S')}] "
        f"carState_updated={int(sm.updated['carState'])} "
        f"carState_alive={int(sm.alive['carState'])} "
        f"pandaStates_updated={int(sm.updated['pandaStates'])} "
        f"pandaStates_alive={int(sm.alive['pandaStates'])} "
        f"can_updated={int(sm.updated['can'])} "
        f"can_alive={int(sm.alive['can'])}"
      , flush=True)
      last_heartbeat = now

    if sm.updated["can"]:
      for m in sm["can"]:
        if m.src == 2 and m.address == 217 and len(m.dat) >= 4:
          dat = bytes(m.dat)
          gas217_raw16 = dat[0] | (dat[1] << 8)
          gas217_word23 = dat[2] | (dat[3] << 8)

    if not sm.updated["carState"]:
      continue

    cs = sm["carState"]
    state = (
      str(cs.gearShifter),
      float(cs.vEgo),
      float(cs.vEgoRaw),
      float(cs.vEgoCluster),
      bool(cs.leftBlinker),
      bool(cs.rightBlinker),
      bool(cs.seatbeltUnlatched),
      bool(cs.doorOpen),
      bool(cs.brakePressed),
      bool(cs.gasPressed),
      bool(cs.cruiseState.available),
      bool(cs.cruiseState.enabled),
    )

    events = []
    for be in cs.buttonEvents:
      try:
        be_type = int(be.type.raw) if hasattr(be.type, 'raw') else int(be.type)
      except Exception:
        be_type = 0
      events.append(f"{button_name(be_type)}:{'1' if be.pressed else '0'}")

    should_print = (last_state is None or (now - last_print) >= 2.0)
    if should_print:
      ts = time.strftime("%H:%M:%S")
      extra = []
      if gas217_raw16 is not None:
        extra.append(f"gas217_raw16={gas217_raw16}")
      if gas217_word23 is not None:
        extra.append(f"gas217_word23={gas217_word23}")

      for name in (
        'stock_lat96_phase',
        'stock_lat96_b1',
        'stock_lat96_b2',
        'stock_lat96_b3',
        'stock_lat112_b5',
        'stock_lat116_b5',
        'stock_lat_active_hint',
        'stock_lat_dir_hint',
        'stock_lat_dir_confidence',
        'stock_lat_mag_hint',
        'stock_lat_mag_confidence',
      ):
        if hasattr(cs, name):
          extra.append(f"{name}={getattr(cs, name)}")

      shadow_summary = ""
      if hasattr(cs, "stock_lat96_phase") and hasattr(cs, "stock_lat96_b1"):
        phase = int(getattr(cs, "stock_lat96_phase", 0))
        direction = str(getattr(cs, "stock_lat_dir_hint", "unknown"))
        b1 = int(getattr(cs, "stock_lat96_b1", 0))
        b2 = int(getattr(cs, "stock_lat96_b2", 0))
        b3 = int(getattr(cs, "stock_lat96_b3", 0))
        if direction in ("left", "right"):
          mag_norm, mag_conf = infer_mag_norm_from_b1(phase, b1, direction)
          shadow96 = pack_lat96(phase, direction, mag_norm, get_phase_profiles())
          if shadow96 is not None:
            stock96 = bytes([phase & 0xFF, b1 & 0xFF, b2 & 0xFF, b3 & 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
            shadow_summary = (
              f" stock96={stock96.hex()} shadow96={shadow96.hex()} "
              f"shadowMatch={fmt_bool(stock96 == shadow96)} shadowMag={mag_norm:.4f} shadowMagConf={mag_conf}"
            )
      print(
        f"[{ts}] "
        f"gear={state[0]} "
        f"vEgo={state[1]:.2f} "
        f"vEgoRaw={state[2]:.2f} "
        f"vEgoCluster={state[3]:.2f} "
        f"L={fmt_bool(state[4])} R={fmt_bool(state[5])} "
        f"belt={fmt_bool(state[6])} door={fmt_bool(state[7])} brakePressed={fmt_bool(state[8])} "
        f"gasPressed={fmt_bool(state[9])} "
        f"cruiseAvail={fmt_bool(state[10])} cruiseEn={fmt_bool(state[11])} "
        f"{' '.join(extra)}{shadow_summary}",
        flush=True,
      )
      last_state = state
      last_print = now


if __name__ == "__main__":
  main()
