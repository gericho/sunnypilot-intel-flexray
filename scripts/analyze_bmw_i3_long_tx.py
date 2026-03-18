#!/usr/bin/env python3
from collections import defaultdict, Counter
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'b3': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000b3--bc708b46e1--0/rlog.zst',
    'windows': [
      ('OFF', 0, 6),
      ('MANUAL_ACCEL', 6, 12),
      ('ACC_BASE', 12, 24),
      ('MANAGED1', 24, 40),
      ('MANAGED2', 88, 100),
      ('AUTO_BRAKE_LIGHT', 92, 98),
      ('OFF2', 100, 118),
    ],
  },
  'e9': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
    'windows': [
      ('MANUAL', 0, 11),
      ('ACC_BASE', 11, 22),
      ('TJA_MANAGED', 22, 44),
      ('AUTO_BRAKE_HEAVY', 44, 56),
      ('ACC_BASE2', 56, 61),
      ('TJA_MANAGED2', 61, 72),
    ],
  },
  '55': {
    'fn': '/home/gericho/.comma/media/0/realdata/00000055--24e188a5e5--0/rlog.zst',
    'windows': [
      ('MANUAL', 0, 12),
      ('ACC_BASE', 12, 15),
      ('TJA_MANAGED', 15, 76),
      ('AUTO_BRAKE_HEAVY', 76, 81),
      ('OFF', 85, 95),
    ],
  },
}

TARGETS = [54, 59, 131, 135]

agg = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
raws = defaultdict(lambda: defaultdict(Counter))

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
      if c.address not in TARGETS:
        continue
      d = bytes(c.dat)
      src = c.src
      key = f'{src}/{c.address}'
      raws[key][label].update([d.hex()])
      for i, b in enumerate(d):
        agg[key][f'b{i}'][label].append(b)
      if len(d) >= 6:
        agg[key]['wA'][label].append(int.from_bytes(d[1:3], 'little', signed=False))
        agg[key]['wB'][label].append(int.from_bytes(d[3:5], 'little', signed=False))
        agg[key]['wC'][label].append(int.from_bytes(d[5:7], 'little', signed=False))

# focus on 1/54 and 1/59 primarily
for key in ['1/54', '1/59', '0/131', '0/135']:
  print(f'## {key}')
  if key not in agg:
    print('missing')
    continue
  labels = sorted({lbl for metric in agg[key].values() for lbl in metric.keys()})
  for label in labels:
    print('\n#', label)
    for metric in sorted(agg[key].keys()):
      vals = agg[key][metric].get(label, [])
      if not vals:
        continue
      uniq = sorted(set(vals))
      if metric.startswith('b') or metric.startswith('w'):
        print(metric, 'mean', round(mean(vals), 3), 'uniq', uniq[:16])
    print('raw', raws[key][label].most_common(8))
  print()

print('### discriminators for 1/54 and 1/59')
comparisons = [
  ('1/59', 'ACC_BASE', 'TJA_MANAGED'),
  ('1/59', 'TJA_MANAGED', 'AUTO_BRAKE_HEAVY'),
  ('1/54', 'ACC_BASE', 'TJA_MANAGED'),
  ('1/54', 'TJA_MANAGED', 'AUTO_BRAKE_HEAVY'),
]
for key, a, b in comparisons:
  if key not in agg:
    continue
  print('\n', key, a, 'vs', b)
  rows = []
  for metric, bylab in agg[key].items():
    va, vb = bylab.get(a, []), bylab.get(b, [])
    if len(va) >= 3 and len(vb) >= 3:
      rows.append((abs(mean(vb) - mean(va)), metric, round(mean(va), 3), round(mean(vb), 3), sorted(set(va))[:10], sorted(set(vb))[:10]))
  rows.sort(reverse=True)
  for row in rows[:15]:
    print(row)
