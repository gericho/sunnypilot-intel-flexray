#!/usr/bin/env python3
from collections import Counter
from opendbc.can import CANPacker
from tools.lib.logreader import LogReader

fn='/home/gericho/.comma/media/0/realdata/000000e9--f69facea42--0/rlog.zst'
packer = CANPacker('bmw_sp2018')

observed=[]
start=None
for m in LogReader(fn):
  if start is None: start=m.logMonoTime
  t=(m.logMonoTime-start)/1e9
  if not (22 <= t < 30):
    continue
  if m.which()!='can':
    continue
  for c in m.can:
    if c.src==0 and c.address==72:
      d=bytes(c.dat)
      if d[0] % 2 == 1:
        observed.append(d)

print('observed odd count', len(observed))
print('observed top', Counter(d.hex() for d in observed).most_common(20))

# synthesize ACC m1 payloads with varying angle around plausible values
vals_base = {
  'cycle_count': 1,
  'crc1': 0,
  'cnt1': 0,
  'always_0x9': 9,
  'steering_angle_req': 0.0,
  'steer_torque_req': 0.0,
  'TJA_ready': 0,
  'assist_mode': 1,
  'wayback_en1_lane_keeping_trigger': 0,
  'lane_keeping_triggered': 0,
  'like_assist_torque_reserve': 0xA0,
  'constants': 0x03ff17fe,
  'wayback_en_2': 0,
  'steering_engaged': 2,
  'maybe_assist_force_enhance': 0xA2,
  'maybe_assist_force_weaken': 0xFA,
}

synthetic=[]
for cnt in range(16):
  for angle in [-10,-5,-2,-1,0,1,2,5,10]:
    vals = dict(vals_base)
    vals['cnt1']=cnt
    vals['steering_angle_req']=float(angle)
    msg = packer.make_can_msg('ACC', 4, vals)
    synthetic.append(bytes(msg[2]))

print('synthetic sample')
for d in synthetic[:20]:
  print(d.hex())

# compare per-byte uniqueness to see if log matches DBC field layout at all
print('\nobserved byte positions')
for i in range(len(observed[0])):
  print(i, sorted(set(d[i] for d in observed))[:20])
print('\nsynthetic byte positions')
for i in range(len(synthetic[0])):
  print(i, sorted(set(d[i] for d in synthetic))[:20])
