#!/usr/bin/env python3
import math
import capnp
import calendar
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict
from dataclasses import dataclass

from cereal import log
from cereal import messaging
from openpilot.system.ubloxd.ubx import Ubx
from openpilot.system.ubloxd.gps import Gps
from openpilot.system.ubloxd.glonass import Glonass


SECS_IN_MIN = 60
SECS_IN_HR = 60 * SECS_IN_MIN
SECS_IN_DAY = 24 * SECS_IN_HR
SECS_IN_WEEK = 7 * SECS_IN_DAY


class UbxFramer:
  PREAMBLE1 = 0xB5
  PREAMBLE2 = 0x62
  HEADER_SIZE = 6
  CHECKSUM_SIZE = 2

  def __init__(self) -> None:
    self.buf = bytearray()
    self.last_log_time = 0.0

  def reset(self) -> None:
    self.buf.clear()

  @staticmethod
  def _checksum_ok(frame: bytes) -> bool:
    ck_a = 0
    ck_b = 0
    for b in frame[2:-2]:
      ck_a = (ck_a + b) & 0xFF
      ck_b = (ck_b + ck_a) & 0xFF
    return ck_a == frame[-2] and ck_b == frame[-1]

  def add_data(self, log_time: float, incoming: bytes) -> list[bytes]:
    self.last_log_time = log_time
    out: list[bytes] = []
    if not incoming:
      return out
    self.buf += incoming

    while True:
      # find preamble
      if len(self.buf) < 2:
        break
      start = self.buf.find(b"\xb5\x62")
      if start < 0:
        # no preamble in buffer
        self.buf.clear()
        break
      if start > 0:
        # drop garbage before preamble
        self.buf = self.buf[start:]

      if len(self.buf) < self.HEADER_SIZE:
        break

      length_le = int.from_bytes(self.buf[4:6], 'little', signed=False)
      total_len = self.HEADER_SIZE + length_le + self.CHECKSUM_SIZE
      if len(self.buf) < total_len:
        break

      candidate = bytes(self.buf[:total_len])
      if self._checksum_ok(candidate):
        out.append(candidate)
        # consume this frame
        self.buf = self.buf[total_len:]
      else:
        # drop first byte and retry
        self.buf = self.buf[1:]

    return out


class NmeaParser:
  def __init__(self) -> None:
    self.buf = bytearray()
    self.last_rmc: dict[str, object] = {}
    self.last_gga: dict[str, object] = {}
    self.last_gsa: dict[str, object] = {}
    self.last_gsv_sat_count = 0

  @staticmethod
  def _parse_lat_lon(value: str, hemi: str) -> float | None:
    if not value or not hemi:
      return None
    try:
      dot = value.find('.')
      if dot < 0:
        return None
      deg_len = dot - 2
      deg = float(value[:deg_len])
      minutes = float(value[deg_len:])
      out = deg + minutes / 60.0
      if hemi in ('S', 'W'):
        out = -out
      return out
    except Exception:
      return None

  @staticmethod
  def _parse_hms(value: str) -> tuple[int, int, int, int] | None:
    if len(value) < 6:
      return None
    try:
      hour = int(value[0:2])
      minute = int(value[2:4])
      sec = int(value[4:6])
      frac_ms = 0
      if '.' in value:
        frac = value.split('.', 1)[1]
        frac_ms = int((frac + "000")[:3])
      return hour, minute, sec, frac_ms
    except Exception:
      return None

  @staticmethod
  def _parse_date(value: str) -> tuple[int, int, int] | None:
    if len(value) != 6:
      return None
    try:
      day = int(value[0:2])
      month = int(value[2:4])
      year = 2000 + int(value[4:6])
      if year < 2080:
        return year, month, day
      return year - 100, month, day
    except Exception:
      return None

  def add_data(self, incoming: bytes) -> list[tuple[str, capnp.lib.capnp._DynamicStructBuilder]]:
    out: list[tuple[str, capnp.lib.capnp._DynamicStructBuilder]] = []
    if not incoming:
      return out
    self.buf += incoming

    while True:
      nl = self.buf.find(b'\n')
      if nl < 0:
        break
      line = bytes(self.buf[:nl]).strip()
      self.buf = self.buf[nl + 1:]
      if not line.startswith(b'$'):
        continue
      msg = self.parse_line(line.decode('ascii', errors='ignore'))
      if msg is not None:
        out.append(msg)
    return out

  def parse_line(self, line: str) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder] | None:
    if '*' in line:
      line = line.split('*', 1)[0]
    fields = line.split(',')
    if not fields:
      return None

    sentence = fields[0]
    kind = sentence[-3:]

    if kind == 'RMC' and len(fields) >= 10:
      self.last_rmc = {
        'time': self._parse_hms(fields[1]),
        'status': fields[2],
        'lat': self._parse_lat_lon(fields[3], fields[4]),
        'lon': self._parse_lat_lon(fields[5], fields[6]),
        'speed_ms': (float(fields[7]) * 0.514444) if fields[7] else 0.0,
        'bearing_deg': float(fields[8]) if fields[8] else 0.0,
        'date': self._parse_date(fields[9]),
      }
      return self._build_message()

    if kind == 'GGA' and len(fields) >= 10:
      self.last_gga = {
        'time': self._parse_hms(fields[1]),
        'lat': self._parse_lat_lon(fields[2], fields[3]),
        'lon': self._parse_lat_lon(fields[4], fields[5]),
        'fix_quality': int(fields[6]) if fields[6] else 0,
        'satellites': int(fields[7]) if fields[7] else 0,
        'hdop': float(fields[8]) if fields[8] else 99.99,
        'altitude': float(fields[9]) if fields[9] else 0.0,
      }
      return self._build_message()

    if kind == 'GSA' and len(fields) >= 18:
      self.last_gsa = {
        'fix_mode': int(fields[2]) if fields[2] else 1,
        'pdop': float(fields[15]) if fields[15] else 99.99,
        'hdop': float(fields[16]) if fields[16] else 99.99,
        'vdop': float(fields[17]) if fields[17] else 99.99,
      }
      return self._build_message()

    if kind == 'GSV' and len(fields) >= 4:
      self.last_gsv_sat_count = int(fields[3]) if fields[3] else self.last_gsv_sat_count
      return self._build_message()

    return None

  def _build_message(self) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder] | None:
    if not self.last_rmc or not self.last_gga:
      return None

    has_fix = self.last_rmc.get('status') == 'A' and self.last_gga.get('fix_quality', 0) > 0
    lat = self.last_gga.get('lat') if self.last_gga.get('lat') is not None else self.last_rmc.get('lat')
    lon = self.last_gga.get('lon') if self.last_gga.get('lon') is not None else self.last_rmc.get('lon')
    if lat is None or lon is None:
      return None

    hdop = float(self.last_gsa.get('hdop', self.last_gga.get('hdop', 99.99)))
    vdop = float(self.last_gsa.get('vdop', max(hdop * 1.5, 1.0)))
    horizontal_accuracy = max(1.5, hdop * 5.0)
    vertical_accuracy = max(2.5, vdop * 8.0)
    speed = float(self.last_rmc.get('speed_ms', 0.0))
    bearing_deg = float(self.last_rmc.get('bearing_deg', 0.0))
    bearing_rad = math.radians(bearing_deg)
    vn = speed * math.cos(bearing_rad)
    ve = speed * math.sin(bearing_rad)

    unix_timestamp_millis = 0
    if self.last_rmc.get('date') and self.last_rmc.get('time'):
      year, month, day = self.last_rmc['date']
      hour, minute, sec, frac_ms = self.last_rmc['time']
      try:
        dt = datetime(year, month, day, hour, minute, sec, frac_ms * 1000, tzinfo=timezone.utc)
        unix_timestamp_millis = int(dt.timestamp() * 1000)
      except Exception:
        unix_timestamp_millis = 0

    dat = messaging.new_message('gpsLocationExternal', valid=True)
    gps = dat.gpsLocationExternal
    gps.source = log.GpsLocationData.SensorSource.ublox
    gps.flags = 1 if has_fix else 0
    gps.hasFix = has_fix
    gps.latitude = float(lat)
    gps.longitude = float(lon)
    gps.altitude = float(self.last_gga.get('altitude', 0.0))
    gps.speed = speed
    gps.bearingDeg = bearing_deg
    gps.horizontalAccuracy = horizontal_accuracy
    gps.verticalAccuracy = vertical_accuracy
    gps.speedAccuracy = max(0.5, 0.1 + hdop * 0.1)
    gps.bearingAccuracyDeg = max(2.0, 5.0 + hdop)
    gps.satelliteCount = int(self.last_gga.get('satellites', self.last_gsv_sat_count))
    gps.unixTimestampMillis = unix_timestamp_millis
    gps.vNED = [float(vn), float(ve), 0.0]
    return ('gpsLocationExternal', dat)


def _bit(b: int, shift: int) -> bool:
  return (b & (1 << shift)) != 0


@dataclass
class EphemerisCaches:
  gps_subframes: defaultdict[int, dict[int, bytes]]
  glonass_strings: defaultdict[int, dict[int, bytes]]
  glonass_string_times: defaultdict[int, dict[int, float]]
  glonass_string_superframes: defaultdict[int, dict[int, int]]


class UbloxMsgParser:
  gpsPi = 3.1415926535898

  # user range accuracy in meters
  glonass_URA_lookup: dict[int, float] = {
    0: 1,
    1: 2,
    2: 2.5,
    3: 4,
    4: 5,
    5: 7,
    6: 10,
    7: 12,
    8: 14,
    9: 16,
    10: 32,
    11: 64,
    12: 128,
    13: 256,
    14: 512,
    15: 1024,
  }

  def __init__(self) -> None:
    self.framer = UbxFramer()
    self.caches = EphemerisCaches(
      gps_subframes=defaultdict(dict),
      glonass_strings=defaultdict(dict),
      glonass_string_times=defaultdict(dict),
      glonass_string_superframes=defaultdict(dict),
    )

  # Message generation entry point
  def parse_frame(self, frame: bytes) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder] | None:
    # Quick header parse
    msg_type = int.from_bytes(frame[2:4], 'big')
    payload = frame[6:-2]
    if msg_type == 0x0107:
      body = Ubx.NavPvt.from_bytes(payload)
      return self._gen_nav_pvt(body)
    if msg_type == 0x0213:
      # Manually parse RXM-SFRBX to avoid EOF on some frames
      if len(payload) < 8:
        return None
      gnss_id = payload[0]
      sv_id = payload[1]
      freq_id = payload[3]
      num_words = payload[4]
      exp = 8 + 4 * num_words
      if exp != len(payload):
        return None
      words: list[int] = []
      off = 8
      for _ in range(num_words):
        words.append(int.from_bytes(payload[off : off + 4], 'little'))
        off += 4

      class _SfrbxView:
        def __init__(self, gid: int, sid: int, fid: int, body: list[int]):
          self.gnss_id = Ubx.GnssType(gid)
          self.sv_id = sid
          self.freq_id = fid
          self.body = body

      view = _SfrbxView(gnss_id, sv_id, freq_id, words)
      return self._gen_rxm_sfrbx(view)
    if msg_type == 0x0215:
      body = Ubx.RxmRawx.from_bytes(payload)
      return self._gen_rxm_rawx(body)
    if msg_type == 0x0A09:
      body = Ubx.MonHw.from_bytes(payload)
      return self._gen_mon_hw(body)
    if msg_type == 0x0A0B:
      body = Ubx.MonHw2.from_bytes(payload)
      return self._gen_mon_hw2(body)
    if msg_type == 0x0135:
      body = Ubx.NavSat.from_bytes(payload)
      return self._gen_nav_sat(body)
    return None

  # NAV-PVT -> gpsLocationExternal
  def _gen_nav_pvt(self, msg: Ubx.NavPvt) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder]:
    dat = messaging.new_message('gpsLocationExternal', valid=True)
    gps = dat.gpsLocationExternal
    gps.source = log.GpsLocationData.SensorSource.ublox
    gps.flags = msg.flags
    gps.hasFix = (msg.flags % 2) == 1
    gps.latitude = msg.lat * 1e-07
    gps.longitude = msg.lon * 1e-07
    gps.altitude = msg.height * 1e-03
    gps.speed = msg.g_speed * 1e-03
    gps.bearingDeg = msg.head_mot * 1e-5
    gps.horizontalAccuracy = msg.h_acc * 1e-03
    gps.satelliteCount = msg.num_sv

    # build UTC timestamp millis (NAV-PVT is in UTC)
    # tolerate invalid or unset date values like C++ timegm
    try:
      utc_tt = calendar.timegm((msg.year, msg.month, msg.day, msg.hour, msg.min, msg.sec, 0, 0, 0))
    except Exception:
      utc_tt = 0
    gps.unixTimestampMillis = int(utc_tt * 1e3 + (msg.nano * 1e-6))

    # match C++ float32 rounding semantics exactly
    gps.vNED = [
      float(np.float32(msg.vel_n) * np.float32(1e-03)),
      float(np.float32(msg.vel_e) * np.float32(1e-03)),
      float(np.float32(msg.vel_d) * np.float32(1e-03)),
    ]
    gps.verticalAccuracy = msg.v_acc * 1e-03
    gps.speedAccuracy = msg.s_acc * 1e-03
    gps.bearingAccuracyDeg = msg.head_acc * 1e-05
    return ('gpsLocationExternal', dat)

  # RXM-SFRBX dispatch to GPS or GLONASS ephemeris
  def _gen_rxm_sfrbx(self, msg) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder] | None:
    if msg.gnss_id == Ubx.GnssType.gps:
      return self._parse_gps_ephemeris(msg)
    if msg.gnss_id == Ubx.GnssType.glonass:
      return self._parse_glonass_ephemeris(msg)
    return None

  def _parse_gps_ephemeris(self, msg: Ubx.RxmSfrbx) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder] | None:
    # body is list of 10 words; convert to 30-byte subframe (strip parity/padding)
    body = msg.body
    if len(body) != 10:
      return None
    subframe_data = bytearray()
    for word in body:
      word >>= 6
      subframe_data.append((word >> 16) & 0xFF)
      subframe_data.append((word >> 8) & 0xFF)
      subframe_data.append(word & 0xFF)

    sf = Gps.from_bytes(bytes(subframe_data))
    subframe_id = sf.how.subframe_id
    if subframe_id < 1 or subframe_id > 3:
      return None
    self.caches.gps_subframes[msg.sv_id][subframe_id] = bytes(subframe_data)

    if len(self.caches.gps_subframes[msg.sv_id]) != 3:
      return None

    dat = messaging.new_message('ubloxGnss', valid=True)
    eph = dat.ubloxGnss.init('ephemeris')
    eph.svId = msg.sv_id

    iode_s2 = 0
    iode_s3 = 0
    iodc_lsb = 0
    week = 0

    # Subframe 1
    sf1 = Gps.from_bytes(self.caches.gps_subframes[msg.sv_id][1])
    s1 = sf1.body
    assert isinstance(s1, Gps.Subframe1)
    week = s1.week_no
    week += 1024
    if week < 1877:
      week += 1024
    eph.tgd = s1.t_gd * math.pow(2, -31)
    eph.toc = s1.t_oc * math.pow(2, 4)
    eph.af2 = s1.af_2 * math.pow(2, -55)
    eph.af1 = s1.af_1 * math.pow(2, -43)
    eph.af0 = s1.af_0 * math.pow(2, -31)
    eph.svHealth = s1.sv_health
    eph.towCount = sf1.how.tow_count
    iodc_lsb = s1.iodc_lsb

    # Subframe 2
    sf2 = Gps.from_bytes(self.caches.gps_subframes[msg.sv_id][2])
    s2 = sf2.body
    assert isinstance(s2, Gps.Subframe2)
    if s2.t_oe == 0 and sf2.how.tow_count * 6 >= (SECS_IN_WEEK - 2 * SECS_IN_HR):
      week += 1
    eph.crs = s2.c_rs * math.pow(2, -5)
    eph.deltaN = s2.delta_n * math.pow(2, -43) * self.gpsPi
    eph.m0 = s2.m_0 * math.pow(2, -31) * self.gpsPi
    eph.cuc = s2.c_uc * math.pow(2, -29)
    eph.ecc = s2.e * math.pow(2, -33)
    eph.cus = s2.c_us * math.pow(2, -29)
    eph.a = math.pow(s2.sqrt_a * math.pow(2, -19), 2.0)
    eph.toe = s2.t_oe * math.pow(2, 4)
    iode_s2 = s2.iode

    # Subframe 3
    sf3 = Gps.from_bytes(self.caches.gps_subframes[msg.sv_id][3])
    s3 = sf3.body
    assert isinstance(s3, Gps.Subframe3)
    eph.cic = s3.c_ic * math.pow(2, -29)
    eph.omega0 = s3.omega_0 * math.pow(2, -31) * self.gpsPi
    eph.cis = s3.c_is * math.pow(2, -29)
    eph.i0 = s3.i_0 * math.pow(2, -31) * self.gpsPi
    eph.crc = s3.c_rc * math.pow(2, -5)
    eph.omega = s3.omega * math.pow(2, -31) * self.gpsPi
    eph.omegaDot = s3.omega_dot * math.pow(2, -43) * self.gpsPi
    eph.iode = s3.iode
    eph.iDot = s3.idot * math.pow(2, -43) * self.gpsPi
    iode_s3 = s3.iode

    eph.toeWeek = week
    eph.tocWeek = week

    # clear cache for this SV
    self.caches.gps_subframes[msg.sv_id].clear()
    if not (iodc_lsb == iode_s2 == iode_s3):
      return None
    return ('ubloxGnss', dat)

  def _parse_glonass_ephemeris(self, msg: Ubx.RxmSfrbx) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder] | None:
    # words are 4 bytes each; Glonass parser expects 16 bytes (string)
    body = msg.body
    if len(body) != 4:
      return None
    string_bytes = bytearray()
    for word in body:
      for i in (3, 2, 1, 0):
        string_bytes.append((word >> (8 * i)) & 0xFF)

    gl = Glonass.from_bytes(bytes(string_bytes))
    string_number = gl.string_number
    if string_number < 1 or string_number > 5 or gl.idle_chip:
      return None

    # correlate by superframe and timing, similar to C++ logic
    freq_id = msg.freq_id
    superframe_unknown = False
    needs_clear = False
    for i in range(1, 6):
      if i not in self.caches.glonass_strings[freq_id]:
        continue
      sf_prev = self.caches.glonass_string_superframes[freq_id].get(i, 0)
      if sf_prev == 0 or gl.superframe_number == 0:
        superframe_unknown = True
      elif sf_prev != gl.superframe_number:
        needs_clear = True
      if superframe_unknown:
        prev_time = self.caches.glonass_string_times[freq_id].get(i, 0.0)
        if abs((prev_time - 2.0 * i) - (self.framer.last_log_time - 2.0 * string_number)) > 10:
          needs_clear = True

    if needs_clear:
      self.caches.glonass_strings[freq_id].clear()
      self.caches.glonass_string_superframes[freq_id].clear()
      self.caches.glonass_string_times[freq_id].clear()

    self.caches.glonass_strings[freq_id][string_number] = bytes(string_bytes)
    self.caches.glonass_string_superframes[freq_id][string_number] = gl.superframe_number
    self.caches.glonass_string_times[freq_id][string_number] = self.framer.last_log_time

    if msg.sv_id == 255:
      # unknown SV id
      return None
    if len(self.caches.glonass_strings[freq_id]) != 5:
      return None

    dat = messaging.new_message('ubloxGnss', valid=True)
    eph = dat.ubloxGnss.init('glonassEphemeris')
    eph.svId = msg.sv_id
    eph.freqNum = msg.freq_id - 7

    current_day = 0
    tk = 0

    # string 1
    try:
      s1 = Glonass.from_bytes(self.caches.glonass_strings[freq_id][1]).data
    except Exception:
      return None
    assert isinstance(s1, Glonass.String1)
    eph.p1 = int(s1.p1)
    tk = int(s1.t_k)
    eph.tkDEPRECATED = tk
    eph.xVel = float(s1.x_vel) * math.pow(2, -20)
    eph.xAccel = float(s1.x_accel) * math.pow(2, -30)
    eph.x = float(s1.x) * math.pow(2, -11)

    # string 2
    try:
      s2 = Glonass.from_bytes(self.caches.glonass_strings[freq_id][2]).data
    except Exception:
      return None
    assert isinstance(s2, Glonass.String2)
    eph.svHealth = int(s2.b_n >> 2)
    eph.p2 = int(s2.p2)
    eph.tb = int(s2.t_b)
    eph.yVel = float(s2.y_vel) * math.pow(2, -20)
    eph.yAccel = float(s2.y_accel) * math.pow(2, -30)
    eph.y = float(s2.y) * math.pow(2, -11)

    # string 3
    try:
      s3 = Glonass.from_bytes(self.caches.glonass_strings[freq_id][3]).data
    except Exception:
      return None
    assert isinstance(s3, Glonass.String3)
    eph.p3 = int(s3.p3)
    eph.gammaN = float(s3.gamma_n) * math.pow(2, -40)
    eph.svHealth = int(eph.svHealth | (1 if s3.l_n else 0))
    eph.zVel = float(s3.z_vel) * math.pow(2, -20)
    eph.zAccel = float(s3.z_accel) * math.pow(2, -30)
    eph.z = float(s3.z) * math.pow(2, -11)

    # string 4
    try:
      s4 = Glonass.from_bytes(self.caches.glonass_strings[freq_id][4]).data
    except Exception:
      return None
    assert isinstance(s4, Glonass.String4)
    current_day = int(s4.n_t)
    eph.nt = current_day
    eph.tauN = float(s4.tau_n) * math.pow(2, -30)
    eph.deltaTauN = float(s4.delta_tau_n) * math.pow(2, -30)
    eph.age = int(s4.e_n)
    eph.p4 = int(s4.p4)
    eph.svURA = float(self.glonass_URA_lookup.get(int(s4.f_t), 0.0))
    # consistency check: SV slot number
    # if it doesn't match, keep going but note mismatch (no logging here)
    eph.svType = int(s4.m)

    # string 5
    try:
      s5 = Glonass.from_bytes(self.caches.glonass_strings[freq_id][5]).data
    except Exception:
      return None
    assert isinstance(s5, Glonass.String5)
    eph.n4 = int(s5.n_4)
    tk_seconds = int(SECS_IN_HR * ((tk >> 7) & 0x1F) + SECS_IN_MIN * ((tk >> 1) & 0x3F) + (tk & 0x1) * 30)
    eph.tkSeconds = tk_seconds

    self.caches.glonass_strings[freq_id].clear()
    return ('ubloxGnss', dat)

  def _gen_rxm_rawx(self, msg: Ubx.RxmRawx) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder]:
    dat = messaging.new_message('ubloxGnss', valid=True)
    mr = dat.ubloxGnss.init('measurementReport')
    mr.rcvTow = msg.rcv_tow
    mr.gpsWeek = msg.week
    mr.leapSeconds = msg.leap_s

    mb = mr.init('measurements', msg.num_meas)
    for i, m in enumerate(msg.meas):
      mb[i].svId = m.sv_id
      mb[i].pseudorange = m.pr_mes
      mb[i].carrierCycles = m.cp_mes
      mb[i].doppler = m.do_mes
      mb[i].gnssId = int(m.gnss_id.value)
      mb[i].glonassFrequencyIndex = m.freq_id
      mb[i].locktime = m.lock_time
      mb[i].cno = m.cno
      mb[i].pseudorangeStdev = 0.01 * (math.pow(2, (m.pr_stdev & 15)))
      mb[i].carrierPhaseStdev = 0.004 * (m.cp_stdev & 15)
      mb[i].dopplerStdev = 0.002 * (math.pow(2, (m.do_stdev & 15)))

      ts = mb[i].init('trackingStatus')
      trk = m.trk_stat
      ts.pseudorangeValid = _bit(trk, 0)
      ts.carrierPhaseValid = _bit(trk, 1)
      ts.halfCycleValid = _bit(trk, 2)
      ts.halfCycleSubtracted = _bit(trk, 3)

    mr.numMeas = msg.num_meas
    rs = mr.init('receiverStatus')
    rs.leapSecValid = _bit(msg.rec_stat, 0)
    rs.clkReset = _bit(msg.rec_stat, 2)
    return ('ubloxGnss', dat)

  def _gen_nav_sat(self, msg: Ubx.NavSat) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder]:
    dat = messaging.new_message('ubloxGnss', valid=True)
    sr = dat.ubloxGnss.init('satReport')
    sr.iTow = msg.itow
    svs = sr.init('svs', msg.num_svs)
    for i, s in enumerate(msg.svs):
      svs[i].svId = s.sv_id
      svs[i].gnssId = int(s.gnss_id.value)
      svs[i].flagsBitfield = s.flags
      svs[i].cno = s.cno
      svs[i].elevationDeg = s.elev
      svs[i].azimuthDeg = s.azim
      svs[i].pseudorangeResidual = s.pr_res * 0.1
    return ('ubloxGnss', dat)

  def _gen_mon_hw(self, msg: Ubx.MonHw) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder]:
    dat = messaging.new_message('ubloxGnss', valid=True)
    hw = dat.ubloxGnss.init('hwStatus')
    hw.noisePerMS = msg.noise_per_ms
    hw.flags = msg.flags
    hw.agcCnt = msg.agc_cnt
    hw.aStatus = int(msg.a_status.value)
    hw.aPower = int(msg.a_power.value)
    hw.jamInd = msg.jam_ind
    return ('ubloxGnss', dat)

  def _gen_mon_hw2(self, msg: Ubx.MonHw2) -> tuple[str, capnp.lib.capnp._DynamicStructBuilder]:
    dat = messaging.new_message('ubloxGnss', valid=True)
    hw = dat.ubloxGnss.init('hwStatus2')
    hw.ofsI = msg.ofs_i
    hw.magI = msg.mag_i
    hw.ofsQ = msg.ofs_q
    hw.magQ = msg.mag_q
    # Map Ubx enum to cereal enum {undefined=0, rom=1, otp=2, configpins=3, flash=4}
    cfg_map = {
      Ubx.MonHw2.ConfigSource.rom: 1,
      Ubx.MonHw2.ConfigSource.otp: 2,
      Ubx.MonHw2.ConfigSource.config_pins: 3,
      Ubx.MonHw2.ConfigSource.flash: 4,
    }
    hw.cfgSource = cfg_map.get(msg.cfg_source, 0)
    hw.lowLevCfg = msg.low_lev_cfg
    hw.postStatus = msg.post_status
    return ('ubloxGnss', dat)


def main():
  parser = UbloxMsgParser()
  nmea_parser = NmeaParser()
  pm = messaging.PubMaster(['ubloxGnss', 'gpsLocationExternal'])
  sock = messaging.sub_sock('ubloxRaw', timeout=100, conflate=False)

  while True:
    msg = messaging.recv_one(sock)
    if msg is None:
      continue

    data = bytes(msg.ubloxRaw)
    log_time = msg.logMonoTime * 1e-9
    frames = parser.framer.add_data(log_time, data)
    for frame in frames:
      try:
        res = parser.parse_frame(frame)
      except Exception:
        continue
      if not res:
        continue
      service, dat = res
      pm.send(service, dat)
    if not frames:
      for service, dat in nmea_parser.add_data(data):
        pm.send(service, dat)


if __name__ == '__main__':
  main()
