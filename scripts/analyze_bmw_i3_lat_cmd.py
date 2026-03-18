#!/usr/bin/env python3
from collections import defaultdict
from math import copysign
from statistics import mean

from tools.lib.logreader import LogReader

ROUTES = {
  'e9': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
  'ea': '/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst',
}

# candidate fields from src1/112 and src1/116
FIELDS = {
  '112_wA': lambda d: int.from_bytes(d[0:2], 'little'),
  '112_wB': lambda d: int.from_bytes(d[2:4], 'little'),
  '112_b0': lambda d: d[0],
  '112_b1': lambda d: d[1],
  '112_b2': lambda d: d[2],
  '112_b5': lambda d: d[5],
  '116_wA': lambda d: int.from_bytes(d[0:2], 'little'),
  '116_wB': lambda d: int.from_bytes(d[2:4], 'little'),
  '116_b0': lambda d: d[0],
  '116_b1': lambda d: d[1],
  '116_b2': lambda d: d[2],
  '116_b5': lambda d: d[5],
}


def signed16(v: int) -> int:
  return v - 65536 if v >= 32768 else v


def nearest(samples, t):
  # samples list of (t, value), ordered by t
  if not samples:
    return None
  lo, hi = 0, len(samples) - 1
  while lo < hi:
    mid = (lo + hi) // 2
    if samples[mid][0] < t:
      lo = mid + 1
    else:
      hi = mid
  idx = lo
  cand = [samples[idx]]
  if idx > 0:
    cand.append(samples[idx - 1])
  return min(cand, key=lambda x: abs(x[0] - t))[1]


for name, fn in ROUTES.items():
  angle = []
  torque = []
  yaw = []
  active = []
  fields = defaultdict(list)
  start = None

  for m in LogReader(fn):
    if start is None:
      start = m.logMonoTime
    t = (m.logMonoTime - start) / 1e9
    if m.which() != 'can':
      continue
    for c in m.can:
      dat = bytes(c.dat)
      if c.src == 1 and c.address == 51:  # EPS_ANGLE
        raw = int.from_bytes(dat[1:3], 'little', signed=True)
        angle.append((t, raw * 0.01))
      elif c.src == 1 and c.address == 49:  # STEER_TORQUE
        raw = int.from_bytes(dat[1:3], 'little', signed=True)
        torque.append((t, raw * 0.01))
      elif c.src == 1 and c.address == 57:  # yaw
        raw = int.from_bytes(dat[1:3], 'little', signed=True)
        yaw.append((t, raw * 0.01))
      elif c.src == 0 and c.address == 135:
        active.append((t, int.from_bytes(dat, 'little')))
      elif c.src == 1 and c.address in (112, 116):
        prefix = '112' if c.address == 112 else '116'
        for k, fnf in FIELDS.items():
          if k.startswith(prefix):
            v = fnf(dat)
            if k.endswith('wA') or k.endswith('wB'):
              v = signed16(v)
            fields[k].append((t, v))

  # build labeled samples at 112 timestamps only, assisted and low driver torque
  deriv_labels = defaultdict(list)
  for i in range(1, len(angle)):
    t0, a0 = angle[i - 1]
    t1, a1 = angle[i]
    dt = t1 - t0
    if dt <= 0:
      continue
    da = (a1 - a0) / dt
    if abs(da) < 3.0:
      continue
    ctrl = nearest(active, t1)
    tq = nearest(torque, t1)
    yw = nearest(yaw, t1)
    if ctrl != 115463535908537685520 and ctrl != 115463535908538341128 and ctrl != 103934320862469475892:
      # managed/TJA-ish states observed in modern routes; keep only assisted windows
      continue
    if tq is not None and abs(tq) > 0.5:
      continue
    label = 'right' if da > 0 else 'left'
    deriv_labels['angle_rate'].append((label, da, yw if yw is not None else 0.0, t1))
    for field_name, samples in fields.items():
      v = nearest(samples, t1)
      if v is not None:
        deriv_labels[field_name].append((label, v))

  print(f'## {name}')
  print('matched_events', len(deriv_labels['angle_rate']))
  if deriv_labels['angle_rate']:
    left_da = [x[1] for x in deriv_labels['angle_rate'] if x[0] == 'left']
    right_da = [x[1] for x in deriv_labels['angle_rate'] if x[0] == 'right']
    print('mean_angle_rate_left', round(mean(left_da), 3) if left_da else None)
    print('mean_angle_rate_right', round(mean(right_da), 3) if right_da else None)
  scored = []
  for field_name, entries in deriv_labels.items():
    if field_name == 'angle_rate':
      continue
    left = [v for lbl, v in entries if lbl == 'left']
    right = [v for lbl, v in entries if lbl == 'right']
    if len(left) < 3 or len(right) < 3:
      continue
    score = abs(mean(right) - mean(left))
    scored.append((score, field_name, round(mean(left), 3), round(mean(right), 3), len(left), len(right), sorted(set(left))[:8], sorted(set(right))[:8]))
  scored.sort(reverse=True)
  for s in scored[:8]:
    print(s)
  print()
