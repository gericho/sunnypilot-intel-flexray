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
  vals = defaultdict(Counter)
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
        vals[(label,'112_b0')].update([c.dat[0]])
        vals[(label,'112_b1')].update([c.dat[1]])
        vals[(label,'112_b2')].update([c.dat[2]])
        vals[(label,'112_b5')].update([c.dat[5]])
        vals[(label,'112_wA')].update([int.from_bytes(c.dat[0:2],'little')])
        vals[(label,'112_wB')].update([int.from_bytes(c.dat[2:4],'little')])
      elif c.src == 1 and c.address == 116:
        vals[(label,'116_b0')].update([c.dat[0]])
        vals[(label,'116_b1')].update([c.dat[1]])
        vals[(label,'116_b2')].update([c.dat[2]])
        vals[(label,'116_b5')].update([c.dat[5]])
        vals[(label,'116_wA')].update([int.from_bytes(c.dat[0:2],'little')])
        vals[(label,'116_wB')].update([int.from_bytes(c.dat[2:4],'little')])
  print('##', name)
  for field in ['112_b0','112_b1','112_b2','112_b5','112_wA','112_wB','116_b0','116_b1','116_b2','116_b5','116_wA','116_wB']:
    l = vals.get(('left', field), Counter())
    r = vals.get(('right', field), Counter())
    if not l or not r:
      continue
    lm = mean([k for k,v in l.items() for _ in range(v)])
    rm = mean([k for k,v in r.items() for _ in range(v)])
    print(field, 'left', l.most_common(6), 'right', r.most_common(6), 'delta_mean', round(rm-lm,3))
  print()
