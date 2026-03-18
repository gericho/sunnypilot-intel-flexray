#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from statistics import fmean, median

from tools.lib.logreader import LogReader


ROUTES = {
  "b3": {
    "fn": "/home/gericho/.comma/media/0/realdata/000000b3--bc708b46e1--0/rlog.zst",
    "windows": [
      ("MANUAL_ACCEL", 6, 12),
      ("ACC_BASE", 12, 24),
      ("MANAGED", 24, 40),
      ("AUTO_BRAKE_LIGHT", 92, 98),
    ],
  },
  "e9": {
    "fn": "/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst",
    "windows": [
      ("ACC_BASE", 11, 22),
      ("MANAGED", 22, 44),
      ("AUTO_BRAKE_HEAVY", 44, 56),
      ("MANAGED2", 61, 72),
    ],
  },
  "55": {
    "fn": "/home/gericho/.comma/media/0/realdata/00000055--24e188a5e5--0/rlog.zst",
    "windows": [
      ("ACC_BASE", 12, 15),
      ("MANAGED", 15, 76),
      ("AUTO_BRAKE_HEAVY", 76, 81),
    ],
  },
  "147": {
    "fn": "/home/gericho/.comma/media/0/realdata/00000147--1294d32c66--0/rlog.zst",
    "windows": [
      ("ACC_BASE", 1, 13),
      ("TRANSITION", 14, 16),
      ("MANAGED", 16, 72),
    ],
  },
}


def window_label(t: float, windows: list[tuple[str, float, float]]) -> str | None:
  for label, a, b in windows:
    if a <= t < b:
      return label
  return None


def collect() -> dict[str, list[dict[str, int]]]:
  vals: dict[str, list[dict[str, int]]] = defaultdict(list)
  for cfg in ROUTES.values():
    start = None
    latest: dict[str, tuple[float, bytes]] = {}
    for msg in LogReader(cfg["fn"]):
      if start is None:
        start = msg.logMonoTime
      t = (msg.logMonoTime - start) / 1e9
      if msg.which() != "can":
        continue
      label = window_label(t, cfg["windows"])
      if label is None:
        continue
      for can_msg in msg.can:
        dat = bytes(can_msg.dat)
        if can_msg.src == 1 and can_msg.address == 59 and len(dat) >= 7:
          latest["59"] = (t, dat)
        elif can_msg.src == 1 and can_msg.address == 54 and len(dat) >= 7:
          latest["54"] = (t, dat)
        elif can_msg.src == 0 and can_msg.address == 135 and len(dat) >= 7:
          latest["135"] = (t, dat)
      if all(k in latest for k in ("59", "54", "135")) and max(abs(latest[k][0] - t) for k in latest) < 0.03:
        d59 = latest["59"][1]
        d54 = latest["54"][1]
        vals[label].append({
          "phase59": d59[0],
          "phase54": d54[0],
          "w59b": int.from_bytes(d59[3:5], "little"),
          "w59c": int.from_bytes(d59[5:7], "little"),
          "w54b": int.from_bytes(d54[3:5], "little"),
          "w54c": int.from_bytes(d54[5:7], "little"),
        })
  return vals


def med(xs: list[int]) -> int:
  return int(median(xs)) if xs else 0


def summarize(vals: dict[str, list[dict[str, int]]]) -> None:
  armed = vals.get("ACC_BASE", [])
  managed = vals.get("MANAGED", []) + vals.get("MANAGED2", [])
  brake = vals.get("AUTO_BRAKE_HEAVY", []) + vals.get("AUTO_BRAKE_LIGHT", [])

  centers = {
    "59": {
      "wB": med([r["w59b"] for r in armed]),
      "wC": med([r["w59c"] for r in armed]),
    },
    "54": {
      "wB": med([r["w54b"] for r in armed]),
      "wC": med([r["w54c"] for r in armed]),
    },
  }

  print("# neutral centers from ACC_BASE")
  print(f"59: wB={centers['59']['wB']} wC={centers['59']['wC']}")
  print(f"54: wB={centers['54']['wB']} wC={centers['54']['wC']}")

  print("\n# window medians")
  for label in ("MANUAL_ACCEL", "ACC_BASE", "MANAGED", "MANAGED2", "AUTO_BRAKE_LIGHT", "AUTO_BRAKE_HEAVY", "TRANSITION"):
    arr = vals.get(label, [])
    if not arr:
      continue
    print(f"\n{label} n={len(arr)}")
    for key in ("w59b", "w59c", "w54b", "w54c"):
      xs = [r[key] for r in arr]
      print(f"  {key}: med={med(xs)} mean={fmean(xs):.1f} min={min(xs)} max={max(xs)}")

  def delta(label: str, arr: list[dict[str, int]]) -> None:
    if not arr:
      return
    d59 = [((r["w59b"] - centers["59"]["wB"]) + 0.5 * (r["w59c"] - centers["59"]["wC"])) for r in arr]
    d54 = [((r["w54b"] - centers["54"]["wB"]) + 0.5 * (r["w54c"] - centers["54"]["wC"])) for r in arr]
    print(f"{label}: delta59_med={median(d59):.1f} delta54_med={median(d54):.1f}")

  print("\n# centered branch deltas vs ACC_BASE neutral")
  delta("MANUAL_ACCEL", vals.get("MANUAL_ACCEL", []))
  delta("MANAGED", managed)
  delta("AUTO_BRAKE", brake)

  print("\n# subcycle parity medians")
  active = {}
  for branch, phase_key, wb_key, wc_key in (
    ("59", "phase59", "w59b", "w59c"),
    ("54", "phase54", "w54b", "w54c"),
  ):
    branch_stats = {}
    for label in ("ACC_BASE", "MANAGED", "AUTO_BRAKE_HEAVY", "AUTO_BRAKE_LIGHT"):
      arr = vals.get(label, [])
      if not arr:
        continue
      for parity in (0, 1):
        sub = [r for r in arr if (r[phase_key] % 2) == parity]
        if not sub:
          continue
        wb_med = med([r[wb_key] for r in sub])
        wc_med = med([r[wc_key] for r in sub])
        branch_stats.setdefault(label, {})[parity] = (wb_med, wc_med, len(sub))
        print(f"{branch} {label} parity={parity}: wB_med={wb_med} wC_med={wc_med} n={len(sub)}")
    active[branch] = branch_stats

  print("\n# inferred active subcycle family")
  for branch in ("59", "54"):
    stats = active[branch].get("MANAGED") or active[branch].get("ACC_BASE") or {}
    if not stats:
      continue
    parity = max(stats, key=lambda p: abs(stats[p][0]) + abs(stats[p][1]))
    wb_med, wc_med, _ = stats[parity]
    print(f"{branch}: active parity={parity} active_center_wB={wb_med} active_center_wC={wc_med}")

  print("\n# pragmatic interpretation")
  print("59 = primary positive/coast branch, active mainly on even subcycles")
  print("54 = primary negative/brake-blend branch, active mainly on odd subcycles")
  print("TX is still not closed: amplitude, packing, counter/checksum remain open")


if __name__ == "__main__":
  summarize(collect())
