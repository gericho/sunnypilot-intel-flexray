#!/usr/bin/env python3
from collections import defaultdict, Counter
from tools.lib.logreader import LogReader

fn='/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst'
start=None
# focus on TJA2 window where lane keep is clearly active
win=(34,62)
per_phase=defaultdict(Counter)
for m in LogReader(fn):
  if start is None: start=m.logMonoTime
  t=(m.logMonoTime-start)/1e9
  if not (win[0] <= t < win[1]):
    continue
  if m.which()!='can': continue
  for c in m.can:
    if c.src==0 and c.address==72:
      d=bytes(c.dat)
      if d[0] % 2 == 1:
        per_phase[d[0]].update([d.hex()])

for phase in sorted(per_phase):
  print('\nphase', phase)
  top=per_phase[phase].most_common(12)
  for raw,n in top:
    bs=bytes.fromhex(raw)
    print(n, raw, 'b1', bs[1], 'b2', bs[2], 'b8', bs[8], 'tail', raw[6:18])
