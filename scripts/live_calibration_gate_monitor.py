#!/usr/bin/env python3
import math
import time

import cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.selfdrive.locationd.calibrationd import MAX_HEIGHT_STD, MAX_VEL_ANGLE_STD, MAX_YAW_RATE_FILTER, MIN_SPEED_FILTER


def main() -> None:
  sm = messaging.SubMaster(["carState", "cameraOdometry", "liveCalibration", "roadCameraState"])

  print(
    "monitoring calibration gates: "
    f"min_speed={MIN_SPEED_FILTER * CV.MS_TO_KPH:.1f}km/h "
    f"max_yaw_rate={math.degrees(MAX_YAW_RATE_FILTER):.2f}deg/s "
    f"max_angle_std={math.degrees(MAX_VEL_ANGLE_STD):.2f}deg "
    f"max_height_std={MAX_HEIGHT_STD:.4f}",
    flush=True,
  )

  while True:
    sm.update(100)

    cs = sm["carState"]
    co = sm["cameraOdometry"]
    lc = sm["liveCalibration"]

    v_ego = float(cs.vEgo)
    trans = list(co.trans)
    rot = list(co.rot)
    trans_std = list(co.transStd)
    road_std = list(co.roadTransformTransStd)

    trans_x = float(trans[0]) if len(trans) > 0 else 0.0
    yaw_rate = abs(float(rot[2])) if len(rot) > 2 else 0.0
    angle_std = math.atan2(float(trans_std[1]), trans_x) if len(trans_std) > 1 and trans_x > 1e-6 else math.inf
    height_std = float(road_std[2]) if len(road_std) > 2 else float("nan")

    speed_ok = v_ego > MIN_SPEED_FILTER
    trans_ok = trans_x > MIN_SPEED_FILTER
    yaw_ok = yaw_rate < MAX_YAW_RATE_FILTER
    angle_ok = angle_std < MAX_VEL_ANGLE_STD
    height_ok = height_std < MAX_HEIGHT_STD if not math.isnan(height_std) else True
    accepted = speed_ok and trans_ok and yaw_ok and ((angle_ok and height_ok) or getattr(lc, "validBlocks", 0) < 5)

    print(
      f"[{time.strftime('%H:%M:%S')}] "
      f"vEgo={v_ego * CV.MS_TO_KPH:5.1f}km/h "
      f"trans_x={trans_x:5.3f} "
      f"yaw={math.degrees(yaw_rate):5.2f}deg/s "
      f"angle_std={math.degrees(angle_std) if math.isfinite(angle_std) else float('inf'):6.2f}deg "
      f"height_std={height_std:7.4f} "
      f"cal={str(lc.calStatus):>12} {getattr(lc, 'calPerc', 'na'):>3} "
      f"ok[speed={int(speed_ok)} trans={int(trans_ok)} yaw={int(yaw_ok)} angle={int(angle_ok)} height={int(height_ok)}] "
      f"accept={int(accepted)}",
      flush=True,
    )
    time.sleep(0.2)


if __name__ == "__main__":
  main()
