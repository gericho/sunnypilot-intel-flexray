#!/usr/bin/env python3
from collections import Counter, defaultdict
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'b3': ('/home/gericho/.comma/media/0/realdata/000000b3--bc708b46e1--0/rlog.zst', [
    ('MANUAL_ACCEL', 6, 12), ('ACC_BASE', 12, 24), ('MANAGED', 24, 40), ('AUTO_BRAKE_LIGHT', 92, 98),
  ]),
  'e9': ('/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst', [
    ('ACC_BASE', 11, 22), ('MANAGED', 22, 44), ('AUTO_BRAKE_HEAVY', 44, 56), ('MANAGED2', 61, 72),
  ]),
  '55': ('/home/gericho/.comma/media/0/realdata/00000055--24e188a5e5--0/rlog.zst', [
    ('ACC_BASE', 12, 15), ('MANAGED', 15, 76), ('AUTO_BRAKE_HEAVY', 76, 81),
  ]),
  'eb': ('/home/gericho/.comma/media/0/realdata/000000eb--41f9ac2c70--0/rlog.zst', [
    ('ACC_BASE', 13, 21), ('MANAGED', 21, 46), ('ACC_ONLY', 46, 58), ('MANAGED2', 58, 95),
  ]),
}

rows = []
for name, (fn, wins) in ROUTES.items():
  start = None
  latest = {}
  for m in LogReader(fn):
    if start is None:
      start = m.logMonoTime
    t = (m.logMonoTime - start) / 1e9
    if m.which() != 'can':
      continue
    label = None
    for lbl, a, b in wins:
      if a <= t < b:
        label = lbl
        break
    if label is None:
      continue
    for c in m.can:
      d = bytes(c.dat)
      if c.src == 1 and c.address in (54, 59):
        latest[f'1/{c.address}'] = (t, d)
      elif c.src == 0 and c.address in (131, 135):
        latest[f'0/{c.address}'] = (t, d)
    if all(k in latest for k in ('1/54','1/59','0/131','0/135')):
      if max(abs(latest[k][0]-t) for k in latest) < 0.03:
        d54 = latest['1/54'][1]
        d59 = latest['1/59'][1]
        d131 = latest['0/131'][1]
        d135 = latest['0/135'][1]
        rows.append({
          'route': name,
          'label': label,
          'gate': int.from_bytes(d131[5:7], 'little'),
          'state': int.from_bytes(d135[5:7], 'little'),
          '59_wB': int.from_bytes(d59[3:5], 'little'),
          '59_wC': int.from_bytes(d59[5:7], 'little'),
          '59_b3': d59[3],
          '59_b5': d59[5],
          '54_wB': int.from_bytes(d54[3:5], 'little'),
          '54_wC': int.from_bytes(d54[5:7], 'little'),
          '54_b4': d54[4],
          '54_b6': d54[6],
        })

print('rows', len(rows))
print('\n## by label')
for label in sorted(set(r['label'] for r in rows)):
  sub = [r for r in rows if r['label'] == label]
  print('\n#', label, 'n', len(sub))
  for key in ['gate','state','59_wB','59_wC','59_b3','59_b5','54_wB','54_wC','54_b4','54_b6']:
    vals = [r[key] for r in sub]
    print(key, 'mean', round(mean(vals),3), 'uniq', sorted(set(vals))[:16])

print('\n## coarse monotonic checks')
for a,b in [('ACC_BASE','MANAGED'),('MANAGED','AUTO_BRAKE_HEAVY'),('ACC_BASE','ACC_ONLY'),('ACC_ONLY','MANAGED2')]:
  A=[r for r in rows if r['label']==a]
  B=[r for r in rows if r['label']==b]
  if not A or not B:
    continue
  print('\n',a,'->',b)
  for key in ['59_wB','59_wC','59_b3','59_b5','54_wB','54_wC','54_b4','54_b6']:
    print(key, round(mean(r[key] for r in A),3), '->', round(mean(r[key] for r in B),3))
