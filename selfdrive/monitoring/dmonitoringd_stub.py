#!/usr/bin/env python3
import cereal.messaging as messaging

from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.selfdrive.monitoring.helpers import DriverMonitoring


def dmonitoringd_stub_thread():
  config_realtime_process([0, 1, 2, 3], 5)
  rk = Ratekeeper(20, print_delay_threshold=None)

  params = Params()
  pm = messaging.PubMaster(['driverMonitoringState'])
  dm = DriverMonitoring(rhd_saved=params.get_bool("IsRhdDetected"), always_on=params.get_bool("AlwaysOnDM"))

  while True:
    pm.send('driverMonitoringState', dm.get_state_packet(valid=True))
    rk.keep_time()


def main():
  dmonitoringd_stub_thread()


if __name__ == '__main__':
  main()
