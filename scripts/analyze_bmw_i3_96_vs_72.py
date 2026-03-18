#!/usr/bin/env python3
from collections import defaultdict, Counter
from statistics import mean
from tools.lib.logreader import LogReader

ROUTES = {
  'e9': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst',
    'windows': [('right', 25, 28), ('left', 29, 34), ('right', 40, 44), ('right', 66, 67), ('left', 69, 70)],
  },
  'ea': {
    'fn': '/home/gericho/.comma/media/0/realdata/000000ea--291dc1d088--0/rlog.zst',
    'windows': [('right', 37, 41), ('left', 59, 60), ('right', 66, 67), ('left', 69, 70), ('right', 73, 74), ('left', 77, 78), ('right', 101, 106)],
  },
}

rows=[]
by72=defaultdict(lambda: defaultdict(list))
for name,cfg in ROUTES.items():
  start=None
  last72=None
  angle=None
  yaw=None
  for m in LogReader(cfg['fn']):
    if start is None: start=m.logMonoTime
    t=(m.logMonoTime-start)/1e9
    if m.which()!='can': continue
    label=None
    for lbl,a,b in cfg['windows']:
      if a<=t<b: label=lbl; break
    if label is None: continue
    for c in m.can:
      d=bytes(c.dat)
      if c.src==1 and c.address==51 and len(d)>=3:
        angle=(t, int.from_bytes(d[1:3],'little',signed=True)*0.1)
      elif c.src==1 and c.address==56 and len(d)>=3:
        yaw=(t, int.from_bytes(d[1:3],'little',signed=True)*0.01)
      elif c.src==0 and c.address==72:
        last72=(t,d)
      elif c.src==0 and c.address==96 and len(d)>=9 and last72 is not None and angle and yaw:
        if abs(last72[0]-t)>0.03 or abs(angle[0]-t)>0.03 or abs(yaw[0]-t)>0.03:
          continue
        d72=last72[1]
        row=(name,label,d72[0],d72[2],d72[8],d[0],d[1],d[2],d[3],d[4],d[8],angle[1],yaw[1],d.hex(),d72.hex())
        rows.append(row)
        by72[d72[0]][label].append(row)

print('rows',len(rows))
print('top mappings 72phase -> 96b0')
mapc=Counter((r[2],r[5]) for r in rows)
for k,v in mapc.most_common(80):
  print(k,v)

print('\n72 phase candidates with both left/right')
for p in sorted(by72):
  l=by72[p]['left']
  r=by72[p]['right']
  if len(l)>=3 and len(r)>=3:
    print('\nphase72',p,'left',len(l),'right',len(r))
    for idx,name in [(5,'96b0'),(6,'96b1'),(7,'96b2'),(8,'96b3'),(9,'96b4'),(10,'96b8')]:
      lv=[x[idx] for x in l]; rv=[x[idx] for x in r]
      print(name,'lm',round(mean(lv),3),'rm',round(mean(rv),3),'luniq',sorted(set(lv))[:10],'runiq',sorted(set(rv))[:10])
    print('angle', round(mean(x[11] for x in l),2), round(mean(x[11] for x in r),2), 'yaw', round(mean(x[12] for x in l),3), round(mean(x[12] for x in r),3))
    print('rawL', Counter(x[13] for x in l).most_common(6))
    print('rawR', Counter(x[13] for x in r).most_common(6))
