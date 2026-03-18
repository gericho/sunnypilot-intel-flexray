#!/usr/bin/env python3
from collections import defaultdict, Counter
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
  'eb': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000eb--41f9ac2c70--0/rlog.zst',
    'windows': [('right', 41, 42), ('left', 43, 44), ('left', 86, 87)],
  },
}

rows = []
for name, cfg in ROUTES.items():
  start = None
  angle = None
  yaw = None
  last72 = None
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
    for c in m.can:
      d = bytes(c.dat)
      if c.src == 1 and c.address == 51 and len(d) >= 3:
        angle = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.1)
      elif c.src == 1 and c.address == 56 and len(d) >= 3:
        yaw = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.01)
      elif c.src == 0 and c.address == 72:
        last72 = (t, d)
      elif label is not None and c.src == 0 and c.address == 96 and len(d) >= 9 and angle and yaw and last72:
        if abs(angle[0] - t) > 0.03 or abs(yaw[0] - t) > 0.03 or abs(last72[0] - t) > 0.03:
          continue
        rows.append({
          'route': name,
          'label': label,
          'phase72': last72[1][0],
          'phase96': d[0],
          'b1': d[1],
          'b2': d[2],
          'angle': angle[1],
          'yaw': yaw[1],
          'raw96': d.hex(),
        })

print('rows', len(rows))

by_phase = defaultdict(list)
for r in rows:
  if r['phase72'] == r['phase96']:
    by_phase[r['phase96']].append(r)

print('\n## per-phase byte1 distributions')
for phase in sorted(by_phase):
  vals = [r['b1'] for r in by_phase[phase]]
  if len(vals) < 2:
    continue
  print('phase', phase, 'n', len(vals), 'mean', round(mean(vals), 3), 'uniq', sorted(set(vals)),
        'dirs', Counter(r['label'] for r in by_phase[phase]),
        'angle_mean', round(mean(r['angle'] for r in by_phase[phase]), 3),
        'yaw_mean', round(mean(r['yaw'] for r in by_phase[phase]), 3))

print('\n## per-phase per-dir byte1')
for phase in sorted(by_phase):
  left = [r['b1'] for r in by_phase[phase] if r['label'] == 'left']
  right = [r['b1'] for r in by_phase[phase] if r['label'] == 'right']
  if left and right:
    print('phase', phase,
          'L', len(left), round(mean(left),3), sorted(set(left)),
          'R', len(right), round(mean(right),3), sorted(set(right)))

print('\n## repeated exact 96 payloads')
for raw, n in Counter(r['raw96'] for r in rows).most_common(50):
  if n > 1:
    print(n, raw)
