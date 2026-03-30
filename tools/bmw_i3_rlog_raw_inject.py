#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import ctypes
import struct
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, "/home/gericho/sunnypilot")

if TYPE_CHECKING:
  from tools.bmw_i3_direct_lat_sweep import RawUsbDevice

USB_READ_EP = 1
USB_CAN_READ_EP = 0x82
USB_CAN_WRITE_EP = 0x04

USB_VIDS = (0xBBAA, 0x3801)
USB_PIDS = (0xDDEE, 0xDDCC)
USB_WRITE_EP = 3
USB_WRITE_TIMEOUT_MS = 250
PANDA_GET_CAN_HEALTH_STATS = 0xC2
PANDA_SET_CAN_SPEED_KBPS = 0xDE
REQ_GET_INJECTOR_DIAG = 0xDA
INJECTOR_DIAG_FMT = "<IIHBBBBBBB3xIII4BIII4BIII"
CAN_HEALTH_FMT = "<BIBBBBBBBBIIIIIIIHHBBBIIII"

DEFAULT_FRAME_IDS = (72, 96)
PREFERRED_TX_ORDER = (96, 72)
FRAME_NAMES = {
  54: "BRAKE_BLEND_CANDIDATE_B",
  59: "LONG_ACCEL_CANDIDATE_C",
  72: "LAT_STOCK_TX_PHASE_CANDIDATE",
  96: "LAT_STOCK_TX_PAYLOAD_CANDIDATE",
  97: "ACC_TJA_OLD_ROUTE_HELPER_B",
  112: "ACC_STALK_TJA_CANDIDATE_D",
  116: "ACC_STALK_TJA_CANDIDATE_E",
  131: "TJA_GATE_STATE_CANDIDATE",
  135: "TJA_STATE_MAIN_CANDIDATE",
}

DLC_TO_LEN = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]

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

@dataclass(frozen=True)
class LiveKeyState:
  phase72: int | None = None
  overflow: bytes = b""


@dataclass(frozen=True)
class LiveCanState:
  steer770_deg: float | None = None
  overflow: bytes = b""


@dataclass(frozen=True)
class ReplayMessage:
  ts_ns: int
  address: int
  src: int
  base: int
  payload: bytes


@dataclass(frozen=True)
class ReplayBatch:
  ts_ns: int
  messages: tuple[ReplayMessage, ...]
  raw: bytes


@dataclass(frozen=True)
class CanReplayMessage:
  ts_ns: int
  address: int
  src: int
  payload: bytes


@dataclass(frozen=True)
class CanReplayBatch:
  ts_ns: int
  messages: tuple[CanReplayMessage, ...]


@dataclass(frozen=True)
class MimicPhaseModel:
  phase72: int
  confidence: str
  best_lag_s: float
  center_b1: float
  scale_b1: float
  polarity: int
  corr_b1_rate: float


@dataclass(frozen=True)
class ActionPhaseModel:
  phase72: int
  dominant: str
  direction: str
  corr_pred: float
  r2: float
  avg_target: float
  bias: float
  k_b1: float
  k_b2: float
  b1min: int
  b1max: int
  b2min: int
  b2max: int


@dataclass(frozen=True)
class StockActionPoint:
  p0: int
  b1: int
  b2: int
  b3: int
  b4: int


@dataclass(frozen=True)
class PendingFeedback:
  due_monotonic: float
  phase72: int
  target_delta770: float | None
  base_steer770: float
  label: str = ""


@dataclass(frozen=True)
class InjectorDiag:
  override_rx_count: int
  inject_fire_count: int
  last_target_id: int
  last_cycle_count: int
  last_direction: int
  last_replace_len: int
  dbg135_trigger_seen: int
  dbg135_cycle_match: int
  dbg135_template_cached: int
  dbg135_override_present: int
  dbg135_submit_count: int
  dbg135_pop_attempt_count: int
  dbg135_pop_hit_count: int
  dbg72_trigger_seen: int
  dbg72_cycle_match: int
  dbg72_template_cached: int
  dbg72_override_present: int
  dbg72_submit_count: int
  dbg72_pop_attempt_count: int
  dbg72_pop_hit_count: int
  dbg96_trigger_seen: int
  dbg96_cycle_match: int
  dbg96_template_cached: int
  dbg96_override_present: int
  dbg96_submit_count: int
  dbg96_pop_attempt_count: int
  dbg96_pop_hit_count: int


@dataclass(frozen=True)
class CanHealth:
  bus_off: int
  bus_off_cnt: int
  error_warning: int
  error_passive: int
  last_error: int
  last_stored_error: int
  last_data_error: int
  last_data_stored_error: int
  receive_error_cnt: int
  transmit_error_cnt: int
  total_error_cnt: int
  total_tx_lost_cnt: int
  total_rx_lost_cnt: int
  total_tx_cnt: int
  total_rx_cnt: int
  total_fwd_cnt: int
  total_tx_checksum_error_cnt: int
  can_speed: int
  can_data_speed: int
  canfd_enabled: int
  brs_enabled: int
  canfd_non_iso: int
  irq0_call_rate: int
  irq1_call_rate: int
  irq2_call_rate: int
  can_core_reset_count: int


MIMIC_PHASE_MODELS: dict[int, MimicPhaseModel] = {
  34: MimicPhaseModel(phase72=34, confidence="high", best_lag_s=0.05, center_b1=151.3, scale_b1=75.7, polarity=-1, corr_b1_rate=-0.975),
  53: MimicPhaseModel(phase72=53, confidence="high", best_lag_s=0.00, center_b1=196.7, scale_b1=65.7, polarity=1, corr_b1_rate=0.905),
  29: MimicPhaseModel(phase72=29, confidence="medium", best_lag_s=0.10, center_b1=158.4, scale_b1=59.4, polarity=-1, corr_b1_rate=-0.671),
  45: MimicPhaseModel(phase72=45, confidence="medium", best_lag_s=0.20, center_b1=67.4, scale_b1=31.6, polarity=-1, corr_b1_rate=-0.993),
  44: MimicPhaseModel(phase72=44, confidence="medium", best_lag_s=-0.05, center_b1=179.2, scale_b1=116.2, polarity=-1, corr_b1_rate=-0.999),
  62: MimicPhaseModel(phase72=62, confidence="medium", best_lag_s=-0.10, center_b1=161.9, scale_b1=64.6, polarity=-1, corr_b1_rate=-0.916),
}

ACTION_PHASE_MODELS: dict[int, ActionPhaseModel] = {
  44: ActionPhaseModel(phase72=44, dominant="b2", direction="neg", corr_pred=0.725, r2=0.526, avg_target=-0.583, bias=-65.7867, k_b1=-0.00012, k_b2=0.26350, b1min=10, b1max=237, b2min=242, b2max=253),
  56: ActionPhaseModel(phase72=56, dominant="b2", direction="pos", corr_pred=0.549, r2=0.302, avg_target=0.197, bias=40.0430, k_b1=0.01085, k_b2=-0.16698, b1min=10, b1max=236, b2min=240, b2max=254),
  16: ActionPhaseModel(phase72=16, dominant="b2", direction="pos", corr_pred=0.541, r2=0.293, avg_target=0.149, bias=-80.9324, k_b1=-0.00861, k_b2=0.33050, b1min=10, b1max=237, b2min=243, b2max=254),
  8: ActionPhaseModel(phase72=8, dominant="hybrid", direction="neg", corr_pred=0.480, r2=0.231, avg_target=-0.754, bias=-12.6415, k_b1=-0.00729, k_b2=0.05191, b1min=10, b1max=237, b2min=241, b2max=252),
  20: ActionPhaseModel(phase72=20, dominant="b2", direction="pos", corr_pred=0.459, r2=0.210, avg_target=0.547, bias=26.3616, k_b1=-0.00332, k_b2=-0.10289, b1min=11, b1max=237, b2min=240, b2max=254),
  4: ActionPhaseModel(phase72=4, dominant="b2", direction="neg", corr_pred=0.437, r2=0.191, avg_target=-0.697, bias=46.2247, k_b1=0.00090, k_b2=-0.19026, b1min=10, b1max=237, b2min=240, b2max=254),
  36: ActionPhaseModel(phase72=36, dominant="b2", direction="neg", corr_pred=0.432, r2=0.187, avg_target=-0.538, bias=42.5300, k_b1=-0.00498, k_b2=-0.17262, b1min=10, b1max=237, b2min=240, b2max=251),
}

STOCK_ACTION_POINTS: dict[int, tuple[StockActionPoint, ...]] = {
  4: (
    StockActionPoint(0, 212, 242, 33, 255),
    StockActionPoint(4, 237, 251, 224, 255),
    StockActionPoint(4, 62, 253, 224, 255),
    StockActionPoint(4, 133, 241, 224, 255),
    StockActionPoint(0, 176, 250, 224, 255),
  ),
  8: (
    StockActionPoint(4, 86, 247, 224, 255),
    StockActionPoint(8, 10, 248, 224, 255),
  ),
  16: (
    StockActionPoint(12, 91, 251, 33, 255),
    StockActionPoint(16, 189, 246, 33, 255),
    StockActionPoint(16, 98, 242, 224, 255),
    StockActionPoint(16, 11, 246, 224, 255),
    StockActionPoint(12, 7, 244, 33, 255),
  ),
  20: (
    StockActionPoint(20, 237, 251, 224, 255),
    StockActionPoint(20, 133, 241, 224, 255),
    StockActionPoint(20, 98, 242, 224, 255),
    StockActionPoint(20, 177, 244, 224, 255),
    StockActionPoint(20, 236, 245, 224, 255),
    StockActionPoint(16, 99, 252, 224, 255),
    StockActionPoint(16, 91, 251, 33, 255),
  ),
  36: (
    StockActionPoint(36, 216, 240, 224, 255),
    StockActionPoint(36, 11, 246, 224, 255),
    StockActionPoint(32, 62, 253, 224, 255),
    StockActionPoint(32, 216, 240, 224, 255),
    StockActionPoint(32, 133, 241, 224, 255),
    StockActionPoint(32, 63, 243, 224, 255),
  ),
  44: (
    StockActionPoint(40, 6, 250, 33, 255),
    StockActionPoint(44, 63, 243, 224, 255),
    StockActionPoint(44, 177, 244, 224, 255),
    StockActionPoint(44, 237, 251, 224, 255),
    StockActionPoint(40, 137, 243, 33, 255),
  ),
  56: (
    StockActionPoint(52, 177, 244, 224, 255),
    StockActionPoint(56, 62, 253, 224, 255),
    StockActionPoint(52, 10, 248, 224, 255),
    StockActionPoint(52, 87, 249, 224, 255),
    StockActionPoint(56, 189, 246, 33, 255),
  ),
}


def resolve_latest_route() -> Path | None:
  root = Path("/home/gericho/.comma/media/0/realdata")
  if not root.exists():
    return None
  candidates = sorted(root.glob("*--0"), key=lambda p: p.stat().st_mtime, reverse=True)
  return candidates[0] if candidates else None


def route_to_rlog(route: str) -> str:
  p = Path(route)
  if p.is_file():
    return str(p)
  if p.name == "rlog.zst":
    return str(p)
  return str(p / "rlog.zst")


def parse_csv_ints(raw: str) -> tuple[int, ...]:
  out = []
  for part in raw.split(","):
    part = part.strip()
    if not part:
      continue
    out.append(int(part, 0))
  return tuple(out)


def crc8(data: bytes, init_value: int = 0xF1) -> int:
  crc = init_value & 0xFF
  for b in data:
    crc = CRC8_TABLE[crc ^ b]
  return crc


def pack_override(frame_id: int, base: int, dat: bytes) -> bytes:
  payload_len = len(dat)
  out = bytearray([0x90, frame_id & 0xFF, (frame_id >> 8) & 0x07, base & 0xFF])
  out.extend(struct.pack("<H", payload_len))
  out.append(crc8(dat[1:]))
  out.extend(dat[1:])
  return bytes(out)


def pack_batch(messages: tuple[ReplayMessage, ...], base_override: int | None = None) -> bytes:
  blob = bytearray()
  for msg in messages:
    key_base = msg.base if base_override is None else base_override
    blob.extend(pack_override(msg.address, key_base, bytes([key_base]) + msg.payload))
  return bytes(blob)


class PandaCanHeader(ctypes.LittleEndianStructure):
  _pack_ = 1
  _fields_ = [
    ("reserved", ctypes.c_uint8, 1),
    ("bus", ctypes.c_uint8, 3),
    ("data_len_code", ctypes.c_uint8, 4),
    ("rejected", ctypes.c_uint8, 1),
    ("returned", ctypes.c_uint8, 1),
    ("extended", ctypes.c_uint8, 1),
    ("addr", ctypes.c_uint32, 29),
    ("checksum", ctypes.c_uint8),
  ]


def can_len_to_dlc(length: int) -> int:
  if length <= 8:
    return length
  if length <= 24:
    return 8 + ((length - 8) // 4) + (1 if (length % 4) else 0)
  return 11 + (length // 16) + (1 if (length % 16) else 0)


def can_checksum(data: bytes) -> int:
  checksum = 0
  for b in data:
    checksum ^= b
  return checksum


def pack_can_message(address: int, payload: bytes, bus: int = 0) -> bytes:
  header = PandaCanHeader()
  header.reserved = 0
  header.bus = bus & 0x7
  header.data_len_code = can_len_to_dlc(len(payload)) & 0xF
  header.rejected = 0
  header.returned = 0
  header.extended = 1 if address >= 0x800 else 0
  header.addr = address
  header.checksum = 0
  header_bytes = bytearray(bytes(header))
  raw = bytes(header_bytes) + payload
  header_bytes[-1] = can_checksum(raw)
  return bytes(header_bytes) + payload


def pack_can_batch(messages: tuple[CanReplayMessage, ...], bus: int = 0) -> bytes:
  return b"".join(pack_can_message(msg.address, msg.payload, bus) for msg in messages)


def clamp(value: float, lo: float, hi: float) -> float:
  return max(lo, min(hi, value))


def extract_lat_fields(messages: tuple[ReplayMessage, ...]) -> tuple[int | None, int | None, int | None]:
  phase72 = None
  b1_96 = None
  b2_96 = None
  for msg in messages:
    if msg.address == 72 and len(msg.payload) >= 1:
      phase72 = msg.payload[0]
    elif msg.address == 96 and len(msg.payload) >= 2:
      if phase72 is None and len(msg.payload) >= 1:
        phase72 = msg.payload[0]
      b1_96 = msg.payload[1]
      if len(msg.payload) >= 3:
        b2_96 = msg.payload[2]
  return phase72, b1_96, b2_96


def filter_batches_by_phase(batches: list[ReplayBatch], phases: set[int]) -> list[ReplayBatch]:
  if not phases:
    return batches
  out: list[ReplayBatch] = []
  for batch in batches:
    phase72, _b1, _b2 = extract_lat_fields(batch.messages)
    if phase72 in phases:
      out.append(batch)
  return out


def infer_signed_cmd(messages: tuple[ReplayMessage, ...]) -> tuple[MimicPhaseModel | None, float | None]:
  phase72, b1_96, _b2_96 = extract_lat_fields(messages)
  if phase72 is None or b1_96 is None:
    return None, None
  model = MIMIC_PHASE_MODELS.get(phase72)
  if model is None or model.scale_b1 <= 0.0:
    return None, None
  signed_cmd = model.polarity * (float(b1_96) - model.center_b1) / model.scale_b1
  return model, clamp(signed_cmd, -1.0, 1.0)


def synthesize_b1_from_signed_cmd(model: MimicPhaseModel, signed_cmd: float) -> int:
  raw_b1 = model.center_b1 + (model.polarity * clamp(signed_cmd, -1.0, 1.0) * model.scale_b1)
  return int(clamp(round(raw_b1), 0, 255))


def predict_action_delta(model: ActionPhaseModel, b1_96: int, b2_96: int) -> float:
  return model.bias + (model.k_b1 * float(b1_96)) + (model.k_b2 * float(b2_96))


def extract_action_model(messages: tuple[ReplayMessage, ...]) -> tuple[ActionPhaseModel | None, int | None, int | None]:
  phase72, b1_96, b2_96 = extract_lat_fields(messages)
  if phase72 is None or b1_96 is None or b2_96 is None:
    return None, None, None
  model = ACTION_PHASE_MODELS.get(phase72)
  return model, b1_96, b2_96


def solve_action_bytes(model: ActionPhaseModel, desired_delta770: float, current_b1: int, current_b2: int) -> tuple[int, int]:
  solve_b2 = model.dominant == "b2" or (model.dominant == "hybrid" and abs(model.k_b2) >= abs(model.k_b1))
  if solve_b2 and abs(model.k_b2) > 1e-6:
    raw_b2 = (desired_delta770 - model.bias - (model.k_b1 * float(current_b1))) / model.k_b2
    b2 = int(clamp(round(raw_b2), model.b2min, model.b2max))
    return current_b1, b2
  if abs(model.k_b1) > 1e-6:
    raw_b1 = (desired_delta770 - model.bias - (model.k_b2 * float(current_b2))) / model.k_b1
    b1 = int(clamp(round(raw_b1), model.b1min, model.b1max))
    return b1, current_b2
  return current_b1, current_b2


def select_stock_action_point(model: ActionPhaseModel, desired_delta770: float) -> StockActionPoint | None:
  points = STOCK_ACTION_POINTS.get(model.phase72)
  if not points:
    return None
  best = None
  best_err = None
  for point in points:
    predicted = predict_action_delta(model, point.b1, point.b2)
    err = abs(predicted - desired_delta770)
    if best is None or err < best_err:
      best = point
      best_err = err
  return best


def rewrite_batch_96_b1(batch: ReplayBatch, forced_signed_cmd: float | None) -> ReplayBatch:
  model, inferred_signed_cmd = infer_signed_cmd(batch.messages)
  if model is None:
    return batch
  signed_cmd = inferred_signed_cmd if forced_signed_cmd is None else forced_signed_cmd
  if signed_cmd is None:
    return batch
  new_messages: list[ReplayMessage] = []
  changed = False
  for msg in batch.messages:
    if msg.address == 96 and len(msg.payload) >= 2:
      payload = bytearray(msg.payload)
      payload[1] = synthesize_b1_from_signed_cmd(model, signed_cmd)
      new_messages.append(ReplayMessage(ts_ns=msg.ts_ns, address=msg.address, src=msg.src, base=msg.base, payload=bytes(payload)))
      changed = True
    else:
      new_messages.append(msg)
  if not changed:
    return batch
  messages = tuple(new_messages)
  return ReplayBatch(ts_ns=batch.ts_ns, messages=messages, raw=pack_batch(messages))


def rewrite_batch_96_action(batch: ReplayBatch, forced_delta770: float | None, scale_delta770: float) -> ReplayBatch:
  model, current_b1, current_b2 = extract_action_model(batch.messages)
  if model is None or current_b1 is None or current_b2 is None:
    return batch
  predicted = predict_action_delta(model, current_b1, current_b2)
  desired = predicted * scale_delta770 if forced_delta770 is None else forced_delta770
  stock_point = select_stock_action_point(model, desired)
  new_messages: list[ReplayMessage] = []
  changed = False
  for msg in batch.messages:
    if msg.address == 96 and len(msg.payload) >= 5:
      payload = bytearray(msg.payload)
      if stock_point is not None:
        payload[0] = stock_point.p0
        payload[1] = stock_point.b1
        payload[2] = stock_point.b2
        payload[3] = stock_point.b3
        payload[4] = stock_point.b4
      else:
        new_b1, new_b2 = solve_action_bytes(model, desired, current_b1, current_b2)
        if new_b1 == current_b1 and new_b2 == current_b2:
          new_messages.append(msg)
          continue
        payload[1] = new_b1
        payload[2] = new_b2
      new_messages.append(ReplayMessage(ts_ns=msg.ts_ns, address=msg.address, src=msg.src, base=msg.base, payload=bytes(payload)))
      changed = changed or (bytes(payload) != msg.payload)
    else:
      new_messages.append(msg)
  if not changed:
    return batch
  messages = tuple(new_messages)
  return ReplayBatch(ts_ns=batch.ts_ns, messages=messages, raw=pack_batch(messages))


def perturb_batch_96(batch: ReplayBatch, delta_b1: int, delta_b2: int) -> ReplayBatch:
  if delta_b1 == 0 and delta_b2 == 0:
    return batch
  new_messages: list[ReplayMessage] = []
  changed = False
  for msg in batch.messages:
    if msg.address == 96 and len(msg.payload) >= 3:
      payload = bytearray(msg.payload)
      payload[1] = int(clamp(payload[1] + delta_b1, 0, 255))
      payload[2] = int(clamp(payload[2] + delta_b2, 0, 255))
      new_messages.append(ReplayMessage(ts_ns=msg.ts_ns, address=msg.address, src=msg.src, base=msg.base, payload=bytes(payload)))
      changed = changed or (bytes(payload) != msg.payload)
    else:
      new_messages.append(msg)
  if not changed:
    return batch
  messages = tuple(new_messages)
  return ReplayBatch(ts_ns=batch.ts_ns, messages=messages, raw=pack_batch(messages))


def order_frame_ids(frame_ids: set[int]) -> tuple[int, ...]:
  ordered = [frame_id for frame_id in PREFERRED_TX_ORDER if frame_id in frame_ids]
  ordered.extend(sorted(frame_id for frame_id in frame_ids if frame_id not in PREFERRED_TX_ORDER))
  return tuple(ordered)


def import_usb_helpers() -> tuple[Any, Any]:
  from tools.bmw_i3_direct_lat_sweep import open_picoflex_device, unpack_flexray_records
  return open_picoflex_device, unpack_flexray_records


def calculate_can_checksum(data: bytes) -> int:
  checksum = 0
  for b in data:
    checksum ^= b
  return checksum


def unpack_can_buffer(dat: bytes) -> tuple[list[tuple[int, bytes, int]], bytes]:
  ret: list[tuple[int, bytes, int]] = []
  while len(dat) >= 6:
    data_len = DLC_TO_LEN[(dat[0] >> 4) & 0xF]
    if data_len > len(dat) - 6:
      break
    packet = dat[:6 + data_len]
    if calculate_can_checksum(packet) != 0:
      dat = dat[1:]
      continue
    header = packet[:6]
    bus = (header[0] >> 1) & 0x7
    address = (header[4] << 24 | header[3] << 16 | header[2] << 8 | header[1]) >> 3
    if (header[1] >> 1) & 0x1:
      bus += 128
    if header[1] & 0x1:
      bus += 192
    payload = packet[6:]
    ret.append((address, payload, bus))
    dat = dat[6 + data_len:]
  return ret, dat


def scale_770(raw: int) -> float:
  return raw * 0.04375 - 1433.6


def read_injector_diag(dev: RawUsbDevice) -> InjectorDiag:
  raw = dev.handle.controlRead(0xC0, REQ_GET_INJECTOR_DIAG, 0, 0, struct.calcsize(INJECTOR_DIAG_FMT), timeout=1000)
  return InjectorDiag(*struct.unpack(INJECTOR_DIAG_FMT, bytes(raw)))


def read_can_health(dev: RawUsbDevice) -> CanHealth:
  raw = bytes(dev.handle.controlRead(0xC0, PANDA_GET_CAN_HEALTH_STATS, 0, 0, struct.calcsize(CAN_HEALTH_FMT), timeout=1000))
  return CanHealth(*struct.unpack(CAN_HEALTH_FMT, raw))


def configure_can_bitrate(dev: RawUsbDevice, bus: int = 2, speed_kbps: int = 500) -> None:
  speed_x10 = speed_kbps * 10
  dev.handle.controlWrite(0x40, PANDA_SET_CAN_SPEED_KBPS, bus, speed_x10, b"", timeout=1000)


def print_can_health(label: str, health: CanHealth) -> None:
  print(
    f"# can_{label} speed={health.can_speed}kbps rx={health.total_rx_cnt} tx={health.total_tx_cnt} "
    f"rx_lost={health.total_rx_lost_cnt} tx_lost={health.total_tx_lost_cnt} "
    f"err={health.total_error_cnt} rec={health.receive_error_cnt} tec={health.transmit_error_cnt} "
    f"bus_off={health.bus_off}"
  )


def poll_live_phase72(dev: RawUsbDevice, state: LiveKeyState, timeout_ms: int) -> LiveKeyState:
  import usb1

  try:
    raw = bytes(dev.handle.bulkRead(USB_READ_EP, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return state

  _, unpack_flexray_records = import_usb_helpers()
  phase72 = state.phase72
  records, overflow = unpack_flexray_records(state.overflow + raw)
  for frame_id, _source, _cycle, payload in records:
    if frame_id == 72 and len(payload) >= 1:
      phase72 = payload[0]
  return LiveKeyState(phase72=phase72, overflow=overflow)


def poll_live_steer770(dev: RawUsbDevice, state: LiveCanState, timeout_ms: int) -> LiveCanState:
  import usb1

  try:
    raw = bytes(dev.handle.bulkRead(USB_CAN_READ_EP, 16384, timeout=timeout_ms))
  except usb1.USBErrorTimeout:
    return state

  steer770 = state.steer770_deg
  records, overflow = unpack_can_buffer(state.overflow + raw)
  for address, payload, bus in records:
    if bus == 2 and address == 770 and len(payload) >= 4:
      steer770 = scale_770(payload[2] | (payload[3] << 8))
  return LiveCanState(steer770_deg=steer770, overflow=overflow)


def drain_live_steer770(dev: RawUsbDevice, state: LiveCanState, timeout_ms: int, max_reads: int = 64) -> tuple[LiveCanState, int]:
  import usb1

  reads = 0
  current = state
  while reads < max_reads:
    try:
      raw = bytes(dev.handle.bulkRead(USB_CAN_READ_EP, 16384, timeout=timeout_ms if reads == 0 else 0))
    except usb1.USBErrorTimeout:
      break
    next_state = current
    steer770 = current.steer770_deg
    records, overflow = unpack_can_buffer(current.overflow + raw)
    for address, payload, bus in records:
      if bus == 2 and address == 770 and len(payload) >= 4:
        steer770 = scale_770(payload[2] | (payload[3] << 8))
    next_state = LiveCanState(steer770_deg=steer770, overflow=overflow)
    current = next_state
    reads += 1
    if not raw:
      break
  return current, reads


def print_diag(label: str, diag: InjectorDiag) -> None:
  print(
    f"# diag_{label} override_rx={diag.override_rx_count} fire={diag.inject_fire_count} "
    f"last_target={diag.last_target_id} last_cycle={diag.last_cycle_count} last_len={diag.last_replace_len}"
  )
  print(
    f"# diag_{label} 72 submit={diag.dbg72_submit_count} pop_attempt={diag.dbg72_pop_attempt_count} "
    f"pop_hit={diag.dbg72_pop_hit_count} flags="
    f"{diag.dbg72_trigger_seen}/{diag.dbg72_cycle_match}/{diag.dbg72_template_cached}/{diag.dbg72_override_present}"
  )
  print(
    f"# diag_{label} 96 submit={diag.dbg96_submit_count} pop_attempt={diag.dbg96_pop_attempt_count} "
    f"pop_hit={diag.dbg96_pop_hit_count} flags="
    f"{diag.dbg96_trigger_seen}/{diag.dbg96_cycle_match}/{diag.dbg96_template_cached}/{diag.dbg96_override_present}"
  )


def print_diag_delta(before: InjectorDiag, after: InjectorDiag) -> None:
  print(
    f"# diag_delta override_rx={after.override_rx_count - before.override_rx_count} "
    f"fire={after.inject_fire_count - before.inject_fire_count}"
  )
  print(
    f"# diag_delta 72 submit={after.dbg72_submit_count - before.dbg72_submit_count} "
    f"pop_attempt={after.dbg72_pop_attempt_count - before.dbg72_pop_attempt_count} "
    f"pop_hit={after.dbg72_pop_hit_count - before.dbg72_pop_hit_count}"
  )
  print(
    f"# diag_delta 96 submit={after.dbg96_submit_count - before.dbg96_submit_count} "
    f"pop_attempt={after.dbg96_pop_attempt_count - before.dbg96_pop_attempt_count} "
    f"pop_hit={after.dbg96_pop_hit_count - before.dbg96_pop_hit_count}"
  )


def iter_replay_batches(
  route: str,
  frame_ids: set[int],
  sources: set[int] | None,
  limit_batches: int | None,
  limit_messages: int | None,
  start_sec: float | None,
  end_sec: float | None,
) -> tuple[list[ReplayBatch], Counter[int], int]:
  from opendbc.car.logreader import LogReader

  batches: list[ReplayBatch] = []
  counts: Counter[int] = Counter()
  total_messages = 0
  partial_batches = 0
  ordered_ids = order_frame_ids(frame_ids)
  first_ts_ns: int | None = None

  for evt in LogReader(route_to_rlog(route), only_union_types=True):
    if evt.which() != "can":
      continue
    if first_ts_ns is None:
      first_ts_ns = evt.logMonoTime
    rel_sec = (evt.logMonoTime - first_ts_ns) / 1e9
    if start_sec is not None and rel_sec < start_sec:
      continue
    if end_sec is not None and rel_sec > end_sec:
      break

    per_addr: dict[int, ReplayMessage] = {}
    for m in evt.can:
      if m.address not in frame_ids:
        continue
      if sources is not None and m.src not in sources:
        continue

      payload = bytes(m.dat)
      if len(payload) < 1:
        continue

      tx_payload = payload[:9]
      base = tx_payload[0]
      per_addr[m.address] = ReplayMessage(
        ts_ns=evt.logMonoTime,
        address=m.address,
        src=m.src,
        base=base,
        payload=tx_payload,
      )
      if len(per_addr) == len(frame_ids):
        break

    if per_addr:
      missing = frame_ids.difference(per_addr)
      if missing:
        partial_batches += 1
      else:
        ordered_messages = tuple(per_addr[addr] for addr in ordered_ids)
        batch_blob = bytearray(pack_batch(ordered_messages))
        for msg in ordered_messages:
          counts[msg.address] += 1
          total_messages += 1

        batches.append(ReplayBatch(ts_ns=evt.logMonoTime, messages=ordered_messages, raw=bytes(batch_blob)))
      if limit_batches is not None and len(batches) >= limit_batches:
        break

    if limit_messages is not None and total_messages >= limit_messages:
      break

  return batches, counts, partial_batches


def iter_event_batches(
  route: str,
  frame_ids: set[int],
  sources: set[int] | None,
  limit_events: int | None,
  start_sec: float | None,
  end_sec: float | None,
) -> list[ReplayBatch]:
  from opendbc.car.logreader import LogReader

  batches: list[ReplayBatch] = []
  first_ts_ns: int | None = None
  for evt in LogReader(route_to_rlog(route), only_union_types=True):
    if evt.which() != "can":
      continue
    if first_ts_ns is None:
      first_ts_ns = evt.logMonoTime
    rel_sec = (evt.logMonoTime - first_ts_ns) / 1e9
    if start_sec is not None and rel_sec < start_sec:
      continue
    if end_sec is not None and rel_sec > end_sec:
      break
    msgs: list[ReplayMessage] = []
    for m in evt.can:
      if m.address not in frame_ids:
        continue
      if sources is not None and m.src not in sources:
        continue
      payload = bytes(m.dat)
      if len(payload) < 1:
        continue
      tx_payload = payload[:9]
      msgs.append(
        ReplayMessage(
          ts_ns=evt.logMonoTime,
          address=m.address,
          src=m.src,
          base=tx_payload[0],
          payload=tx_payload,
        )
      )
    if not msgs:
      continue
    order = {fid: idx for idx, fid in enumerate(order_frame_ids(set(m.address for m in msgs)))}
    ordered = tuple(sorted(msgs, key=lambda m: (order.get(m.address, 999), m.address)))
    batches.append(ReplayBatch(ts_ns=evt.logMonoTime, messages=ordered, raw=pack_batch(ordered)))
    if limit_events is not None and len(batches) >= limit_events:
      break
  return batches


def iter_can_event_batches(
  route: str,
  frame_ids: set[int],
  sources: set[int] | None,
  limit_events: int | None,
  start_sec: float | None,
  end_sec: float | None,
) -> tuple[list[CanReplayBatch], Counter[int]]:
  from opendbc.car.logreader import LogReader

  batches: list[CanReplayBatch] = []
  counts: Counter[int] = Counter()
  first_ts_ns: int | None = None
  for evt in LogReader(route_to_rlog(route), only_union_types=True):
    if evt.which() != "can":
      continue
    if first_ts_ns is None:
      first_ts_ns = evt.logMonoTime
    rel_sec = (evt.logMonoTime - first_ts_ns) / 1e9
    if start_sec is not None and rel_sec < start_sec:
      continue
    if end_sec is not None and rel_sec > end_sec:
      break
    msgs: list[CanReplayMessage] = []
    for m in evt.can:
      if m.address not in frame_ids:
        continue
      if sources is not None and m.src not in sources:
        continue
      payload = bytes(m.dat)
      if len(payload) > 8:
        continue
      msgs.append(
        CanReplayMessage(
          ts_ns=evt.logMonoTime,
          address=m.address,
          src=m.src,
          payload=payload,
        )
      )
      counts[m.address] += 1
    if not msgs:
      continue
    ordered = tuple(sorted(msgs, key=lambda m: (m.address, len(m.payload))))
    batches.append(CanReplayBatch(ts_ns=evt.logMonoTime, messages=ordered))
    if limit_events is not None and len(batches) >= limit_events:
      break
  return batches, counts


def select_sequence_windows(
  events: list[ReplayBatch],
  center_phases: set[int],
  before: int,
  after: int,
) -> list[ReplayBatch]:
  if not center_phases:
    return events
  keep: set[int] = set()
  for i, batch in enumerate(events):
    addrs = {m.address for m in batch.messages}
    phase72, _b1, _b2 = extract_lat_fields(batch.messages)
    if 72 in addrs and 96 in addrs and phase72 in center_phases:
      for j in range(max(0, i - before), min(len(events), i + after + 1)):
        keep.add(j)
  return [events[i] for i in sorted(keep)]


def print_summary(route: str, batches: list[ReplayBatch], counts: Counter[int], speed: float, partial_batches: int) -> None:
  msg_total = sum(counts.values())
  print(f"# route {route}")
  print(f"# replay batches={len(batches)} messages={msg_total} speed={speed:.3f}x")
  print(f"# dropped_partial_batches={partial_batches}")
  for frame_id in sorted(counts):
    name = FRAME_NAMES.get(frame_id, "UNKNOWN")
    print(f"# frame {frame_id:>3} {name:<32} count={counts[frame_id]}")


def print_can_summary(batches: list[CanReplayBatch], counts: Counter[int], bus: int) -> None:
  if not batches:
    return
  msg_total = sum(counts.values())
  print(f"# can_replay batches={len(batches)} messages={msg_total} bus={bus}")
  for frame_id in sorted(counts):
    print(f"# can_frame {frame_id:>4} count={counts[frame_id]}")


def print_preview(batches: list[ReplayBatch], preview_batches: int) -> None:
  print("# preview")
  for idx, batch in enumerate(batches[:preview_batches]):
    model, signed_cmd = infer_signed_cmd(batch.messages)
    action_model, act_b1, act_b2 = extract_action_model(batch.messages)
    phase72, b1_96, _b2_96 = extract_lat_fields(batch.messages)
    extra = ""
    if model is not None and signed_cmd is not None:
      extra = (
        f" phase72={model.phase72:>2} b1_96={b1_96:>3} signed_cmd={signed_cmd:+.3f}"
        f" lag_ms={model.best_lag_s*1000:+.0f} conf={model.confidence}"
      )
    elif action_model is not None and act_b1 is not None and act_b2 is not None:
      predicted = predict_action_delta(action_model, act_b1, act_b2)
      extra = (
        f" phase72={action_model.phase72:>2} b1_96={act_b1:>3} b2_96={act_b2:>3}"
        f" pred_d770={predicted:+.3f} dom={action_model.dominant}"
      )
    elif phase72 is not None and b1_96 is not None:
      extra = f" phase72={phase72:>2} b1_96={b1_96:>3}"
    print(f"# batch {idx:04d} ts_ns={batch.ts_ns} frames={len(batch.messages)} raw_len={len(batch.raw)}{extra}")
    for msg in batch.messages:
      name = FRAME_NAMES.get(msg.address, "UNKNOWN")
      print(
        f"  src={msg.src} addr={msg.address:>3} {name:<32} "
        f"base=0x{msg.base:02x} payload={msg.payload.hex()}"
      )


def replay_batches(
  dev: RawUsbDevice,
  batches: list[ReplayBatch],
  can_batches: list[CanReplayBatch],
  speed: float,
  lead_s: float,
  live_phase_key: bool,
  synthesize_96_action: bool,
  feedback_770: bool,
  feedback_kp: float,
  can_bus: int,
) -> None:
  if not batches and not can_batches:
    return

  speed = max(speed, 1e-3)
  first_ts_ns = min(
    [batch.ts_ns for batch in batches[:1]] + [batch.ts_ns for batch in can_batches[:1]]
  )
  start_monotonic = time.monotonic()
  live_state = LiveKeyState()
  live_can_state = LiveCanState()
  pending_feedback: collections.deque[PendingFeedback] = collections.deque()
  feedback_term = 0.0
  if live_phase_key:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and live_state.phase72 is None:
      live_state = poll_live_phase72(dev, live_state, timeout_ms=100)
    if live_state.phase72 is None:
      raise TimeoutError("timed out waiting for live 72 phase")
  if feedback_770:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and live_can_state.steer770_deg is None:
      live_can_state, _ = drain_live_steer770(dev, live_can_state, timeout_ms=100)
    if live_can_state.steer770_deg is None:
      raise TimeoutError("timed out waiting for live 770 feedback")

  timeline: list[tuple[int, str, ReplayBatch | CanReplayBatch]] = []
  timeline.extend((batch.ts_ns, "can", batch) for batch in can_batches)
  timeline.extend((batch.ts_ns, "flex", batch) for batch in batches)
  timeline.sort(key=lambda item: (item[0], 0 if item[1] == "can" else 1))

  flex_idx = 0
  can_idx = 0
  for item_ts_ns, kind, item in timeline:
    if feedback_770:
      live_can_state, _ = drain_live_steer770(dev, live_can_state, timeout_ms=0)
      now = time.monotonic()
      while pending_feedback and pending_feedback[0].due_monotonic <= now and live_can_state.steer770_deg is not None:
        fb = pending_feedback.popleft()
        actual = live_can_state.steer770_deg - fb.base_steer770
        if fb.target_delta770 is None:
          print(f"# fb {fb.label} phase72={fb.phase72:>2} actual_d770={actual:+.3f}")
        else:
          err = fb.target_delta770 - actual
          feedback_term = clamp(feedback_kp * err, -2.0, 2.0)
          print(
            f"# fb phase72={fb.phase72:>2} target_d770={fb.target_delta770:+.3f} "
            f"actual_d770={actual:+.3f} err={err:+.3f} corr={feedback_term:+.3f}"
          )
    target_s = ((item_ts_ns - first_ts_ns) / 1e9) / speed
    sched_s = max(0.0, target_s - lead_s)
    while True:
      now = time.monotonic()
      sleep_s = (start_monotonic + sched_s) - now
      if sleep_s <= 0:
        break
      if feedback_770:
        poll_timeout_ms = max(0, min(int(sleep_s * 1000.0), 20))
        live_can_state, _ = drain_live_steer770(dev, live_can_state, timeout_ms=poll_timeout_ms)
        now = time.monotonic()
        while pending_feedback and pending_feedback[0].due_monotonic <= now and live_can_state.steer770_deg is not None:
          fb = pending_feedback.popleft()
          actual = live_can_state.steer770_deg - fb.base_steer770
          if fb.target_delta770 is None:
            print(f"# fb {fb.label} phase72={fb.phase72:>2} actual_d770={actual:+.3f}")
          else:
            err = fb.target_delta770 - actual
            feedback_term = clamp(feedback_kp * err, -2.0, 2.0)
            print(
              f"# fb phase72={fb.phase72:>2} target_d770={fb.target_delta770:+.3f} "
              f"actual_d770={actual:+.3f} err={err:+.3f} corr={feedback_term:+.3f}"
            )
      else:
        time.sleep(min(sleep_s, 0.02))
    if kind == "can":
      can_batch = item
      raw_can = pack_can_batch(can_batch.messages, can_bus)
      dev.handle.bulkWrite(USB_CAN_WRITE_EP, raw_can, timeout=USB_WRITE_TIMEOUT_MS)
      print(
        f"tx can  ={can_idx:04d} dt={target_s:8.4f}s sched={sched_s:8.4f}s "
        f"lead_ms={lead_s*1000:5.1f} frames={len(can_batch.messages)} raw_len={len(raw_can)}"
      )
      can_idx += 1
      continue

    batch = item
    key_base = None
    if live_phase_key:
      live_state = poll_live_phase72(dev, live_state, timeout_ms=0)
      if live_state.phase72 is not None:
        key_base = live_state.phase72 & 0xFF
    send_batch = batch
    if feedback_770:
      action_model, act_b1, act_b2 = extract_action_model(send_batch.messages)
      if synthesize_96_action:
        send_batch = rewrite_batch_96_action(batch, None, 1.0)
        action_model, act_b1, act_b2 = extract_action_model(send_batch.messages)
        if action_model is not None and act_b1 is not None and act_b2 is not None:
          predicted = predict_action_delta(action_model, act_b1, act_b2)
          desired = predicted + feedback_term
          send_batch = rewrite_batch_96_action(send_batch, desired, 1.0)
          action_model, act_b1, act_b2 = extract_action_model(send_batch.messages)
      if action_model is not None and act_b1 is not None and act_b2 is not None and live_can_state.steer770_deg is not None:
        predicted = predict_action_delta(action_model, act_b1, act_b2)
        pending_feedback.append(PendingFeedback(
          due_monotonic=time.monotonic() + 0.60,
          phase72=action_model.phase72,
          target_delta770=predicted,
          base_steer770=live_can_state.steer770_deg,
        ))
      elif live_can_state.steer770_deg is not None:
        phase72, b1_96, b2_96 = extract_lat_fields(send_batch.messages)
        if b1_96 is not None:
          label = f"raw96 b1={b1_96}"
          if b2_96 is not None:
            label += f" b2={b2_96}"
          pending_feedback.append(PendingFeedback(
            due_monotonic=time.monotonic() + 0.60,
            phase72=-1 if phase72 is None else phase72,
            target_delta770=None,
            base_steer770=live_can_state.steer770_deg,
            label=label,
          ))
    raw = pack_batch(send_batch.messages, key_base)
    model, signed_cmd = infer_signed_cmd(send_batch.messages)
    action_model, act_b1, act_b2 = extract_action_model(send_batch.messages)
    phase72, b1_96, _b2_96 = extract_lat_fields(send_batch.messages)
    extra = ""
    if model is not None and signed_cmd is not None:
      extra = (
        f" phase72={model.phase72:>2} b1_96={b1_96:>3} signed_cmd={signed_cmd:+.3f}"
        f" lag_ms={model.best_lag_s*1000:+.0f} conf={model.confidence}"
      )
    elif action_model is not None and act_b1 is not None and act_b2 is not None:
      predicted = predict_action_delta(action_model, act_b1, act_b2)
      extra = (
        f" phase72={action_model.phase72:>2} b1_96={act_b1:>3} b2_96={act_b2:>3}"
        f" pred_d770={predicted:+.3f} dom={action_model.dominant}"
      )
    elif phase72 is not None and b1_96 is not None:
      extra = f" phase72={phase72:>2} b1_96={b1_96:>3}"
    dev.handle.bulkWrite(USB_WRITE_EP, raw, timeout=USB_WRITE_TIMEOUT_MS)
    print(
      f"tx batch={flex_idx:04d} dt={target_s:8.4f}s sched={sched_s:8.4f}s "
      f"lead_ms={lead_s*1000:5.1f} key_base={(key_base if key_base is not None else batch.messages[0].base):3d} "
      f"frames={len(send_batch.messages)} raw_len={len(raw)}{extra}"
    )
    flex_idx += 1

  if feedback_770 and pending_feedback:
    deadline = max(fb.due_monotonic for fb in pending_feedback) + 0.05
    while pending_feedback and time.monotonic() < deadline:
      live_can_state, _ = drain_live_steer770(dev, live_can_state, timeout_ms=20)
      now = time.monotonic()
    while pending_feedback and pending_feedback[0].due_monotonic <= now and live_can_state.steer770_deg is not None:
      fb = pending_feedback.popleft()
      actual = live_can_state.steer770_deg - fb.base_steer770
      if fb.target_delta770 is None:
        print(f"# fb {fb.label} phase72={fb.phase72:>2} actual_d770={actual:+.3f}")
      else:
        err = fb.target_delta770 - actual
        feedback_term = clamp(feedback_kp * err, -2.0, 2.0)
        print(
          f"# fb phase72={fb.phase72:>2} target_d770={fb.target_delta770:+.3f} "
          f"actual_d770={actual:+.3f} err={err:+.3f} corr={feedback_term:+.3f}"
        )


def main() -> int:
  ap = argparse.ArgumentParser(description="Replay raw BMW i3 rlog frames to pico-flexray override transport")
  ap.add_argument("route", nargs="?", help="route dir or rlog.zst path; omit to use latest route")
  ap.add_argument("--serial", default="", help="picoflex USB serial; empty selects first match")
  ap.add_argument("--frame-ids", default=",".join(str(x) for x in DEFAULT_FRAME_IDS))
  ap.add_argument("--sources", default="0", help="comma-separated src filter; empty keeps all sources")
  ap.add_argument("--can-frame-ids", default="", help="comma-separated CAN ids to replay on USB CAN OUT in parallel")
  ap.add_argument("--can-sources", default="2", help="comma-separated src filter for --can-frame-ids; empty keeps all sources")
  ap.add_argument("--can-bus", type=int, default=0, help="host TX bus index encoded in panda CAN header")
  ap.add_argument("--can-limit-batches", type=int, default=0, help="0 means unlimited for CAN event replay")
  ap.add_argument("--speed", type=float, default=1.0, help="timing scale; 2.0 replays 2x faster")
  ap.add_argument("--lead-ms", type=float, default=20.0, help="send overrides this many milliseconds before logged batch time")
  ap.add_argument("--start-sec", type=float, default=None, help="start replay at this many seconds from route start")
  ap.add_argument("--end-sec", type=float, default=None, help="stop replay at this many seconds from route start")
  ap.add_argument("--limit-batches", type=int, default=0, help="0 means unlimited")
  ap.add_argument("--limit-messages", type=int, default=0, help="0 means unlimited")
  ap.add_argument("--preview-batches", type=int, default=8)
  ap.add_argument("--only-phases", default="", help="comma-separated 72.phase filter applied after batch extraction")
  ap.add_argument("--event-stream", action="store_true", help="replay matching CAN events as-is instead of requiring a complete same-event 72/96 batch")
  ap.add_argument("--sequence-center-phases", default="", help="comma-separated 72.phase values used as center events for micro-sequence replay")
  ap.add_argument("--window-before", type=int, default=0, help="when --sequence-center-phases is set, include this many preceding CAN events")
  ap.add_argument("--window-after", type=int, default=0, help="when --sequence-center-phases is set, include this many following CAN events")
  ap.add_argument("--synthesize-96-b1", action="store_true", help="rewrite only byte1 of frame 96 using the phase-local mimic model")
  ap.add_argument("--fixed-signed-cmd", type=float, default=None, help="if set with --synthesize-96-b1, force this normalized command on modeled phases")
  ap.add_argument("--synthesize-96-action", action="store_true", help="rewrite byte1/byte2 of frame 96 using the phase action map fitted against 770")
  ap.add_argument("--target-delta770", type=float, default=None, help="with --synthesize-96-action, target this 600 ms steering delta in degrees on modeled phases")
  ap.add_argument("--scale-delta770", type=float, default=1.0, help="with --synthesize-96-action, scale the predicted 600 ms delta by this factor")
  ap.add_argument("--delta-b1", type=int, default=0, help="after any synthesis step, add this signed offset to 96.byte1")
  ap.add_argument("--delta-b2", type=int, default=0, help="after any synthesis step, add this signed offset to 96.byte2")
  ap.add_argument("--feedback-770", action="store_true", help="close the loop using live 770 feedback from the CAN USB endpoint")
  ap.add_argument("--feedback-kp", type=float, default=0.35, help="proportional correction gain for live 770 feedback")
  ap.add_argument("--diag", action="store_true", help="read injector diagnostics before and after replay")
  ap.add_argument("--no-live-phase-key", action="store_true", help="use route base as injector key instead of live 96 phase")
  ap.add_argument("--run", action="store_true", help="actually transmit; default is dry-run")
  args = ap.parse_args()

  route = args.route
  if route is None:
    latest = resolve_latest_route()
    if latest is None:
      raise FileNotFoundError("no route provided and no routes found in /home/gericho/.comma/media/0/realdata")
    route = str(latest)

  frame_ids = set(parse_csv_ints(args.frame_ids))
  sources = None if not args.sources.strip() else set(parse_csv_ints(args.sources))
  can_frame_ids = set(parse_csv_ints(args.can_frame_ids)) if args.can_frame_ids.strip() else set()
  can_sources = None if not args.can_sources.strip() else set(parse_csv_ints(args.can_sources))
  only_phases = set(parse_csv_ints(args.only_phases)) if args.only_phases.strip() else set()
  sequence_center_phases = set(parse_csv_ints(args.sequence_center_phases)) if args.sequence_center_phases.strip() else set()
  limit_batches = None if args.limit_batches <= 0 else args.limit_batches
  limit_messages = None if args.limit_messages <= 0 else args.limit_messages
  can_limit_batches = None if args.can_limit_batches <= 0 else args.can_limit_batches

  if args.event_stream:
    batches = iter_event_batches(route, frame_ids, sources, limit_batches, args.start_sec, args.end_sec)
    counts = Counter()
    for batch in batches:
      for msg in batch.messages:
        counts[msg.address] += 1
    partial_batches = 0
  elif sequence_center_phases:
    events = iter_event_batches(route, frame_ids, sources, limit_batches, args.start_sec, args.end_sec)
    batches = select_sequence_windows(events, sequence_center_phases, max(args.window_before, 0), max(args.window_after, 0))
    counts = Counter()
    for batch in batches:
      for msg in batch.messages:
        counts[msg.address] += 1
    partial_batches = 0
  else:
    batches, counts, partial_batches = iter_replay_batches(route, frame_ids, sources, limit_batches, limit_messages, args.start_sec, args.end_sec)
    batches = filter_batches_by_phase(batches, only_phases)
  if args.synthesize_96_b1:
    batches = [rewrite_batch_96_b1(batch, args.fixed_signed_cmd) for batch in batches]
  if args.synthesize_96_action:
    batches = [rewrite_batch_96_action(batch, args.target_delta770, args.scale_delta770) for batch in batches]
  if args.delta_b1 or args.delta_b2:
    batches = [perturb_batch_96(batch, args.delta_b1, args.delta_b2) for batch in batches]
  print_summary(route, batches, counts, args.speed, partial_batches)
  can_batches: list[CanReplayBatch] = []
  can_counts: Counter[int] = Counter()
  if can_frame_ids:
    can_batches, can_counts = iter_can_event_batches(route, can_frame_ids, can_sources, can_limit_batches, args.start_sec, args.end_sec)
    print_can_summary(can_batches, can_counts, args.can_bus)
  if only_phases:
    print(f"# only_phases={','.join(str(x) for x in sorted(only_phases))}")
  if args.event_stream:
    print("# event_stream=1")
  if sequence_center_phases:
    print(
      f"# sequence_center_phases={','.join(str(x) for x in sorted(sequence_center_phases))} "
      f"window_before={max(args.window_before, 0)} window_after={max(args.window_after, 0)}"
    )
  if args.start_sec is not None or args.end_sec is not None:
    print(f"# time_window start={args.start_sec} end={args.end_sec}")
  if args.synthesize_96_b1:
    cmd_note = "decoded"
    if args.fixed_signed_cmd is not None:
      cmd_note = f"forced={clamp(args.fixed_signed_cmd, -1.0, 1.0):+.3f}"
    print(f"# synth_96_b1 enabled cmd={cmd_note}")
  if args.synthesize_96_action:
    action_note = f"scale={args.scale_delta770:.3f}"
    if args.target_delta770 is not None:
      action_note = f"target_d770={args.target_delta770:+.3f}"
    print(f"# synth_96_action enabled {action_note}")
  print_preview(batches, args.preview_batches)

  if not batches:
    if can_batches:
      print("# note: no flexray batches, CAN-only replay armed")
    else:
      print("no matching frames found")
      return 1

  if not args.run:
    print("dry-run only; add --run to transmit to pico")
    return 0

  open_picoflex_device, _ = import_usb_helpers()
  dev = open_picoflex_device(args.serial)
  try:
    if args.feedback_770 or can_batches:
      try:
        dev.handle.claimInterface(1)
      except Exception:
        pass
      configure_can_bitrate(dev, bus=2, speed_kbps=500)
    print(f"connected picoflex: {dev.serial}")
    can_before = read_can_health(dev) if args.feedback_770 else None
    if can_before is not None:
      print_can_health("before", can_before)
    diag_before = read_injector_diag(dev) if args.diag else None
    if diag_before is not None:
      print_diag("before", diag_before)
    replay_batches(
      dev,
      batches,
      can_batches,
      args.speed,
      max(args.lead_ms, 0.0) / 1000.0,
      not args.no_live_phase_key,
      args.synthesize_96_action,
      args.feedback_770,
      args.feedback_kp,
      args.can_bus,
    )
    if diag_before is not None:
      time.sleep(0.25)
      diag_after = read_injector_diag(dev)
      print_diag("after", diag_after)
      print_diag_delta(diag_before, diag_after)
    if can_before is not None:
      can_after = read_can_health(dev)
      print_can_health("after", can_after)
  finally:
    dev.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
