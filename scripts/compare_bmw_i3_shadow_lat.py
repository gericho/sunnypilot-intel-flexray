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
  out: list[Path] = []
  for seg in segs:
    rlog = seg / "rlog.zst"
    if rlog.exists():
      out.append(rlog)
  return out


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


def collect_route_lat(route: str) -> list[dict]:
  rows: list[dict] = []
  seg_offset = 0
  for rlog in expand_route_segments(route):
    first_ts = None
    last_sec = -1
    state = {
      "gate131": None,
      "state135": None,
      "lat72_phase": None,
      "lat72_cnt": None,
      "lat72_flag": None,
      "lat96_b0": None,
      "lat96_b1": None,
      "lat96_b2": None,
      "lat96_b3": None,
      "lat96_b4": None,
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
        elif (m.src, m.address) == (0, 72) and len(dat) >= 9:
          state["lat72_phase"] = dat[0]
          state["lat72_cnt"] = dat[2] & 0x0F
          state["lat72_flag"] = dat[8]
        elif (m.src, m.address) == (0, 96) and len(dat) >= 5:
          state["lat96_b0"] = dat[0]
          state["lat96_b1"] = dat[1]
          state["lat96_b2"] = dat[2]
          state["lat96_b3"] = dat[3]
          state["lat96_b4"] = dat[4]
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


def collect_shadow_lat(swaglog: str) -> list[dict]:
  out = []
  with Path(swaglog).open("r", encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
      data = extract_dict(line, "bmw_i3_shadow_acc")
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
  ap = argparse.ArgumentParser(description="Compare BMW i3 shadow lateral logs against real 72/96 route data")
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

  route_rows = collect_route_lat(route)
  managed_rows = [r for r in route_rows if r["mode"] == "MANAGED" and r["lat96_b1"] is not None]
  shadow_rows = collect_shadow_lat(swaglog)

  print(f"ROUTE={route}")
  print(f"SWAGLOG={swaglog}")
  print(f"route_rows={len(route_rows)} managed_rows={len(managed_rows)} shadow_rows={len(shadow_rows)}")

  if not managed_rows:
    print("no MANAGED route rows found")
    return 0
  if not shadow_rows:
    print("no bmw_i3_shadow_acc lines found")
    return 0

  n = min(len(managed_rows), len(shadow_rows))
  aligned_route = managed_rows[:n]
  aligned_shadow = shadow_rows[:n]

  route_b1 = [float(r["lat96_b1"]) for r in aligned_route]
  route_b2 = [float(r["lat96_b2"]) for r in aligned_route]
  shadow_angle = [float(s["angle_deg"]) for s in aligned_shadow]
  shadow_torque = [float(s["steer_torque_req"]) for s in aligned_shadow]

  print("\n# summary")
  print(f"aligned_samples={n}")
  print(f"route_t_range={aligned_route[0]['t']}..{aligned_route[-1]['t']}")
  print(f"route_lat96_b1_mean={statistics.fmean(route_b1):.3f} min={min(route_b1):.0f} max={max(route_b1):.0f}")
  print(f"route_lat96_b2_mean={statistics.fmean(route_b2):.3f} min={min(route_b2):.0f} max={max(route_b2):.0f}")
  print(f"shadow_angle_mean={statistics.fmean(shadow_angle):.3f} min={min(shadow_angle):.3f} max={max(shadow_angle):.3f}")
  print(f"shadow_torque_mean={statistics.fmean(shadow_torque):.3f} min={min(shadow_torque):.3f} max={max(shadow_torque):.3f}")

  corr_b1_angle = pearson(route_b1, shadow_angle)
  corr_b1_torque = pearson(route_b1, shadow_torque)
  corr_b2_angle = pearson(route_b2, shadow_angle)
  print("\n# correlation")
  print(f"corr(lat96_b1, shadow_angle)={corr_b1_angle if corr_b1_angle is not None else 'n/a'}")
  print(f"corr(lat96_b1, shadow_torque)={corr_b1_torque if corr_b1_torque is not None else 'n/a'}")
  print(f"corr(lat96_b2, shadow_angle)={corr_b2_angle if corr_b2_angle is not None else 'n/a'}")

  phase_hist = {}
  for r in managed_rows:
    phase_hist[r["lat72_phase"]] = phase_hist.get(r["lat72_phase"], 0) + 1
  top_phases = sorted(phase_hist.items(), key=lambda kv: kv[1], reverse=True)[:12]
  print("\n# top_managed_phases")
  for phase, count in top_phases:
    vals = [r["lat96_b1"] for r in managed_rows if r["lat72_phase"] == phase and r["lat96_b1"] is not None]
    if vals:
      print(f"phase={phase:2d} count={count:3d} lat96_b1_mean={statistics.fmean(vals):.3f} uniq={sorted(set(vals))[:8]}")

  print("\n# aligned_samples_preview")
  for r, s in list(zip(aligned_route, aligned_shadow))[:20]:
    print(
      f"t={r['t']:4d} mode={r['mode']:8s} "
      f"72=({r['lat72_phase']},{r['lat72_cnt']},{r['lat72_flag']}) "
      f"96=({r['lat96_b0']},{r['lat96_b1']},{r['lat96_b2']},{r['lat96_b3']},{r['lat96_b4']}) "
      f"shadow(angle={s['angle_deg']}, torque={s['steer_torque_req']}, cycle={s['cycle_count']}, cnt={s['cnt1']}, ready={s['tja_ready']}, trig={s['lat_triggered']})"
    )

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
