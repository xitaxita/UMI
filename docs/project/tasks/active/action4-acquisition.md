# Design DJI Action 4 acquisition

## Active implementation — D-013

Add repeated episode start/stop without terminating the ROS launch. One camera
control node owns a persistent camera worker, MP4 validation and per-episode
rosbag2; a keyboard client toggles Trigger services. The worker warms once at
startup. Waiting frames are preview-only; recording frames are both saved and
previewed. Each episode gets a new folder without reopening the camera. Verify
state transitions, two sequential episodes, active Ctrl+C, continuous preview,
separate pose bags and clean files.

Implemented in software. Canonical controls are Trigger services; the separate
terminal client toggles with Enter. Twenty-one tests, focused flake8, package
build and launch parsing pass. A synthetic persistent worker warmed once and
then recorded two sequential 24-frame, 0.8-second decodable MP4 episodes while
returning to `waiting` between them. D-012 physical warmup previously passed
with 270 accepted/decoded frames and preview during warmup. Two sequential
episodes remain unverified on Action 4 because `/dev/video0` was absent on
2026-09-12.

## Active implementation — D-012

Implement genuine continuous-stream warmup with a recording gate, live preview,
pose pre-roll and explicit video-start timing metadata. Verify startup burst
exclusion, no camera restart, graceful EOS, pre-ready stop, timeout/failure,
and real-device opening PTS. Keep recording after readiness non-dropping.
Software and hardware validation are pending for this change.

## Current execution — D-011

Startup diagnosis: encoder-free v4l2src → identity → fakesink, 45-buffer
comparison plus repeated 30-buffer runs, shows short PTS AND arrival intervals
with either do-timestamp setting. Initial buffer carries corrupted/discont.
Current launch delays camera and recorder together, providing no camera-stream
warmup. No runtime change made in this diagnostic turn. A true pre-record
streaming warmup is recommended; internal camera/driver origin remains open.

User stopped kernel work and selected MJPEG capture with H264 MP4 encoding.
Implemented x264enc ultrafast at configurable 12000 kbps, non-leaky recording,
independently leaky JPEG preview, existing pose/session layout. Direct MJPEG
storage is deferred fallback only. Fourteen tests and venv build pass.

Hardware evidence: /tmp/umi_mjpeg_test_gxspknow/video.mp4 contains 361 decoded
frames from ~12 seconds, max PTS gap 41.333 ms, no errors, exit 0. ROS preview
received 90 valid 640x360 BGR8 messages in 6 seconds. Launch parsing passes.
No visual RViz acceptance or long combined Vive test is claimed.

## Latest execution — D-010

Repair candidate: tools/action4_uvc/action4-h264-compressed.patch marks only
2ca3:0023 H264 as COMPRESSED despite bVariableSize=0. Descriptor bpp is also 0;
upstream driver logic explains zero allocation. Matching-kernel compilation
and temporary privileged module loading remain pending (sudo needs password).

Physical diagnosis: native H.264 1920x1080 and 1280x720 both return
sizeimage=0 and VIDIOC_REQBUFS EINVAL. Explicit sizeimage=4147200 does not
change readback. Kernel warns in vb2_core_reqbufs. Device is uvcvideo on USB
480M; no process owned the camera before tests. MJPEG 1080p sizeimage=4147200
receives 150 buffers, but reports 30–31 dropped buffers per reporting interval
and ~60 fps; do not interpret this as verified 60 fps or lossless acquisition.
Restored native H.264 1080p after tests. No driver or application code changes.

Venv build and online launch parsing passed. Synthetic H.264 input yielded
60/60 decoded MP4 frames, maximum PTS interval 33.334 ms, no decode errors.

Online development resumed with explicit native H.264 input. MP4 is remuxed
without re-encoding. Preview dropping moved after decoding to preserve H.264
reference frames. Preview publication is limited to 15 fps; stdout is drained
through shutdown. Removed misleading preview-based video timestamp CSV and
added post-stop MP4 validation JSON. Fourteen tests pass. Physical camera is
not exposed in this environment; H.264 negotiation and sustained capture are
pending. Offline implementation is retained.

- **Task identity:** `action4-acquisition`
- **Project and delivery:** UMI, camera and raw-session acquisition
- **Status:** In progress; recording-first native H.264 capture is implemented;
  runtime dependencies, hardware re-verification, and offline mode remain.
- **Scope source:** User decisions recorded in D-003 and D-004.
- **Working copy:** `/home/xing/Documents/UMI`; preserve the existing Vive implementation and unrelated user changes.

## Goal and boundary

Add DJI Osmo Action 4 acquisition around the existing Vive pose source. The
camera and Tracker are rigidly mounted on the same gripper and EIS is disabled.
Offline acquisition is the primary mode; online USB acquisition is a separate
mode. This task does not yet select or implement temporal synchronization,
define synchronization accuracy, calibrate camera intrinsics or camera-to-Tracker
extrinsics, or convert data to LeRobot.

## Confirmed behavior

| Area | Required behavior |
| --- | --- |
| Offline mode | Record 4K/60 fps MP4 to Action 4 microSD without USB image capture. Record Vive pose and TF on Linux and display pose/path/TF in RViz. |
| Online mode | Use Action 4 USB/UVC at a target 1080p/30 fps without SD recording. Record and display image plus Vive pose in ROS 2/RViz. |
| Mode isolation | Do not implement a hybrid SD-recording plus USB-preview mode. |
| Camera geometry | Keep Action 4 and Tracker rigidly mounted; disable electronic image stabilization. |
| Offline data | Preserve source MP4, Vive rosbag2, and session/calibration metadata. |
| Online data | Store one H.264 MP4 plus frame timestamps and a separate Vive pose/TF MCAP under one session directory. |
| Path | Publish `/vive/path` for RViz but exclude it from recordings; reconstruct it from `/vive/pose` when needed. |

## Acceptance and evidence

| Acceptance item | Current conclusion |
| --- | --- |
| Action 4 exposes a usable Linux UVC device | Passed 2026-09-10: USB `2ca3:0023`, `uvcvideo`, capture node `/dev/video0`; MJPEG and H.264 at 720p30 and 1080p30 advertised. |
| Online capture sustains the target 1080p/30 fps | Initial test passed 2026-09-10: valid 1920x1080 MJPEG frame plus 300 frames in 9.913 s with no reported errors. Longer endurance testing remains. |
| Offline SD recording sustains 4K/60 fps with EIS off | Pending hardware test |
| Vive and camera can operate without USB/resource interference | Initial combined launch passed 2026-09-10; longer simultaneous operation remains. |
| Offline session stores MP4, pose bag, and metadata | Not implemented |
| Online session records and displays image plus pose | Split MP4 plus pose-MCAP implementation is in progress; hardware acceptance is pending. |
| `/vive/path` is not included in recordings | Implemented and covered by a static topic-contract test. |

## Implementation direction

1. Replace the current MJPEG-through-ROS capture chain with native H.264 direct
   MP4 recording and a decoded, leaky best-effort RViz preview branch.
2. Verify one online session directory containing H.264 MP4, frame timestamps,
   and a separate pose/TF MCAP without `/vive/path`.
3. Verify offline 4K/60 fps recording, EIS-off configuration, file segmentation,
   thermal behavior, and power/runtime constraints.
4. Define camera-node and session-recorder interfaces without introducing a
   temporal synchronization algorithm.
5. Implement and verify the two separate launch/recording modes and RViz views.

## Open items

- Temporal synchronization method and accuracy target are deferred by user request.
- Camera intrinsics and camera-to-Tracker rigid transform are not calibrated.
- Online H.264 encoding and sustained storage performance require hardware validation.
- Action 4 remote recording control is not part of the confirmed first implementation.

## Hardware evidence — 2026-09-10

- Linux enumerated `DJI Technology Co., Ltd. OsmoAction4` with USB ID
  `2ca3:0023`; the kernel interface is `uvcvideo`.
- `/dev/video0` advertises capture capability. `/dev/video1` belongs to the same
  device but does not advertise capture capability.
- GStreamer reported MJPEG and H.264 at 1280x720/30 and 1920x1080/30.
- A 1920x1080 MJPEG still frame contained a valid camera image.
- A 300-frame MJPEG 1920x1080/30 pipeline completed normally in 9.913 seconds.
- This test validates the camera-only UVC path, not simultaneous Vive operation,
  ROS topic publication, rosbag recording, RViz display, or long-duration heat
  and stability behavior.

## ROS implementation evidence — 2026-09-10

- Added the independent `action4_ros2` ament Python package and
  `action4_camera_node`, using GStreamer rather than a GoPro-specific SDK.
- FastUMI's ROS1 `usb_cam` pattern informed the standard ROS image-topic
  boundary; the Action 4 implementation uses ROS2 and its verified UVC stream.
- `/action4/image_raw/compressed` publishes source MJPEG at 1920x1080 and an
  observed 29.95–29.98 fps. This is the intended recording topic.
- `/action4/image_preview` targets BGR8 at 640x360/30 with best-effort QoS and
  matching RViz configuration; the updated runtime rate still requires
  verification.
- `/action4/camera_info` reports 1920x1080 and matching publication timestamps;
  intrinsic and distortion matrices are intentionally unset.
- Unit test: 1 passed. Flake8, `compileall`, `git diff --check`, and ROS2 Jazzy
  `colcon build --packages-select action4_ros2` passed.
- Physical node startup and shutdown passed. The original full-resolution BGR
  design only reached roughly 11–22 fps under subscription, so it was replaced
  by native MJPEG plus a lower-bandwidth preview.
- The camera-only `action4.launch.py` publishes only; it does not start rosbag2
  or write to disk. Recording requires the separate `umi_bringup` entry point.
- `vive_with_rviz.launch.py` now starts Vive pose, Action 4 capture, and RViz.
  RViz subscribes reliably to `/action4/image_preview`; the live endpoint check
  found one compatible RViz subscriber and no QoS warning. Both hardware nodes
  started together. A duplicate pre-existing Action 4 publisher was visible and
  was left untouched.

## Recording implementation evidence — 2026-09-10

- Historical implementation: added `umi_bringup` with `online_record.launch.py`;
  output defaulted to `recordings/online_<timestamp>` and was overridden with
  `bag_output`. This combined-bag interface was superseded by D-008.
- MCAP records only `/action4/image_raw/compressed`, `/action4/camera_info`,
  `/vive/pose`, `/tf`, and `/tf_static`; preview and path are excluded.
- Added a static allowlist test; it passes. Three-package venv build, flake8,
  compile check, launch parsing, and `git diff --check` pass.
- A real launch started rosbag2 and subscribed to the requested topics. Action 4
  was no longer present as `/dev/video0`, so the image-plus-pose bag could not be
  accepted. The resulting zero-message test bag is not valid data.
- Fail-fast behavior was then added and verified: camera failure shut down the
  recorder, rosbag2 flushed its cache and exited cleanly, and Vive exited
  cleanly. Complete hardware recording remains pending.
- The user-created `online_20260910_205248` MCAP was inspected: 20.349 seconds,
  125.5 MiB, 609 compressed images, 612 CameraInfo messages, 1654 poses, and
  1654 TF messages. This is a valid initial complete online recording; longer
  write-performance acceptance remains.
- Added and verified `replay.launch.py`. It uses simulated bag time, decodes
  recorded MJPEG into `/action4/image_preview`, reconstructs `/vive/path` from
  recorded poses, and opens RViz with compatible best-effort QoS.
- Normal end-of-bag playback shuts the launch down automatically. During one
  manual Ctrl+C test, RViz/Qt exited with `std::system_error`; the player and
  decoder stopped cleanly. This shutdown-only RViz issue remains to monitor.

## Frame-gap correction — 2026-09-10

- Detailed analysis found the only gap over 50 ms at 0.328 seconds after the
  first recorded image: 135.506 ms, corresponding to roughly three missing
  30-fps periods. After the first second, the maximum interval was 40.984 ms and
  there were no gaps over 50 ms.
- Image headers previously used Python callback time. They now map GStreamer
  buffer PTS onto the ROS clock, preserving source intervals despite callback
  scheduling jitter; compressed and preview branches have independent mappers.
- Online recording now waits `warmup_seconds` (default 5.0) before rosbag2
  starts, excluding simultaneous camera/Vive/RViz/DDS startup from accepted data.
- PTS mapping, missing-PTS fallback, and warm-up launch contracts are covered by
  tests. All 11 tests, flake8, compile checks, three-package venv build, launch
  parsing, and `git diff --check` pass.
- Action 4 was not enumerated after the change, so a new physical bag must still
  verify maximum header interval, missing-frame count, and sustained rate.

## Official usb_cam migration — 2026-09-11

- Replaced the custom live GStreamer node in all camera-only, combined-RViz,
  and online-recording launches with `usb_cam_node_exe`.
- Initially configured `raw_mjpeg` 1920×1080/30 fps with `mmap`, and preserved
  `/action4/image_raw/compressed` and `/action4/camera_info` through remapping.
- Retained the project-owned decoder only for the 640×360 best-effort
  `/action4/image_preview`; existing MCAP and replay interfaces are unchanged.
- Removed the obsolete live GStreamer node/backend and its PTS mapper tests.
- Three-package venv build passes. The host now has `ros-jazzy-usb-cam` 0.8.1;
  hardware behavior is not yet accepted.
- The first installed-driver launch rejected `pixel_format: mjpeg`; Jazzy
  `usb_cam` exposes the passthrough format as `raw_mjpeg`. Configuration and its
  contract test were corrected accordingly.
- A sandboxed launch accepted the corrected parameter and reached device
  discovery, but the sandbox could not access `/dev/video0`; this is not a
  physical-camera acceptance result.
- Physical RViz testing then showed that `raw_mjpeg` did not feed the standard
  `CompressedImage` subscriber, leaving `/action4/image_preview` empty. Live
  capture was tested with `mjpeg2rgb`, but `usb_cam` exited with SIGSEGV as soon
  as its timer started. The final workaround keeps official `usb_cam` for
  `raw_mjpeg` V4L2 capture and uses a project bridge to trim/publish the source
  JPEG and decode only the small RViz preview.

## Package consolidation — 2026-09-11

- All current camera code, configuration, launch files, and tests moved to the
  single `umi_ros2` package under `umi_ros2/camera`, `config`, and `launch`.
- Current commands are `ros2 launch umi_ros2 camera.launch.py`,
  `online_view.launch.py`, `online_record.launch.py`, and `replay.launch.py`.
- Earlier references in this task to `action4_ros2`, `vive_ros2`, and
  `umi_bringup` are retained as historical implementation evidence only.
- The package refactor passed 12 tests, unified build, six launch parsers, and
  old-bag readability checks. It does not replace pending camera hardware
  acceptance.

## Split online session recording — 2026-09-11

- The user replaced the combined image-plus-pose bag requirement for online
  acquisition. One session now owns a standalone MP4 video and a separate
  pose/TF MCAP, while RViz live preview remains available.
- MP4 was selected because LeRobot uses MP4 for visual streams and Parquet for
  low-dimensional timestamped data; DROID raw episodes similarly pair MP4
  recordings with separate trajectory data.
- Acquisition retains pose and TF in MCAP rather than converting directly to
  Parquet because temporal synchronization and the final LeRobot schema remain
  undecided. Per-frame ROS timestamps are preserved in a CSV beside the video.

## Native H.264 capture implementation — 2026-09-11

- Added `action4_h264_capture_node`, which owns `/dev/video0` once. Its primary
  GStreamer branch remuxes native H.264 into MP4 without an encoder; a bounded
  leaky branch decodes and scales BGR8 preview frames for best-effort RViz.
- Recording mode writes one CSV row per parsed H.264 access unit with GStreamer
  PTS and the mapped ROS timestamp. Preview-only mode builds no file branch.
- Active camera, online-view, and online-record launches now use this process.
  The `usb_cam`, raw-MJPEG bridge, and ROS-subscribing MP4 writer were removed
  from the active package; legacy compressed-bag replay remains.
- Fourteen tests, the venv ROS build, three affected launch parsers, and
  `git diff --check` pass. The required plugins were subsequently confirmed;
  runtime acceptance remains pending after the first SIGABRT correction.

## First native H.264 runtime correction — 2026-09-11

- The user's first `online_view` run started Vive, the camera process, and RViz,
  but the H.264 process aborted with signal 6 and emitted no Python traceback.
- Required GStreamer elements are now present. Hardware cannot be reproduced in
  the inspection sandbox because `/dev/video0` is not exposed there.
- Removed direct `rclpy.publish()` calls from the GStreamer streaming thread.
  That thread now only copies the newest decoded preview into a one-slot handoff;
  the ROS executor publishes it. This further isolates record priority from
  preview and removes the riskiest native-thread boundary.
- Added Python faulthandler and made `online_view` shut down if camera capture
  exits. Fourteen tests, ROS build/test, and `git diff --check` pass; a physical
  rerun is required to confirm whether the SIGABRT is resolved.

## Related records

### Simplified external GStreamer correction — 2026-09-11

- The second physical run traced SIGSEGV to `rclpy.Node.__init__`, before camera
  construction. The in-process PyGObject binding was removed completely.
- FFmpeg then failed `VIDIOC_REQBUFS` on the advertised H.264 mode. The active
  implementation is now one Python ROS node plus one external GStreamer child:
  native H.264 is remuxed to MP4, decoded 640×360 BGR frames are drained from
  stdout, and only the latest frame is published best-effort to RViz.
- Fourteen tests, ROS build/test, and `git diff --check` pass. Physical rerun is
  pending.

- [Requirements](../../REQUIREMENTS.md)
- [Architecture](../../ARCHITECTURE.md)
- [Decisions](../../DECISIONS.md)
- [Vive task](vive-ros2-node.md)
