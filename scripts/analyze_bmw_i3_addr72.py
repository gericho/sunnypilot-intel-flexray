#!/usr/bin/env python3
from collections import Counter, defaultdict
from tools.lib.logreader import LogReader

ROUTES = {
  'e9': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
  'ea': '/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst',
}
WINS = {
  'e9': [('ACC',11,22),('TJA1',22,44),('ACC2',44,61),('TJA2',61,72)],
  'ea': [('START_TJA',0,7),('ACC1',11,34),('TJA2',34,62),('ACC2',62,70),('OFF2',70,72.2)],
}

def get_le(dat, start, size):
  x = int.from_bytes(dat, 'little')
  return (x >> start) & ((1 << size) - 1)

for name, fn in ROUTES.items():
  print('##', name)
  start = None
  vals = {wn: defaultdict(Counter) for wn,_,_ in WINS[name]}
  for m in LogReader(fn):
    if start is None:
      start = m.logMonoTime
    t = (m.logMonoTime - start) / 1e9
    if m.which() != 'can':
      continue
    win = None
    for wn,a,b in WINS[name]:
      if a <= t < b:
        win = wn
        break
    if win is None:
      continue
    for c in m.can:
      if c.src == 0 and c.address == 72:
        d = bytes(c.dat)
        vals[win]['raw'].update([d.hex()])
        vals[win]['b0'].update([d[0]])
        vals[win]['cycle'].update([get_le(d,1,2)])
        vals[win]['crc1'].update([get_le(d,8,8)])
        vals[win]['cnt1'].update([get_le(d,16,4)])
        vals[win]['const9'].update([get_le(d,20,4)])
        vals[win]['angle_req_raw'].update([get_le(d,24,16)])
        vals[win]['torque_req_raw'].update([get_le(d,40,16)])
        vals[win]['tja_ready'].update([get_le(d,56,8)])
        vals[win]['assist_mode'].update([get_le(d,64,2)])
        vals[win]['lane_trig'].update([get_le(d,72,8)])
        vals[win]['reserve'].update([get_le(d,80,8)])
  for wn,_,_ in WINS[name]:
    print('\n#', wn)
    for k in ['cycle','cnt1','const9','angle_req_raw','torque_req_raw','tja_ready','assist_mode','lane_trig','reserve']:
      print(k, vals[wn][k].most_common(10))
