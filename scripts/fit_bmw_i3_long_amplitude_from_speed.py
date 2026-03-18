#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from collections import deque
from pathlib import Path
from statistics import fmean, median
from typing import Optional

from tools.lib.logreader import LogReader


ROUTES = {
  "147": "/home/gericho/.comma/media/0/realdata/00000147--1294d32c66--0/rlog.zst",
  "148": "/home/gericho/.comma/media/0/realdata/00000148--ddcfbc9103--0/rlog.zst",
}

LONG_59_CENTER_WB = 32777
LONG_59_CENTER_WC = 32767
LONG_54_CENTER_WB = 65025
LONG_54_CENTER_WC = 7
LONG_59_ACTIVE_PARITY = 0
LONG_54_ACTIVE_PARITY = 1


def mode_from_state(gate: Optional[int], state: Optional[int]) -> str:
  if gate is None or state is None:
    return "UNKNOWN"
  if gate == 643 and state == 35041:
    return "OFF"
  if gate == 3584 and state == 16610:
    return "ACC_ARMED"
  if gate in (640, 656) and state == 24802:
    return "MANAGED"
  if gate in (640, 656):
    return "TRANSITION"
  return "UNKNOWN"


def u16_le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


def delta_u16(val: int, center: int) -> int:
  return ((val - center + 32768) % 65536) - 32768


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
  if len(xs) < 2 or len(xs) != len(ys):
    return None
  mx = fmean(xs)
  my = fmean(ys)
  num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
  denx = sum((x - mx) ** 2 for x in xs)
  deny = sum((y - my) ** 2 for y in ys)
  if denx <= 0 or deny <= 0:
    return None
  return num / ((denx * deny) ** 0.5)


def bucket_from_accel(a: float, th: float) -> str:
  if a > th:
    return "ACCEL"
  if a < -th:
    return "DECEL"
  return "COAST"


def active_delta(phase: Optional[int], raw_delta: float, active_parity: int) -> float:
  if phase is None:
    return 0.0
  return raw_delta if (phase % 2) == active_parity else 0.0


def collect_route(route_name: str, path: str, accel_th: float, alpha: float) -> list[dict]:
  samples: list[dict] = []
  nonzero_frames: list[dict] = []
  latest = {
    "gate131": None,
    "state135": None,
    "phase59": None,
    "w59b": None,
    "w59c": None,
    "phase54": None,
    "w54b": None,
    "w54c": None,
  }
  prev_cs_t = None
  prev_v = None
  a_filt = None
  recent59: deque[dict] = deque()
  recent54: deque[dict] = deque()

  def prune_recent(now: float) -> None:
    while recent59 and (now - recent59[0]["t"]) > 0.10:
      recent59.popleft()
    while recent54 and (now - recent54[0]["t"]) > 0.10:
      recent54.popleft()

  def best_recent(recent: deque[dict]) -> Optional[dict]:
    if not recent:
      return None
    return max(recent, key=lambda r: abs(r["delta"]))

  for msg in LogReader(path):
    which = msg.which()
    t = msg.logMonoTime / 1e9

    if which == "can":
      for can_msg in msg.can:
        dat = bytes(can_msg.dat)
        if (can_msg.src, can_msg.address) == (0, 131) and len(dat) >= 7:
          latest["gate131"] = u16_le(dat, 5)
        elif (can_msg.src, can_msg.address) == (0, 135) and len(dat) >= 7:
          latest["state135"] = u16_le(dat, 5)
        elif (can_msg.src, can_msg.address) == (1, 59) and len(dat) >= 7:
          latest["phase59"] = dat[0]
          latest["w59b"] = u16_le(dat, 3)
          latest["w59c"] = u16_le(dat, 5)
          if prev_cs_t is not None:
            delta = delta_u16(int(latest["w59b"]), LONG_59_CENTER_WB) + 0.5 * delta_u16(int(latest["w59c"]), LONG_59_CENTER_WC)
            if latest["w59b"] != 0 or latest["w59c"] != 0:
              nonzero_frames.append({
                "route": route_name,
                "branch": 59,
                "mode": mode_from_state(latest["gate131"], latest["state135"]),
                "bucket": bucket_from_accel(a_filt or 0.0, accel_th),
                "phase": dat[0],
                "wB": latest["w59b"],
                "wC": latest["w59c"],
                "delta": delta,
              })
          recent59.append({
            "t": t,
            "phase": dat[0],
            "wB": latest["w59b"],
            "wC": latest["w59c"],
            "delta": delta_u16(int(latest["w59b"]), LONG_59_CENTER_WB) + 0.5 * delta_u16(int(latest["w59c"]), LONG_59_CENTER_WC),
          })
        elif (can_msg.src, can_msg.address) == (1, 54) and len(dat) >= 7:
          latest["phase54"] = dat[0]
          latest["w54b"] = u16_le(dat, 3)
          latest["w54c"] = u16_le(dat, 5)
          if prev_cs_t is not None:
            delta = delta_u16(int(latest["w54b"]), LONG_54_CENTER_WB) + 0.5 * delta_u16(int(latest["w54c"]), LONG_54_CENTER_WC)
            if latest["w54b"] != 0 or latest["w54c"] != 0:
              nonzero_frames.append({
                "route": route_name,
                "branch": 54,
                "mode": mode_from_state(latest["gate131"], latest["state135"]),
                "bucket": bucket_from_accel(a_filt or 0.0, accel_th),
                "phase": dat[0],
                "wB": latest["w54b"],
                "wC": latest["w54c"],
                "delta": delta,
              })
          recent54.append({
            "t": t,
            "phase": dat[0],
            "wB": latest["w54b"],
            "wC": latest["w54c"],
            "delta": delta_u16(int(latest["w54b"]), LONG_54_CENTER_WB) + 0.5 * delta_u16(int(latest["w54c"]), LONG_54_CENTER_WC),
          })
      prune_recent(t)
      continue

    if which != "carState":
      continue

    cs = msg.carState
    v_ego = float(cs.vEgo)
    if prev_cs_t is None or prev_v is None:
      raw_a = float(cs.aEgo)
    else:
      dt = max(t - prev_cs_t, 1e-3)
      raw_a = (v_ego - prev_v) / dt
    prev_cs_t = t
    prev_v = v_ego
    a_filt = raw_a if a_filt is None else (alpha * raw_a + (1.0 - alpha) * a_filt)

    mode = mode_from_state(latest["gate131"], latest["state135"])
    if mode not in ("ACC_ARMED", "MANAGED"):
      continue
    if bool(cs.gasPressed) or bool(cs.standstill):
      continue
    if v_ego < 1.0:
      continue
    if any(latest[k] is None for k in ("w59b", "w59c", "w54b", "w54c", "phase59", "phase54")):
      continue

    prune_recent(t)
    best59 = best_recent(recent59)
    best54 = best_recent(recent54)
    if best59 is None or best54 is None:
      continue

    raw59 = float(best59["delta"])
    raw54 = float(best54["delta"])
    act59 = active_delta(int(best59["phase"]), raw59, LONG_59_ACTIVE_PARITY)
    act54 = active_delta(int(best54["phase"]), raw54, LONG_54_ACTIVE_PARITY)

    samples.append({
      "route": route_name,
      "t": t,
      "mode": mode,
      "vEgo": v_ego,
      "aRaw": raw_a,
      "aProxy": a_filt,
      "bucket": bucket_from_accel(a_filt, accel_th),
      "phase59": int(best59["phase"]),
      "w59b": int(best59["wB"]),
      "w59c": int(best59["wC"]),
      "raw59": raw59,
      "act59": act59,
      "phase54": int(best54["phase"]),
      "w54b": int(best54["wB"]),
      "w54c": int(best54["wC"]),
      "raw54": raw54,
      "act54": act54,
    })

  return samples, nonzero_frames


def summarize(samples: list[dict], nonzero_frames: list[dict], accel_th: float) -> None:
  print(f"samples={len(samples)} accel_threshold={accel_th}")
  if not samples:
    return

  print("\n# overall")
  a_proxy = [s["aProxy"] for s in samples]
  raw59 = [s["raw59"] for s in samples]
  raw54 = [s["raw54"] for s in samples]
  act59 = [s["act59"] for s in samples]
  act54 = [s["act54"] for s in samples]
  print(f"corr(aProxy, raw59)={pearson(a_proxy, raw59)}")
  print(f"corr(aProxy, raw54)={pearson(a_proxy, raw54)}")
  print(f"corr(aProxy, act59)={pearson(a_proxy, act59)}")
  print(f"corr(aProxy, act54)={pearson(a_proxy, act54)}")
  print(f"corr(aProxy, -act54)={pearson(a_proxy, [-x for x in act54])}")

  print("\n# per route")
  by_route = defaultdict(list)
  for s in samples:
    by_route[s["route"]].append(s)
  for route, arr in sorted(by_route.items()):
    xs = [s["aProxy"] for s in arr]
    print(
      f"{route}: n={len(arr)} "
      f"corr(a,act59)={pearson(xs, [s['act59'] for s in arr])} "
      f"corr(a,-act54)={pearson(xs, [-s['act54'] for s in arr])}"
    )

  print("\n# buckets")
  for bucket in ("ACCEL", "COAST", "DECEL"):
    arr = [s for s in samples if s["bucket"] == bucket]
    if not arr:
      continue
    print(
      f"{bucket}: n={len(arr)} "
      f"a_med={median([s['aProxy'] for s in arr]):.4f} "
      f"act59_med={median([s['act59'] for s in arr]):.1f} "
      f"act54_med={median([s['act54'] for s in arr]):.1f} "
      f"w59b_med={median([s['w59b'] for s in arr])} "
      f"w59c_med={median([s['w59c'] for s in arr])} "
      f"w54b_med={median([s['w54b'] for s in arr])} "
      f"w54c_med={median([s['w54c'] for s in arr])}"
    )

  print("\n# managed-only buckets")
  managed = [s for s in samples if s["mode"] == "MANAGED"]
  for bucket in ("ACCEL", "COAST", "DECEL"):
    arr = [s for s in managed if s["bucket"] == bucket]
    if not arr:
      continue
    print(
      f"MANAGED {bucket}: n={len(arr)} "
      f"a_med={median([s['aProxy'] for s in arr]):.4f} "
      f"act59_med={median([s['act59'] for s in arr]):.1f} "
      f"act54_med={median([s['act54'] for s in arr]):.1f} "
      f"w59b_med={median([s['w59b'] for s in arr])} "
      f"w59c_med={median([s['w59c'] for s in arr])} "
      f"w54b_med={median([s['w54b'] for s in arr])} "
      f"w54c_med={median([s['w54c'] for s in arr])}"
    )

  print("\n# first LUT guess")
  for bucket in ("ACCEL", "COAST", "DECEL"):
    arr = [s for s in managed if s["bucket"] == bucket]
    if not arr:
      continue
    if bucket == "DECEL":
      print(
        f"{bucket}: branch=54 "
        f"target_wB={median([s['w54b'] for s in arr])} "
        f"target_wC={median([s['w54c'] for s in arr])}"
      )
    else:
      print(
        f"{bucket}: branch=59 "
        f"target_wB={median([s['w59b'] for s in arr])} "
        f"target_wC={median([s['w59c'] for s in arr])}"
      )

  print("\n# nonzero frame buckets")
  by_branch_bucket = defaultdict(list)
  for row in nonzero_frames:
    if row["mode"] in ("ACC_ARMED", "MANAGED"):
      by_branch_bucket[(row["branch"], row["bucket"])].append(row)
  for branch in (59, 54):
    for bucket in ("ACCEL", "COAST", "DECEL"):
      arr = by_branch_bucket.get((branch, bucket), [])
      if not arr:
        continue
      counts = defaultdict(int)
      for row in arr:
        counts[(row["wB"], row["wC"], row["phase"])] += 1
      top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:6]
      print(
        f"{branch} {bucket}: n={len(arr)} "
        f"delta_med={median([row['delta'] for row in arr]):.1f} "
        f"top={top}"
      )


def main() -> int:
  ap = argparse.ArgumentParser(description="Fit BMW i3 long amplitude from vEgo/dvdt against 54/59")
  ap.add_argument("--accel-th", type=float, default=0.12, help="accel/decel bucket threshold in m/s^2")
  ap.add_argument("--alpha", type=float, default=0.35, help="EMA alpha for dv/dt")
  args = ap.parse_args()

  samples: list[dict] = []
  nonzero_frames: list[dict] = []
  for name, path in ROUTES.items():
    if not Path(path).exists():
      continue
    route_samples, route_nonzero = collect_route(name, path, accel_th=args.accel_th, alpha=args.alpha)
    samples.extend(route_samples)
    nonzero_frames.extend(route_nonzero)
  summarize(samples, nonzero_frames, accel_th=args.accel_th)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
