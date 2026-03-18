#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import signal
import sys
import time
from pathlib import Path

import cereal.messaging as messaging

LONG_59_ACTIVE_PARITY = 0
LONG_54_ACTIVE_PARITY = 1
LONG_59_CENTER_WB = 32777
LONG_59_CENTER_WC = 32767
LONG_54_CENTER_WB = 65025
LONG_54_CENTER_WC = 7


def u16_le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def mode_from_state(gate: int | None, state: int | None) -> str:
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


def long_tx_hint(desired_accel: float) -> tuple[str, int, int, int, int]:
  if desired_accel < -0.05:
    return ("negative", 54, LONG_54_ACTIVE_PARITY, LONG_54_CENTER_WB, LONG_54_CENTER_WC)
  return ("positive_or_coast", 59, LONG_59_ACTIVE_PARITY, LONG_59_CENTER_WB, LONG_59_CENTER_WC)


def main() -> int:
  ap = argparse.ArgumentParser(description="Capture live BMW i3 longitudinal signals for ACC bucket fitting")
  ap.add_argument("--out", default=None, help="output csv path; default writes under /home/gericho/sunnypilot/captures")
  ap.add_argument("--seconds", type=float, default=180.0, help="capture duration")
  args = ap.parse_args()

  out_path = Path(args.out) if args.out else Path("/home/gericho/sunnypilot/captures") / f"bmw_i3_long_capture_{int(time.time())}.csv"
  out_path.parent.mkdir(parents=True, exist_ok=True)

  sm = messaging.SubMaster(["carState", "selfdriveState", "pandaStates"])
  can_sock = messaging.sub_sock("can", timeout=50)

  state = {
    "gate131": None,
    "state135": None,
    "long59_wb": None,
    "long59_wc": None,
    "long59_b3": None,
    "long59_b5": None,
    "long54_wb": None,
    "long54_wc": None,
    "long54_b4": None,
    "long54_b6": None,
  }

  running = True

  def stop(_sig=None, _frame=None):
    nonlocal running
    running = False

  signal.signal(signal.SIGINT, stop)
  signal.signal(signal.SIGTERM, stop)

  with out_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
      "mono_s",
      "vEgo_kph",
      "aEgo",
      "standstill",
      "gasPressed",
      "brakePressed",
      "gearShifter",
      "selfdriveEnabled",
      "controlsAllowed",
      "gate131",
      "state135",
      "mode",
      "long59_wb",
      "long59_wc",
      "long59_b3",
      "long59_b5",
      "long54_wb",
      "long54_wc",
      "long54_b4",
      "long54_b6",
      "tx_mode",
      "tx_branch",
      "tx_parity",
      "tx_target_wb",
      "tx_target_wc",
    ])

    end_t = time.monotonic() + args.seconds
    last_print = 0.0

    while running and time.monotonic() < end_t:
      sm.update(0)

      for can_evt in messaging.drain_sock(can_sock, wait_for_one=False):
        for m in can_evt.can:
          dat = bytes(m.dat)
          if (m.src, m.address) == (0, 131) and len(dat) >= 7:
            state["gate131"] = u16_le(dat, 5)
          elif (m.src, m.address) == (0, 135) and len(dat) >= 7:
            state["state135"] = u16_le(dat, 5)
          elif (m.src, m.address) == (1, 59) and len(dat) >= 7:
            state["long59_wb"] = u16_le(dat, 3)
            state["long59_wc"] = u16_le(dat, 5)
            state["long59_b3"] = dat[3]
            state["long59_b5"] = dat[5]
          elif (m.src, m.address) == (1, 54) and len(dat) >= 7:
            state["long54_wb"] = u16_le(dat, 3)
            state["long54_wc"] = u16_le(dat, 5)
            state["long54_b4"] = dat[4]
            state["long54_b6"] = dat[6]

      if not sm.seen["carState"]:
        time.sleep(0.02)
        continue

      cs = sm["carState"]
      controls_allowed = False
      if sm.seen["pandaStates"] and len(sm["pandaStates"]):
        controls_allowed = any(ps.controlsAllowed for ps in sm["pandaStates"])

      row = [
        round(time.monotonic(), 3),
        round(float(cs.vEgo) * 3.6, 3),
        round(float(cs.aEgo), 4),
        int(cs.standstill),
        int(cs.gasPressed),
        int(cs.brakePressed),
        str(cs.gearShifter),
        int(sm["selfdriveState"].enabled) if sm.seen["selfdriveState"] else 0,
        int(controls_allowed),
        state["gate131"],
        state["state135"],
        mode_from_state(state["gate131"], state["state135"]),
        state["long59_wb"],
        state["long59_wc"],
        state["long59_b3"],
        state["long59_b5"],
        state["long54_wb"],
        state["long54_wc"],
        state["long54_b4"],
        state["long54_b6"],
      ]
      tx_mode, tx_branch, tx_parity, tx_target_wb, tx_target_wc = long_tx_hint(float(cs.aEgo))
      row.extend([tx_mode, tx_branch, tx_parity, tx_target_wb, tx_target_wc])
      w.writerow(row)

      now = time.monotonic()
      if now - last_print > 1.0:
        print(
          f"v={row[1]:6.2f} kph mode={row[11]:>10s} "
          f"59=({row[12]},{row[13]}) 54=({row[16]},{row[17]}) "
          f"tx={tx_mode}:{tx_branch}/p{tx_parity} tgt=({tx_target_wb},{tx_target_wc}) "
          f"gas={row[4]} brake={row[5]} enabled={row[7]}",
          flush=True,
        )
        last_print = now

      time.sleep(0.05)

  print(f"WROTE={out_path}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
