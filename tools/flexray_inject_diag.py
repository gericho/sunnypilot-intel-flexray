#!/usr/bin/env python3
import struct
import usb1

VENDOR = 0x3801
PRODUCT = 0xddcc
REQ_GET_INJECTOR_DIAG = 0xDA
FMT = '<IIHBBBBBBB3xIII4BIII4BIII'

ctx = usb1.USBContext()
handle = None
for dev in ctx.getDeviceList(skip_on_error=True):
    if dev.getVendorID() == VENDOR and dev.getProductID() == PRODUCT:
        handle = dev.open()
        break
if handle is None:
    raise SystemExit('picoflex not found')
try:
    handle.claimInterface(0)
except Exception:
    pass
raw = handle.controlRead(0xC0, REQ_GET_INJECTOR_DIAG, 0, 0, struct.calcsize(FMT), timeout=1000)
(
    override_rx_count,
    inject_fire_count,
    last_target_id,
    last_cycle_count,
    last_direction,
    last_replace_len,
    dbg135_trigger_seen,
    dbg135_cycle_match,
    dbg135_template_cached,
    dbg135_override_present,
    dbg135_submit_count,
    dbg135_pop_attempt_count,
    dbg135_pop_hit_count,
    dbg72_trigger_seen,
    dbg72_cycle_match,
    dbg72_template_cached,
    dbg72_override_present,
    dbg72_submit_count,
    dbg72_pop_attempt_count,
    dbg72_pop_hit_count,
    dbg96_trigger_seen,
    dbg96_cycle_match,
    dbg96_template_cached,
    dbg96_override_present,
    dbg96_submit_count,
    dbg96_pop_attempt_count,
    dbg96_pop_hit_count,
) = struct.unpack(FMT, bytes(raw))
print(f'override_rx_count={override_rx_count}')
print(f'inject_fire_count={inject_fire_count}')
print(f'last_target_id={last_target_id}')
print(f'last_cycle_count={last_cycle_count}')
print(f'last_direction={last_direction}')
print(f'last_replace_len={last_replace_len}')
print(f'dbg135_trigger_seen={dbg135_trigger_seen}')
print(f'dbg135_cycle_match={dbg135_cycle_match}')
print(f'dbg135_template_cached={dbg135_template_cached}')
print(f'dbg135_override_present={dbg135_override_present}')
print(f'dbg135_submit_count={dbg135_submit_count}')
print(f'dbg135_pop_attempt_count={dbg135_pop_attempt_count}')
print(f'dbg135_pop_hit_count={dbg135_pop_hit_count}')
print(f'dbg72_trigger_seen={dbg72_trigger_seen}')
print(f'dbg72_cycle_match={dbg72_cycle_match}')
print(f'dbg72_template_cached={dbg72_template_cached}')
print(f'dbg72_override_present={dbg72_override_present}')
print(f'dbg72_submit_count={dbg72_submit_count}')
print(f'dbg72_pop_attempt_count={dbg72_pop_attempt_count}')
print(f'dbg72_pop_hit_count={dbg72_pop_hit_count}')
print(f'dbg96_trigger_seen={dbg96_trigger_seen}')
print(f'dbg96_cycle_match={dbg96_cycle_match}')
print(f'dbg96_template_cached={dbg96_template_cached}')
print(f'dbg96_override_present={dbg96_override_present}')
print(f'dbg96_submit_count={dbg96_submit_count}')
print(f'dbg96_pop_attempt_count={dbg96_pop_attempt_count}')
print(f'dbg96_pop_hit_count={dbg96_pop_hit_count}')
