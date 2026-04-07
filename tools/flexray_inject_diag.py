#!/usr/bin/env python3
import argparse
import csv
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import usb1

VENDOR = 0x3801
PRODUCT = 0xddcc
REQ_GET_INJECTOR_DIAG = 0xDA
FMT = "<IIIIIIHBBBB"


@dataclass(frozen=True)
class InjectorDiag:
  override_submit_count: int
  override_submit_accept_count: int
  target96_cache_count: int
  trigger60_cycle_match_count: int
  override96_pop_hit_count: int
  inject_fire_count: int
  last_target_id: int
  last_cycle_count: int
  last_direction: int
  last_replace_len: int
  injector_enabled: int


FIELDS = list(InjectorDiag.__annotations__.keys())


def open_picoflex():
  ctx = usb1.USBContext()
  handle = None
  for dev in ctx.getDeviceList(skip_on_error=True):
    if dev.getVendorID() == VENDOR and dev.getProductID() == PRODUCT:
      handle = dev.open()
      break
  if handle is None:
    raise SystemExit("picoflex not found")
  try:
    handle.claimInterface(0)
  except Exception:
    pass
  return ctx, handle


def read_diag(handle) -> InjectorDiag:
  raw = handle.controlRead(0xC0, REQ_GET_INJECTOR_DIAG, 0, 0, struct.calcsize(FMT), timeout=1000)
  return InjectorDiag(*struct.unpack(FMT, bytes(raw)))


def diff_diag(before: InjectorDiag | None, after: InjectorDiag) -> dict[str, int]:
  if before is None:
    return {k: getattr(after, k) for k in FIELDS}
  return {k: getattr(after, k) - getattr(before, k) for k in FIELDS}


def print_diag(diag: InjectorDiag, prefix: str = ""):
  for key in FIELDS:
    print(f"{prefix}{key}={getattr(diag, key)}")


def print_compact(diag: InjectorDiag, delta: dict[str, int], stamp: float):
  print(
    f"{stamp:12.3f} "
    f"submit={diag.override_submit_count:6d} (+{delta['override_submit_count']:4d}) "
    f"accept={diag.override_submit_accept_count:6d} (+{delta['override_submit_accept_count']:4d}) "
    f"cache96={diag.target96_cache_count:6d} (+{delta['target96_cache_count']:4d}) "
    f"trig60={diag.trigger60_cycle_match_count:6d} (+{delta['trigger60_cycle_match_count']:4d}) "
    f"pop96={diag.override96_pop_hit_count:6d} (+{delta['override96_pop_hit_count']:4d}) "
    f"fire={diag.inject_fire_count:6d} (+{delta['inject_fire_count']:4d}) "
    f"last={diag.last_target_id:03d}/{diag.last_cycle_count:02d}/dir{diag.last_direction}/len{diag.last_replace_len} "
    f"en={diag.injector_enabled}"
  )


def main():
  ap = argparse.ArgumentParser(description="Read Pico FlexRay injector diagnostics")
  ap.add_argument("--watch", action="store_true", help="poll continuously")
  ap.add_argument("--interval", type=float, default=0.2, help="poll interval in seconds")
  ap.add_argument("--log", type=Path, default=None, help="optional CSV log path")
  ap.add_argument("--all", action="store_true", help="print full fields every cycle instead of compact summary")
  args = ap.parse_args()

  _, handle = open_picoflex()
  writer = None
  csv_file = None
  if args.log is not None:
    args.log.parent.mkdir(parents=True, exist_ok=True)
    csv_file = args.log.open("w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=["host_time", *FIELDS, *[f"delta_{k}" for k in FIELDS]])
    writer.writeheader()

  prev = None
  try:
    while True:
      now = time.time()
      diag = read_diag(handle)
      delta = diff_diag(prev, diag)
      if args.watch:
        if args.all:
          print(f"host_time={now:.3f}")
          print_diag(diag)
          print_diag(InjectorDiag(**delta), prefix="delta_")
          print("")
        else:
          print_compact(diag, delta, now)
      else:
        print_diag(diag)
        break

      if writer is not None:
        row = {"host_time": now}
        row.update(asdict(diag))
        row.update({f"delta_{k}": v for k, v in delta.items()})
        writer.writerow(row)
        csv_file.flush()

      prev = diag
      time.sleep(max(0.02, args.interval))
  except KeyboardInterrupt:
    pass
  finally:
    if csv_file is not None:
      csv_file.close()


if __name__ == "__main__":
  main()
