#!/usr/bin/env python3
from collections import Counter, defaultdict
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

for name, cfg in ROUTES.items():
  # phase -> label -> field -> list
  vals = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
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
      if c.src == 1 and c.address in (112, 116):
        dat = bytes(c.dat)
        phase = dat[0]
        prefix = '112' if c.address == 112 else '116'
        vals[(prefix, phase)][label]['b1'].append(dat[1])
        vals[(prefix, phase)][label]['b2'].append(dat[2])
        vals[(prefix, phase)][label]['wA'].append(int.from_bytes(dat[0:2], 'little'))
        vals[(prefix, phase)][label]['wB'].append(int.from_bytes(dat[2:4], 'little'))

  print(f'## {name}')
  results = []
  for (prefix, phase), by_label in vals.items():
    if 'left' not in by_label or 'right' not in by_label:
      continue
    for field in ('b1', 'b2', 'wA', 'wB'):
      left = by_label['left'][field]
      right = by_label['right'][field]
      if len(left) < 2 or len(right) < 2:
        continue
      delta = mean(right) - mean(left)
      # consistency: if all right > all left or all right < all left
      consistent = int(min(right) > max(left) or max(right) < min(left))
      results.append((abs(delta), consistent, prefix, phase, field, round(mean(left),3), round(mean(right),3), len(left), len(right), sorted(set(left))[:6], sorted(set(right))[:6]))
  results.sort(reverse=True)
  for row in results[:20]:
    print(row)
  print()
