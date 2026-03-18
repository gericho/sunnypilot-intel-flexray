#!/usr/bin/env python3
from collections import defaultdict
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'e9': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
    'windows': [('right', 25, 28), ('left', 29, 34), ('right', 40, 44), ('right', 66, 67), ('left', 69, 70)],
  },
  'ea': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst',
    'windows': [('right', 37, 41), ('left', 59, 60), ('right', 66, 67), ('left', 69, 70), ('right', 73, 74), ('left', 77, 78), ('right', 101, 106)],
  },
}

# Use nearest previous angle/yaw and estimate forward delta over ~100ms
rows = []
for name, cfg in ROUTES.items():
  start = None
  angle_hist = []
  yaw_hist = []
  last72 = None
  pending = []
  for m in LogReader(cfg['fn']):
    if start is None:
      start = m.logMonoTime
    t = (m.logMonoTime - start) / 1e9
    if m.which() != 'can':
      continue
    label = None
    for lbl, a, b in cfg['windows']:
      if a <= t < b:
        label = lbl
        break

    # first update pending deltas when newer dynamics are available
    if label is not None:
      new_pending = []
      for rec in pending:
        age = t - rec['t']
        if age < 0.08:
          new_pending.append(rec)
          continue
        # use latest dynamics not older than 40ms from current packet time
        if angle_hist and yaw_hist and abs(angle_hist[-1][0] - t) < 0.04 and abs(yaw_hist[-1][0] - t) < 0.04:
          rec['angle_after'] = angle_hist[-1][1]
          rec['yaw_after'] = yaw_hist[-1][1]
          rec['dangle'] = rec['angle_after'] - rec['angle_before']
          rec['dyaw'] = rec['yaw_after'] - rec['yaw_before']
          rows.append(rec)
      pending = new_pending

    for c in m.can:
      d = bytes(c.dat)
      if c.src == 1 and c.address == 51 and len(d) >= 3:
        angle_hist.append((t, int.from_bytes(d[1:3], 'little', signed=True) * 0.1))
        angle_hist = angle_hist[-10:]
      elif c.src == 1 and c.address == 56 and len(d) >= 3:
        yaw_hist.append((t, int.from_bytes(d[1:3], 'little', signed=True) * 0.01))
        yaw_hist = yaw_hist[-10:]
      elif c.src == 0 and c.address == 72:
        last72 = (t, d)
      elif label is not None and c.src == 0 and c.address == 96 and len(d) >= 9:
        if not angle_hist or not yaw_hist or last72 is None:
          continue
        if abs(angle_hist[-1][0] - t) > 0.03 or abs(yaw_hist[-1][0] - t) > 0.03 or abs(last72[0] - t) > 0.03:
          continue
        pending.append({
          'route': name,
          'label': label,
          't': t,
          'phase72': last72[1][0],
          'b96_0': d[0],
          'b96_1': d[1],
          'b96_2': d[2],
          'angle_before': angle_hist[-1][1],
          'yaw_before': yaw_hist[-1][1],
        })

# aggregate by phase where both dirs exist
per_phase = defaultdict(lambda: defaultdict(list))
for r in rows:
  if r['phase72'] != r['b96_0']:
    continue
  per_phase[r['phase72']][r['label']].append(r)

print('rows_with_delta', len(rows))
print('phase conditioned candidates for 96.byte1 vs dynamic delta')
res=[]
for phase in sorted(per_phase):
  left = per_phase[phase]['left']
  right = per_phase[phase]['right']
  if len(left) < 2 or len(right) < 2:
    continue
  for key in ['b96_1', 'dangle', 'dyaw']:
    pass
  res.append((
    phase,
    len(left), len(right),
    round(mean(r['b96_1'] for r in left),3), round(mean(r['b96_1'] for r in right),3),
    round(mean(r['dangle'] for r in left),3), round(mean(r['dangle'] for r in right),3),
    round(mean(r['dyaw'] for r in left),4), round(mean(r['dyaw'] for r in right),4),
    sorted(set(r['b96_1'] for r in left))[:12], sorted(set(r['b96_1'] for r in right))[:12],
  ))
for row in res:
  print(row)
