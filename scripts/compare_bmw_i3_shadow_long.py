#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import statistics
from typing import Optional

import sys
sys.path.insert(0, "/home/gericho/sunnypilot")
from opendbc.car.logreader import LogReader


def resolve_latest_route() -> Optional[Path]:
  root = Path("/home/gericho/.comma/media/0/realdata")
  candidates = sorted(root.glob("*--0"), key=lambda p: p.stat().st_mtime, reverse=True)
  return candidates[0] if candidates else None


def resolve_latest_swaglog() -> Optional[Path]:
  root = Path("/home/gericho/.comma/log")
  candidates = sorted(root.glob("swaglog.*"), key=lambda p: p.stat().st_mtime, reverse=True)
  return candidates[0] if candidates else None


def expand_route_segments(route: str) -> list[Path]:
  p = Path(route)
  if p.is_file():
    if p.name == "rlog.zst":
      return [p]
    raise FileNotFoundError(f"unsupported file path: {p}")
  if p.name.endswith("--0"):
    stem = p.name[:-1]
    base = p.parent
  elif "--" in p.name and p.name.rsplit("--", 1)[-1].isdigit():
    stem = p.name.rsplit("--", 1)[0] + "--"
    base = p.parent
  else:
    stem = p.name
    base = p.parent
  segs = sorted(base.glob(f"{stem}[0-9]*"))
  if not segs:
    if (p / "rlog.zst").exists():
      return [p / "rlog.zst"]
    raise FileNotFoundError(f"no route segments found for {route}")
  return [seg / "rlog.zst" for seg in segs if (seg / "rlog.zst").exists()]


def u16_le(dat: bytes, off: int) -> int:
  return dat[off] | (dat[off + 1] << 8)


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
    return f"TRANSITION({state})"
  return "UNKNOWN"


def collect_route_long(route: str) -> list[dict]:
  rows: list[dict] = []
  seg_offset = 0
  for rlog in expand_route_segments(route):
    first_ts = None
    last_sec = -1
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
    for evt in LogReader(str(rlog), only_union_types=True):
      if evt.which() != "can":
        continue
      evt_ts = evt.logMonoTime / 1e9
      if first_ts is None:
        first_ts = evt_ts
      sec = int(evt_ts - first_ts)
      for m in evt.can:
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
      if sec != last_sec and sec >= 0:
        rows.append({
          "t": seg_offset + sec,
          "mode": mode_from_state(state["gate131"], state["state135"]),
          **state,
        })
        last_sec = sec
    if last_sec >= 0:
      seg_offset += last_sec + 1
  return rows


def extract_dict(line: str, event: str) -> Optional[dict]:
  if event not in line:
    return None
  start = line.find("{")
  end = line.rfind("}")
  if start == -1 or end == -1 or end <= start:
    return None
  try:
    data = ast.literal_eval(line[start:end + 1])
  except Exception:
    return None
  if data.get("event") != event:
    return None
  return data


def collect_shadow_long(swaglog: str) -> list[dict]:
  out = []
  with Path(swaglog).open("r", encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
      data = extract_dict(line, "bmw_i3_shadow_long")
      if data is not None:
        data["_idx"] = i
        out.append(data)
  return out


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
  if len(xs) < 2 or len(xs) != len(ys):
    return None
  mx = statistics.fmean(xs)
  my = statistics.fmean(ys)
  num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
  denx = sum((x - mx) ** 2 for x in xs)
  deny = sum((y - my) ** 2 for y in ys)
  if denx <= 0 or deny <= 0:
    return None
  return num / ((denx * deny) ** 0.5)


def main() -> int:
  ap = argparse.ArgumentParser(description="Compare BMW i3 shadow longitudinal logs against real 59/54 route data")
  ap.add_argument("route", nargs="?", help="route dir or segment; omit to use latest route")
  ap.add_argument("--swaglog", help="swaglog path; omit to use latest swaglog")
  args = ap.parse_args()

  route = args.route
  if route is None:
    latest = resolve_latest_route()
    if latest is None:
      raise FileNotFoundError("no routes found")
    route = str(latest)
  swaglog = args.swaglog
  if swaglog is None:
    latest_log = resolve_latest_swaglog()
    if latest_log is None:
      raise FileNotFoundError("no swaglogs found")
    swaglog = str(latest_log)

  route_rows = collect_route_long(route)
  active_rows = [r for r in route_rows if r["mode"] in ("ACC_ARMED", "MANAGED")]
  shadow_rows = collect_shadow_long(swaglog)

  print(f"ROUTE={route}")
  print(f"SWAGLOG={swaglog}")
  print(f"route_rows={len(route_rows)} active_rows={len(active_rows)} shadow_rows={len(shadow_rows)}")

  if not active_rows:
    print("no ACC_ARMED/MANAGED route rows found")
    return 0
  if not shadow_rows:
    print("no bmw_i3_shadow_long lines found")
    return 0

  n = min(len(active_rows), len(shadow_rows))
  aligned_route = active_rows[:n]
  aligned_shadow = shadow_rows[:n]

  desired = [float(s["desired_accel"]) for s in aligned_shadow]
  wb59 = [float(r["long59_wb"]) for r in aligned_route]
  wc59 = [float(r["long59_wc"]) for r in aligned_route]
  wb54 = [float(r["long54_wb"]) for r in aligned_route]
  wc54 = [float(r["long54_wc"]) for r in aligned_route]

  print("\n# summary")
  print(f"aligned_samples={n}")
  print(f"route_t_range={aligned_route[0]['t']}..{aligned_route[-1]['t']}")
  print(f"desired_accel_mean={statistics.fmean(desired):.4f} min={min(desired):.4f} max={max(desired):.4f}")
  print(f"59_wb_mean={statistics.fmean(wb59):.3f} min={min(wb59):.0f} max={max(wb59):.0f}")
  print(f"59_wc_mean={statistics.fmean(wc59):.3f} min={min(wc59):.0f} max={max(wc59):.0f}")
  print(f"54_wb_mean={statistics.fmean(wb54):.3f} min={min(wb54):.0f} max={max(wb54):.0f}")
  print(f"54_wc_mean={statistics.fmean(wc54):.3f} min={min(wc54):.0f} max={max(wc54):.0f}")

  print("\n# correlation")
  print(f"corr(desired_accel, 59_wb)={pearson(desired, wb59)}")
  print(f"corr(desired_accel, 59_wc)={pearson(desired, wc59)}")
  print(f"corr(desired_accel, 54_wb)={pearson(desired, wb54)}")
  print(f"corr(desired_accel, 54_wc)={pearson(desired, wc54)}")

  print("\n# mode_buckets")
  for mode in ("ACC_ARMED", "MANAGED"):
    sub = [r for r in active_rows if r["mode"] == mode]
    if not sub:
      continue
    print(
      f"{mode}: n={len(sub)} "
      f"59_wb_mean={statistics.fmean(float(r['long59_wb']) for r in sub):.3f} "
      f"59_wc_mean={statistics.fmean(float(r['long59_wc']) for r in sub):.3f} "
      f"54_wb_mean={statistics.fmean(float(r['long54_wb']) for r in sub):.3f} "
      f"54_wc_mean={statistics.fmean(float(r['long54_wc']) for r in sub):.3f}"
    )

  print("\n# aligned_samples_preview")
  for r, s in list(zip(aligned_route, aligned_shadow))[:20]:
    print(
      f"t={r['t']:4d} mode={r['mode']:9s} "
      f"59=({r['long59_wb']},{r['long59_wc']},{r['long59_b3']},{r['long59_b5']}) "
      f"54=({r['long54_wb']},{r['long54_wc']},{r['long54_b4']},{r['long54_b6']}) "
      f"shadow(accel={s['desired_accel']}, active={s['long_active']}, base={s['acc_base_armed']}, managed={s['tja_active']})"
    )

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
