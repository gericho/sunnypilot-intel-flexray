#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path

import cereal.messaging as messaging
from openpilot.common.params import Params
from opendbc.can.packer import CANPacker
from opendbc.car import Bus
from opendbc.car.bmw_i3.values import CAR, DBC

POLL_S = 0.05
LAT_PHASE_THRESHOLDS = {
  60: 112.083,
  24: 80.833,
  8: 149.5,
}
LONG_59_CENTER_WB = 32777
LONG_59_CENTER_WC = 32767
LONG_54_CENTER_WB = 65025
LONG_54_CENTER_WC = 7

# Stock-derived templates from 000003c1--ac22d1c806.
# These are not a final TX implementation; they are a route-fit shadow model
# so the next compare is against the right payload family instead of center words.
LONG_TEMPLATES = {
  ("ACC_ARMED", "positive"): {
    54: "3000000000000000000000000000000000",
    59: "0a80fe4d750a7e2fffffffffffffffffff",
    "branch": 59,
    "mode": "positive_or_coast",
  },
  ("ACC_ARMED", "neutral"): {
    54: "2bfffec062846d31b53bc622223dd553ff",
    59: "2b00000000000000000000000000000000",
    "branch": 59,
    "mode": "positive_or_coast",
  },
  ("ACC_ARMED", "blended"): {
    54: "2bfffec062846d31b53bc622223dd553ff",
    59: "2b00000000000000000000000000000000",
    "branch": 54,
    "mode": "blended",
  },
  ("MANAGED", "neutral"): {
    54: "1bfffa46f42d00c046fe582222811338ff",
    59: "1b00000000000000000000000000000000",
    "branch": 59,
    "mode": "positive_or_coast",
  },
  ("MANAGED", "positive"): {
    54: "0a00000000000000000000000000000000",
    59: "0a55fb777c9b7f2fffffffffffffffffff",
    "branch": 59,
    "mode": "positive_or_coast",
  },
  ("MANAGED", "blended"): {
    54: "3bfff3a3301d3cd5806a922222644446ff",
    59: "12a3f9f37fff7f2fffffffffffffffffff",
    "branch": 54,
    "mode": "blended",
  },
  ("MANAGED", "negative"): {
    54: "3bfff3a3301d3cd5806a922222644446ff",
    59: "1e91faed7fff7f2fffffffffffffffffff",
    "branch": 54,
    "mode": "negative",
  },
  ("UNKNOWN", "positive"): {
    54: "2dfc2701fe07007efffffffffffffff594",
    59: "2055f37a8031802fffffffffffffffffff",
    "branch": 59,
    "mode": "positive_or_coast",
  },
  ("UNKNOWN", "neutral"): {
    54: "2dfc2701fe07007efffffffffffffff594",
    59: "2d00000000000000000000000000000000",
    "branch": 59,
    "mode": "positive_or_coast",
  },
  ("UNKNOWN", "blended"): {
    54: "07fffe8ad05ddced1d8b2f2222e88eeeff",
    59: "16c6f4ef7fff7f2fffffffffffffffffff",
    "branch": 54,
    "mode": "blended",
  },
}

LONG_PHASE_TEMPLATES = {
  ("ACC_ARMED", "positive"): {
    54: {
      "0a": "0a00000000000000000000000000000000",
      "31": "31fe2701ff07007efffffffffffffff268",
      "0b": "0bfffc743d4e4a9590c5a32222b99bbbff",
      "07": "07fff11ca60db37c0528192222077110ff",
      "17": "17fffc6fad55bae10c84202222eff11eff",
      "2b": "2bfff2e391999e2bf199042222388ee3ff",
      "0f": "0ffff0d595faa21ef5fa082222caaeecff",
      "38": "3800000000000000000000000000000000",
      "20": "2000000000000000000000000000000000",
      "26": "2600000000000000000000000000000000",
      "30": "3000000000000000000000000000000000",
      "28": "2800000000000000000000000000000000",
      "14": "1400000000000000000000000000000000",
      "1c": "1c00000000000000000000000000000000",
      "0e": "0e00000000000000000000000000000000",
      "34": "3400000000000000000000000000000000",
    },
    59: {
      "0a": "0a80fe4d750a7e2fffffffffffffffffff",
      "30": "306afa5c7eff7f2fffffffffffffffffff",
      "20": "2058faf07ffe7f2fffffffffffffffffff",
      "28": "2877f2037f057f2fffffffffffffffffff",
      "14": "14dcf5837c437d2fffffffffffffffffff",
      "38": "388ff4de7dcd7f2fffffffffffffffffff",
      "19": "1900000000000000000000000000000000",
      "3f": "3f00000000000000000000000000000000",
      "2b": "2b00000000000000000000000000000000",
      "1f": "1f00000000000000000000000000000000",
      "17": "1700000000000000000000000000000000",
      "31": "3100000000000000000000000000000000",
      "0f": "0f00000000000000000000000000000000",
      "07": "0700000000000000000000000000000000",
      "0b": "0b00000000000000000000000000000000",
    },
  },
  ("MANAGED", "neutral"): {
    54: {
      "3d": "3dff2701ff07007ffffffffffffffffbc3",
      "18": "1800000000000000000000000000000000",
      "1e": "1e00000000000000000000000000000000",
      "03": "03fff6ec06d2129759d46b2222955559ff",
      "2b": "2bfff3b6be97cab210e5222222888cc8ff",
      "1c": "1c00000000000000000000000000000000",
      "22": "2200000000000000000000000000000000",
      "1b": "1bfffa46f42d00c046fe582222811338ff",
      "23": "23fffeaf2b46383b8569982222b2266bff",
      "1f": "1ffff78d78b8856ed532e92222911aa9ff",
      "1d": "1d022802fe07007ffffffffffffffff751",
      "0f": "0f00000000000000000000000000000000",
      "27": "2700000000000000000000000000000000",
      "2f": "2f00000000000000000000000000000000",
      "0b": "0b00000000000000000000000000000000",
      "2a": "2a00000000000000000000000000000000",
      "32": "3200000000000000000000000000000000",
      "37": "37fff844d023dc622295342222aeeeeaff",
      "35": "35ff2701ff07007ffffffffffffffffbc3",
      "30": "3000000000000000000000000000000000",
      "06": "0600000000000000000000000000000000",
      "12": "1200000000000000000000000000000000",
      "28": "2800000000000000000000000000000000",
      "3e": "3e00000000000000000000000000000000",
      "20": "2000000000000000000000000000000000",
      "02": "0200000000000000000000000000000000",
      "16": "1600000000000000000000000000000000",
    },
    59: {
      "18": "18ccf00d80ff7f2fffffffffffffffffff",
      "1e": "1e18f11280ff7f2fffffffffffffffffff",
      "03": "0300000000000000000000000000000000",
      "2b": "2b00000000000000000000000000000000",
      "1c": "1cd6f00e80cc7f2fffffffffffffffffff",
      "22": "22a5feee7ffe7f2fffffffffffffffffff",
      "1b": "1b00000000000000000000000000000000",
      "1d": "1d00000000000000000000000000000000",
      "2a": "2a02f2e37ffe7f2fffffffffffffffffff",
      "32": "3228f90080ff7f2fffffffffffffffffff",
      "37": "3700000000000000000000000000000000",
      "35": "3500000000000000000000000000000000",
      "30": "30a9f4e480ff7f2fffffffffffffffffff",
      "28": "2886f78d7fff7f2fffffffffffffffffff",
      "06": "069cf10380ff7f2fffffffffffffffffff",
      "0f": "0f00000000000000000000000000000000",
      "27": "2700000000000000000000000000000000",
      "1f": "1f00000000000000000000000000000000",
      "23": "2300000000000000000000000000000000",
      "2f": "2f00000000000000000000000000000000",
      "0b": "0b00000000000000000000000000000000",
      "3d": "3d00000000000000000000000000000000",
      "3f": "3f00000000000000000000000000000000",
      "3b": "3b00000000000000000000000000000000",
    },
  },
  ("MANAGED", "positive"): {
    54: {
      "0e": "0e00000000000000000000000000000000",
      "18": "1800000000000000000000000000000000",
      "08": "0800000000000000000000000000000000",
      "25": "25fe2701ff07007efffffffffffffff14f",
      "20": "2000000000000000000000000000000000",
      "2a": "2a00000000000000000000000000000000",
    },
    59: {
      "0e": "0eaef37e7fff7f2fffffffffffffffffff",
      "18": "1818f8997fff7f2fffffffffffffffffff",
      "08": "0814f4fd7f31802fffffffffffffffffff",
      "25": "2500000000000000000000000000000000",
      "20": "200af1f97fff7f2fffffffffffffffffff",
      "2a": "2abaf80280ff7f2fffffffffffffffffff",
    },
  },
  ("MANAGED", "blended"): {
    54: {
      "20": "2000000000000000000000000000000000",
      "36": "3600000000000000000000000000000000",
      "2d": "2dfe2701fe07007efffffffffffffffb44",
      "0e": "0e00000000000000000000000000000000",
    },
    59: {
      "20": "202df0ff7fff7f2fffffffffffffffffff",
      "36": "3610fefc7fff7f2fffffffffffffffffff",
      "2d": "2d00000000000000000000000000000000",
      "0e": "0e31f15a7f30802fffffffffffffffffff",
    },
  },
  ("OFF", "positive"): {
    54: {
      "35": "35ca2704fc07007dfffffffffffffffb35",
      "13": "13fffb3f9c39a8e3ed280022229cc889ff",
      "26": "2600000000000000000000000000000000",
      "02": "0200000000000000000000000000000000",
      "04": "0400000000000000000000000000000000",
      "16": "1600000000000000000000000000000000",
      "0a": "0a00000000000000000000000000000000",
      "06": "0600000000000000000000000000000000",
      "38": "3800000000000000000000000000000000",
      "30": "3000000000000000000000000000000000",
      "0f": "0ffff092b991c5760ff7212222c6633cff",
      "3b": "3bfff81ebf37cb1215ab2722225cc555ff",
      "2d": "2df327020108007efffffffffffffff5c8",
      "21": "21062802ff07007ffffffffffffffff679",
      "23": "23fff75fba62c64510c8222222100441ff",
      "2c": "2c00000000000000000000000000000000",
      "0c": "0c00000000000000000000000000000000",
      "00": "0000000000000000000000000000000000",
    },
    59: {
      "35": "3500000000000000000000000000000000",
      "13": "1300000000000000000000000000000000",
      "26": "261df7577dec822fffffffffffffffffff",
      "02": "022bfa56809a7f2fffffffffffffffffff",
      "04": "0456f782816d7e2fffffffffffffffffff",
      "16": "165df4596aff7f2fffffffffffffffffff",
      "0a": "0a01f2e86d97882fffffffffffffffffff",
      "06": "0610f6047ca7852fffffffffffffffffff",
      "38": "38d3f93280ff7f2fffffffffffffffffff",
      "2b": "2b00000000000000000000000000000000",
      "23": "2300000000000000000000000000000000",
      "3b": "3b00000000000000000000000000000000",
      "30": "3074f60382ff7f2fffffffffffffffffff",
      "0f": "0f00000000000000000000000000000000",
      "2d": "2d00000000000000000000000000000000",
      "21": "2100000000000000000000000000000000",
      "00": "00cbfa7681c7802fffffffffffffffffff",
      "17": "1700000000000000000000000000000000",
      "18": "189ff306833b7e2fffffffffffffffffff",
    },
  },
  ("OFF", "blended"): {
    54: {
      "21": "21f22702fc07007efffffffffffffffc86",
      "35": "35012801fe07007ffffffffffffffff145",
    },
    59: {
      "21": "2100000000000000000000000000000000",
      "35": "3500000000000000000000000000000000",
    },
  },
  ("OFF", "negative"): {
    54: {
      "16": "1600000000000000000000000000000000",
      "17": "17fffd87b87fc4690ee1202222899ff8ff",
      "3b": "3bfff587b87fc4690ee12022223cc113ff",
      "37": "37fffd87b87fc4690ee12022227aa007ff",
      "23": "23fff989b87fc46b0ee1202222700227ff",
      "18": "1800000000000000000000000000000000",
      "3e": "3e00000000000000000000000000000000",
      "09": "0906480afe07007ffffffffffffffffc30",
      "30": "3000000000000000000000000000000000",
      "32": "3200000000000000000000000000000000",
      "2e": "2e00000000000000000000000000000000",
      "36": "3600000000000000000000000000000000",
    },
    59: {
      "16": "161cf19282ff7f2fffffffffffffffffff",
      "17": "1700000000000000000000000000000000",
      "3b": "3b00000000000000000000000000000000",
      "37": "3700000000000000000000000000000000",
      "23": "2300000000000000000000000000000000",
      "18": "18def3a482ff7f2fffffffffffffffffff",
      "3e": "3e9afb9282ff7f2fffffffffffffffffff",
      "09": "0900000000000000000000000000000000",
    },
  },
  ("TRANSITION", "positive"): {
    54: {
      "2a": "2a00000000000000000000000000000000",
      "28": "2800000000000000000000000000000000",
      "06": "0600000000000000000000000000000000",
    },
    59: {
      "2a": "2af7f9cb7e94802fffffffffffffffffff",
      "28": "287dfc707fff7f2fffffffffffffffffff",
      "06": "0611fa677fff7f2fffffffffffffffffff",
    },
  },
  ("UNKNOWN", "positive"): {
    54: {
      "3f": "3ffff13cb71bc32909591b2222b22bbbff",
      "09": "09002802ff07007ffffffffffffffff845",
      "18": "1800000000000000000000000000000000",
      "39": "39ff2701ff07007ffffffffffffffffbc3",
      "25": "25fe2701ff07007efffffffffffffff052",
      "0d": "0dff2701fe07007ffffffffffffffff83d",
      "03": "03fff3f3a6d0b2b9f8e80a2222f4499fff",
      "20": "2000000000000000000000000000000000",
      "34": "3400000000000000000000000000000000",
      "21": "21fe2701ff07007efffffffffffffffb9d",
    },
    59: {
      "3f": "3f00000000000000000000000000000000",
      "09": "0900000000000000000000000000000000",
      "18": "18a7fa3180ff7f2fffffffffffffffffff",
      "39": "3900000000000000000000000000000000",
      "25": "2500000000000000000000000000000000",
      "0d": "0d00000000000000000000000000000000",
      "03": "0300000000000000000000000000000000",
      "20": "20e9fb0c80fe7f2fffffffffffffffffff",
      "34": "34fcf60480cc7f2fffffffffffffffffff",
      "21": "2100000000000000000000000000000000",
    },
  },
  ("UNKNOWN", "neutral"): {
    54: {
      "21": "21fe2701fe07007efffffffffffffff7d8",
      "2c": "2c00000000000000000000000000000000",
      "3f": "3ffff1fa13e01fc46604792222f3366fff",
    },
    59: {
      "21": "2100000000000000000000000000000000",
      "2c": "2ca4fb0080ff7f2fffffffffffffffffff",
      "3f": "3f00000000000000000000000000000000",
    },
  },
}

# Fine-state templates derived from route-backed shadow logs. These are more
# stable than coarse (mode,intent) buckets for long payload families.
LONG_FINE_PHASE_TEMPLATES = {
  "ACC_ARMED_POSITIVE_PULL": {
    54: {
      "0b": "0bfff915be8bd4d04ab26a2222088000ff",
      "34": "3400000000000000000000000000000000",
      "1c": "1c00000000000000000000000000000000",
      "11": "11f12702ff07007efffffffffffffffaf3",
      "07": "07fff376b9eecf224607662222655ff6ff",
      "3b": "3bfffaf8100427769cdfbb2222feebbfff",
      "33": "33fff90d22cb37adadcccc2222faaddfff",
      "1d": "1df62702fe07007efffffffffffffff144",
    },
    59: {
      "0b": "0b00000000000000000000000000000000",
      "34": "347cf74b7dff7f2fffffffffffffffffff",
      "1c": "1c12fe357fc0812fffffffffffffffffff",
      "11": "1100000000000000000000000000000000",
      "07": "0700000000000000000000000000000000",
      "3b": "3b00000000000000000000000000000000",
      "33": "3300000000000000000000000000000000",
      "1d": "1d00000000000000000000000000000000",
    },
  },
  "ACC_ARMED_POSITIVE_LOW": {
    54: {
      "17": "17fff10c317246c5bc90db2222accffaff",
      "37": "37fff41dbb93d1f24388632222dbb44dff",
      "39": "39f92701ff07007efffffffffffffff6bd",
      "2f": "2ffffe9407ed1d0393b7b22222f88aafff",
    },
    59: {
      "17": "1700000000000000000000000000000000",
      "37": "3700000000000000000000000000000000",
      "39": "3900000000000000000000000000000000",
      "2f": "2f00000000000000000000000000000000",
    },
  },
  "ACC_ARMED_NEGATIVE_BRAKE_HOLD": {
    54: {
      "3d": "3d0c480af507007ffffffffffffffff1f2",
    },
    59: {
      "3d": "3d00000000000000000000000000000000",
    },
  },
  "MANAGED_NEUTRAL_IDLE": {
    54: {
      "31": "31fe2701fe07007efffffffffffffff196",
      "2b": "2bfff82d88989e87145c342222577995ff",
      "07": "07fffa51a8c2bede34be542222855cc8ff",
      "32": "3200000000000000000000000000000000",
      "16": "1600000000000000000000000000000000",
      "0a": "0a00000000000000000000000000000000",
      "25": "25fe2701fe07007efffffffffffffffc17",
      "1d": "1dfd2701fe07007efffffffffffffffe60",
      "0d": "0dff2701fe07007ffffffffffffffff1c8",
      "2a": "2a00000000000000000000000000000000",
      "24": "2400000000000000000000000000000000",
      "3c": "3c00000000000000000000000000000000",
      "2e": "2e00000000000000000000000000000000",
      "26": "2600000000000000000000000000000000",
      "1c": "1c00000000000000000000000000000000",
      "10": "1000000000000000000000000000000000",
      "22": "2200000000000000000000000000000000",
      "05": "05002801fe07007ffffffffffffffff17e",
      "33": "33fffed4ae4cc5653b4a5b22229bbdd9ff",
      "15": "15fe2701ff07007efffffffffffffffcce",
      "3d": "3dff2701fe07007ffffffffffffffff83d",
      "30": "3000000000000000000000000000000000",
      "2d": "2dff2701ff07007ffffffffffffffff32b",
      "28": "2800000000000000000000000000000000",
      "1e": "1e00000000000000000000000000000000",
      "18": "1800000000000000000000000000000000",
      "02": "0200000000000000000000000000000000",
      "2f": "2ffff4695f2476abe99e092222588005ff",
      "29": "29ff2701ff07007ffffffffffffffffade",
      "1b": "1bfffbc8e48dfb026eed8d22226dd886ff",
      "0f": "0ffff44b32024921bc0ddc2222877dd8ff",
      "21": "21ff2701ff07007ffffffffffffffff642",
      "3a": "3a00000000000000000000000000000000",
      "36": "3600000000000000000000000000000000",
      "14": "1400000000000000000000000000000000",
      "12": "1200000000000000000000000000000000",
      "0b": "0bfffdfca39dbacf2eb34e2222666446ff",
      "06": "0600000000000000000000000000000000",
      "04": "0400000000000000000000000000000000",
    },
    59: {
      "31": "3100000000000000000000000000000000",
      "2b": "2b00000000000000000000000000000000",
      "07": "0700000000000000000000000000000000",
      "16": "160ff4e47fff7f2fffffffffffffffffff",
      "32": "3253f9c67fff7f2fffffffffffffffffff",
      "37": "3700000000000000000000000000000000",
      "01": "0100000000000000000000000000000000",
      "25": "2500000000000000000000000000000000",
      "1d": "1d00000000000000000000000000000000",
      "0a": "0ab6f70980ff7f2fffffffffffffffffff",
      "0d": "0d00000000000000000000000000000000",
      "2a": "2a5cfad67fcd7f2fffffffffffffffffff",
      "39": "3900000000000000000000000000000000",
      "23": "2300000000000000000000000000000000",
      "24": "24a2f7ba7fff7f2fffffffffffffffffff",
      "3c": "3c10f9af7fff7f2fffffffffffffffffff",
      "26": "262af67880ff7f2fffffffffffffffffff",
      "1c": "1cb2f1a27fff7f2fffffffffffffffffff",
      "10": "1032f8dd7fff7f2fffffffffffffffffff",
      "2e": "2e7df3cb7fff7f2fffffffffffffffffff",
      "33": "3300000000000000000000000000000000",
      "27": "2700000000000000000000000000000000",
      "15": "1500000000000000000000000000000000",
      "05": "0500000000000000000000000000000000",
      "22": "22c0f7907fff7f2fffffffffffffffffff",
      "3d": "3d00000000000000000000000000000000",
      "2f": "2f00000000000000000000000000000000",
      "2d": "2d00000000000000000000000000000000",
      "29": "2900000000000000000000000000000000",
      "1b": "1b00000000000000000000000000000000",
      "18": "18b1f9cd7fcd7f2fffffffffffffffffff",
      "0f": "0f00000000000000000000000000000000",
      "02": "0294f20f80ff7f2fffffffffffffffffff",
      "28": "2840feef7fff7f2fffffffffffffffffff",
      "30": "30a8f40b80ff7f2fffffffffffffffffff",
      "1e": "1e1ff2fc7fff7f2fffffffffffffffffff",
      "36": "364af7f27fff7f2fffffffffffffffffff",
      "14": "14a2f6a77fff7f2fffffffffffffffffff",
      "06": "06cefd078031802fffffffffffffffffff",
      "04": "0415fd397f377f2fffffffffffffffffff",
      "3a": "3a8af22a80ff7f2fffffffffffffffffff",
      "21": "2100000000000000000000000000000000",
      "0b": "0b00000000000000000000000000000000",
    },
  },
}


def latest(sock):
  msgs = messaging.drain_sock(sock, wait_for_one=False)
  return msgs[-1] if msgs else None


def ema(prev, value, alpha=0.25):
  if value is None:
    return prev
  if prev is None:
    return float(value)
  return (1.0 - alpha) * float(prev) + alpha * float(value)


def infer_long_intent(gas_pct, brake_pct):
  gas_pct = 0.0 if gas_pct is None else float(gas_pct)
  brake_pct = 0.0 if brake_pct is None else float(brake_pct)
  if gas_pct < 0.02 and brake_pct < 0.02:
    return "neutral", 0.0
  if gas_pct > brake_pct + 0.05:
    return "positive", min(1.0, gas_pct)
  if brake_pct > gas_pct + 0.03:
    return "negative", min(1.0, brake_pct)
  return "blended", min(1.0, abs(gas_pct - brake_pct) + max(gas_pct, brake_pct) * 0.5)


def parse_word_fields(payload_hex):
  dat = bytes.fromhex(payload_hex)
  return {
    "wb": dat[0] | (dat[1] << 8) if len(dat) >= 2 else 0,
    "wc": dat[2] | (dat[3] << 8) if len(dat) >= 4 else 0,
  }


def merge_phase_byte(template_hex, stock_hex):
  if not stock_hex or len(stock_hex) < 2:
    return template_hex
  return stock_hex[:2] + template_hex[2:]


def apply_phase_template(template_hex, stock_hex, bucket, branch, fine_state=None):
  if not stock_hex or len(stock_hex) < 2:
    return template_hex
  phase = stock_hex[:2]
  if fine_state is not None:
    override = LONG_FINE_PHASE_TEMPLATES.get(fine_state, {}).get(branch, {}).get(phase)
    if override is not None:
      return override
  override = LONG_PHASE_TEMPLATES.get(bucket, {}).get(branch, {}).get(phase)
  if override is not None:
    return override
  return merge_phase_byte(template_hex, stock_hex)


def shadow_long_tx_hint(desired_accel, acc_mode, long_intent):
  desired_accel = float(desired_accel)
  template = LONG_TEMPLATES.get((acc_mode, long_intent))
  if template is None:
    template = LONG_TEMPLATES.get(("UNKNOWN", long_intent))
  if template is None:
    if desired_accel < -0.05:
      template = {
        54: "1c00000000000000000000000000000000",
        59: "1b00000000000000000000000000000000",
        "branch": 54,
        "mode": "negative",
      }
    else:
      template = {
        54: "1c00000000000000000000000000000000",
        59: "1cbcf1b590dc7c2fffffffffffffffffff",
        "branch": 59,
        "mode": "positive_or_coast",
      }
  f54 = parse_word_fields(template[54])
  f59 = parse_word_fields(template[59])
  return {
    "tx_mode": template["mode"],
    "tx_branch": template["branch"],
    "tx_target_wb": f54["wb"] if template["branch"] == 54 else f59["wb"],
    "tx_target_wc": f54["wc"] if template["branch"] == 54 else f59["wc"],
    "tx54": template[54],
    "tx59": template[59],
  }


def mode_from_state(gate, state):
  if gate is None or state is None:
    return "UNKNOWN"
  if gate == 643 and state == 35041:
    return "OFF"
  if gate == 3584 and state == 16610:
    return "ACC_ARMED"
  if gate in (640, 656) and state == 24802:
    return "MANAGED"
  if state == 26850:
    return "TRANSITION"
  return "UNKNOWN"


def fine_long_state(acc_mode, long_intent, gas_ema, brake_ema, fr1_54, fr1_59):
  gas = 0.0 if gas_ema is None else float(gas_ema)
  brake = 0.0 if brake_ema is None else float(brake_ema)
  phase = ""
  if fr1_59:
    phase = fr1_59[:2]
  elif fr1_54:
    phase = fr1_54[:2]

  gas_bin = round(gas / 0.05) * 0.05
  brake_bin = round(brake / 0.05) * 0.05

  if acc_mode == "ACC_ARMED" and long_intent == "negative" and phase == "3d":
    return "ACC_ARMED_NEGATIVE_BRAKE_HOLD", gas_bin, brake_bin
  if acc_mode == "ACC_ARMED" and long_intent == "positive":
    if gas_bin >= 0.35:
      return "ACC_ARMED_POSITIVE_PULL", gas_bin, brake_bin
    return "ACC_ARMED_POSITIVE_LOW", gas_bin, brake_bin
  if acc_mode == "ACC_ARMED" and long_intent == "neutral":
    return "ACC_ARMED_NEUTRAL", gas_bin, brake_bin
  if acc_mode == "ACC_ARMED" and long_intent == "blended":
    return "ACC_ARMED_BLENDED", gas_bin, brake_bin

  if acc_mode == "MANAGED" and long_intent == "neutral":
    if brake_bin <= 0.0 and gas_bin <= 0.0:
      return "MANAGED_NEUTRAL_IDLE", gas_bin, brake_bin
    return "MANAGED_NEUTRAL_EDGE", gas_bin, brake_bin
  if acc_mode == "MANAGED" and long_intent == "positive":
    return "MANAGED_POSITIVE", gas_bin, brake_bin
  if acc_mode == "MANAGED" and long_intent == "blended":
    return "MANAGED_BLENDED", gas_bin, brake_bin
  if acc_mode == "MANAGED" and long_intent == "negative":
    return "MANAGED_NEGATIVE", gas_bin, brake_bin

  if acc_mode == "OFF" and long_intent == "positive":
    return "OFF_POSITIVE", gas_bin, brake_bin
  if acc_mode == "OFF" and long_intent == "negative":
    return "OFF_NEGATIVE", gas_bin, brake_bin
  if acc_mode == "OFF" and long_intent == "blended":
    return "OFF_BLENDED", gas_bin, brake_bin
  if acc_mode == "OFF" and long_intent == "neutral":
    return "OFF_NEUTRAL", gas_bin, brake_bin

  if acc_mode == "TRANSITION":
    return "TRANSITION", gas_bin, brake_bin
  return f"{acc_mode}_{long_intent}".upper(), gas_bin, brake_bin


def infer_lat_direction(phase, b1):
  thr = LAT_PHASE_THRESHOLDS.get(phase)
  if thr is None or b1 is None:
    return "unknown", "none"
  if phase == 60:
    return ("right", "high") if b1 > thr else ("left", "high")
  if phase in (24, 8):
    return ("right", "medium") if b1 > thr else ("left", "medium")
  return "unknown", "none"


def infer_lat_mag(phase, b1):
  thr = LAT_PHASE_THRESHOLDS.get(phase)
  if thr is None or b1 is None:
    return 0.0, "none"
  if phase == 60:
    return min(1.0, abs(float(b1) - thr) / 110.0), "high"
  if phase == 24:
    return min(1.0, abs(float(b1) - thr) / 135.0), "low"
  if phase == 8:
    return min(1.0, abs(float(b1) - thr) / 90.0), "low"
  return 0.0, "none"


def current_route_name(params: Params):
  v = params.get("CurrentRoute")
  if not v:
    return None
  if isinstance(v, bytes):
    return v.decode("utf-8", errors="ignore")
  return str(v)


def current_segment_dir(root: Path, route_name: str):
  candidates = []
  prefix = f"{route_name}--"
  for p in root.glob(f"{route_name}--*"):
    if not p.is_dir():
      continue
    try:
      seg = int(p.name.split("--")[-1])
    except ValueError:
      continue
    candidates.append((seg, p))
  if not candidates:
    return None
  candidates.sort(key=lambda x: x[0])
  return candidates[-1][1]


def resolve_output_path(params: Params, root: Path, fallback: Path):
  route_name = current_route_name(params)
  if route_name is None:
    return fallback
  seg_dir = current_segment_dir(root, route_name)
  if seg_dir is None:
    return fallback
  out_dir = seg_dir / "bmw_i3_shadow"
  out_dir.mkdir(parents=True, exist_ok=True)
  return out_dir / "rlog.jsonl"


def open_output(current_file, current_path, new_path: Path):
  if current_path == new_path and current_file is not None:
    return current_file, current_path
  if current_file is not None:
    current_file.close()
  new_path.parent.mkdir(parents=True, exist_ok=True)
  return new_path.open("a", buffering=1), new_path


def main() -> None:
  parser = argparse.ArgumentParser(description="BMW i3 background shadow logger")
  parser.add_argument("--addr", default="127.0.0.1")
  parser.add_argument("--out", required=True)
  parser.add_argument("--interval", type=float, default=0.2)
  parser.add_argument("--root", default=os.path.expanduser("~/.comma/media/0/realdata"))
  args = parser.parse_args()

  if args.addr != "127.0.0.1":
    messaging.reset_context()

  params = Params()
  root = Path(args.root)
  fallback_path = Path(args.out)
  fallback_path.parent.mkdir(parents=True, exist_ok=True)
  packer = CANPacker(DBC[CAR.BMW_I3_EXPERIMENTAL][Bus.pt])

  carstate_sock = messaging.sub_sock("carState", addr=args.addr, conflate=True)
  panda_sock = messaging.sub_sock("pandaStates", addr=args.addr, conflate=True)
  can_sock = messaging.sub_sock("can", addr=args.addr, conflate=True)
  controlsstate_sock = messaging.sub_sock("controlsState", addr=args.addr, conflate=True)
  carcontrol_sock = messaging.sub_sock("carControl", addr=args.addr, conflate=True)
  longplan_sock = messaging.sub_sock("longitudinalPlan", addr=args.addr, conflate=True)
  longplan_sp_sock = messaging.sub_sock("longitudinalPlanSP", addr=args.addr, conflate=True)
  carcontrol_sp_sock = messaging.sub_sock("carControlSP", addr=args.addr, conflate=True)

  cs = None
  controls_state = None
  car_control = None
  long_plan = None
  long_plan_sp = None
  car_control_sp = None
  panda_count = 0
  gas217_word23 = None
  brake538_b0 = None
  brake239_word23 = None
  brake239_word56 = None
  turn502_raw = None
  cruise415_raw = None
  blink274_raw = None
  seatbelt435_raw = None
  seatbelt663_raw = None
  door481_raw = None
  steer770_raw = None
  fr0_72 = None
  fr0_96 = None
  fr0_131 = None
  fr0_135 = None
  fr1_54 = None
  fr1_59 = None
  fr1_97 = None
  fr1_112 = None
  fr1_116 = None
  fr1_275 = None
  fr1_2e = None
  fr1_31 = None
  fr1_37 = None
  fr1_38 = None
  fr1_3f = None
  fr1_5d = None
  gas_ema = None
  brake_ema = None
  last_write = 0.0
  out_file = None
  out_path = None

  try:
    while True:
      m = latest(carstate_sock)
      if m is not None:
        cs = m.carState

      m = latest(panda_sock)
      if m is not None:
        panda_count = len(m.pandaStates)

      m = latest(controlsstate_sock)
      if m is not None:
        controls_state = m.controlsState

      m = latest(carcontrol_sock)
      if m is not None:
        car_control = m.carControl

      m = latest(longplan_sock)
      if m is not None:
        long_plan = m.longitudinalPlan

      m = latest(longplan_sp_sock)
      if m is not None:
        long_plan_sp = m.longitudinalPlanSP

      m = latest(carcontrol_sp_sock)
      if m is not None:
        car_control_sp = m.carControlSP

      can_msgs = messaging.drain_sock(can_sock, wait_for_one=False)
      if can_msgs:
        for pkt in can_msgs:
          for msg in pkt.can:
            dat = bytes(msg.dat)
            if msg.src == 2 and msg.address == 217 and len(dat) >= 4:
              gas217_word23 = dat[2] | (dat[3] << 8)
            elif msg.src == 2 and msg.address == 538 and len(dat) >= 1:
              brake538_b0 = dat[0]
            elif msg.src == 2 and msg.address == 239 and len(dat) >= 7:
              brake239_word23 = dat[2] | (dat[3] << 8)
              brake239_word56 = dat[5] | (dat[6] << 8)
            elif msg.src == 2 and msg.address == 502 and len(dat) >= 2:
              turn502_raw = dat[0] | (dat[1] << 8)
            elif msg.src == 2 and msg.address == 415 and len(dat) >= 2:
              cruise415_raw = dat.hex()
            elif msg.src == 2 and msg.address == 274 and len(dat) >= 2:
              blink274_raw = dat.hex()
            elif msg.src == 2 and msg.address == 435 and len(dat) >= 5:
              seatbelt435_raw = dat.hex()
            elif msg.src == 2 and msg.address == 663 and len(dat) >= 3:
              seatbelt663_raw = dat.hex()
            elif msg.src == 2 and msg.address == 481 and len(dat) >= 3:
              door481_raw = dat.hex()
            elif msg.src == 2 and msg.address == 770 and len(dat) >= 2:
              steer770_raw = dat.hex()
            elif msg.src == 0 and msg.address == 72 and len(dat) >= 9:
              fr0_72 = dat.hex()
            elif msg.src == 0 and msg.address == 96 and len(dat) >= 9:
              fr0_96 = dat.hex()
            elif msg.src == 0 and msg.address == 131 and len(dat) >= 9:
              fr0_131 = dat.hex()
            elif msg.src == 0 and msg.address == 135 and len(dat) >= 9:
              fr0_135 = dat.hex()
            elif msg.src == 1 and msg.address == 46 and len(dat) >= 9:
              fr1_2e = dat.hex()
            elif msg.src == 1 and msg.address == 49 and len(dat) >= 9:
              fr1_31 = dat.hex()
            elif msg.src == 1 and msg.address == 54 and len(dat) >= 9:
              fr1_54 = dat.hex()
            elif msg.src == 1 and msg.address == 55 and len(dat) >= 9:
              fr1_37 = dat.hex()
            elif msg.src == 1 and msg.address == 56 and len(dat) >= 9:
              fr1_38 = dat.hex()
            elif msg.src == 1 and msg.address == 59 and len(dat) >= 9:
              fr1_59 = dat.hex()
            elif msg.src == 1 and msg.address == 63 and len(dat) >= 9:
              fr1_3f = dat.hex()
            elif msg.src == 1 and msg.address == 93 and len(dat) >= 9:
              fr1_5d = dat.hex()
            elif msg.src == 1 and msg.address == 97 and len(dat) >= 9:
              fr1_97 = dat.hex()
            elif msg.src == 1 and msg.address == 112 and len(dat) >= 9:
              fr1_112 = dat.hex()
            elif msg.src == 1 and msg.address == 116 and len(dat) >= 9:
              fr1_116 = dat.hex()
            elif msg.src == 1 and msg.address == 275 and len(dat) >= 9:
              fr1_275 = dat.hex()

      now = time.monotonic()
      if now - last_write < args.interval:
        time.sleep(POLL_S)
        continue

      active_out = resolve_output_path(params, root, fallback_path)
      out_file, out_path = open_output(out_file, out_path, active_out)

      gas217_value = None if gas217_word23 is None else min(4000, max(0, gas217_word23 - 4096))
      gas217_pct = None if gas217_value is None else gas217_value / 4000.0
      brake239_delta = None if brake239_word56 is None else max(0, 32000 - brake239_word56)
      brake239_pct = None if brake239_delta is None else min(1.0, brake239_delta / 2060.0)

      gas_ema = ema(gas_ema, gas217_pct)
      brake_ema = ema(brake_ema, brake239_pct)
      long_mode, long_conf = infer_long_intent(gas_ema, brake_ema)
      lat_phase = None
      lat_b1 = None
      lat_b2 = None
      lat_b3 = None
      if fr0_96 is not None:
        d = bytes.fromhex(fr0_96)
        lat_phase, lat_b1, lat_b2, lat_b3 = d[0], d[1], d[2], d[3]
      lat_dir, lat_dir_conf = infer_lat_direction(lat_phase, lat_b1)
      lat_mag, lat_mag_conf = infer_lat_mag(lat_phase, lat_b1)
      lat_helper_active = None
      if fr1_112 is not None:
        d112 = bytes.fromhex(fr1_112)
        lat_helper_active = (d112[5] & 0x20) == 0 if len(d112) > 5 else None
      gate131 = None
      state135 = None
      if fr0_131 is not None:
        d131 = bytes.fromhex(fr0_131)
        if len(d131) > 6:
          gate131 = d131[5] | (d131[6] << 8)
      if fr0_135 is not None:
        d135 = bytes.fromhex(fr0_135)
        if len(d135) > 6:
          state135 = d135[5] | (d135[6] << 8)
      acc_mode = mode_from_state(gate131, state135)
      fine_state, gas_bin, brake_bin = fine_long_state(acc_mode, long_mode, gas_ema, brake_ema, fr1_54, fr1_59)
      desired_accel = 0.0 if car_control is None else float(car_control.actuators.accel)
      shadow_long = shadow_long_tx_hint(desired_accel, acc_mode, long_mode)
      bucket = (acc_mode, long_mode)
      shadow_54_bytes = apply_phase_template(shadow_long["tx54"], fr1_54, bucket, 54, fine_state)
      shadow_59_bytes = apply_phase_template(shadow_long["tx59"], fr1_59, bucket, 59, fine_state)
      acc_active = acc_mode in ("ACC_ARMED", "MANAGED")
      lat_active = (acc_mode == "MANAGED") and bool(lat_helper_active)
      tja_active = lat_active

      row = {
        "ts_wall": time.time(),
        "ts_mono": now,
        "route_out": str(out_path),
        "panda_count": panda_count,
        "gas217_word23": gas217_word23,
        "gas217_value": gas217_value,
        "gas217_pct": gas217_pct,
        "gas217_pct_ema": gas_ema,
        "brake538_b0": brake538_b0,
        "brake239_word23": brake239_word23,
        "brake239_word56": brake239_word56,
        "brake239_delta": brake239_delta,
        "brake239_pct": brake239_pct,
        "brake239_pct_ema": brake_ema,
        "turn502_raw": turn502_raw,
        "cruise415_raw": cruise415_raw,
        "blink274_raw": blink274_raw,
        "seatbelt435_raw": seatbelt435_raw,
        "seatbelt663_raw": seatbelt663_raw,
        "door481_raw": door481_raw,
        "steer770_raw": steer770_raw,
        "stock_long_intent": long_mode,
        "stock_long_intent_confidence": long_conf,
        "stock_long_state_fine": fine_state,
        "stock_long_gas_bin": gas_bin,
        "stock_long_brake_bin": brake_bin,
        "shadow_long_desired_accel": desired_accel,
        "shadow_long_tx_mode": shadow_long["tx_mode"],
        "shadow_long_tx_branch": shadow_long["tx_branch"],
        "shadow_long_tx_target_wb": shadow_long["tx_target_wb"],
        "shadow_long_tx_target_wc": shadow_long["tx_target_wc"],
        "shadow_long_tx54": shadow_54_bytes,
        "shadow_long_tx59": shadow_59_bytes,
        "stock_acc_gate131": gate131,
        "stock_acc_state135": state135,
        "stock_acc_mode": acc_mode,
        "stock_acc_active": acc_active,
        "stock_tja_active": tja_active,
        "stock_lat_helper_active": lat_helper_active,
        "stock_lat_active": lat_active,
        "stock_lat_phase": lat_phase,
        "stock_lat_b1": lat_b1,
        "stock_lat_b2": lat_b2,
        "stock_lat_b3": lat_b3,
        "stock_lat_direction": lat_dir,
        "stock_lat_direction_confidence": lat_dir_conf,
        "stock_lat_magnitude": lat_mag,
        "stock_lat_magnitude_confidence": lat_mag_conf,
        "fr0_72": fr0_72,
        "fr0_96": fr0_96,
        "fr0_131": fr0_131,
        "fr0_135": fr0_135,
        "fr1_2e": fr1_2e,
        "fr1_31": fr1_31,
        "fr1_37": fr1_37,
        "fr1_38": fr1_38,
        "fr1_3f": fr1_3f,
        "fr1_54": fr1_54,
        "fr1_59": fr1_59,
        "fr1_5d": fr1_5d,
        "fr1_97": fr1_97,
        "fr1_112": fr1_112,
        "fr1_116": fr1_116,
        "fr1_275": fr1_275,
      }
      if controls_state is not None:
        row.update({
          "op_long_control_state": str(controls_state.longControlState),
          "op_up_accel_cmd": float(controls_state.upAccelCmd),
          "op_ui_accel_cmd": float(controls_state.uiAccelCmd),
          "op_uf_accel_cmd": float(controls_state.ufAccelCmd),
          "op_curvature": float(controls_state.curvature),
          "op_desired_curvature": float(controls_state.desiredCurvature),
          "op_force_decel": bool(controls_state.forceDecel),
        })
        try:
          row["op_v_cruise_cluster_kph"] = float(controls_state.vCruiseCluster)
        except Exception:
          pass
        try:
          row["op_v_cruise_kph"] = float(controls_state.vCruise)
        except Exception:
          pass
        lat_state = controls_state.lateralControlState.which()
        row["op_lat_control_state"] = lat_state
        if lat_state == "angleState":
          s = controls_state.lateralControlState.angleState
          row.update({
            "op_lat_active": bool(s.active),
            "op_lat_output": float(s.output),
            "op_lat_saturated": bool(s.saturated),
            "op_lat_steering_angle_deg": float(s.steeringAngleDeg),
            "op_lat_steering_angle_desired_deg": float(s.steeringAngleDesiredDeg),
          })
        elif lat_state == "torqueState":
          s = controls_state.lateralControlState.torqueState
          row.update({
            "op_lat_active": bool(s.active),
            "op_lat_output": float(s.output),
            "op_lat_saturated": bool(s.saturated),
            "op_lat_error": float(s.error),
            "op_lat_error_rate": float(s.errorRate),
            "op_lat_actual_lateral_accel": float(s.actualLateralAccel),
            "op_lat_desired_lateral_accel": float(s.desiredLateralAccel),
            "op_lat_desired_lateral_jerk": float(s.desiredLateralJerk),
          })
        elif lat_state == "pidState":
          s = controls_state.lateralControlState.pidState
          row.update({
            "op_lat_active": bool(s.active),
            "op_lat_output": float(s.output),
            "op_lat_saturated": bool(s.saturated),
            "op_lat_steering_angle_deg": float(s.steeringAngleDeg),
            "op_lat_steering_angle_desired_deg": float(s.steeringAngleDesiredDeg),
            "op_lat_p": float(s.p),
            "op_lat_i": float(s.i),
            "op_lat_f": float(s.f),
          })
      if car_control is not None:
        row.update({
          "op_enabled": bool(car_control.enabled),
          "op_lat_enabled": bool(car_control.latActive),
          "op_long_enabled": bool(car_control.longActive),
          "op_left_blinker_cmd": bool(car_control.leftBlinker),
          "op_right_blinker_cmd": bool(car_control.rightBlinker),
          "op_current_curvature": float(car_control.currentCurvature),
          "op_actuators_torque": float(car_control.actuators.torque),
          "op_actuators_steering_angle_deg": float(car_control.actuators.steeringAngleDeg),
          "op_actuators_curvature": float(car_control.actuators.curvature),
          "op_actuators_accel": float(car_control.actuators.accel),
          "op_actuators_speed": float(car_control.actuators.speed),
          "op_actuators_long_state": str(car_control.actuators.longControlState),
          "op_actuators_gas": float(car_control.actuators.gas),
          "op_actuators_brake": float(car_control.actuators.brake),
        })
      if long_plan is not None:
        row.update({
          "op_long_has_lead": bool(long_plan.hasLead),
          "op_long_fcw": bool(long_plan.fcw),
          "op_long_plan_source": str(long_plan.longitudinalPlanSource),
          "op_long_a_target": float(long_plan.aTarget),
          "op_long_should_stop": bool(long_plan.shouldStop),
          "op_long_allow_throttle": bool(long_plan.allowThrottle),
          "op_long_allow_brake": bool(long_plan.allowBrake),
        })
      if long_plan_sp is not None:
        row.update({
          "op_sp_long_source": str(long_plan_sp.longitudinalPlanSource),
          "op_sp_v_target": float(long_plan_sp.vTarget),
          "op_sp_a_target": float(long_plan_sp.aTarget),
          "op_sp_dec_enabled": bool(long_plan_sp.dec.enabled),
          "op_sp_dec_active": bool(long_plan_sp.dec.active),
          "op_sp_dec_state": str(long_plan_sp.dec.state),
          "op_sp_scc_vision_enabled": bool(long_plan_sp.smartCruiseControl.vision.enabled),
          "op_sp_scc_vision_active": bool(long_plan_sp.smartCruiseControl.vision.active),
          "op_sp_scc_vision_state": str(long_plan_sp.smartCruiseControl.vision.state),
          "op_sp_scc_vision_v_target": float(long_plan_sp.smartCruiseControl.vision.vTarget),
          "op_sp_scc_vision_a_target": float(long_plan_sp.smartCruiseControl.vision.aTarget),
          "op_sp_scc_map_enabled": bool(long_plan_sp.smartCruiseControl.map.enabled),
          "op_sp_scc_map_active": bool(long_plan_sp.smartCruiseControl.map.active),
          "op_sp_scc_map_state": str(long_plan_sp.smartCruiseControl.map.state),
          "op_sp_scc_map_v_target": float(long_plan_sp.smartCruiseControl.map.vTarget),
          "op_sp_scc_map_a_target": float(long_plan_sp.smartCruiseControl.map.aTarget),
          "op_sp_speed_limit_active": bool(long_plan_sp.speedLimit.assist.active),
          "op_sp_speed_limit_state": str(long_plan_sp.speedLimit.assist.state),
          "op_sp_speed_limit_v_target": float(long_plan_sp.speedLimit.assist.vTarget),
          "op_sp_speed_limit_a_target": float(long_plan_sp.speedLimit.assist.aTarget),
        })
      if car_control_sp is not None:
        row.update({
          "op_sp_mads_enabled": bool(car_control_sp.mads.enabled),
          "op_sp_mads_active": bool(car_control_sp.mads.active),
          "op_sp_mads_available": bool(car_control_sp.mads.available),
          "op_sp_mads_state": str(car_control_sp.mads.state),
          "op_sp_icbm_state": str(car_control_sp.intelligentCruiseButtonManagement.state),
          "op_sp_icbm_send_button": str(car_control_sp.intelligentCruiseButtonManagement.sendButton),
          "op_sp_icbm_v_target": float(car_control_sp.intelligentCruiseButtonManagement.vTarget),
        })
      if cs is not None:
        row.update({
          "gear": str(cs.gearShifter),
          "vEgo": float(cs.vEgo),
          "vEgoRaw": float(cs.vEgoRaw),
          "vEgoCluster": float(cs.vEgoCluster),
          "aEgo": float(cs.aEgo),
          "steeringAngleDeg": float(cs.steeringAngleDeg),
          "steeringTorque": float(cs.steeringTorque),
          "steeringPressed": bool(cs.steeringPressed),
          "yawRate": float(cs.yawRate),
          "wheelSpeedFL": float(cs.wheelSpeeds.fl),
          "wheelSpeedFR": float(cs.wheelSpeeds.fr),
          "wheelSpeedRL": float(cs.wheelSpeeds.rl),
          "wheelSpeedRR": float(cs.wheelSpeeds.rr),
          "leftBlinker": bool(cs.leftBlinker),
          "rightBlinker": bool(cs.rightBlinker),
          "seatbeltUnlatched": bool(cs.seatbeltUnlatched),
          "doorOpen": bool(cs.doorOpen),
          "gasPressed": bool(cs.gasPressed),
          "brakePressed": bool(cs.brakePressed),
          "cruiseAvailable": bool(cs.cruiseState.available),
          "cruiseEnabled": bool(cs.cruiseState.enabled),
          "cruiseStandstill": bool(cs.cruiseState.standstill),
          "standstill": bool(cs.standstill),
        })
        try:
          row["buttonEvents"] = [{"type": str(be.type), "pressed": bool(be.pressed)} for be in cs.buttonEvents]
        except Exception:
          row["buttonEvents"] = []

      out_file.write(json.dumps(row, separators=(",", ":")) + "\n")
      last_write = now
      time.sleep(POLL_S)
  finally:
    if out_file is not None:
      out_file.close()


if __name__ == "__main__":
  main()
