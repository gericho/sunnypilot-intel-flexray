#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable

from tools.lib.logreader import LogReader


@dataclass(frozen=True)
class Window:
  route: str
  path: str
  src: int
  addr: int
  start_s: float
  end_s: float
  label: str


WINDOWS = [
  Window('lat_176', '/home/gericho/.comma/media/0/realdata/00000176--3a6e928ca3--0/rlog.zst', 0, 72, 7.0, 47.0, 'managed_lat'),
  Window('lat_176', '/home/gericho/.comma/media/0/realdata/00000176--3a6e928ca3--0/rlog.zst', 0, 96, 7.0, 47.0, 'managed_lat'),
  Window('long_147', '/home/gericho/.comma/media/0/realdata/00000147--1294d32c66--0/rlog.zst', 1, 54, 16.0, 72.0, 'managed_long'),
  Window('long_147', '/home/gericho/.comma/media/0/realdata/00000147--1294d32c66--0/rlog.zst', 1, 59, 16.0, 72.0, 'managed_long'),
]


def iter_window_bytes(win: Window) -> list[bytes]:
  out: list[bytes] = []
  start = None
  for m in LogReader(win.path):
    if start is None:
      start = m.logMonoTime
    t = (m.logMonoTime - start) / 1e9
    if t < win.start_s or t >= win.end_s or m.which() != 'can':
      continue
    for c in m.can:
      if c.src == win.src and c.address == win.addr:
        out.append(bytes(c.dat))
  if len(out) > 2048:
    step = max(len(out) // 2048, 1)
    out = out[::step][:2048]
  return out


def crc8(data: bytes, poly: int, init: int = 0x00, xorout: int = 0x00) -> int:
  crc = init
  for b in data:
    crc ^= b
    for _ in range(8):
      crc = ((crc << 1) ^ poly) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
  return crc ^ xorout


CRC_VARIANTS = {
  'crc8_07': lambda d: crc8(d, 0x07),
  'crc8_1d': lambda d: crc8(d, 0x1D),
  'crc8_2f': lambda d: crc8(d, 0x2F),
  'crc8_31': lambda d: crc8(d, 0x31),
  'crc8_9b': lambda d: crc8(d, 0x9B),
  'crc8_d5': lambda d: crc8(d, 0xD5),
  'sum8': lambda d: sum(d) & 0xFF,
  'sum8_inv': lambda d: (-sum(d)) & 0xFF,
  'xor8': lambda d: _xor(d),
  'nibble_sum': lambda d: sum(((b >> 4) + (b & 0xF)) for b in d) & 0xFF,
}


def _xor(data: bytes) -> int:
  x = 0
  for b in data:
    x ^= b
  return x


def score_byte_formula(frames: list[bytes], idx: int, fn: Callable[[bytes], int]) -> float:
  good = 0
  for d in frames:
    payload = d[:idx] + d[idx + 1:]
    if fn(payload) == d[idx]:
      good += 1
  return good / max(len(frames), 1)


def main() -> None:
  for win in WINDOWS:
    frames = iter_window_bytes(win)
    print(f'## {win.route}:{win.src}/{win.addr}:{win.label} n={len(frames)}')
    if not frames:
      continue
    nbytes = len(frames[0])
    best = []
    for idx in range(nbytes):
      for name, fn in CRC_VARIANTS.items():
        s = score_byte_formula(frames, idx, fn)
        if s >= 0.60:
          best.append((s, idx, name))
    best.sort(reverse=True)
    if not best:
      print('no_simple_checksum_match_above_0.60')
    else:
      for s, idx, name in best[:20]:
        print(f'byte={idx} formula={name} score={s:0.3f}')
    print()


if __name__ == '__main__':
  main()
