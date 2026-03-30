#!/usr/bin/env python3
import argparse
import struct
import time
from dataclasses import dataclass
import usb1

CRC8_TABLE = [
  0x00, 0x1D, 0x3A, 0x27, 0x74, 0x69, 0x4E, 0x53, 0xE8, 0xF5, 0xD2, 0xCF, 0x9C, 0x81, 0xA6, 0xBB,
  0xCD, 0xD0, 0xF7, 0xEA, 0xB9, 0xA4, 0x83, 0x9E, 0x25, 0x38, 0x1F, 0x02, 0x51, 0x4C, 0x6B, 0x76,
  0x87, 0x9A, 0xBD, 0xA0, 0xF3, 0xEE, 0xC9, 0xD4, 0x6F, 0x72, 0x55, 0x48, 0x1B, 0x06, 0x21, 0x3C,
  0x4A, 0x57, 0x70, 0x6D, 0x3E, 0x23, 0x04, 0x19, 0xA2, 0xBF, 0x98, 0x85, 0xD6, 0xCB, 0xEC, 0xF1,
  0x13, 0x0E, 0x29, 0x34, 0x67, 0x7A, 0x5D, 0x40, 0xFB, 0xE6, 0xC1, 0xDC, 0x8F, 0x92, 0xB5, 0xA8,
  0xDE, 0xC3, 0xE4, 0xF9, 0xAA, 0xB7, 0x90, 0x8D, 0x36, 0x2B, 0x0C, 0x11, 0x42, 0x5F, 0x78, 0x65,
  0x94, 0x89, 0xAE, 0xB3, 0xE0, 0xFD, 0xDA, 0xC7, 0x7C, 0x61, 0x46, 0x5B, 0x08, 0x15, 0x32, 0x2F,
  0x59, 0x44, 0x63, 0x7E, 0x2D, 0x30, 0x17, 0x0A, 0xB1, 0xAC, 0x8B, 0x96, 0xC5, 0xD8, 0xFF, 0xE2,
  0x26, 0x3B, 0x1C, 0x01, 0x52, 0x4F, 0x68, 0x75, 0xCE, 0xD3, 0xF4, 0xE9, 0xBA, 0xA7, 0x80, 0x9D,
  0xEB, 0xF6, 0xD1, 0xCC, 0x9F, 0x82, 0xA5, 0xB8, 0x03, 0x1E, 0x39, 0x24, 0x77, 0x6A, 0x4D, 0x50,
  0xA1, 0xBC, 0x9B, 0x86, 0xD5, 0xC8, 0xEF, 0xF2, 0x49, 0x54, 0x73, 0x6E, 0x3D, 0x20, 0x07, 0x1A,
  0x6C, 0x71, 0x56, 0x4B, 0x18, 0x05, 0x22, 0x3F, 0x84, 0x99, 0xBE, 0xA3, 0xF0, 0xED, 0xCA, 0xD7,
  0x35, 0x28, 0x0F, 0x12, 0x41, 0x5C, 0x7B, 0x66, 0xDD, 0xC0, 0xE7, 0xFA, 0xA9, 0xB4, 0x93, 0x8E,
  0xF8, 0xE5, 0xC2, 0xDF, 0x8C, 0x91, 0xB6, 0xAB, 0x10, 0x0D, 0x2A, 0x37, 0x64, 0x79, 0x5E, 0x43,
  0xB2, 0xAF, 0x88, 0x95, 0xC6, 0xDB, 0xFC, 0xE1, 0x5A, 0x47, 0x60, 0x7D, 0x2E, 0x33, 0x14, 0x09,
  0x7F, 0x62, 0x45, 0x58, 0x0B, 0x16, 0x31, 0x2C, 0x97, 0x8A, 0xAD, 0xB0, 0xE3, 0xFE, 0xD9, 0xC4,
]
USB_VIDS=(0xBBAA,0x3801)
USB_PIDS=(0xDDEE,0xDDCC)
USB_READ_EP=1
USB_WRITE_EP=3

@dataclass
class RawUsbDevice:
  context: usb1.USBContext
  handle: usb1.USBDeviceHandle
  serial: str
  def close(self):
    try: self.handle.close()
    finally: self.context.close()

@dataclass
class LongState:
  phase54:int=0
  phase59:int=0
  seen53:bool=False
  seen54:bool=False
  seen59:bool=False
  last_rx:float=0.0

def crc8(data: bytes, init_value: int = 0xF1) -> int:
  crc = init_value & 0xFF
  for b in data:
    crc = CRC8_TABLE[crc ^ b]
  return crc

def pack_override(frame_id: int, base: int, dat: bytes) -> bytes:
  payload_len=len(dat)
  out=bytearray([0x90, frame_id & 0xFF, (frame_id>>8) & 0x07, base & 0xFF])
  out.extend(struct.pack('<H', payload_len))
  out.append(crc8(dat[1:]))
  out.extend(dat[1:])
  return bytes(out)

def unpack(buf: bytes):
  out=[]; pos=0; size=len(buf)
  while pos+2<=size:
    body_len=buf[pos] | (buf[pos+1]<<8)
    rec_len=body_len+2
    if body_len < 9 or pos+rec_len>size:
      pos += 1; continue
    rec=buf[pos+2:pos+rec_len]
    hdr=rec[1:6]
    fid=((hdr[0] & 0x07)<<8) | hdr[1]
    payload_words=hdr[2]>>1
    payload_bytes=payload_words*2
    actual=body_len-(1+5+3)
    if actual!=payload_bytes or payload_bytes>254:
      pos += 1; continue
    out.append((fid, bytes(rec[6:6+payload_bytes])))
    pos += rec_len
  return out

def open_dev(serial=''):
  ctx=usb1.USBContext(); ctx.open()
  for d in ctx.getDeviceList(skip_on_error=True):
    if d.getVendorID() in USB_VIDS and d.getProductID() in USB_PIDS:
      s=d.getSerialNumber()
      if serial and s!=serial: continue
      h=d.open(); h.claimInterface(0)
      return RawUsbDevice(ctx,h,s)
  ctx.close(); raise RuntimeError('no picoflex device')

def poll_long_state(dev: RawUsbDevice, st: LongState, timeout_ms=100):
  try:
    raw=bytes(dev.handle.bulkRead(USB_READ_EP, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return st
  now=time.monotonic()
  for fid,payload in unpack(raw):
    if fid==53:
      st.seen53=True; st.last_rx=now
    elif fid==54 and len(payload)>=1:
      st.phase54=payload[0]; st.seen54=True; st.last_rx=now
    elif fid==59 and len(payload)>=1:
      st.phase59=payload[0]; st.seen59=True; st.last_rx=now
  return st

def recv_until_ready(dev: RawUsbDevice, timeout_s=3.0):
  st=LongState(); deadline=time.monotonic()+timeout_s
  while time.monotonic()<deadline:
    st=poll_long_state(dev, st, timeout_ms=150)
    if st.seen53 and st.seen54 and st.seen59:
      return st
  raise TimeoutError('timed out waiting for live 53/54/59')

def send_long_pair(dev: RawUsbDevice, tx54: bytes, tx59: bytes, base: int=0x01):
  pkt54=pack_override(54, base, bytes([base]) + tx54[:9])
  pkt59=pack_override(59, base, bytes([base]) + tx59[:9])
  dev.handle.bulkWrite(USB_WRITE_EP, pkt54+pkt59, timeout=10)

# valid-looking but intentionally inconsistent stock-like families
NEG59 = bytes.fromhex('00d9f95981ff7f2fffffffffffffffffff')
POS59 = bytes.fromhex('3a96f99a7fd37e2fffffffffffffffffff')
NEG54 = bytes.fromhex('0000000000000000000000000000000000')
BLEND54 = bytes.fromhex('3dfc470aff07007efffffffffffffff899')

def main():
  ap=argparse.ArgumentParser(description='BMW i3 direct long pulse tool')
  ap.add_argument('--serial', default='')
  ap.add_argument('--hz', type=float, default=10.0)
  ap.add_argument('--seconds', type=float, default=6.0)
  ap.add_argument('--pattern', choices=['neg_vs_pos','blend_vs_pos'], default='neg_vs_pos')
  ap.add_argument('--run', action='store_true')
  args=ap.parse_args()
  dev=open_dev(args.serial)
  try:
    print('connected picoflex:', dev.serial)
    st=recv_until_ready(dev)
    print(f'live long: phase54={st.phase54} phase59={st.phase59}')
    period=1.0/max(args.hz,1.0)
    steps=max(1,int(args.seconds/period))
    if not args.run:
      print('dry-run only; add --run to transmit')
    start=time.monotonic()
    for i in range(steps):
      st=poll_long_state(dev, st, timeout_ms=0)
      odd = (i % 2) == 1
      if args.pattern=='neg_vs_pos':
        p54 = bytearray(BLEND54 if odd else NEG54)
        p59 = bytearray(POS59 if odd else NEG59)
      else:
        p54 = bytearray(NEG54 if odd else BLEND54)
        p59 = bytearray(POS59)
      p54[0] = st.phase54 & 0xFF
      p59[0] = st.phase59 & 0xFF
      idle = (time.monotonic() - st.last_rx) > 0.7
      print(f'i={i:03d} idle={int(idle)} tx54={bytes(p54[:9]).hex()} tx59={bytes(p59[:9]).hex()}')
      if args.run and not idle:
        send_long_pair(dev, bytes(p54), bytes(p59), base=0x01)
      next_t = start + (i+1)*period
      sleep_s = next_t - time.monotonic()
      if sleep_s > 0: time.sleep(sleep_s)
  finally:
    dev.close()
  return 0

if __name__ == '__main__':
  raise SystemExit(main())
