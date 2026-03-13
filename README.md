# SUNNYPILOT for BMW i3 FlexRay (Intel PC/OpenCL Build)

![](https://user-images.githubusercontent.com/47793918/233812617-beab2e71-57b9-479e-8bff-c3931347ca40.png)

## Technical Delta Summary
> **Status:** Work in progress. This fork should currently be considered **Bʀᴏᴋᴇɴ**.

This project is based in part on CzokNorris's FlexRay work and the CzokNorris V1 board design.

1. Added BMW i3 support in `opendbc` with a dedicated DBC and platform registration.
2. Integrated FlexRay-related Panda communication/safety changes and Cabana decoding support.
3. Enabled Intel hardware video encoding for PC testing (`hevc_vaapi` / `h264_vaapi`) with explicit runtime fallback paths.
4. Reworked FFmpeg encoder handling for NV12/VAAPI and added safer software fallback behavior for unsupported cases.
5. Aligned logger segmentation with runtime camera FPS (`ROAD_FPS`) to improve route/segment timing consistency.
6. Added dedicated qcamera tuning knobs (`QCAM_FPS`, `QCAM_BITRATE`) to reduce encoder/queue pressure on low-power CPUs.
7. Optimized the webcam pipeline with a raw NV12 fast path (`WEBCAM_RAW_NV12`) and camera FOURCC control from env.
8. Added robust webcam format handling (including YUYV fallback conversion) and runtime stage profiling output.
9. Switched webcam publish timing to monotonic nanosecond timestamps for improved playback/signal synchronization.
10. Enforced Intel OpenCL execution for models (`DEV=CL` + Intel ICD-only `OCL_ICD_VENDORS`) to avoid CPU OpenCL fallback.
11. Switched current logging profile to `fcamera`-only (qcamera disabled) to keep Cabana route handling deterministic on PC runs.
12. Added logger queue tuning for encoder bursts (`LOGGERD_ENCODER_QUEUE_LIMIT`) and increased default buffering in `loggerd` to prevent HEVC packet drops during segment rotation.
13. Tuned HEVC stability settings for PC capture: shorter GOP (keyframe cadence tied to `ROAD_FPS`) and reduced main-road bitrates (`ROAD_MAIN_BITRATE_LOW/HIGH`) to lower encoder pressure.

## FlexRay MITM Mapping
- Group 1 uses `FR1` and `FR2`.
- `FR1` (`U5`) is the vehicle-side transceiver: `TXD GPIO28`, `TXEN GPIO27`, `RXD GPIO26`.
- `FR2` (`U8`) is the ECU-side transceiver: `TXD GPIO4`, `TXEN GPIO5`, `RXD GPIO6`.
- Group 2 uses `FR3` and `FR4`.
- `FR3` (`U9`) is the vehicle-side transceiver: `TXD GPIO10`, `TXEN GPIO9`, `RXD GPIO8`.
- `FR4` (`U10`) is the ECU-side transceiver: `TXD GPIO16`, `TXEN GPIO22`, `RXD GPIO21`.
- In the dual-channel firmware, `src 24` means `FR2 + FR4` and `src 23` means `FR2 + FR3`.

## Tested Hardware
- CPU: Intel Core i5-7200U (4 vCPU, x86_64)
- Webcam(s): Logitech BRIO (`usb-046d_Logitech_BRIO_6C9B1E5A`)

## 🌞 What is sunnypilot?
[sunnypilot](https://github.com/sunnyhaibin/sunnypilot) is a fork of comma.ai's openpilot, an open source driver assistance system. sunnypilot offers the user a unique driving experience for over 300+ supported car makes and models with modified behaviors of driving assist engagements. sunnypilot complies with comma.ai's safety rules as accurately as possible.

## 💭 Join our Community Forum
Join the official sunnypilot community forum to stay up to date with all the latest features and be a part of shaping the future of sunnypilot!
* https://community.sunnypilot.ai/

## Documentation
https://docs.sunnypilot.ai/ is your one stop shop for everything from features to installation to FAQ about the sunnypilot

## 🚘 Running on a dedicated device in a car
First, check out this list of items you'll need to [get started](https://community.sunnypilot.ai/t/getting-started-using-sunnypilot-in-your-supported-car/251).

## Installation
Next, refer to the sunnypilot community forum for [installation instructions](https://community.sunnypilot.ai/t/read-before-installing-sunnypilot/254), as well as a complete list of [Recommended Branch Installations](https://community.sunnypilot.ai/t/recommended-branch-installations/235).

## 🎆 Pull Requests
We welcome both pull requests and issues on GitHub. Bug fixes are encouraged.

Pull requests should be against the most current `master` branch.

## 📊 User Data

By default, sunnypilot uploads the driving data to comma servers. You can also access your data through [comma connect](https://connect.comma.ai/).

sunnypilot is open source software. The user is free to disable data collection if they wish to do so.

sunnypilot logs the road-facing camera, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver-facing camera and microphone are only logged if you explicitly opt-in in settings.

By using this software, you understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.

## Licensing

sunnypilot is released under the [MIT License](LICENSE). This repository includes original work as well as significant portions of code derived from [openpilot by comma.ai](https://github.com/commaai/openpilot), which is also released under the MIT license with additional disclaimers.

The original openpilot license notice, including comma.ai’s indemnification and alpha software disclaimer, is reproduced below as required:

> openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.
>
> Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.
>
> **THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
> YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
> NO WARRANTY EXPRESSED OR IMPLIED.**

For full license terms, please see the [`LICENSE`](LICENSE) file.

## 💰 Support sunnypilot
If you find any of the features useful, consider becoming a [sponsor on GitHub](https://github.com/sponsors/sunnyhaibin) to support future feature development and improvements.


By becoming a sponsor, you will gain access to exclusive content, early access to new features, and the opportunity to directly influence the project's development.


<h3>GitHub Sponsor</h3>

<a href="https://github.com/sponsors/sunnyhaibin">
  <img src="https://user-images.githubusercontent.com/47793918/244135584-9800acbd-69fd-4b2b-bec9-e5fa2d85c817.png" alt="Become a Sponsor" width="300" style="max-width: 100%; height: auto;">
</a>
<br>

<h3>PayPal</h3>

<a href="https://paypal.me/sunnyhaibin0850" target="_blank">
<img src="https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif" alt="PayPal this" title="PayPal - The safer, easier way to pay online!" border="0" />
</a>
<br></br>

Your continuous love and support are greatly appreciated! Enjoy 🥰

<span>-</span> Jason, Founder of sunnypilot
