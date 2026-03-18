#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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

SUPPORT_ROUTES = {
  '176': {
    'fn': '/home/gericho/.comma/media/0/realdata/00000176--3a6e928ca3--0/rlog.zst',
  },
}


@dataclass
class Row:
  route: str
  label: str
  t: float
  phase: int
  b1: int
  b2: int
  angle: float
  yaw: float


@dataclass
class SupportRow:
  route: str
  t: float
  phase: int
  b1: int
  b2: int
  mode: str


def label_for_time(t: float, windows: list[tuple[str, float, float]]) -> str | None:
  for lbl, a, b in windows:
    if a <= t < b:
      return lbl
  return None


def collect_rows() -> list[Row]:
  rows: list[Row] = []
  for name, cfg in ROUTES.items():
    fn = Path(cfg['fn'])
    if not fn.exists():
      continue
    start = None
    angle = None
    yaw = None
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
        elif c.src == 0 and c.address == 72 and len(d) >= 1:
          last72 = (t, d)
        elif label is not None and c.src == 0 and c.address == 96 and len(d) >= 9 and angle and yaw and last72:
          if abs(angle[0] - t) > 0.03 or abs(yaw[0] - t) > 0.03 or abs(last72[0] - t) > 0.03:
            continue
          if last72[1][0] != d[0]:
            continue
          rows.append(Row(name, label, t, d[0], d[1], d[2], angle[1], yaw[1]))
  return rows


def mode_from_state(gate: int | None, state: int | None) -> str:
  if gate == 643 and state == 35041:
    return 'OFF'
  if gate == 3584 and state == 16610:
    return 'ACC_ARMED'
  if state == 26850:
    return 'TRANSITION'
  if gate in (640, 656) and state == 24802:
    return 'MANAGED'
  return 'UNKNOWN'


def collect_support_rows() -> list[SupportRow]:
  rows: list[SupportRow] = []
  for name, cfg in SUPPORT_ROUTES.items():
    fn = Path(cfg['fn'])
    if not fn.exists():
      continue
    start = None
    gate131 = None
    state135 = None
    last72 = None
    for evt in LogReader(str(fn)):
      if start is None:
        start = evt.logMonoTime
      t = (evt.logMonoTime - start) / 1e9
      if evt.which() != 'can':
        continue
      for c in evt.can:
        d = bytes(c.dat)
        if c.src == 0 and c.address == 131 and len(d) >= 7:
          gate131 = int.from_bytes(d[5:7], 'little')
        elif c.src == 0 and c.address == 135 and len(d) >= 7:
          state135 = int.from_bytes(d[5:7], 'little')
        elif c.src == 0 and c.address == 72 and len(d) >= 1:
          last72 = (t, d)
        elif c.src == 0 and c.address == 96 and len(d) >= 9 and last72:
          if abs(last72[0] - t) > 0.03:
            continue
          if last72[1][0] != d[0]:
            continue
          rows.append(SupportRow(name, t, d[0], d[1], d[2], mode_from_state(gate131, state135)))
  return rows


def summarize(rows: list[Row]) -> list[dict]:
  by_phase: dict[int, dict[str, list[Row]]] = defaultdict(lambda: defaultdict(list))
  for r in rows:
    by_phase[r.phase][r.label].append(r)

  out: list[dict] = []
  for phase in sorted(by_phase):
    left = by_phase[phase].get('left', [])
    right = by_phase[phase].get('right', [])
    if not left or not right:
      continue

    left_b1 = [r.b1 for r in left]
    right_b1 = [r.b1 for r in right]
    lmean = mean(left_b1)
    rmean = mean(right_b1)
    direction = 'right_gt_left' if rmean > lmean else 'left_gt_right'
    threshold = (lmean + rmean) / 2.0
    gap = abs(rmean - lmean)
    overlap = min(max(left_b1), max(right_b1)) - max(min(left_b1), min(right_b1))
    disjoint = max(left_b1) < min(right_b1) or max(right_b1) < min(left_b1)
    score = gap + (40.0 if disjoint else 0.0) - max(0.0, overlap)

    out.append({
      'phase': phase,
      'n_left': len(left),
      'n_right': len(right),
      'left_mean_b1': round(lmean, 3),
      'right_mean_b1': round(rmean, 3),
      'left_vals': sorted(set(left_b1)),
      'right_vals': sorted(set(right_b1)),
      'direction': direction,
      'threshold_b1': round(threshold, 3),
      'gap': round(gap, 3),
      'overlap': round(float(overlap), 3),
      'disjoint': disjoint,
      'score': round(score, 3),
      'angle_left': round(mean(r.angle for r in left), 3),
      'angle_right': round(mean(r.angle for r in right), 3),
      'yaw_left': round(mean(r.yaw for r in left), 4),
      'yaw_right': round(mean(r.yaw for r in right), 4),
    })
  out.sort(key=lambda r: r['score'], reverse=True)
  return out


def main() -> int:
  rows = collect_rows()
  support_rows = collect_support_rows()
  print(f'rows {len(rows)}')
  print(f'support_rows {len(support_rows)}')
  results = summarize(rows)
  print('\n# ranked phase-local classifier candidates for LAT96.byte1')
  for r in results:
    print(r)

  support_managed = [r for r in support_rows if r.mode == 'MANAGED']
  if support_managed:
    support_by_phase: dict[int, list[SupportRow]] = defaultdict(list)
    for r in support_managed:
      support_by_phase[r.phase].append(r)
    print('\n# managed_support_phase_coverage')
    for phase, vals in sorted(support_by_phase.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:24]:
      b1s = [r.b1 for r in vals]
      print({
        'phase': phase,
        'support_count': len(vals),
        'support_b1_mean': round(mean(b1s), 3),
        'support_b1_uniq': sorted(set(b1s))[:12],
      })

  print('\n# pragmatic_lut')
  for r in results:
    if r['n_left'] < 2 or r['n_right'] < 2:
      continue
    if r['gap'] < 20:
      continue
    support_count = 0
    if support_managed:
      support_count = sum(1 for row in support_managed if row.phase == r['phase'])
    print({
      'phase': r['phase'],
      'field': 'b1',
      'threshold': r['threshold_b1'],
      'direction': r['direction'],
      'confidence': 'high' if r['disjoint'] else 'medium',
      'support_count': support_count,
    })
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
