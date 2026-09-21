# UMI — Development decisions

## D-019: Decoupled raw-to-dataset post-processing pipeline

- **Status:** Accepted on 2026-09-20.
- Post-processing is an ordinary Python workflow with four independently
  runnable stages: temporal calibration, frame/pose alignment, episode-local
  coordinate transformation, and format-specific export.
- Raw sensor artifacts are immutable. Calibration may attach reviewed metadata
  to the session; later stages consume versioned contracts and write to a
  separate processed-data root.
- Episode-local coordinates use the first valid aligned video-frame pose as
  the reference: `T_episode_i = inverse(T_world_0) * T_world_i`. Invalid frames
  remain invalid; the transform stage does not extrapolate or repair tracking.
- HDF5 and native LeRobot v3 are supported export targets. Both format
  exporters depend on the transformed intermediate contract, never on ROS bags
  or calibration internals, so either exporter can change without changing
  synchronization or coordinate math.
- One orchestration CLI may run the stages in order, but orchestration contains
  no calibration, interpolation, transform, or serialization algorithms.

## D-014: First temporal calibration uses the exUMI trajectory method

- **Status:** Accepted for the first implementation on 2026-09-12.
- Record one dedicated calibration episode after the online camera completes
  its one-time warmup. Keep an ArUco marker fixed and move the rigid Action 4 +
  Vive assembly horizontally left and right several times, with stationary
  intervals before and after the motion.
- Extract one scalar marker-motion trajectory from video and the corresponding
  Vive motion trajectory. Interpolate both trajectories and search a bounded
  time offset; select the offset that minimizes normalized trajectory MSE, as
  described by exUMI. Preserve the offset sign convention explicitly.
- Store the estimated video-to-pose offset, search bounds, residual/error,
  confidence/acceptance facts and a visual alignment report. Do not silently
  accept a weak or ambiguous match.
- One accepted calibration applies only to the same uninterrupted acquisition
  session: camera/Vive restart or reconnect, stream-parameter change, or clock
  discontinuity requires a new calibration. Ordinary episode boundaries do not.
- First delivery excludes optical-flow fallback, Action 4 IMU alignment,
  hardware triggering and joint spatial-temporal optimization. exUMI's reported
  `<50 ms` result is reference evidence, not an accuracy claim for this system.

## D-013: Long-running online session with episode controls

- Keep Vive, camera control, preview, RViz and launch alive across episodes.
- `start_episode` creates a new `online_episode_<timestamp>` directory and starts
  video plus pose/TF recording. `stop_episode` finalizes both artifacts and
  returns to preview. Repeated start/stop creates independent episodes.
- Provide ROS Trigger services as the reliable control interface and a terminal
  keyboard executable: Enter toggles start/stop; `q` exits only the controller.
- The camera worker opens once with the online launch and performs D-012 stream
  warmup only once. It then stays alive in `waiting` or `recording`. Waiting
  frames feed preview but are discarded by the recorder; recording frames feed
  both preview and the active episode MP4. Episode transitions do not reopen
  the camera or interrupt preview.
- Reject start while recording and stop while idle. Ctrl+C remains whole-system
  shutdown and finalizes an active episode.

## D-012: Warm up the running camera before accepting video

- User approves genuine camera-stream warmup after the startup-burst diagnosis.
- Start one continuous MJPEG stream immediately; keep preview active. Accept
  recording frames only after at least 5 seconds from the first received buffer
  and 15 consecutive valid source-PTS intervals within 0.5–1.5 frame periods.
  Warmup is bounded by a 30-second startup timeout. Do not restart the camera.
- Implementation choice: pose bag starts immediately and retains pre-roll so
  the video start is covered. Video timing metadata records the first accepted
  source PTS and host receive clocks; neither is a calibrated exposure timestamp.
  Pose and MP4 time zero must not be assumed equal. Synchronization is deferred.
- Use a ROS-free GStreamer worker process to control the recording gate, keeping
  PyGObject and rclpy out of the same process because of the prior native crash.
- Once recording starts, never discard frames to satisfy the interval test.
  Preserve later irregularities and report them. Early stop before readiness is
  not a valid video recording. Offline capture is unchanged.

## D-011: MJPEG input with H.264 MP4 encoding

User supersedes native-H.264 input requirement and stops kernel repair work.
Capture MJPEG 1080p30, encode H.264 MP4, keep a best-effort RViz preview and
separate pose bag. Recording must not intentionally drop frames. Direct MJPEG
storage is only a future fallback if encoding performance is inadequate.
No kernel module was changed or loaded. Retain diagnostic patch as inactive.

## D-010: Resume online recording with MP4 completeness as priority

- **Date:** 2026-09-11
- **Source:** User relaxes online requirements to complete MP4 recording plus
  one ROS preview publisher. Preview frame delivery is not an acceptance target.
- **Latest user clarification:** Input must remain native H.264. Remux to MP4
  without re-encoding. The briefly proposed MJPEG fallback is not adopted.
  Native H.264 negotiation previously failed and needs hardware verification.
- Recording queues must not intentionally drop buffers. Preview uses a bounded
  leaky queue after H.264 decoding and a latest-frame slot. Never drop arbitrary
  compressed H.264 frames before decoding.
- Remove preview-derived `video_timestamps.csv`: it is not a video frame log.
  Save a post-stop MP4 validation report; source completeness remains pending
  real-device validation and cannot be proved by a nominal 30 fps alone.
- Offline acquisition stays available. No synchronization algorithm is added.

## D-001: Use pysurvive for Vive tracking

- **Status:** Accepted
- **Date:** 2026-09-07
- **Source:** The user explicitly requested `pysurvive` instead of OpenVR.
- **Decision:** Acquire Vive poses through libsurvive's high-level
  `pysurvive.SimpleContext` API. This node does not require SteamVR or OpenVR.
- **Impact:** The host needs libsurvive, pysurvive, suitable USB rules,
  lighthouse calibration, and connected Vive hardware.
- **Supersedes:** The initial task-level choice to use SteamVR/OpenVR.
- **Current evidence:** On 2026-09-08 the user reported that the live Vive pose
  is correct and has no observed problem. Path, TF, loss recovery, and timestamp
  suitability were not included in that report.

## D-002: Publish stationary-reference drift diagnostics (withdrawn)

- **Status:** Withdrawn on 2026-09-09
- **Date:** 2026-09-09
- **Source:** The user requested publication and RViz visualization of apparent
  position and velocity drift while the Vive is physically stationary.
- **Decision:** `vive_drift_monitor_node` uses the first pose, or a reset pose,
  as its reference. It publishes displacement, displacement magnitude,
  finite-difference linear/angular velocity, speed, and RViz arrow markers.
- **Interpretation constraint:** The node observes motion in tracking output; it
  cannot classify physical movement versus sensor drift. Values represent drift
  only when the operator keeps the tracker stationary.
- **Withdrawal:** After trying the combined launch, the user requested a rollback
  because the result was not useful enough. Drift-related nodes, topics, markers,
  dependencies, tests, configuration, and launch integration are removed for now.

## D-003: Support separate offline and online DJI Action 4 modes

- **Status:** Accepted
- **Date:** 2026-09-10
- **Source:** User camera-acquisition design decision.
- **Decision:** DJI Osmo Action 4 is the camera. Offline acquisition is the
  primary mode: the camera records 4K/60 fps to microSD without a USB image
  connection, while Linux records Vive pose and RViz displays pose/path/TF.
  Online acquisition is separate: the camera connects to Linux over USB at a
  target 1080p/30 fps, does not record to microSD, and ROS 2 records and displays
  image and pose streams.
- **Physical constraint:** The Action 4 and Vive Tracker are rigidly mounted on
  the same gripper. Electronic image stabilization is disabled.
- **No hybrid mode:** SD recording and USB preview are not combined.
- **Pending:** Linux UVC formats and sustained operation require hardware
  validation. Temporal synchronization method and accuracy target are deferred.

## D-004: Preserve source-native acquisition data

- **Status:** Accepted
- **Date:** 2026-09-10
- **Source:** User requirements plus the agreed post-processing layout.
- **Decision:** Offline sessions retain Action 4 MP4 files, Vive rosbag2, and
  session/calibration metadata. The original online design used one rosbag2 for
  camera, pose, camera information/status, and TF topics; that online portion is
  superseded by D-008. `/vive/path` is visualization only and is not recorded
  because it can be reconstructed from `/vive/pose`.
- **Pending:** Exact online image transport/compression and the synchronized
  intermediate schema will be selected during implementation.

## D-005: Use the UMI Python virtual environment for ROS 2 builds

- **Status:** Accepted
- **Date:** 2026-09-10
- **Source:** User development-environment decision.
- **Decision:** Python ROS 2 packages in this workspace are built and run with
  `/home/xing/umi_ros_venv`, using Python 3.12 and system site packages for ROS
  2 Jazzy and GStreamer. Source `/opt/ros/jazzy/setup.bash` before activating
  the venv, then invoke the venv-local `colcon` entry point.
- **Compatibility constraint:** Pin `setuptools==68.1.2`. Version 84.0.0 failed
  because the current colcon Python build extension still passes the removed
  `setup.py --uninstall` option.

## D-006: Use the official ROS 2 usb_cam driver for online Action 4 capture

- **Status:** Accepted
- **Date:** 2026-09-11
- **Source:** The user requested replacing the custom online camera capture with
  the official ROS `usb_cam` package.
- **Decision:** Start `usb_cam_node_exe` with Action 4 UVC settings
  (`raw_mjpeg`, 1920×1080, 30 fps, mmap). Remap its standard image and CameraInfo
  interfaces into `/action4`. A project-owned bridge extracts the source JPEG
  for recording and decodes only the 640×360 RViz preview.
- **Compatibility:** Preserve `/action4/image_raw/compressed`,
  `/action4/image_preview`, and `/action4/camera_info`, so recording and replay
  contracts do not change.
- **Supersedes:** The custom Python/GStreamer live capture node and its PTS
  mapping. Existing bags remain replayable.
- **Pending:** Perform a new hardware recording. The driver switch does not
  itself prove zero dropped frames.

## D-007: Consolidate project-owned ROS runtime into one package

- **Status:** Implemented
- **Date:** 2026-09-11
- **Source:** The user accepted the proposed macro-level cleanup and requested
  explicit separation of shared, online-only, and offline-only responsibilities.
- **Decision:** Consolidate `vive_ros2`, `action4_ros2`, and `umi_bringup` into
  one project-owned ROS package, provisionally named `umi_ros2`. One ROS package
  may contain multiple focused executables; package boundaries will not mirror
  individual nodes. Keep non-realtime inspection, synchronization, validation,
  and dataset conversion as ordinary tools rather than ROS nodes.
- **Shared layer:** Vive acquisition, common pose/TF interfaces, session identity
  and metadata, calibration records, validation/reporting conventions, reusable
  visualization assets, and the eventual normalized post-processing contract.
- **Offline-only layer:** Action 4 microSD 4K/60 recording workflow, Linux
  pose-only recording, SD video import, and offline image/pose alignment.
- **Online-only layer:** Action 4 USB/UVC acquisition, JPEG bridge and live image
  preview, combined image-plus-pose rosbag2 recording, and online-bag replay.
- **Compatibility:** Preserve current ROS topic names and existing MCAP replay.
  Migrate before deleting old packages, and verify each launch path before the
  old structure is removed.
- **Implemented:** `umi_ros2` now owns all project nodes, launch files,
  configuration, RViz assets, and tests. The three superseded package sources
  and stale build/install artifacts were removed after verification.

## D-008: Separate online video and pose storage

- **Status:** Accepted
- **Date:** 2026-09-11
- **Source:** The user requested that online image and pose acquisition be
  stored separately while remaining in one session directory.
- **Decision:** Online acquisition writes the Action 4 stream as one H.264 MP4
  video and records only Vive pose and TF in a separate MCAP rosbag2 directory.
  A frame-timestamp sidecar is stored beside the video so later synchronization
  does not depend on MP4 frame rate alone. RViz continues to display the live
  low-resolution image preview and Vive pose/path/TF.
- **Session boundary:** One `online_<timestamp>` directory owns `video.mp4`,
  `video_timestamps.csv` and a `pose/` rosbag2 directory.
  `/vive/path`, preview images, source JPEG messages, and CameraInfo are not
  recorded in the pose bag.
- **Rationale:** LeRobot stores visual streams as MP4 and low-dimensional
  timestamped signals separately; DROID likewise separates MP4 recordings from
  trajectory data. Keeping raw pose/TF in MCAP at acquisition time preserves
  ROS timestamps and types until the synchronization and final dataset schema
  are defined.
- **Supersedes:** The online portion of D-004 that put camera and pose topics in
  one rosbag2 recording. D-004 remains effective for offline acquisition.

## D-009: Capture native H.264 and make RViz preview secondary

- **Status:** Accepted; implementation pending
- **Date:** 2026-09-11
- **Source:** The user selected Action 4 native H.264 for online acquisition and
  stated that recording has higher priority than visualization.
- **Decision:** Replace the online MJPEG-through-ROS recording path with one
  Python ROS node and one external GStreamer child process. GStreamer captures
  native H.264, remuxes it into MP4, and outputs decoded 640×360 BGR frames
  through stdout. Python retains only the newest frame and publishes it
  best-effort. Python does not import PyGObject.
- **Priority rule:** Video capture and file finalization must not wait for RViz,
  DDS delivery, preview decoding, or resizing. Preview frames may be dropped;
  recording errors must be visible and terminate the session.
- **Clarification:** RViz does not require MJPEG. It requires a decoded ROS
  image representation; H.264 may remain encoded on the recording branch and
  only the preview branch needs decoding.
- **Supersedes:** D-006 for the active online capture implementation. The old
  `usb_cam`/raw-MJPEG path and legacy bag replay remain historical compatibility
  evidence until the H.264 path passes hardware acceptance.

## D-010: Focus on pose-only offline acquisition

- **Status:** Accepted
- **Date:** 2026-09-11
- **Source:** The user requested an offline-first implementation and paused
  consideration of the online camera path.
- **Decision:** The computer-side offline workflow starts no camera process and
  records only `/vive/pose`, `/tf`, and `/tf_static`, while RViz displays pose,
  path, and TF. Each session is named `offline_<timestamp>` and stores rosbag2
  output under `pose/`.
- **Later image placement:** The operator later copies the corresponding Action
  4 recording into the same session root as `video.mp4`. This yields the same
  top-level `video.mp4` plus `pose/` boundary used by online sessions and avoids
  changing downstream calibration inputs.
- **Excluded:** `/vive/path` is not recorded, and offline acquisition does not
  start USB camera capture, image publication, video import, or synchronization.
- **Scheduling impact:** Online acquisition remains in the repository but is
  paused and is not the current implementation or acceptance priority.

## D-015: Use an explicit session-level recording layout

- **Status:** Accepted
- **Date:** 2026-09-13
- **Source:** The user requested a shared session organization for online and
  offline acquisition, while leaving the detailed offline episode design open.
- **Decision:** Each acquisition launch creates one timestamped session with a
  root `session.yaml`. Online ordinary recordings are stored under
  `episodes/episode_<sequence>/`; dedicated temporal-calibration recordings are
  stored separately under `calibration/calibration_<sequence>/`. One online
  launch process owns one session and may contain many recordings.
- **Offline boundary:** Offline acquisition creates
  `offline_session_<timestamp>/session.yaml`, `calibration/`, and `pose/`.
  The current pose-only behavior is otherwise unchanged. No offline episode or
  calibration-file schema is implied until those workflows are confirmed.
- **Compatibility:** `session_output` remains the launch argument. For online
  acquisition it denotes the parent recordings directory in which the runtime
  creates a session; for offline acquisition an explicit override denotes the
  session directory itself.

## D-016: Replay sessions and individual recordings through one entry point

- **Status:** Accepted
- **Date:** 2026-09-13
- **Source:** The user requested automatic replay-level detection and ordered
  session playback.
- **Decision:** `replay.launch.py` accepts either a session root or one concrete
  calibration/episode directory. A session is replayed in deterministic order:
  all `calibration_<sequence>` items, followed by all `episode_<sequence>`
  items. A concrete recording is replayed directly.
- **Separated-artifact behavior:** The replay coordinator publishes decoded
  `video.mp4` frames to `/action4/image_preview` while invoking rosbag2 for the
  matching `pose/`. It uses the video receive anchor and bag start timestamp to
  preserve their recorded relative start, but does not apply the estimated
  temporal-calibration offset. The RViz path resets between recordings.

## D-017: Keep synchronization and dataset export outside ROS

- **Status:** Accepted
- **Date:** 2026-09-13
- **Source:** The user completed the recording path and requested Python-only
  post-processing for temporal alignment and dataset preparation.
- **Decision:** Implement post-processing as ordinary Python command-line tools,
  not ROS nodes or launch files. The pipeline reads session metadata, MP4 frame
  PTS, accepted temporal offset, and pose MCAP; computes one corrected timestamp
  and interpolated pose per video frame; validates the result; and exports a
  normalized intermediate representation to LeRobot and/or HDF5.
- **Data integrity:** Raw session files are read-only inputs. Aligned indexes,
  validation reports, and exported datasets are written to separate output
  paths and must identify their source session and calibration result.
- **Dependency clarification:** Reading ROS-recorded MCAP may still use Python
  libraries for ROS message deserialization, but no ROS graph, running node,
  DDS communication, RViz, or launch process is required.

## D-018: Keep the online pose recorder subscribed for the whole session

- **Status:** Accepted
- **Date:** 2026-09-13
- **Source:** The user selected persistent pose recording and required separate
  per-recording bags plus pose warmup alongside the camera warmup.
- **Decision:** Start one internal pose-recorder node per online session. It
  subscribes continuously to `/vive/pose`, `/tf`, and `/tf_static`; during the
  initial five-second warmup it receives but does not store messages. Each
  calibration or ordinary episode opens a fresh MCAP writer in that recording's
  own `pose/` directory, while waiting periods remain unrecorded.
- **Start boundary:** After an episode command, open the new pose writer and
  require its first `/vive/pose` sample before enabling MP4 writing. Stop MP4
  first and pose second. This removes per-episode DDS discovery latency without
  merging episode files or inventing pose extrapolation.
