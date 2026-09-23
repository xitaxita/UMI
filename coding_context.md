# UMI — Coding context

## Latest update — multi-feature temporal calibration v2 (2026-09-21)

The `calibrate_time` CLI now fuses all informative ArUco centre-X/Y, log-area
and unwrapped in-plane-angle channels with TCP XYZ, continuous rotation-vector
channels and motion energy. It rejects weak channel pairs, clusters agreeing
offsets, quadratically refines scalar minima, and requires temporal-window
repeatability. The offset convention and output paths remain unchanged. The
real `online_session_20260921_181056_923446/calibration/calibration_001` run
detected 1279/1332 marker frames, estimated -95.01 ms, and produced
-98.58/-89.40/-90.27 ms window estimates (4.14 ms standard deviation), passing software
acceptance. This is not yet a repeated-session or hardware-sync accuracy claim.

## Latest update — pose/path now represent the gripper TCP (2026-09-21)

Only `umi_ros2/umi_ros2/vive/pose_node.py` runtime behavior changed. Each raw
libsurvive `vive_world -> vive_tracker` pose is composed with the accepted
D-020 `vive_tracker -> gripper_tcp` rigid transform before publishing
`/vive/pose` and appending `/vive/path`. Following the user's next request, the
optional TF broadcaster now publishes both `vive_world -> vive_tracker` and
`vive_world -> gripper_tcp`; `/vive/pose` and `/vive/path` remain TCP data.
No launch, recorder, synchronization or post-processing code changed. Identity
and 180-degree composition checks,
focused flake8, all 51 tests and `git diff --check` pass. Hardware/RViz
direction and endpoint placement remain for user inspection.

## Latest update — Tracker-to-gripper extrinsic recorded (2026-09-21)

D-020 records the user-supplied `co2_in_co1.txt` transform as parent
`vive_tracker` (co1) to child `gripper_tcp` (co2). The canonical values are now
in `umi_ros2/config/gripper_extrinsics.yaml`: translation
`[0.0, -0.080371453, 0.194957425]` metres and ROS-order XYZW quaternion
`[0.628736470, -0.628736470, 0.323559039, 0.323559039]`. These are the user's
remeasured values from 2026-09-21 and replace the previous calibration. The
same values are synchronized in the pose node's active constants. Numerical checks
confirm a unit quaternion, orthonormal rotation and agreement between the
supplied matrix and quaternion to below `1e-9`. The pose node applies this
transform to TCP pose/path and publishes both raw Tracker and converted TCP TF;
the standalone relative-TF diagnostic remains Tracker-only. Hardware/RViz
inspection is next.

## Latest update — decoupled raw-to-HDF5/LeRobot v3 pipeline (2026-09-20)

D-019 is implemented for the HDF5 and native LeRobot v3 targets. Post-processing has independent
stages: accepted `calibrate_time` metadata, `align_session` world-frame arrays,
`transform_session` episode-local arrays, and `export_hdf5`. The transform uses
the first valid aligned video-frame pose and computes
`T_episode_i = inverse(T_world_reference) * T_world_i`; invalid frames remain
invalid. `process_session` is orchestration only and writes `aligned/`,
`transformed/`, and `dataset.hdf5` under a separate processed root. HDF5 stores
per-frame JPEG payloads, relative `[x,y,z,qx,qy,qz,qw]`, source frame indices,
video PTS and pose query timestamps; invalid frames are omitted and counted.
`h5py==3.16.0` is installed in `/home/xing/umi_ros_venv` and declared as a ROS
dependency. LeRobot 0.4.4 is isolated in `/home/xing/umi_lerobot_venv312`;
`process_session --format lerobot|both` launches that interpreter so ROS NumPy
and setuptools remain untouched. The exporter uses the official dataset API,
writes video + Parquet + metadata, preserves real PTS/query timestamps, and
does not fabricate an action field. All 51 tests, focused flake8, Jazzy symlink build, installed CLI
help and `git diff --check` pass. A real zero-offset diagnostic on
`online_session_20260916_185704_823701` exported 396 synchronized samples to an
80.3 MiB HDF5 file in `/tmp`; both first relative poses were identity and JPEGs
decoded at 1920x1080. This validates software plumbing only—the session remains
uncalibrated. The same 174+222 samples exported to a 9.31 MB native LeRobot v3
dataset and reloaded as 2 episodes/396 frames with 1080p images and identity
first states. Action/task schema acceptance and an accepted-offset dataset run
remain pending. Task:
[dataset pipeline](docs/project/tasks/active/dataset-pipeline.md).

## Replay preview resolution update (2026-09-16)

The replay-only preview now defaults to 1280x720 instead of 640x360; the
installed `replay.launch.py` exposes `preview_width` and `preview_height`
arguments (1920x1080 is selectable for 1080p source files). Rosbag `/clock`
is requested at 120 Hz instead of 30 Hz to reduce scheduling quantization.
This does not alter MP4 content, source video FPS, or the live preview. The
user request was for clearer/smoother playback, not frame interpolation.
All 43 current tests, focused flake8, Jazzy symlink build, and installed replay
launch argument parsing pass. The replay-only late threshold is now two nominal
frame periods. A 1x headless run on the 468-frame old episode published 443
frames and skipped 25, versus 442/26 with the prior one-period threshold. That
old recording begins video 0.347 s before pose; the change primarily improves
preview resolution, not source frame rate. Real RViz visual smoothness remains
to be observed. Task: [session replay](docs/project/tasks/active/session-replay.md).

## Current structure audit and board sync (2026-09-16)

The current workspace was audited against `setup.py`, all six installed launch
sources, configuration, camera/pose workers, session layout, replay,
calibration, alignment, active tasks, and sample recording metadata. The
user-facing `project.md` now distinguishes implemented behavior from software
verification and hardware acceptance, includes all active entry points, and
corrects the recording guarantee: `video.validation.json` checks the produced
MP4 but reports `source_completeness: not_verified`. The existing
`online_session_20260913_172757_796981` contains one calibration and three
episodes but is still `not_calibrated` and predates D-018 hardware acceptance.
The current source suite was rerun: 42 tests passed on 2026-09-16. No rebuild,
hardware run, runtime code, or raw recording was changed in this audit. Next:
record two real episodes with the current persistent pose worker, then a real
calibration and accepted-offset alignment. The older architecture/requirements
records contain historical descriptions; current runtime is MJPEG UVC to H.264
MP4, not native-H.264 remux or `usb_cam`.

## Latest update — operator environment and project board (2026-09-14)

README now contains the complete verified Ubuntu 24.04 / ROS 2 Jazzy setup,
system dependencies, creation of `/home/xing/umi_ros_venv` with system site
packages, pinned Python tooling (`setuptools==68.1.2`), rosdep/build checks,
per-terminal sourcing order, and hardware/device permission preflight. The
user-facing `project.md` has been expanded into a complete current-state board:
scope, online/offline behavior, components, raw and processed layouts,
calibration/alignment, verified evidence, pending hardware acceptance,
constraints, roadmap, and project-record links. No runtime code changed.

## Latest update — persistent online pose recording (2026-09-14)

D-018 is implemented. `h264_capture_node` starts one internal
`PoseRecordingWorker` before the camera worker. The pose node subscribes once
to `/vive/pose`, `/tf`, and transient-local `/tf_static`; its configured five
second warmup runs alongside camera warmup and discards data. Every calibration
or episode opens a fresh `pose/` MCAP, requires its first pose (`recording_ready`)
before MP4 starts, then closes video before pose and returns both workers to
waiting. Thus episode directories remain independent while per-episode DDS
startup delay is removed. A ROS integration test reused one subscriber and
successfully finalized two distinct MCAP bags. All 42 tests, focused flake8,
ROS 2 Jazzy venv build, online launch parsing, and `git diff --check` pass.
Hardware acceptance is pending.
Task: [persistent pose recording](docs/project/tasks/active/persistent-pose-recording.md).
`project.md` was restored from the last Git baseline and rewritten to reflect
the current verified project state after the user asked to finish pending work.

## Latest update — per-frame alignment (2026-09-13)

D-017 `align_session` is implemented in `umi_ros2/umi_ros2/postprocess/` as an
ordinary Python CLI. Session input processes numeric ordinary episodes;
episode input processes one item. It reads actual MP4 PTS, the accepted session
offset (or an explicit diagnostic override), and `/vive/pose` MCAP; linearly
interpolates XYZ and shortest-path SLERPs normalized XYZW quaternions. Frames
outside pose coverage or across a >0.1 s gap are invalid rather than
extrapolated. Outputs are separate `aligned_frames.npz`, inspectable CSV,
per-episode `alignment.json`, and session summary. Raw data stays unchanged.
A real-session zero-offset diagnostic produced 457/468, 393/405, and 240/249
valid frames; this is software evidence, not temporal-accuracy acceptance.
All 39 tests and focused flake8 pass. Task:
[align session](docs/project/tasks/active/align-session.md). HDF5 and LeRobot
exporters remain unimplemented.

## Next phase decision — Python-only post-processing (2026-09-13)

D-017 fixes the next implementation boundary: temporal alignment, per-frame
pose interpolation, validation, and LeRobot/HDF5 export are ordinary offline
Python CLIs, not ROS nodes or launches. Raw sessions are immutable inputs.
Reading pose MCAP may reuse Python ROS-message deserialization libraries, but
the workflow must not require a running ROS graph. Design one normalized
aligned intermediate representation before format-specific exporters. Pending
user decisions include the exact sample schema and whether LeRobot or HDF5 is
the first acceptance target; no exporter implementation has started yet.

## Latest update — session-aware replay (2026-09-13)

D-016 replaces legacy combined-bag replay for the active separated MP4 + pose
layout. `replay.launch.py` now takes `input_path`: a session resolves all
`calibration_<sequence>` directories first and then all
`episode_<sequence>` directories; a concrete calibration/episode replays only
itself. `session_replay_node` decodes MP4 into `/action4/image_preview`, starts
the matching pose rosbag with `/clock`, and schedules frames against bag clock
using the recorded absolute video anchor. `replay_path_node` exposes a reset
service used between items. The estimated `time_offset.json` is deliberately
not yet applied. Real-session path resolution and installed real-episode runs at
20x and 5x pass; the latter confirms compatible `/clock` QoS. All 32 tests,
focused flake8, ROS 2 Jazzy build, installed launch parsing, and
`git diff --check` pass. Full RViz session playback remains visual acceptance.
Task: [session replay](docs/project/tasks/active/session-replay.md).

## Latest update — session-level recording layout (2026-09-13)

D-015 is implemented in source and pending final verification. Shared
ROS-independent helpers in `umi_ros2/umi_ros2/session/layout.py` create and
atomically update `session.yaml`.

- Online `session_output` remains the parent recordings root. Starting
  `online_record.launch.py` creates one `online_session_<timestamp>/` with
  `session.yaml`, `calibration/`, and `episodes/`. Enter starts ordinary
  `episodes/episode_<sequence>` recordings; `c` + Enter starts dedicated
  `calibration/calibration_<sequence>` recordings; Enter stops either one.
  Each completed item is indexed in `session.yaml`. The persistent camera,
  one-time warmup, preview, video/pose contents, and stop behavior are unchanged.
- `calibrate_time` still writes its result beside calibration raw data and now
  also records accepted/rejected state, result path and signed offset in the
  containing session's `session.yaml`.
- Offline defaults to `offline_session_<timestamp>/`. It creates
  `session.yaml` and `calibration/` before rosbag2 creates `pose/`. Detailed
  offline episode and calibration rules remain deliberately undecided.
- Relevant decision: [D-015](docs/project/DECISIONS.md). Active tasks remain
  [temporal calibration](docs/project/tasks/active/temporal-calibration.md) and
  [offline acquisition](docs/project/tasks/active/offline-acquisition.md).
- Verification: 28 tests pass in an isolated ROS/venv environment; focused
  flake8, ROS 2 Jazzy symlink build, installed online/offline launch argument
  parsing, and `git diff --check` pass. Hardware acquisition using the new
  directories remains pending. The first test attempt was an environment-only
  zsh prefix failure and did not execute implementation tests.

## Current execution goal

D-014 estimator software is implemented; real calibration acceptance is next.
`calibrate_time` reads MP4 PTS, `video.timing.json`, and `/vive/pose` MCAP;
detects ArUco `DICT_4X4_50` ID 4; projects Vive position to an automatic or
configured axis; tests both signs; and searches the constant signed offset by
normalized MSE. It writes `time_offset.json` and `alignment_report.png` without
altering raw data. `generate_aruco_marker` creates the printable marker. All 26
tests, focused flake8, build, installed CLI checks and `git diff --check` pass;
generated-marker detection and reading 2,821 poses from an existing MCAP pass.
Pending: one real calibration episode, threshold/repeatability evaluation, and
consumption of accepted offset during frame-to-pose interpolation. Do not add
optical flow, Action 4 IMU, hardware sync or joint spatial-temporal calibration
to V1. No synchronization accuracy is yet claimed. Active task:
[temporal calibration](docs/project/tasks/active/temporal-calibration.md).

D-013 software implementation complete; hardware acceptance pending. Online
recording is now a long-running episode session.
Keep ROS/RViz/Vive alive; a second-terminal keyboard client toggles per-episode
MP4 + pose/TF recordings grouped inside one online session. The camera
worker opens once and warms once; waiting frames are preview-only and recording
frames are saved plus previewed without restarting the stream. Trigger services
are canonical controls. Twenty-one tests, focused flake8, package build and
launch parsing pass. A synthetic persistent worker warmed once and recorded two
sequential 24-frame/0.8-second decodable MP4s without restarting. Real D-012
warmup previously passed with 270/270 decoded frames and 208 preview messages.
Sequential episode hardware acceptance could not run on
2026-09-12 because Action 4 was not enumerated as /dev/video0. Next: reconnect
Webcam mode and run two complete episodes, checking both MP4 and MCAP outputs.

D-012 IN PROGRESS: implement real camera warmup, replacing launch delay.
Preview streams immediately; recording starts after >=5 seconds of received
frames and 15 good PTS intervals. Pose bag starts immediately with pre-roll.
Add video.timing.json, startup timeout, and isolated non-ROS GStreamer worker.
No synchronization accuracy is claimed. Validate startup and shutdown on hardware.

Startup diagnosis: direct v4l2src MJPEG → identity → fakesink reproduces
the startup burst without encoder, MP4 or ROS. Repeated do-timestamp=false
and true runs both deliver the first ~12 buffers within ~0.09–0.126 seconds;
first buffer is flagged corrupted/discont. Exact camera versus driver buffering
is not isolated. Existing warmup_seconds delays camera creation as well as the
recorder, so it does NOT warm up camera streaming. Recommended future fix:
start streaming before opening the accepted recording interval and retain
proper timestamp alignment. This turn diagnoses only; runtime code unchanged.

CURRENT D-011 supersedes the native-H264/driver work below: user selected
MJPEG UVC input → x264enc ultrafast 12000 kbps → H264 MP4. Preview JPEG queue
is bounded/leaky before decode (JPEG frames are independent); recording queue
is non-leaky. Preview remains best effort at 15 fps. No videorate or frame
duplication. Output video.mp4 + pose/ + video.validation.json remains unchanged.
Kernel repair is stopped; no module was loaded or changed. Direct MJPEG storage
is only a fallback for future poor encoding performance, not implemented now.
The existing h264_capture_node name refers to output encoding for compatibility.
Fourteen tests, venv build and online launch parsing pass. Physical pipeline
recorded 361 frames in about 12 seconds; full decode passes, max PTS gap
41.333 ms, no stderr, clean EOS. Artifact: /tmp/umi_mjpeg_test_gxspknow/video.mp4.
Physical ROS preview test received 90 BGR8 640x360 frames over 6 seconds.
RViz visual inspection and sustained simultaneous Vive/recording remain pending.

Repair attempt: USB descriptors show H264 bVariableSize=0 and bBitsPerPixel=0.
Upstream uvc_driver.c marks compression only when bVariableSize is nonzero;
uvc_video.c then overwrites uncompressed buffer size with the computed zero.
A VID/PID-scoped candidate patch and validation plan are in tools/action4_uvc/.
Not built or loaded: matching kernel source/build and administrator access are
required; sudo -n fails because a password is required. Source-level diagnosis
does not establish that camera H264 includes valid SPS/PPS or complete frames.

Hardware diagnosis 2026-09-11: host device access requires sandbox escalation.
Action 4 is present as /dev/video0, uvcvideo, USB 480M. Native H.264 at both
1080p30 and 720p30 reports sizeimage=0 and fails VIDIOC_REQBUFS with EINVAL.
Explicit sizeimage=4147200 is ignored (readback remains zero). Kernel log shows
vb2_core_reqbufs warnings. MJPEG 1080p reports sizeimage=4147200 and completes
150 buffers, but v4l2-ctl reports dropped buffers and an anomalous ~60 fps;
this is NOT a lossless capture acceptance. Restored H.264 1080p after testing.
The immediate H.264 blocker is the device/driver buffer negotiation, before
ROS, decoding or writing. Firmware versus driver responsibility is not isolated.
Next: inspect UVC negotiation/descriptor compatibility; do not claim that
switching applications or increasing CPU resources fixes the failure.

Latest update (2026-09-11, D-010): online work is resumed. User explicitly
requires native H.264 input, direct MP4 recording and one ROS preview publisher.
The pipeline drops only decoded preview frames, publishes latest BGR at 15 fps,
and retains non-leaky recording. No MJPEG fallback is selected.
Preview-derived video_timestamps.csv is removed; post-stop ffprobe writes
video.validation.json with decode status, frame count and maximum PTS gap.
This does not prove absence of source drops. Hardware is unavailable here;
previous H.264 buffer negotiation failures remain unresolved. Offline behavior
is unchanged. Older paused-online and CSV descriptions below are historical.
Current verification: 14 tests pass using the explicit venv Python; venv build
and online launch argument parsing pass. A synthetic native-H.264 pipeline
produced 60/60 decoded MP4 frames with a 33.334 ms maximum PTS interval and no
decode errors. This tests mux/preview/file checking, not the physical UVC input.

- **Goal:** Deliver pose-only offline acquisition with RViz and a session layout
  ready for later manual Action 4 video placement.
- **Status:** Offline launch/session changes are implemented and
  software-verified; hardware verification is pending. Online acquisition is paused.
- **Task:** [Implement pose-only offline acquisition](docs/project/tasks/active/offline-acquisition.md)
- **Working copy:** `/home/xing/Documents/UMI`, with pre-existing user deletions and README changes preserved.

## Scope

Current work is limited to offline computer-side Vive pose/TF recording and
RViz pose/path/TF display. It starts no camera process. The operator later adds
`video.mp4` beside the `pose/` directory. It does not include online camera work,
a temporal synchronization algorithm,
synchronization accuracy target, camera calibration implementation,
multi-device Vive publication, or LeRobot conversion.

The active offline entry is `offline_record.launch.py`. It defaults to
`recordings/offline_session_<timestamp>`, records `/vive/pose`, `/tf`, and `/tf_static`
under `pose/`, displays pose/path/TF in `umi_offline_rviz`, and starts no camera
process. The operator later adds `video.mp4` at the session root. The launch
argument is `session_output`; recorder and RViz runtime names retain the
`offline` prefix. Fourteen tests, venv build/test, launch parsing, and
`git diff --check` pass. A physical pose recording is pending.

`README.md` is the current Chinese operator guide and is intentionally organized
as a chronological procedure rather than a technical design document. It covers
preflight and environment setup, Vive checking, online startup and episode
controls, ArUco marker generation, calibration-episode recording and result
inspection, ordinary online episodes, clean shutdown, offline pose/video
collection, data checks and operator troubleshooting. Internal implementation
history and algorithm derivations stay in project records, not the README.

## Effective constraints and decisions

| Rule | Effective behavior | Source |
| --- | --- | --- |
| ROS 2 interface | Publish timestamped Vive pose and make it usable in RViz/TF. | [Requirements](docs/project/REQUIREMENTS.md) |
| Vive backend | Use pysurvive directly; do not depend on SteamVR/OpenVR. | User decision [D-001](docs/project/DECISIONS.md) |
| Coordinates | Retain libsurvive's calibrated right-handed pose and reorder quaternion `wxyz` to ROS `xyzw`. | [Architecture](docs/project/ARCHITECTURE.md) |
| Dependency boundary | Keep pysurvive and ROS integration separate; pose adaptation remains hardware-independent. | [Architecture](docs/project/ARCHITECTURE.md) |
| Existing worktree | Do not alter or restore unrelated deleted files. | Working-tree evidence at task start |
| Camera hardware | Use DJI Action 4 rigidly mounted with the Vive Tracker on the same gripper; disable EIS. | User decision [D-003](docs/project/DECISIONS.md) |
| Offline mode | Primary mode; record 4K/60 fps to microSD without USB while Linux records Vive pose and RViz displays pose/path/TF. | User decision [D-003](docs/project/DECISIONS.md) |
| Online mode | Use native H.264 USB capture at 1080p/30 without SD recording; write MP4 directly and publish only a decoded best-effort preview to RViz. | User decision [D-009](docs/project/DECISIONS.md) |
| Recording boundary | Preserve offline MP4 plus pose bag and metadata. Online writes H.264 MP4 plus frame timestamps and a separate pose/TF MCAP in one session; never record `/vive/path`. | [D-008](docs/project/DECISIONS.md) |
| Python build/runtime | Source ROS 2 Jazzy, activate `/home/xing/umi_ros_venv`, and use its `python` and `colcon`; keep `setuptools==68.1.2`. | User decision [D-005](docs/project/DECISIONS.md) |
| Target code structure | All project-owned ROS runtime is consolidated in `umi_ros2`; shared, offline-only, and online-only responsibilities remain explicit, and one-shot processing stays outside ROS nodes. | User decision [D-007](docs/project/DECISIONS.md) |

## Current state and verification

Under D-009, active online launches now use `action4_h264_capture_node` instead
of `usb_cam`, `raw_mjpeg_bridge_node`, and `video_recorder_node`. It launches one
external `gst-launch-1.0` process that remuxes native 1080p30 H.264 into MP4 and
emits decoded 640x360 BGR frames through stdout. A Python reader drains the pipe
and overwrites one latest-frame slot; the ROS executor publishes it best-effort.
Observation mode omits the MP4 output. The old compressed preview executable
remains only for legacy combined-bag replay.

Software verification: 14 tests pass; the venv ROS build, camera/online-view/
online-record launch parsing, compile checks, and `git diff --check` pass.
The first physical runs exposed a PyGObject/rclpy initialization crash. After
removing that binding, FFmpeg V4L2 failed `VIDIOC_REQBUFS` with EINVAL even
though H.264 is advertised. The active node therefore launches external
GStreamer, with no in-process GStreamer binding. Fourteen tests and the rebuilt
package pass. Because mmap failed when the device returned no H.264 buffer size,
the active configuration now tries V4L2 `rw` mode; physical rerun is pending.

Implemented files are under `umi_ros2/`; runtime parameters select libsurvive
name/serial/index, libsurvive arguments, frames, topic, rate, and TF publication.
The node also publishes `/vive/path`, retaining at most `max_path_points`, and
`online_view.launch.py` opens RViz with that path, TF, and image configured.
`vive.launch.py` starts only the pose node. `offline_record.launch.py` reuses
Vive and pose-only RViz without starting the USB camera. The experimental drift
monitor was removed at the user's request on 2026-09-09.

- The original Vive backend tests were migrated into the unified suite.
- `python3 -m compileall` and `py_compile`: passed.
- `flake8 --jobs 1`: passed after formatting.
- `git diff --check`: passed.
- ROS 2 Jazzy `colcon build --packages-select umi_ros2 --symlink-install`: passed.
- ROS 2 Jazzy `colcon test` and `colcon test-result --verbose`: 13 tests,
  0 errors, 0 failures, 0 skipped.
- All six installed `umi_ros2` launch files parse successfully with
  `ros2 launch ... --show-args`.
- Physical Vive/libsurvive pose: user-verified as correct on 2026-09-08; no
  captured topic log or device identity is recorded.
- RViz path rendering and pose/TF agreement: not yet confirmed.
- Tracking-loss and recovery behavior: not yet hardware-tested.
- User combined-launch log on 2026-09-09: the pose node detected `WM0`, RViz2
  opened, and one libsurvive `MP_MAXITER` warning occurred. The experimental
  drift monitor also started in that run but has since been removed.

The pose portion of hardware acceptance is satisfied by the user's report.
Remaining acceptance covers path rendering, TF agreement, loss/recovery,
and timestamp suitability. The current stamp is ROS publication time rather than
the libsurvive pose time, which matters for later camera synchronization.

The camera design and all ROS runtime/recording entry points are consolidated in
`umi_ros2`.
On 2026-09-10 Linux identified the Action 4 as USB `2ca3:0023` through
`uvcvideo`. `/dev/video0` is the capture node; `/dev/video1` is not advertised
as a capture node. The camera advertises MJPEG and H.264 at 1280x720/30 and
1920x1080/30. A 1920x1080 MJPEG frame was captured successfully, and a 300-frame
1080p/30 GStreamer run completed in 9.913 seconds with no reported negotiation,
drop, or USB errors. The UVC device serial reported by udev is
`123456789ABCDEF` and should be treated as a likely firmware placeholder rather
than a verified unique physical identity. 4K/60 SD behavior, thermal limits,
and simultaneous USB operation with Vive remain untested. Temporal
synchronization is intentionally deferred.

The superseded online path started the official ROS 2 `usb_cam` driver with Action 4
`raw_mjpeg` 1920x1080/30 and `mmap`, remapping its standard output to
`/action4/image_raw` and `/action4/camera_info`. A project-owned bridge extracts
the source JPEG into `/action4/image_raw/compressed` without recompression and
decodes a 640x360 BGR8 `/action4/image_preview`. The prior custom
GStreamer capture node was removed. Its historical hardware measurement was
about 29.95–29.98 fps, but that does not verify the new driver path.
The preview publisher uses best-effort sensor-data QoS, with matching RViz
configuration. The camera launch does not start rosbag2 or write recordings.
`online_view.launch.py` now starts both hardware nodes and RViz, whose Image
display is preconfigured for `/action4/image_preview`. Preview publisher and
RViz are both configured for best-effort delivery. The updated 30 fps preview
still requires runtime verification.

The active `umi_ros2/launch/online_record.launch.py` starts Vive and RViz, then
after a five-second delay starts native-H.264 capture and pose-only rosbag2
together. The camera process directly creates `video.mp4` and
`video_timestamps.csv`; rosbag2 writes `/vive/pose`, `/tf`, and `/tf_static`
under `pose/`. Preview and `/vive/path` are not recorded. Hardware or recorder
exit stops the complete launch.

Legacy combined online bags can be replayed with `umi_ros2/replay.launch.py`.
It runs rosbag2
with `/clock`, decodes recorded MJPEG to the best-effort RViz preview, and uses
the unified `replay_path_node` to reconstruct `/vive/path` from `/vive/pose`.
The inspected bag `online_20260910_205248` contains 609 images at approximately
29.9 fps, 612 CameraInfo messages, and 1654 each of pose and TF over 20.349
seconds. Playback image publication and RViz subscription were endpoint-verified.
Manual Ctrl+C caused one RViz/Qt `std::system_error`, while decoder/player
shutdown was clean; natural end-of-bag shutdown had completed normally earlier.

The first complete bag made with the superseded GStreamer node had one 135.506 ms image gap at 0.328 seconds, equivalent
to roughly three 30-fps periods; after one second its maximum interval was
40.984 ms with no gaps over 50 ms. The former PTS mapper was removed with that
node. `online_record.launch.py` retains a configurable `warmup_seconds=5.0`
delay. `usb_cam` supplies the new image timestamps, which require fresh hardware
continuity validation.

The workspace build/runtime interpreter was switched to
`/home/xing/umi_ros_venv/bin/python` on 2026-09-10. The venv uses Python 3.12.3,
can import `rclpy`, GStreamer, and `pysurvive`, and now contains a local colcon
0.21.1 entry point. `setuptools` was changed from incompatible 84.0.0 to the
ROS-compatible 68.1.2. The consolidated `umi_ros2` package builds in the venv;
all four installed console scripts use the venv Python and all six launch files
parse successfully.

## Open items

- D-009 is implemented but not runtime-accepted: install the H.264 GStreamer
  plugins and validate the native-H.264 camera process with Action 4 hardware.

- Exact Vive device/model, selected name/serial, and calibration configuration
  used in the successful run are not recorded. Configure a stable name or serial
  rather than relying on the first detected object before repeatable collection.
- Moving a lighthouse or clearing libsurvive configuration can change the world
  frame and requires recalibration.
- `/vive/path` is capped but republishes the growing path at pose rate, can use
  substantial bandwidth, and resets on node restart.
- There is no explicit tracking-status/confidence topic or pose covariance.
- Sustained topic rates and path visibility are not recorded.
- Vive's duplicate `rclpy.shutdown()` call on Launch SIGINT was guarded after it
  reproduced during the first combined camera run; software re-verification is
  complete, while a final hardware shutdown rerun remains.
- Supported ROS 2 distribution range is unconfirmed; local build used Jazzy.
- Camera/Vive temporal synchronization method and acceptance accuracy are not set.
- Action 4 camera intrinsics and the rigid camera-to-Tracker transform are not calibrated.
- Online recording bypasses ROS image transport: native H.264 goes directly to
  MP4, while only a lower-resolution raw `Image` is published for preview.
  MP4 plus pose-only MCAP orchestration is implemented; sustained hardware
  write performance is untested.

## Read-on-demand entries

- [Requirements](docs/project/REQUIREMENTS.md) for confirmed project scope.
- [Architecture](docs/project/ARCHITECTURE.md) for module boundaries.
- [Decisions](docs/project/DECISIONS.md) for the accepted pysurvive backend.
- [Active task](docs/project/tasks/active/vive-ros2-node.md) for detailed evidence.
- [Camera task](docs/project/tasks/active/action4-acquisition.md) for the next delivery.
- [Temporal calibration task](docs/project/tasks/active/temporal-calibration.md)
  for the current estimator and real-data acceptance work.
- [Completed package consolidation](docs/project/tasks/archive/consolidate-ros-package.md)
  for migration evidence.
- `README.md` for operator build and launch instructions.

User-facing status is in [project.md](project.md).

## Synchronization note

On 2026-09-09, drift diagnostics were rolled back at the user's request. The
active delivery is again pose/path/TF only. Four tests, ROS 2 build/test, launch
argument parsing, and installed executable inspection all pass; only
`vive_pose_node` remains installed. The existing upstream Git repository is now
used for local checkpoints; colcon and Python generated outputs are ignored. On
2026-09-10 the confirmed Action 4 mode and recording boundaries were added. The
Action 4 UVC link and MJPEG 1080p/30 capture were then hardware-verified using
the former node. On 2026-09-11 online capture was switched to official ROS 2
`usb_cam`; version 0.8.1 is installed and repository build/tests pass, but a new
hardware bag remains pending.

On 2026-09-11 the online recording boundary changed under D-008. The new writer
uses the host FFmpeg `libx264` encoder to produce H.264/yuv420p MP4, stores one
CSV row per successfully submitted video frame, and keeps pose/TF in a separate
MCAP directory. Unit/contract tests, the venv build, launch argument parsing,
`git diff --check`, and a synthetic 1920x1080/30 H.264 MP4 encode passed. A
physical one-minute Action 4 plus Vive session is still required for acceptance.

The installed driver rejected `pixel_format: mjpeg`; its accepted passthrough
name is `raw_mjpeg`. Direct RViz display of `/action4/image_raw` produced a green
corrupted view because those bytes are JPEG rather than packed pixels. The first
compressed preview then received no input, and a subsequent `mjpeg2rgb` hardware
test crashed `usb_cam_node_exe` with SIGSEGV (`exit code -11`) after timer start.
The current workaround keeps `usb_cam` in `raw_mjpeg` capture mode and uses
`action4_raw_mjpeg_bridge_node` to locate JPEG SOI/EOI, remove padding, publish
the original JPEG as `CompressedImage`, and decode only the 640x360 preview.
The consolidated suite has 13 passing tests; flake8, compileall, the unified
venv build, all launch parsers, and `git diff --check` pass. This final camera
path is not hardware-accepted.
