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

# phase->dir->samples
vals = defaultdict(lambda: defaultdict(list))
vals116 = defaultdict(lambda: defaultdict(list))

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
      if c.src == 1 and c.address == 112:
        phase = c.dat[0]
        vals[phase][label].append(c.dat[1])
      elif c.src == 1 and c.address == 116:
        phase = c.dat[0]
        vals116[phase][label].append(c.dat[1])

# keep phases present in both dirs and both routes implicitly pooled
res=[]
for phase, bydir in vals.items():
  if len(bydir['left']) >= 3 and len(bydir['right']) >= 3:
    lm, rm = mean(bydir['left']), mean(bydir['right'])
    sep = abs(rm-lm)
    consistent = (min(bydir['right']) > max(bydir['left'])) or (max(bydir['right']) < min(bydir['left']))
    res.append(('112', phase, sep, consistent, lm, rm, sorted(set(bydir['left']))[:8], sorted(set(bydir['right']))[:8], len(bydir['left']), len(bydir['right'])))
for phase, bydir in vals116.items():
  if len(bydir['left']) >= 3 and len(bydir['right']) >= 3:
    lm, rm = mean(bydir['left']), mean(bydir['right'])
    sep = abs(rm-lm)
    consistent = (min(bydir['right']) > max(bydir['left'])) or (max(bydir['right']) < min(bydir['left']))
    res.append(('116', phase, sep, consistent, lm, rm, sorted(set(bydir['left']))[:8], sorted(set(bydir['right']))[:8], len(bydir['left']), len(bydir['right'])))

res.sort(key=lambda x: (x[3], x[2]), reverse=True)
for r in res[:40]:
  print(r)
