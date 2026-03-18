#!/usr/bin/env python3
from collections import defaultdict, Counter
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

CANDS = [72, 96, 216]

# nearest-neighbor sync over raw timestamps inside labeled windows
samples = defaultdict(lambda: defaultdict(list))

for name, cfg in ROUTES.items():
  start = None
  latest = {
    'angle': None,  # src1/51 byte1..2 signed little *0.1
    'yaw': None,    # src1/56 byte1..2 signed little *0.01
    'cand': {},
  }
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
        ang_raw = int.from_bytes(d[1:3], 'little', signed=True)
        latest['angle'] = (t, ang_raw * 0.1)
      elif c.src == 1 and c.address == 56 and len(d) >= 3:
        yaw_raw = int.from_bytes(d[1:3], 'little', signed=True)
        latest['yaw'] = (t, yaw_raw * 0.01)
      elif c.src == 0 and c.address in CANDS:
        latest['cand'][c.address] = (t, d)
        if latest['angle'] is None or latest['yaw'] is None:
          continue
        if abs(latest['angle'][0] - t) > 0.03 or abs(latest['yaw'][0] - t) > 0.03:
          continue
        row = {
          'route': name,
          't': round(t, 3),
          'label': label,
          'angle': latest['angle'][1],
          'yaw': latest['yaw'][1],
          'raw': d.hex(),
        }
        if c.address == 72:
          row.update({
            'phase': d[0],
            'b1': d[1],
            'b2': d[2],
            'b8': d[8] if len(d) > 8 else None,
            'odd': d[0] % 2,
          })
        elif c.address == 96:
          row.update({
            'b0': d[0], 'b1': d[1], 'b2': d[2], 'b3': d[3], 'b4': d[4], 'b8': d[8] if len(d)>8 else None,
          })
        elif c.address == 216:
          row.update({
            'b0': d[0], 'b1': d[1], 'b2': d[2], 'b3': d[3], 'b4': d[4], 'b5': d[5], 'b6': d[6], 'b7': d[7], 'b8': d[8] if len(d)>8 else None,
          })
        samples[c.address][label].append(row)

print('### aggregate by candidate and label')
for addr in CANDS:
  print(f'\n## addr {addr}')
  for label in ('left', 'right'):
    rows = samples[addr][label]
    if not rows:
      continue
    print(label, 'n', len(rows), 'angle_mean', round(mean(r['angle'] for r in rows), 3), 'yaw_mean', round(mean(r['yaw'] for r in rows), 3))
    keys = [k for k in rows[0].keys() if k.startswith('b') or k == 'phase' or k == 'odd']
    for k in keys:
      vals = [r[k] for r in rows if r.get(k) is not None]
      if not vals:
        continue
      uniq = sorted(set(vals))
      print(' ', k, 'mean', round(mean(vals), 3), 'uniq', uniq[:20])

print('\n### top exact raws by candidate and label')
for addr in CANDS:
  print(f'\n## addr {addr}')
  for label in ('left', 'right'):
    c = Counter(r['raw'] for r in samples[addr][label])
    print(label, c.most_common(12))
