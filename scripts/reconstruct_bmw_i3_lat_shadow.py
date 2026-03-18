#!/usr/bin/env python3
from collections import Counter, defaultdict
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'e9': ('/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst', [
    ('right', 25, 28), ('left', 29, 34), ('right', 40, 44), ('right', 66, 67), ('left', 69, 70),
  ]),
  'ea': ('/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst', [
    ('right', 37, 41), ('left', 59, 60), ('right', 66, 67), ('left', 69, 70), ('right', 73, 74), ('left', 77, 78), ('right', 101, 106),
  ]),
  'eb': ('/home/gericho/.comma/media/0/realdata/000000eb--41f9ac2c70--0/rlog.zst', [
    ('right', 41, 42), ('left', 43, 44), ('left', 86, 87),
  ]),
}

pairs = []
for name, (fn, wins) in ROUTES.items():
  start = None
  last72 = None
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
    for c in m.can:
      d = bytes(c.dat)
      if c.src == 0 and c.address == 72:
        last72 = (t, d)
      elif label is not None and c.src == 0 and c.address == 96 and last72 is not None:
        if abs(last72[0] - t) > 0.03:
          continue
        d72 = last72[1]
        pairs.append({
          'route': name,
          'label': label,
          'phase': d72[0],
          'odd': d72[0] & 1,
          'd72': d72,
          'd96': d,
        })

print('pairs', len(pairs))

# Global structural checks
print('\n## structure')
print('phase match count', sum(1 for p in pairs if p['phase'] == p['d96'][0]), '/', len(pairs))
print('72 odd only payload mean b1/b2/b8', round(mean(p['d72'][1] for p in pairs),3), round(mean(p['d72'][2] for p in pairs),3), round(mean(p['d72'][8] for p in pairs),3))
print('96 const bytes')
for idx in [3,4,8]:
  print('b', idx, Counter(p['d96'][idx] for p in pairs).most_common(10))

# Phase-conditioned summary for candidate payload byte
print('\n## phase-conditioned 96.byte1')
by_phase = defaultdict(lambda: defaultdict(list))
for p in pairs:
  by_phase[p['phase']][p['label']].append(p['d96'][1])
for phase in sorted(by_phase):
  left = by_phase[phase]['left']
  right = by_phase[phase]['right']
  if left or right:
    out = [f'phase {phase}']
    if left:
      out.append(f"L n={len(left)} mean={mean(left):.3f} uniq={sorted(set(left))[:8]}")
    if right:
      out.append(f"R n={len(right)} mean={mean(right):.3f} uniq={sorted(set(right))[:8]}")
    print(' | '.join(out))

# Exact raw pair motifs
print('\n## top raw pair motifs')
raw_pair = Counter((p['label'], p['d72'].hex(), p['d96'].hex()) for p in pairs)
for row, n in raw_pair.most_common(40):
  print(n, row)
