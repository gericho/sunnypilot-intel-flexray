#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import mean

from tools.lib.logreader import LogReader

ROUTES = {
  'e9': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
    'windows': [
      ('right', 25, 28), ('left', 29, 34), ('right', 40, 44),
      ('right', 66, 67), ('left', 69, 70),
    ],
  },
  'ea': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst',
    'windows': [
      ('right', 37, 41), ('left', 59, 60), ('right', 66, 67), ('left', 69, 70),
      ('right', 73, 74), ('left', 77, 78), ('right', 101, 106),
    ],
  },
  'eb': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000eb--41f9ac2c70--0/rlog.zst',
    'windows': [('right', 41, 42), ('left', 43, 44), ('left', 86, 87)],
  },
}

PHASE_THRESHOLDS = {
  60: 112.083,
  24: 80.833,
  8: 149.5,
}


@dataclass
class Row:
  route: str
  label: str
  phase: int
  b0: int
  b1: int
  b2: int
  angle: float
  yaw: float
  torque: float


def label_for_time(t: float, windows: list[tuple[str, float, float]]) -> str | None:
  for lbl, a, b in windows:
    if a <= t < b:
      return lbl
  return None


def pearson(xs: list[float], ys: list[float]) -> float:
  if len(xs) < 2 or len(xs) != len(ys):
    return 0.0
  mx = mean(xs)
  my = mean(ys)
  num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
  denx = sqrt(sum((x - mx) ** 2 for x in xs))
  deny = sqrt(sum((y - my) ** 2 for y in ys))
  if denx == 0.0 or deny == 0.0:
    return 0.0
  return num / (denx * deny)


def fit_linear(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
  # y ~= a*x + b ; returns a, b, mae
  mx = mean(xs)
  my = mean(ys)
  varx = sum((x - mx) ** 2 for x in xs)
  if varx == 0.0:
    return 0.0, my, mean(abs(y - my) for y in ys)
  cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
  a = cov / varx
  b = my - a * mx
  mae = mean(abs((a * x + b) - y) for x, y in zip(xs, ys))
  return a, b, mae


def collect_rows() -> list[Row]:
  rows: list[Row] = []
  for name, cfg in ROUTES.items():
    fn = Path(cfg['fn'])
    if not fn.exists():
      continue
    start = None
    angle = None
    yaw = None
    torque = None
    last72 = None
    for evt in LogReader(str(fn)):
      if start is None:
        start = evt.logMonoTime
      t = (evt.logMonoTime - start) / 1e9
      if evt.which() != 'can':
        continue
      label = label_for_time(t, cfg['windows'])
      for c in evt.can:
        d = bytes(c.dat)
        if c.src == 1 and c.address == 51 and len(d) >= 3:
          angle = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.1)
        elif c.src == 1 and c.address == 56 and len(d) >= 3:
          yaw = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.01)
        elif c.src == 1 and c.address == 49 and len(d) >= 3:
          torque = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.01)
        elif c.src == 0 and c.address == 72 and len(d) >= 1:
          last72 = (t, d)
        elif label is not None and c.src == 0 and c.address == 96 and len(d) >= 9 and angle and yaw and torque and last72:
          if max(abs(angle[0] - t), abs(yaw[0] - t), abs(torque[0] - t), abs(last72[0] - t)) > 0.03:
            continue
          if last72[1][0] != d[0]:
            continue
          rows.append(Row(name, label, d[0], d[0], d[1], d[2], angle[1], yaw[1], torque[1]))
  return rows


def main() -> int:
  rows = collect_rows()
  print(f'rows {len(rows)}')
  by_phase: dict[int, list[Row]] = defaultdict(list)
  for r in rows:
    by_phase[r.phase].append(r)

  for phase in sorted(by_phase):
    phase_rows = by_phase[phase]
    left = [r for r in phase_rows if r.label == 'left']
    right = [r for r in phase_rows if r.label == 'right']
    if len(left) < 2 or len(right) < 2:
      continue

    print(f'\n## phase {phase} n={len(phase_rows)} left={len(left)} right={len(right)}')
    print({
      'b0_left_mean': round(mean(r.b0 for r in left), 3),
      'b0_right_mean': round(mean(r.b0 for r in right), 3),
      'b1_left_mean': round(mean(r.b1 for r in left), 3),
      'b1_right_mean': round(mean(r.b1 for r in right), 3),
      'b2_left_mean': round(mean(r.b2 for r in left), 3),
      'b2_right_mean': round(mean(r.b2 for r in right), 3),
      'angle_left_mean': round(mean(abs(r.angle) for r in left), 3),
      'angle_right_mean': round(mean(abs(r.angle) for r in right), 3),
      'torque_left_mean': round(mean(abs(r.torque) for r in left), 3),
      'torque_right_mean': round(mean(abs(r.torque) for r in right), 3),
    })

    abs_angle = [abs(r.angle) for r in phase_rows]
    abs_torque = [abs(r.torque) for r in phase_rows]
    cand_fields = {
      'b0': [r.b0 for r in phase_rows],
      'b1': [r.b1 for r in phase_rows],
      'b2': [r.b2 for r in phase_rows],
    }
    for name, vals in cand_fields.items():
      print(name, {
        'corr_abs_angle': round(pearson(vals, abs_angle), 4),
        'corr_abs_torque': round(pearson(vals, abs_torque), 4),
        'uniq': sorted(set(vals))[:20],
      })

    if phase in PHASE_THRESHOLDS:
      thr = PHASE_THRESHOLDS[phase]
      signed_b1 = []
      signed_target = []
      for r in phase_rows:
        pred_sign = 1.0 if r.b1 > thr else -1.0
        signed_b1.append(pred_sign * abs(r.b1 - thr))
        signed_target.append(1.0 * abs(r.angle) if r.label == 'right' else -1.0 * abs(r.angle))
      a, b, mae = fit_linear(signed_b1, signed_target)
      print('signed_b1_model', {
        'threshold': thr,
        'corr_signed_target': round(pearson(signed_b1, signed_target), 4),
        'slope': round(a, 4),
        'bias': round(b, 4),
        'mae_angle_deg': round(mae, 4),
      })

      # also test b0 as unsigned local magnitude after direction comes from b1
      a0, b0, mae0 = fit_linear([r.b0 for r in phase_rows], abs_angle)
      print('b0_abs_angle_model', {
        'corr_abs_angle': round(pearson([r.b0 for r in phase_rows], abs_angle), 4),
        'slope': round(a0, 4),
        'bias': round(b0, 4),
        'mae_angle_deg': round(mae0, 4),
      })
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
