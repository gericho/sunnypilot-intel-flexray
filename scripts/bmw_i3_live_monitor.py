#!/usr/bin/env python3
import argparse
import time

import cereal.messaging as messaging
from cereal import car


BUTTON_ENUM = {v: k for k, v in car.CarState.ButtonEvent.Type.schema.enumerants.items()}


def button_name(btn_type: int) -> str:
  return BUTTON_ENUM.get(btn_type, f"unknown({btn_type})")


def fmt_bool(v: bool) -> str:
  return "1" if v else "0"


def main() -> None:
  parser = argparse.ArgumentParser(description="Live BMW i3 carState monitor")
  parser.add_argument("--addr", default="127.0.0.1", help="messaging address")
  args = parser.parse_args()

  if args.addr != "127.0.0.1":
    messaging.reset_context()

  sm = messaging.SubMaster(["carState", "pandaStates"], addr=args.addr)

  last_state = None
  last_heartbeat = 0.0
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
        f"pandaStates_alive={int(sm.alive['pandaStates'])}"
      , flush=True)
      last_heartbeat = now

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

    if last_state is None or state != last_state or events:
      ts = time.strftime("%H:%M:%S")
      extra = []
      for name in ('stock_lat96_phase', 'stock_lat96_b1', 'stock_lat112_b5', 'stock_lat116_b5', 'stock_lat_active_hint', 'stock_lat_dir_hint', 'stock_lat_dir_confidence', 'stock_lat_mag_hint', 'stock_lat_mag_confidence'):
        if hasattr(cs, name):
          extra.append(f"{name}={getattr(cs, name)}")
      print(
        f"[{ts}] "
        f"gear={state[0]} "
        f"vEgo={state[1]:.2f} "
        f"vEgoRaw={state[2]:.2f} "
        f"vEgoCluster={state[3]:.2f} "
        f"L={fmt_bool(state[4])} R={fmt_bool(state[5])} "
        f"belt={fmt_bool(state[6])} door={fmt_bool(state[7])} brake={fmt_bool(state[8])} "
        f"gasPressed={fmt_bool(state[9])} "
        f"cruiseAvail={fmt_bool(state[10])} cruiseEn={fmt_bool(state[11])} "
        f"{' '.join(extra)}",
        flush=True,
      )
      if events:
        print(f"[{ts}] buttonEvents: {', '.join(events)}", flush=True)
      last_state = state


if __name__ == "__main__":
  main()
