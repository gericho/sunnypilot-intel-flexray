#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

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
  Window('long_148', '/home/gericho/.comma/media/0/realdata/00000148--ddcfbc9103--0/rlog.zst', 1, 54, 30.0, 72.0, 'managed_long'),
  Window('long_148', '/home/gericho/.comma/media/0/realdata/00000148--ddcfbc9103--0/rlog.zst', 1, 59, 30.0, 72.0, 'managed_long'),
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
  return out


def nibble_series(frames: list[bytes], byte_idx: int, hi: bool) -> list[int]:
  vals = []
  for d in frames:
    b = d[byte_idx]
    vals.append((b >> 4) & 0xF if hi else b & 0xF)
  return vals


def step_score(vals: list[int], mod: int) -> float:
  if len(vals) < 2:
    return 0.0
  good = 0
  total = 0
  for a, b in zip(vals, vals[1:]):
    da = (b - a) % mod
    if da in (0, 1, mod - 1):
      good += 1
    total += 1
  return good / max(total, 1)


def summarize(frames: list[bytes], key: str) -> None:
  print(f'## {key} n={len(frames)} len={len(frames[0]) if frames else 0}')
  if not frames:
    return
  nbytes = len(frames[0])
  per_idx = list(zip(*frames))
  for i, vals in enumerate(per_idx):
    ctr = Counter(vals)
    uniq = len(ctr)
    dom_v, dom_n = ctr.most_common(1)[0]
    dom_ratio = dom_n / len(vals)
    full_step = step_score(list(vals), 256)
    lo_step = step_score(nibble_series(frames, i, False), 16)
    hi_step = step_score(nibble_series(frames, i, True), 16)
    kind = []
    if uniq == 1:
      kind.append('const')
    elif dom_ratio > 0.95:
      kind.append('mostly_const')
    if full_step > 0.95 and uniq > 4:
      kind.append('byte_counter_like')
    if lo_step > 0.97 and len(set(nibble_series(frames, i, False))) > 4:
      kind.append('lo_nibble_counter_like')
    if hi_step > 0.97 and len(set(nibble_series(frames, i, True))) > 4:
      kind.append('hi_nibble_counter_like')
    if not kind and uniq > 8 and dom_ratio < 0.25:
      kind.append('payload_like')
    print(
      f'b{i}: uniq={uniq:3d} dom=0x{dom_v:02x} dom_ratio={dom_ratio:0.3f} '
      f'byte_step={full_step:0.3f} lo_step={lo_step:0.3f} hi_step={hi_step:0.3f} '
      f'kinds={"/".join(kind) or "mixed"} top={[(hex(v), n) for v, n in ctr.most_common(6)]}'
    )
  if nbytes >= 7:
    words = {
      'wA': [int.from_bytes(d[1:3], 'little') for d in frames],
      'wB': [int.from_bytes(d[3:5], 'little') for d in frames],
      'wC': [int.from_bytes(d[5:7], 'little') for d in frames],
    }
    for name, vals in words.items():
      ctr = Counter(vals)
      print(f'{name}: uniq={len(ctr)} mean={mean(vals):0.3f} top={ctr.most_common(8)}')
  print()


def main() -> None:
  grouped: dict[str, list[bytes]] = {}
  for win in WINDOWS:
    key = f'{win.route}:{win.src}/{win.addr}:{win.label}'
    grouped[key] = iter_window_bytes(win)
  for key, frames in grouped.items():
    summarize(frames, key)


if __name__ == '__main__':
  main()
