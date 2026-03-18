#!/usr/bin/env python3
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'b3': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000b3--bc708b46e1--0/rlog.zst',
    'windows': [('MANUAL_ACCEL', 6, 12), ('ACC_BASE', 12, 24), ('MANAGED', 24, 40), ('AUTO_BRAKE_LIGHT', 92, 98)],
  },
  'e9': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
    'windows': [('ACC_BASE', 11, 22), ('MANAGED', 22, 44), ('AUTO_BRAKE_HEAVY', 44, 56), ('MANAGED2', 61, 72)],
  },
  '55': {
    'fn': '/home/gericho/.comma/media/0/realdata/00000055--24e188a5e5--0/rlog.zst',
    'windows': [('ACC_BASE', 12, 15), ('MANAGED', 15, 76), ('AUTO_BRAKE_HEAVY', 76, 81)],
  },
}

# crude signed proxy: normalize 59 as propulsion intent, subtract weighted 54 brake-blend branch
vals = {lbl: [] for lbl in ['MANUAL_ACCEL','ACC_BASE','MANAGED','MANAGED2','AUTO_BRAKE_LIGHT','AUTO_BRAKE_HEAVY']}
for name,cfg in ROUTES.items():
  start=None
  latest={}
  for m in LogReader(cfg['fn']):
    if start is None: start=m.logMonoTime
    t=(m.logMonoTime-start)/1e9
    if m.which()!='can': continue
    label=None
    for n,a,b in cfg['windows']:
      if a<=t<b: label=n; break
    if label is None: continue
    for c in m.can:
      d=bytes(c.dat)
      if c.src==1 and c.address==59 and len(d)>=7:
        latest['59']=(t,d)
      elif c.src==1 and c.address==54 and len(d)>=7:
        latest['54']=(t,d)
      elif c.src==0 and c.address==135 and len(d)>=7:
        latest['135']=(t,d)
    if all(k in latest for k in ['59','54','135']):
      if max(abs(latest[k][0]-t) for k in latest) < 0.03:
        d59=latest['59'][1]; d54=latest['54'][1]; d135=latest['135'][1]
        state = int.from_bytes(d135[5:7],'little')
        w59b = int.from_bytes(d59[3:5],'little')
        w59c = int.from_bytes(d59[5:7],'little')
        w54b = int.from_bytes(d54[3:5],'little')
        w54c = int.from_bytes(d54[5:7],'little')
        # phase-agnostic coarse scalar only for analysis
        propulsion = (w59b - 32768) + 0.5*(w59c - 32768)
        braking = (w54b - 16384) + 0.7*(w54c - 8192)
        proxy = propulsion - braking
        vals[label].append((proxy, state))

for lbl, arr in vals.items():
  if not arr: continue
  print(lbl, 'n', len(arr), 'proxy_mean', round(mean(p for p,_ in arr),3), 'state_modes', sorted(set(s for _,s in arr))[:10])
