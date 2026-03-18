#!/usr/bin/env python3
from collections import defaultdict
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'e9': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
    'windows': [
      ('right', 25, 28), ('left', 29, 34), ('right', 40, 44), ('right', 66, 67), ('left', 69, 70),
    ],
  },
  'ea': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst',
    'windows': [
      ('right', 37, 41), ('left', 59, 60), ('right', 66, 67), ('left', 69, 70), ('right', 73, 74), ('left', 77, 78), ('right', 101, 106),
    ],
  },
}

# sync by nearest latest angle/yaw within 30ms
phase_rows = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # phase -> byte -> dir -> vals
phase_dyn = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))   # phase -> key -> dir -> vals
phase_raw = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

for name, cfg in ROUTES.items():
  start = None
  angle = None
  yaw = None
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
    if label is None:
      continue
    for c in m.can:
      d = bytes(c.dat)
      if c.src == 1 and c.address == 51 and len(d) >= 3:
        angle = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.1)
      elif c.src == 1 and c.address == 56 and len(d) >= 3:
        yaw = (t, int.from_bytes(d[1:3], 'little', signed=True) * 0.01)
      elif c.src == 0 and c.address == 96 and len(d) >= 9:
        if angle is None or yaw is None:
          continue
        if abs(angle[0] - t) > 0.03 or abs(yaw[0] - t) > 0.03:
          continue
        phase = d[0]
        for idx in [1,2,3,4,8]:
          phase_rows[phase][idx][label].append(d[idx])
        phase_dyn[phase]['angle'][label].append(angle[1])
        phase_dyn[phase]['yaw'][label].append(yaw[1])
        phase_raw[phase]['raw'][label].append(d.hex())

res=[]
for phase in sorted(phase_rows):
  if len(phase_dyn[phase]['angle']['left']) < 3 or len(phase_dyn[phase]['angle']['right']) < 3:
    continue
  for idx in [1,2,3,4,8]:
    left = phase_rows[phase][idx]['left']
    right = phase_rows[phase][idx]['right']
    if len(left) < 3 or len(right) < 3:
      continue
    lm, rm = mean(left), mean(right)
    sep = abs(rm - lm)
    overlap = not (min(right) > max(left) or max(right) < min(left))
    res.append((sep, phase, idx, round(lm,3), round(rm,3), overlap, sorted(set(left))[:20], sorted(set(right))[:20], len(left), len(right), round(mean(phase_dyn[phase]['angle']['left']),2), round(mean(phase_dyn[phase]['angle']['right']),2), round(mean(phase_dyn[phase]['yaw']['left']),3), round(mean(phase_dyn[phase]['yaw']['right']),3)))

res.sort(reverse=True)
print('top byte/phase candidates for addr96')
for r in res[:80]:
  print(r)

print('\nphase raw examples')
for phase in sorted(phase_raw):
  l = phase_raw[phase]['raw']['left']
  r = phase_raw[phase]['raw']['right']
  if len(l) >= 3 and len(r) >= 3:
    print('phase', phase, 'left', sorted(set(l))[:8], 'right', sorted(set(r))[:8])
