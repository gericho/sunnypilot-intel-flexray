#!/usr/bin/env python3
from collections import defaultdict
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
}

phase_vals = defaultdict(lambda: defaultdict(list))
flag_vals = defaultdict(lambda: defaultdict(list))

for name, cfg in ROUTES.items():
  start = None
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
      if c.src == 0 and c.address == 72:
        d = bytes(c.dat)
        phase = d[0]
        if phase % 2 == 1:
          phase_vals[phase][label].append(d[2])
          flag_vals[phase][label].append(d[8])

rows = []
for phase in sorted(phase_vals):
  left = phase_vals[phase]['left']
  right = phase_vals[phase]['right']
  if len(left) >= 3 and len(right) >= 3:
    lmean = mean(left)
    rmean = mean(right)
    delta = rmean - lmean
    # overlap test
    overlap = not (min(right) > max(left) or max(right) < min(left))
    rows.append((abs(delta), phase, round(lmean,3), round(rmean,3), round(delta,3), overlap,
                 sorted(set(left)), sorted(set(right)), sorted(set(flag_vals[phase]['left'] + flag_vals[phase]['right']))))

rows.sort(reverse=True)
print('phase map candidates')
for row in rows:
  print(row)
