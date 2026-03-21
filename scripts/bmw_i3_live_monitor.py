#!/usr/bin/env python3
import argparse
import time

import cereal.messaging as messaging

REFRESH_S = 0.2
POLL_S = 0.02


def fmt_bool(v) -> str:
  return "1" if bool(v) else "0"


def fmt_opt(v, hex_byte: bool = False, pct: bool = False) -> str:
  if v is None:
    return "-"
  if hex_byte:
    return f"0x{int(v):02x}"
  if pct:
    return f"{float(v):.3f}"
  return str(v)


def latest(sock):
  msgs = messaging.drain_sock(sock, wait_for_one=False)
  return msgs[-1] if msgs else None


def main() -> None:
  parser = argparse.ArgumentParser(description="Live BMW i3 carState/CAN monitor")
  parser.add_argument("--addr", default="127.0.0.1", help="messaging address")
  args = parser.parse_args()

  if args.addr != "127.0.0.1":
    messaging.reset_context()

  carstate_sock = messaging.sub_sock("carState", addr=args.addr, conflate=True)
  panda_sock = messaging.sub_sock("pandaStates", addr=args.addr, conflate=True)
  can_sock = messaging.sub_sock("can", addr=args.addr, conflate=True)

  cs = None
  panda = None
  gas217_word23 = None
  brake538_b0 = None
  brake239_word23 = None
  brake239_word56 = None
  last_print = 0.0

  print("\x1b[2J\x1b[Hwaiting for messages...", end="", flush=True)

  while True:
    m = latest(carstate_sock)
    if m is not None:
      cs = m.carState

    m = latest(panda_sock)
    if m is not None:
      panda = m.pandaStates

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

    now = time.monotonic()
    if now - last_print < REFRESH_S:
      time.sleep(POLL_S)
      continue

    gas217_value = None
    gas217_pct = None
    if gas217_word23 is not None:
      gas217_value = min(4000, max(0, gas217_word23 - 4096))
      gas217_pct = gas217_value / 4000.0

    brake239_delta = None
    brake239_pct = None
    if brake239_word56 is not None:
      brake239_delta = max(0, 32000 - brake239_word56)
      brake239_pct = min(1.0, brake239_delta / 2060.0)

    if cs is None:
      lines = [
        f"[{time.strftime('%H:%M:%S')}] BMW i3 live monitor",
        "carState: -",
        f"pandaStates: {len(panda) if panda is not None else '-'}",
        "",
        f"gas217_word23={fmt_opt(gas217_word23)} gas217_value={fmt_opt(gas217_value)} gas217_pct={fmt_opt(gas217_pct, pct=True)}",
        f"brake538_b0={fmt_opt(brake538_b0, hex_byte=True)}",
        f"brake239_word23={fmt_opt(brake239_word23)} brake239_word56={fmt_opt(brake239_word56)}",
        f"brake239_delta={fmt_opt(brake239_delta)} brake239_pct={fmt_opt(brake239_pct, pct=True)}",
      ]
    else:
      lines = [
        f"[{time.strftime('%H:%M:%S')}] BMW i3 live monitor",
        f"pandaStates={len(panda) if panda is not None else '-'}",
        "",
        f"gear={cs.gearShifter} vEgo={float(cs.vEgo):.2f} vEgoRaw={float(cs.vEgoRaw):.2f} vEgoCluster={float(cs.vEgoCluster):.2f}",
        f"L={fmt_bool(cs.leftBlinker)} R={fmt_bool(cs.rightBlinker)} belt={fmt_bool(cs.seatbeltUnlatched)} door={fmt_bool(cs.doorOpen)}",
        f"brakePressed={fmt_bool(cs.brakePressed)} gasPressed={fmt_bool(cs.gasPressed)} cruiseAvail={fmt_bool(cs.cruiseState.available)} cruiseEn={fmt_bool(cs.cruiseState.enabled)}",
        "",
        f"gas217_word23={fmt_opt(gas217_word23)} gas217_value={fmt_opt(gas217_value)} gas217_pct={fmt_opt(gas217_pct, pct=True)}",
        f"brake538_b0={fmt_opt(brake538_b0, hex_byte=True)}",
        f"brake239_word23={fmt_opt(brake239_word23)} brake239_word56={fmt_opt(brake239_word56)}",
        f"brake239_delta={fmt_opt(brake239_delta)} brake239_pct={fmt_opt(brake239_pct, pct=True)}",
      ]

    print("\x1b[2J\x1b[H" + "\n".join(lines), end="", flush=True)
    last_print = now
    time.sleep(POLL_S)


if __name__ == "__main__":
  main()
