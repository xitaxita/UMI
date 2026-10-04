# UMI — Development decisions

Decisions are listed in number order. The index below gives each decision's
current status; a decision replaced in whole or in part carries an index note
under its title. The text of each decision is kept as it was accepted.
Numbers were assigned in time order, except that two decisions share D-010.

| Decision | Title | Status |
| --- | --- | --- |
| D-001 | Use pysurvive for Vive tracking | Current |
| D-002 | Publish stationary-reference drift diagnostics (withdrawn) | Withdrawn |
| D-003 | Support separate offline and online DJI Action 4 modes | Partly superseded |
| D-004 | Preserve source-native acquisition data | Partly superseded |
| D-005 | Use the UMI Python virtual environment for ROS 2 builds | Current |
| D-006 | Use the official ROS 2 usb_cam driver for online Action 4 capture | Superseded |
| D-007 | Consolidate project-owned ROS runtime into one package | Current |
| D-008 | Separate online video and pose storage | Current, amended |
| D-009 | Capture native H.264 and make RViz preview secondary | Superseded |
| D-010 | Resume online recording with MP4 completeness as priority | Partly superseded |
| D-010 (offline) | Focus on pose-only offline acquisition | Superseded |
| D-011 | MJPEG input with H.264 MP4 encoding | Current |
| D-012 | Warm up the running camera before accepting video | Current, amended |
| D-013 | Long-running online session with episode controls | Current, amended |
| D-014 | First temporal calibration uses the exUMI trajectory method | Current, amended by D-024 |
| D-015 | Use an explicit session-level recording layout | Current, amended |
| D-016 | Replay sessions and individual recordings through one entry point | Current |
| D-017 | Keep synchronization and dataset export outside ROS | Current |
| D-018 | Keep the online pose recorder subscribed for the whole session | Current |
| D-019 | Decoupled raw-to-dataset post-processing pipeline | Current |
| D-020 | Define the measured Tracker-to-gripper TCP extrinsic | Current; values refreshed 2026-10-04 |
| D-021 | One task per online session, multi-session datasets, no offline mode | Current |
| D-022 | Simplify the project structure | Current |
| D-023 | Calibrate immediately after recording calibration data | Current |
| D-024 | Use translation-only motion for temporal calibration | Current |
| D-025 | Keep calibration data retryable after processing failures | Current |
| D-026 | Replace stale calibration diagnostics on a new result | Current |
| D-027 | Unified camera interface and per-camera image-to-pose calibration | In progress |
| D-028 | RealSense color acquisition through the common camera interface | Implemented; color hardware verified |
| D-029 | Record Action 4 and RealSense color in one online session | Implemented; raw layout amended by D-031 |
| D-030 | Use D435i as the left color camera | Implemented; color hardware verified |
| D-031 | Store every camera under its own recording directory | Implemented; migrated current episode |
| D-032 | Use one pose coverage acceptance check for the current setup | Superseded by D-035 |
| D-033 | Save pose for 500 ms before starting camera recording | Implemented; hardware verified |
| D-034 | Build the live Vive path in a separate 30 Hz node | Implemented; software verified |
| D-035 | Automatically accept or reject each completed episode | Implemented; software verified |
| D-036 | Select and retry translation-only calibration per camera | Implemented; software verified |
| D-037 | Calibrated dual-camera RViz episode review | Implemented; live replay verified |
| D-038 | Use the recording-start TCP frame for calibration and derived poses | Implemented; software verified |
| D-039 | Select the D435i RGB USB interface by serial | Implemented; startup confirmed by user |
| D-040 | Inspect aligned image and pose in a manual local viewer | Implemented; real-file GUI verified |
| D-041 | Two image streams with current and next TCP poses | Standalone expansion/local poses verified; action/export/integration pending |

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

> **Index status:** Partly superseded. Offline mode superseded by D-021. Camera choice, rigid mount, EIS off and online USB 1080p/30 still apply.

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

> **Index status:** Partly superseded. Offline storage superseded by D-021 and online single-bag storage by D-008. "`/vive/path` is not recorded" still applies.

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

> **Index status:** Superseded. `usb_cam` capture replaced by D-009 and then D-011.

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

> **Index status:** Current, amended. Separate MP4 + pose MCAP still applies. `video_timestamps.csv` was replaced by timing/validation JSON (D-010), and the directory layout by D-015.

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

> **Index status:** Superseded. Native H.264 input replaced by D-011. The rule that preview is secondary to recording still applies.

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

## D-010: Resume online recording with MP4 completeness as priority

> **Index status:** Partly superseded. MP4-completeness priority and the validation report still apply. Native H.264 input replaced by D-011. "Offline stays available" superseded by D-021.

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

## D-010: Focus on pose-only offline acquisition

> **Index status:** Superseded. Offline mode removed by D-021.

- **Status:** Superseded by D-021 on 2026-09-28 (offline mode removed).
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

## D-011: MJPEG input with H.264 MP4 encoding

User supersedes native-H.264 input requirement and stops kernel repair work.
Capture MJPEG 1080p30, encode H.264 MP4, keep a best-effort RViz preview and
separate pose bag. Recording must not intentionally drop frames. Direct MJPEG
storage is only a future fallback if encoding performance is inadequate.
No kernel module was changed or loaded. Retain diagnostic patch as inactive.

## D-012: Warm up the running camera before accepting video

> **Index status:** Current, amended. Camera warmup still applies. Per-recording pose pre-roll replaced by the persistent pose recorder (D-018).

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

## D-013: Long-running online session with episode controls

> **Index status:** Current, amended. Directory naming amended by D-015; in-launch session switching added by D-021.

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

## D-014: First temporal calibration uses the exUMI trajectory method

> **Index status:** Current, amended. See its multi-feature amendment.

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

### D-014 amendment: fuse all reliable marker and TCP motion channels

- **Status:** Accepted by user request on 2026-09-21.
- Replace the first scalar-only estimator with a backward-compatible
  multi-feature estimator. Video features are ArUco centre X/Y, logarithmic
  area and unwrapped in-plane angle; pose features are TCP XYZ and a continuous
  rotation vector derived from the recorded quaternion.
- Estimate one constant offset from both multivariate trajectory agreement and
  motion-energy agreement. Refine the discrete search minimum quadratically,
  report per-window repeatability, and reject weak, ambiguous or inconsistent
  results. Preserve the explicit `pose_time = video_time + offset` convention.
- Do not claim camera-to-marker 3D pose without calibrated camera intrinsics.
  Optical flow, Action 4 IMU and hardware synchronization remain separate
  future improvements.

> **Current estimator scope:** D-024 supersedes D-014's inclusion of ArUco
> in-plane angle and TCP rotation channels. The 2026-09-21 implementation
> details above document the historical v2 estimator.

## D-015: Use an explicit session-level recording layout

> **Index status:** Current, amended. Offline boundary and one-session-per-launch rule amended by D-021.

- **Status:** Accepted; offline boundary superseded and one-session-per-launch
  rule amended by D-021 (2026-09-28).
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

## D-020: Define the measured Tracker-to-gripper TCP extrinsic

> **Index status:** Current, amended. Configuration source amended by D-022;
> active numbers superseded by the 2026-10-04 amendment below.

- **Status:** Accepted on 2026-09-21; configuration source amended by D-022.
- The supplied `co2_in_co1.txt` defines co1 as parent `vive_tracker` and co2 as
  child `gripper_tcp`.
- The transform was remeasured on 2026-09-21. Its historical translation was
  `[0.0, -0.080371453, 0.194957425]` metres
  and ROS-order quaternion
  `[0.628736470, -0.628736470, 0.323559039, 0.323559039]` (XYZW).
- Since D-022 the only copy is `vive_pose_node` parameters
  `tracker_to_tcp_translation_m` / `tracker_to_tcp_rotation_xyzw` in
  `umi_ros2/config/vive.yaml` (read at startup, validated live updates via
  `ros2 param set`). The node applies them to TCP pose/path and publishes both
  raw Tracker and converted TCP TF.

### D-020 amendment: Refresh extrinsic from the user's current measurement

- **Status:** Explicit user instruction recorded before implementation on
  2026-10-04. The user identifies the configured transform as outdated and
  requests the current `co2_in_co1.txt` from the 3D-print design directory.
- **Source:** The supplied `.../Use/Documents/...` path does not exist; the
  matching file is `/media/xing/zijun/User/Documents/课题组/UMI/3Dprint/UMI/co2_in_co1.txt`,
  modified on 2026-10-04. Its SHA-256 is
  `af7534484463daf2bf471461277f77f8391741122afbe99cfb274b01a5d8efad`.
  The tracked repository-root file of the same name remains the older source
  artifact and is not used for this update.
- **Direction and units:** The file explicitly gives `parent = co1`,
  `child = co2`, `T_co1_co2`, metre translation and XYZW quaternion. Retain
  the established mapping co1 = `vive_tracker`, co2 = `gripper_tcp`. Apply
  the supplied transform directly, without inversion or mm reinterpretation.
- **Active value:** Translation `[0.0, -0.194899844, 0.080510987]` m;
  quaternion `[0.457263310, 0.0, 0.0, 0.889331359]` XYZW. File quaternion,
  matrix and homogeneous transform agree within rounding; quaternion norm is
  1.0000000003864715 and matrix determinant is 0.9999999997355964.
- **Scope:** Update the existing `config/vive.yaml` values, existing
  configuration regression expectations and operator/project documentation.
  This explicit instruction authorizes this parameter-only exception to the
  D-041 acquisition-configuration freeze. No acquisition algorithm change,
  live parameter update, hardware launch, raw rewrite, calibration rerun or
  post-processing algorithm change. Node startup applies the new values;
  existing raw TCP messages and their derived outputs keep their recorded
  definition and are not retroactively corrected by editing the config.
- **Verification:** Source metre/mm translation, quaternion, rotation matrix
  and 4x4 transform agree at the file's numerical precision. Repository and
  installed configurations match the source exactly, and the source SHA-256
  is unchanged. Eight existing extrinsic tests pass; full suite is 185 passed,
  2 skipped, 2 existing missing-h5py failures. Build, touched-test flake8 and
  `git diff --check` pass. New physical TCP geometry/direction acceptance is
  pending; no real Vive device was started.
- **Frame-definition comparison (2026-10-04):** The user states they changed
  co2's axes. Old/new source translations have the same length (210.874295 mm)
  but differ by `[0, -114.528391, -114.446438]` mm, an origin displacement of
  161.909664 mm if expressed in the same co1 frame. For a pure change of child
  axes with its origin and parent unchanged, right multiplication by a
  zero-translation rotation changes R but leaves t unchanged. Therefore these
  two files cannot both describe that pure child-axis change under the stated
  convention. Check whether co1's definition, co2's origin or the export frame
  convention also changed. Internal matrix/quaternion consistency does not
  establish physical frame identity. Keep the user-requested configuration
  values pending clarification; do not invent an inverse or further correction.

## D-021: One task per online session, multi-session datasets, no offline mode

- **Status:** Accepted by the user on 2026-09-28. Implementation is staged in
  [multi-task sessions](tasks/active/multi-task-sessions.md).
- **Offline acquisition is removed** with no compatibility entry point. This
  supersedes the offline-acquisition D-010 ("Focus on pose-only offline
  acquisition") and the offline parts of D-015. Online acquisition is the only
  recording mode.
- **Session = one task.** A session holds any number of episodes for exactly
  one natural-language task, stored only in `session.yaml` as top-level `task`
  (later used directly as the LeRobot language task). Changing task means a new
  session. Session directory names stay `online_session_<timestamp>` and never
  contain the task.
- `task:=` at launch is optional; an empty task produces a clear terminal
  warning and may be filled in afterwards with a dedicated tool.
- **Sessions are self-contained.** No runtime or post-processing step depends
  on another session.
- **Switching sessions in one launch:** keyboard `n` switches session without
  restarting the camera, Vive or pose subscription. Ctrl+C and relaunching with
  a new `task:=` yields an identical session structure.
- **Calibration within one launch:** on switch, the previous session's raw
  calibration data (`video.mp4`, `video.timing.json`, `video.validation.json`,
  `pose/`) is copied into the new session, keeping its sequence number, and
  `calibrate_time` is rerun there. Derived results are never copied, offsets
  are never shared, and post-processing never looks up calibration across
  sessions. A `copied_from` field is provenance only. Across launches nothing is
  copied; a new calibration must be recorded (unchanged D-014 rule).
- **Dataset merge:** each session is calibrated, aligned and transformed
  independently; sessions are merged only at export. Every export rebuilds the
  dataset from the given session list; there is no incremental append.

### D-021 amendment: `session.yaml` v2 and the `task` field

- **Status:** Implementer choices within D-021, recorded 2026-09-28.
- `session.yaml` `schema_version` is 2 and carries a top-level string `task`
  (may be empty). Version 1 files stay readable; a missing `task` means empty.
  Readers reject unknown future schema versions.
- The top-level `task` is the only authoritative task for post-processing and
  export. Each `recordings[]` entry stores a `task` snapshot of the value at the
  moment it was registered; it is provenance only.
- `set_session_task` changes only the top-level `task` (plus
  `task_updated_at`) and upgrades v1 files to v2. It **does not rewrite
  existing recording snapshots**, so an empty snapshot shows the task was filled
  in afterwards. It never touches MP4 or MCAP data.
- `set_session_task` refuses a session whose status is `active` (a running
  launch may be writing `session.yaml`); `--force` overrides this for sessions
  left `active` by an interrupted launch.

### D-021 amendment: in-launch session switching details

- **Status:** Implementer choices within D-021, recorded 2026-09-28.
- Keyboard `n` + Enter asks for the next task, sets the camera node parameter
  `next_task`, then calls the `std_srvs/Trigger` service `~/new_session`. While
  recording, `n` is refused by the keyboard and the recording continues; the
  service also refuses while recording.
- Worker status files (`.online_camera_status.json`,
  `.online_pose_status.json`) move from the session root to one per-launch
  runtime directory under the system temp directory, removed on shutdown.
  Every recording already passes its own output paths, so the camera and pose
  workers are neither restarted nor re-warmed.
- Only calibrations registered as `complete` in the previous session are
  copied. Each is copied into a hidden `.calibration_<n>.partial` directory and
  renamed when complete, so no resolver ever sees a half-copied
  `calibration_*`. The copy is registered with `copied_from` (provenance only).
  New calibrations continue numbering after the highest copied number.
- The switch is all-or-nothing: on any failure the new session directory is
  removed and the previous session remains active and current. The previous
  session is marked `complete` only after the new session is fully prepared.
- `process_session --run-calibration` uses the highest-numbered calibration by
  default; `--calibration <name|path>` selects one explicitly.

### D-021 amendment: multi-session dataset build

- **Status:** Implementer choices within D-021, recorded 2026-09-28.
- `build_dataset <session|directory-of-sessions...> --output <dir>` always
  rebuilds from scratch into `<dir>.partial` and swaps it in only after every
  session and export succeeded. `<dir>` holds `processed/<session>/aligned`,
  `processed/<session>/transformed`, `dataset.hdf5` and/or `lerobot/`, and
  `build_manifest.json`. `--overwrite` only replaces a directory that already
  contains `build_manifest.json`.
- Calibration: a session's own accepted result is used. `--run-calibration`
  runs `calibrate_time` on the newest calibration only for sessions without an
  accepted result (same rule as `process_session`).
- Whole-build checks, each failing with the session and reason: non-empty
  `task`; accepted calibration; at least one ordinary episode; every episode
  aligned as accepted; equal image size and frame rate (read from each MP4)
  across all episodes; transformed contract version equal to the supported one.
  The detected frame rate is used for LeRobot.
- HDF5 `format_version` 2: episodes are numbered across the dataset
  (`episode_0000…`); each episode has attrs `task`, `task_index`,
  `source_session`, `source_episode`, `video_to_pose_offset_seconds`; the root
  has a `tasks` string dataset indexed by `task_index` (first-appearance order)
  and no single `task` attribute.
- LeRobot: each frame's `task` comes from its session; `umi.source_session` is
  a per-frame `string` feature; `umi_export.json` lists every source session,
  task and offset. No `action` field.
- `transform.json` additionally records the alignment offset and its source
  (additive; contract version unchanged).
- `process_session` stays as the single-session command; its task now
  defaults to `session.yaml` and `--task` is only an override. Standalone
  `export_hdf5`/`export_lerobot` keep `--task` for one transformed root.

## D-022: Simplify the project structure

- **Status:** Accepted by the user on 2026-09-28.
- Remove unused or abandoned code: `compressed_preview_node` and
  `common/images.py` (legacy JPEG-bag replay), `tools/action4_uvc/` (the
  abandoned native-H.264 driver patch) and `tools/test_gripper_relative_tf.py`.
- Remove `process_session`. `build_dataset` is the single orchestration entry
  and also handles one session. This supersedes the D-021 handoff requirement
  to keep `process_session`. Its extra options are replaced by
  `align_session --offset-seconds` (diagnostics), running `calibrate_time` on
  the chosen calibration (calibration choice) and `set_session_task` (task).
- The Tracker-to-TCP extrinsic has one source of truth: `vive_pose_node`
  parameters `tracker_to_tcp_translation_m` and `tracker_to_tcp_rotation_xyzw`
  in `config/vive.yaml`. The node reads them at startup and accepts validated
  live updates through ROS parameters (`ros2 param set`) without restarting.
  `config/gripper_extrinsics.yaml` (never loaded) and the hard-coded constants
  are removed. Amends D-020.
- `coding_context.md` is rewritten as a current-state document without the
  historical update log (history remains in git). Completed tasks move to
  `tasks/archive/`; `ARCHITECTURE.md` describes only the current system.
  Decisions are kept, reordered by number, with a status index.

## D-023: Calibrate immediately after recording calibration data

- **Status:** Accepted as the implementation direction on 2026-09-29.
- When a dedicated calibration recording finishes, run the existing temporal
  estimator on it before returning the stop-service result. Show accepted
  offset and report path, or a clear rejection reason and instruction to record
  another calibration, through the keyboard terminal. A failed latest attempt
  must not leave an older offset marked accepted for the session.
- Ordinary episodes are still recorded normally. The estimator remains the
  existing plain-Python implementation; the camera node invokes it only after
  closing and registering the calibration recording.

## D-024: Use translation-only motion for temporal calibration

- **Status:** Accepted by the user on 2026-09-29.
- Estimate temporal offset from the three TCP translation axes (X/Y/Z), matched
  to ArUco image translation and apparent scale. Do not use TCP orientation or
  ArUco in-plane angle, and do not require deliberate rotations in the
  calibration movement. This amends the multi-feature scope in D-014.

## D-025: Keep calibration data retryable after processing failures

- **Status:** Accepted as an operational correction on 2026-09-29.
- A missing `ffprobe` is a processing environment failure, not evidence that
  the captured calibration motion is unusable. Keep the completed raw recording
  and mark the session `not_calibrated`; tell the operator to install FFmpeg and
  run `calibrate_time` again on that same recording.
- Reserve `rejected` and the instruction to record a new calibration for
  data-quality failures. This narrows D-023's generic retry prompt.

## D-026: Replace stale calibration diagnostics on a new result

- **Status:** Accepted as a metadata correction on 2026-09-29.
- Each completed calibration estimate replaces the session's previous
  `temporal_calibration` result fields. In particular, a successful retry
  removes an earlier attempt's `error`, so the current accepted status and
  diagnostic text cannot contradict each other. Preserve the raw recordings.

## D-027: Unified camera interface and per-camera image-to-pose calibration

- **Status:** Design direction confirmed by the user on 2026-09-30;
  implementation pending.
- Each camera type exposes a common acquisition interface so additional
  cameras can be registered for `online_record` without rewriting its session
  control. Camera configuration supplies a default device port, which a launch
  invocation can override.
- Each registered stream has a stable camera identity and an explicit image
  field name (for example `wrist_image`, `left_image`, `right_image`). Persist
  that mapping with the raw recording so dataset export uses the intended
  field names rather than inferring them from device paths or file order.
- Record each camera's image stream separately alongside the shared Vive pose
  recording. Estimate a separate image-to-pose time offset for each camera:
  wrist-to-pose, left-to-pose and right-to-pose are independent calibrations.
- Interface transport, multi-camera raw schema, required-camera failure policy,
  common dataset sampling timeline and per-camera calibration acceptance rules
  remain implementation design choices to resolve before changing code.

### First implementation choices (2026-09-30)

- Start with one Action 4 adapter behind a ROS-free camera source interface.
  Its existing persistent GStreamer worker provides preview and per-recording
  encoding. Carry source PTS and host receive time with preview frames, while
  continuing to publish only the preview through ROS.
- Use `wrist` as this installed Action 4 instance's `camera_id` and
  `wrist_image` as its dataset field. Preserve the single-camera recording
  filenames and consumers for this step; add identity and field to timing
  metadata. The later multi-camera schema change remains separate.
- Keep the configuration's device path as the default, with a distinct empty
  launch override parameter that takes precedence only when supplied.

## D-028: RealSense color acquisition through the common camera interface

- **Status:** Implemented; standalone color capture hardware verified
- **Date:** 2026-09-30
- **Source:** The user requested an acquisition class for the connected
  RealSense camera after confirming the Action 4 preview.
- **Decision:** Add a `RealSenseSource` implementing the existing `CameraSource`
  lifecycle. Use the RealSense V4L2 color endpoint with YUYV input and the
  persistent GStreamer worker for BGR preview and H.264 MP4 recordings. Share
  worker process control with `Action4Source`; keep distinct camera identity
  and `image_field` in preview and timing metadata.
- **Scope:** The connected device currently exposes color capture at
  `/dev/video14` with YUYV 640×480/30 fps. Depth and infrared endpoints are
  separate streams and are outside this first color adapter. This step does
  not register multiple cameras in `online_record` or change the session raw
  layout and dataset exporters.
- **Verification boundary:** Exercise the class and worker with synthetic
  input, then probe the connected color endpoint for live preview and a short
  recording. Distinguish device delivery from successful downstream session
  integration.
- **Evidence:** A synthetic YUYV stream produced BGR preview and a decodable
  48-frame H.264 MP4 with `left` / `left_image` timing metadata. The first
  USB 2 (480M) connection produced no live frames. After moving the D435 to
  USB 3 (5000M), V4L2 delivered 10 color frames, `RealSenseSource` delivered
  103 preview frames in 10 seconds and completed warmup, and a two-second
  recording produced a decodable 63-frame 640×480 H.264 MP4 with complete
  `left` / `left_image` timing. Preview continued after recording stopped.
  Multi-camera session and dataset integration remain separate work.

## D-029: Record Action 4 and RealSense color in one online session

> **Index status:** The root Action 4 raw layout is amended by D-031;
> new recordings use `cameras/wrist/`.

- **Status:** Implemented; real-camera recording tested with synthetic pose
- **Date:** 2026-09-30
- **Source:** The user requested both cameras in `online_record.launch.py`,
  simultaneous low-resolution previews and recording of both image streams;
  depth is explicitly excluded.
- **Decision:** The existing online capture node coordinates both
  `CameraSource` implementations with the one persistent Vive pose recorder.
  Both cameras are required before starting a recording. Pose starts first;
  then both warmed cameras start writing their own MP4 and timing files. Stop
  finalizes both before closing pose, validates each video and records the
  stream paths and identities in `session.yaml`.
- **Raw layout:** Preserve the existing Action 4 `video.mp4` and associated
  metadata at the recording root for current readers. Add RealSense color
  under `cameras/left/video.mp4` with its own timing and validation files.
  New recording index entries include an `image_streams` list that maps
  `camera_id`, `image_field` and relative file paths. Copy raw calibration
  streams when switching sessions. The current calibration and dataset
  pipeline continues to consume wrist video only until per-camera alignment
  and export are implemented.
- **Failure policy:** A missing or failed required camera blocks a recording;
  a partial recording is marked failed and preserved for diagnosis. Preview
  continues independently of whether an episode is recording. `online_view`
  may use the same two-camera preview configuration.
- **Device selection:** The Action 4 moved from `/dev/video2` to
  `/dev/video8` when RealSense was connected, so the Action 4 config now uses
  its serial-based `/dev/v4l/by-id` color link. Both launch files retain
  explicit per-camera overrides.
- **Evidence:** `online_record.launch.py` published valid 320×180 Action 4
  and 320×240 D435i BGR previews. In one test episode using both real cameras
  and a synthetic `/vive/pose`, it saved separate decodable 78-frame H.264
  MP4 files, complete timing/validation files, a pose MCAP and a complete
  `image_streams` index. RViz stayed alive through that run. Actual Vive pose
  was absent in an earlier run and remains an independent hardware acceptance
  item. Per-camera temporal calibration and multi-image export are later work.

## D-030: Use D435i as the left color camera

- **Status:** Implemented; color acquisition verified
- **Date:** 2026-09-30
- **Source:** The user replaced the previously tested D435 with a D435i and
  asked to re-detect device numbering and continue the two-camera work.
- **Decision:** Keep the `RealSenseSource` YUYV color adapter and the
  `left` / `left_image` identity, but update the left camera configuration to
  the new D435i serial-based V4L2 color link after verifying its format. Do
  not capture depth or infrared. Treat any `/dev/videoN` number as ephemeral.
- **Evidence to collect:** Direct color frames, live adapter preview, both
  ROS preview topics and a complete two-camera online recording with separate
  MP4/timing/validation files.
- **Evidence:** The replacement D435i (serial `254343064631`) enumerated a
  YUYV color endpoint at `/dev/video6` on a 5000M USB 3 link. Direct V4L2
  delivered 10 frames at 640×480/30. Its serial-based by-id link is now the
  configured default. The two-camera online recording evidence is in D-029.

## D-031: Store every camera under its own recording directory

- **Status:** Implemented on 2026-09-30.
- **Source:** The user pointed out that Action 4 files at the episode root are
  inconsistent with the D435i files under `cameras/left/`.
- **Decision:** New recordings put Action 4 MP4, timing and validation under
  `cameras/wrist/`, and D435i under `cameras/left/`. A recording-level
  `image_streams` entry names each relative path. The pose bag and derived
  calibration results remain at the recording root.
- **Compatibility:** Readers resolve the new wrist location first, then the
  legacy root `video.*` files for historical sessions. Session switching
  copies raw files in either layout. Historical single-camera sessions stay
  readable; this change does not introduce per-camera calibration or export.
- **Current user episode:** Migrate the newly recorded dual-camera
  `online_session_20260930_133225_127556/episode_0001` after verifying the
  new readers, updating its stream index and timing self-path without changing
  MP4 bytes or pose data. Leave unrelated historical sessions in place.
- **Evidence:** The migrated episode resolves through replay and alignment,
  decodes 612 wrist and 613 left frames, and retains 2053 Vive pose messages.
  The wrist MP4 SHA-256 before and after migration is
  `c3e8e204c14cc3c5658b039a24a47d5403e359bb3b3a2443053d8b77276479de`.
  A historical root wrist episode still resolves. Focused path tests passed.

## D-032: Use one pose coverage acceptance check for the current setup

- **Status:** Superseded by D-035 on 2026-09-30.
- **Source:** The user explicitly declined checking pose completeness for
  every episode after the real dual-camera episode passed the coverage check.
- **Decision:** Use the checked real episode as pose coverage acceptance
  evidence for the current acquisition setup. Do not add automatic per-episode
  pose coverage/gap checks or require routine manual checks of every recording.
  Keep startup warmup, first-pose recording admission, worker health checks and
  pose bag finalization in the existing recording lifecycle.
- **Evidence scope:** The accepted raw coverage check uses host-receive video
  anchors and pose header stamps. Per-camera temporal calibration remains
  separate work; this decision does not establish exposure-time synchronization.

## D-033: Save pose for 500 ms before starting camera recording

- **Status:** Implemented on 2026-09-30; software and hardware verified.
- **Source:** The user requested that image recording start 500 ms after pose
  recording for each episode, before proceeding to frame-gap statistics.
- **Decision:** Start the pose bag and confirm its first pose has been written,
  then wait 500 ms before sending recording commands to either camera. Apply
  the same start sequence to episodes and calibration recordings. Cameras stay
  open after their existing one-time warmup; pose continues recording during
  the delay. Stop still finalizes both videos before closing pose.
- **Timing meaning:** The delay is a minimum host-side lead from observed
  first-pose readiness to the camera start commands. Frame arrival and encoder
  startup may make the actual video lead longer. It is not a calibrated
  image-to-pose time offset.
- **Scope:** Preserve D-032: do not introduce per-episode pose completeness
  checks at that stage (subsequently superseded by D-035).
  Frame-gap statistics, red terminal warnings and JSON dataset
  exclusion have been authorized as subsequent work and are not implemented
  by this start-sequence change.
- **Verification:** Ordering tests for both episode and calibration starts
  confirm first-pose readiness, a 500 ms delay, then both camera starts. A
  missing first pose starts neither camera. Build and touched-file flake8
  passed; full tests: 93 passed, 2 skipped, 2 existing HDF5 failures due to
  missing `h5py`. In user session `online_session_20260930_145919_328592`,
  episode 0001 wrist/left first images arrived 584.85/601.23 ms after the
  first saved pose bag timestamp; episode 0002 measured 586.49/613.42 ms.
  Both episodes satisfy the minimum 500 ms lead and retain the symmetric raw
  camera layout. Pose frequency varied in the second episode; that is tracked
  separately from this start-delay acceptance.

## D-034: Build the live Vive path in a separate 30 Hz node

- **Status:** Implemented on 2026-09-30; software verified, hardware acceptance
  pending.
- **Source:** After diagnosing whole-history Path publication in the pose
  callback as the sampling-rate bottleneck, the user requested a separate
  node subscribing to Vive pose and assembling/publishing Path at 30 fps.
- **Decision:** `vive_pose_node` publishes TCP PoseStamped and both TFs at its
  configured 90 Hz timer. `vive_path_node` runs in a separate process, caches
  only the newest incoming pose and samples it at 30 Hz, appending at most
  one fresh point and publishing `/vive/path` per timer tick. A best-effort,
  depth-one subscription avoids building a visualization backlog or adding
  reliable-reader backpressure to the pose publisher. Receipt callbacks remain
  lightweight; 30 Hz describes trajectory sampling, not DDS arrival frequency.
- **Configuration and compatibility:** Move `path_topic` and
  `max_path_points` out of the pose-node parameters into a `vive_path_node`
  block in `config/vive.yaml`, with `pose_topic`, `sample_hz: 30.0` and the
  existing 10,000-point cap. Preserve source pose headers and coordinates,
  reset visualization history on frame changes, and do not append old points
  when the pose stream pauses. Start this process alongside Vive in
  `online_record`, `online_view`, and `vive` launch files. The existing RViz
  Path display and `/vive/path` topic remain compatible.
- **Scope:** Path is visualization only; raw MCAP still records the complete
  pose/TF stream. Recording layout, 500 ms image lead and replay path behavior
  are unchanged. Verify separation, latest-pose sampling, bounded history and
  concurrent long-path performance in software; sustained real Tracker plus
  dual-camera, multi-episode behavior needs subsequent hardware acceptance.
- **Verification:** Build, touched-file flake8 and 22 focused tests passed;
  full pytest: 101 passed, 2 skipped, 2 existing missing-`h5py` failures.
  A 12 s isolated concurrent test used the current pose node with a fake
  backend, the path node prefilled with 10,000 points, and a C++ DDS Path
  subscriber in separate processes. Pose measured 90.002 Hz with a maximum
  header gap of 11.915 ms; Path publication and C++ receipt measured about
  29.916 Hz. All processes exited cleanly. This verifies saturated-path
  software behavior, not real Tracker/camera or RViz rendering acceptance.
- **Subsequent real pose-rate check:** User session
  `online_session_20260930_160029_092182` contains three short complete real
  Tracker/dual-camera episodes. Pose averages 89.774/89.799/89.856 Hz with
  5/3/2 isolated approximately 22 ms gaps, without the previous progressive
  decline; image raw-time coverage and the minimum 500 ms lead pass. This
  verifies the observed multi-episode pose-rate improvement in that about
  117 s launch, not zero hardware drops, long single episodes or actual
  Path/RViz frame rate. Full evidence is in
  `reports/raw-recording-check-20260930-160029.md`.

## D-035: Automatically accept or reject each completed episode

- **Status:** Implemented on 2026-09-30; software verified, live automatic
  end-of-recording acceptance pending.
- **Source:** User explicitly requested automatic image/pose diagnostics after
  every episode, with a green `accept` or red `reject` and no new parameters.
  This supersedes D-032's restriction on recurring pose checks.
- **Decision:** Reuse the existing single ffprobe pass per MP4. Require both
  videos to decode, have all frame timestamps strictly increasing, match the
  worker's accepted frame counts, and have no adjacent PTS gap over 50 ms
  (1.5 periods at the current 30 fps). After closing MCAP, scan `/vive/pose`
  once; require increasing header timestamps, average rate at least 88 Hz,
  and complete coverage of both image ranges (first host receipt plus MP4
  PTS). Small pose gaps are diagnostic only and do not independently reject.
- **Output:** Print one colored verdict with short reasons on rejection, also
  returned to the keyboard terminal. Persist `episode/quality.json`, including
  `verdict`, `accepted`, `exclude_from_dataset`, reasons and supporting counts.
  Missing/failed diagnostics reject. Recording completion status remains
  separate from quality acceptance; a rejected episode does not block the next.
- **Scope:** Ordinary episodes only; preserve calibration, capture workers,
  500 ms pose lead and launch arguments. These checks detect recording/timestamp
  gaps; they do not establish physical exposure alignment or prove the camera
  never lost a frame before delivering its source timestamps. Dataset export
  enforcement of the marker remains subsequent work.
- **Verification:** Build, touched-file flake8 and 19 focused tests pass.
  Full suite: 115 passed, 2 skipped, 2 existing missing-h5py failures.
  Read-only verification of four real episodes/eight MP4s plus MCAP took
  6.511 s: the three latest ~90 Hz episodes accept; the earlier 51.899 Hz
  episode rejects. Orchestration verifies one check after pose closure and
  continued recording after reject. Original recordings are unchanged.
  Keyboard control also returns to idle after failed stop/file finalization,
  matching the coordinator's closed state so the next Enter starts afresh.

## D-036: Select and retry translation-only calibration per camera

- **Status:** Implemented on 2026-09-30; software verified, live per-camera
  calibration/retry acceptance pending.
- **Source:** User requests `c` + Enter to select a numbered registered camera,
  record only that camera with shared Vive pose, immediately calibrate on stop,
  print green `accept` or red `reject`, and delete rejected inputs before
  prompting to rerecord in the same directory.
- **Decision:** List cameras from the recording node; expose one calibration
  start service per camera and retain the old default-camera service. Other
  cameras keep previewing. Ordinary episodes continue recording all cameras.
  Each camera's failed attempt reuses its reserved `calibration_<nnn>` folder;
  remove that attempt's video/timing/validation, pose bag and derived results
  after closing writers. Replace its session index entry instead of appending
  duplicates. Preserve accepted attempts and other cameras' files/results.
- **Results:** Add `temporal_calibrations[camera_id]` to schema v2 and annotate
  results with camera identity/field. Keep singular `temporal_calibration` as
  the wrist compatibility view. Offline CLI accepts `--camera-id` and infers
  the camera from a single-camera recording; copied raw calibrations retain
  their identity. Replay resolves single-camera calibration inputs and skips
  indexed rejected folders whose raw inputs were deleted. This stage implements
  calibration; multi-view dataset export remains subsequent work.
- **Timing/motion:** Keep existing ArUco centre X/Y/log-area versus TCP XYZ
  translation estimator and quality thresholds. No rotation features.
  Pose starts at least 500 ms earlier; retain absolute pose headers and each
  camera's first receipt plus MP4 PTS. Do not subtract 500 ms, align independent
  recording starts to zero, or treat this buffer as the latency estimate.
- **Retry UX:** After reject, Enter retries the selected camera; `c` selects
  another camera, `n` switches session and `q` exits keyboard control. No
  automatic recording without user input. Processing failures also visibly
  reject and request retry (superseding the old saved-input retry guidance).
- **Verification:** Ten new test cases cover camera numbering, single-camera
  recording, retry/cleanup/index replacement, preservation of another camera's
  accepted data, keyboard reject/retry/accept, left raw copying, rejected-folder
  replay, and real-MCAP signed-offset estimates with synthetic image features.
  With a 500 ms pose lead and varying unused orientations, -137.4/+127.4 ms
  estimates recover within 4 ms; orientation-only movement rejects.
  Full suite: 125 passed, 2 skipped, 2 existing missing-h5py failures. Colcon
  build, touched-file flake8 and diff checks pass. Original recordings unchanged;
  actual camera marker/motion, repeated results and live retry remain hardware
  acceptance.

## D-037: Calibrated dual-camera RViz episode review

- **Status:** Implemented on 2026-09-30; live RViz replay verified.
- **Source:** User requests the recorded `online_session_20260930_193959_496910`
  image streams and Vive pose shown together in RViz2 at source 30 fps.
- **Decision:** Replay the ordinary episode with its original MP4 frames and
  pose MCAP. For each camera, require its accepted session calibration and
  schedule frame display at `first_receive_unix_ns + MP4 PTS + camera offset`
  on rosbag `/clock`; stamp the published image with that aligned time. Publish
  both cameras to their existing RViz preview topics and keep Vive pose/TF/path
  from the bag. Use actual PTS instead of imposing a synthetic 30 fps grid;
  repeat the short episode for visual inspection. Preserve all raw files.
- **Boundary:** This is playback for inspection. It does not change raw data,
  dataset alignment/export or claim exposure-level hardware synchronization.
- **Evidence:** The accepted `episode_0001` has 99 decoded frames in each
  camera. Its accepted offsets are wrist -93.77 ms and left -10.07 ms. The
  calibrated loop launched RViz2 and repeatedly published 99/99 image frames;
  `/vive/pose` and rebuilt `/vive/path` both published in `vive_world`. Focused
  replay/launch tests, flake8 and ROS package build passed. The operator's
  visual judgment of alignment remains the purpose of this review.

## D-038: Use the recording-start TCP frame for calibration and derived poses

- **Status:** Implemented and software verified on 2026-09-30.
- **Source:** User requests XYZ relative to the pose when Enter starts a
  recording, so translation channels follow the initial assembly axes.
- **Reference:** The first TCP PoseStamped saved after the start command is
  the sampled approximation of the Enter-time pose. It precedes the existing
  500 ms image delay. Define a fixed frame with that pose's position and
  orientation: `p_local = R_start^T (p_world - p_start)` and
  `q_local = inverse(q_start) * q_world`. Keep these axes fixed through the
  recording; they do not track subsequent rotations.
- **Calibration:** Use local XYZ for the existing translation-only ArUco
  matcher. Initial orientation defines the frame; changing orientation is
  still not a matching feature. Preserve absolute timestamps and offset sign.
- **Derived pose:** Alignment carries the recording-start reference into
  dataset transformation, replacing the first aligned image pose reference.
  Historical aligned intermediates can obtain the reference from their source
  MCAP; metadata explicitly identifies any legacy reference fallback.
- **Raw contract:** Preserve recorded world pose and TF as source data; both
  calibration and dataset processing perform this coordinate conversion.
  No raw recording or existing calibration result is rewritten by this change.
- **Verification:** Signed-offset real-MCAP tests recover known delays under
  initial 90-degree and arbitrary world rotations while retaining the 500 ms
  image lead. Tests also verify fixed axes after subsequent rotation and
  nonzero first-image position when movement occurs before image recording.
  Focused tests: 22 passed, 1 skipped. Full suite: 130 passed, 2 skipped,
  2 pre-existing missing-h5py failures. Build, touched-file flake8 and diff
  checks pass; real motion under the new coordinate basis remains acceptance.

## D-039: Select the D435i RGB USB interface by serial

- **Status:** Implemented and startup confirmed by the user on 2026-09-30.
- **Evidence:** After Action 4 entered Webcam mode, its adapter delivered 297
  previews in 10 seconds. Full online launch then failed in the left worker
  with GStreamer `not-negotiated`. The RealSense by-id `video-index0` link
  resolved to `/dev/video0` (Z16 depth), while RGB YUYV was `/dev/video4` on
  USB interface 03. Several UVC interfaces advertise the same by-id index,
  so the link does not uniquely identify color.
- **Decision:** Configure D435i serial `254343064631` and RGB USB interface
  `03`. Resolve that interface's V4L2 capture endpoint (`index == 0`) from
  sysfs at source construction, independent of numeric video node or port.
  Explicit `left_video_device` overrides retain precedence; synthetic sources
  bypass hardware discovery. Do not select depth/infrared or another serial.
- **Verification:** Three new selection tests cover reordered video nodes,
  depth/IR/metadata/other serial exclusion, missing/ambiguous RGB and explicit
  override/synthetic precedence. Full pytest: 133 passed, 2 skipped,
  2 pre-existing missing-h5py failures; build, touched-file flake8 and diff
  checks pass. Real online launch selected `/dev/video4` for left and both
  camera workers completed warmup with no error. Diagnostic session is under
  `/tmp/umi_rgb_interface_retest_20260930`; no new recording was made.
- **Operator acceptance:** The diagnostic launch initially remained running
  after interruption and held both cameras during the user's next attempts.
  It has been stopped and its workers released. The user then confirmed
  their own online launch works; its left worker uses the selected RGB node.
  New recorded-episode quality is outside this startup check.

## D-040: Inspect aligned image and pose in a manual local viewer

- **Status:** Implemented and real-file GUI verified on 2026-09-30.
- **Source:** User requests visual inspection of the current session, advancing
  one image per keypress, to avoid independent ROS image/pose playback delays.
- **Decision:** Read MP4 and pose MCAP directly into one local desktop viewer;
  no image/pose publishers or realtime playback clock. For the primary camera,
  each keypress chooses one actual MP4 frame and interpolates pose at
  `first_receive_unix_ns + PTS + accepted camera offset`. Display XYZ/path and
  orientation in the fixed recording-start TCP frame (D-038). Preserve the
  500 ms buffer in the recorded anchors rather than applying it as an offset.
- **Two views:** Pair the other camera by nearest corrected frame time and
  report its time difference; show that image's own interpolated pose marker.
  Do not assume equal frame indices indicate synchronization. Allow switching
  primary camera and ordinary/calibration recordings, forward/backward steps
  and a raw-versus-calibrated comparison. Invalid pose queries remain visible.
- **Input:** Current `online_session_20260930_212318_104281` has one episode and
  accepted wrist/left offsets -112.143/-6.703 ms. Keep raw files immutable.
- **Verification:** Five tests cover signed offsets, the recording-start frame
  with 500 ms pre-roll, unequal/irregular camera timelines and invalid pose
  coverage/gaps. The real episode has 1080 wrist / 1081 left frames, all with
  valid corrected poses. Backward seek to the first decoded frame is exact for
  both videos; manual steps, raw/corrected redraw and switching both calibration
  clips (987/1325 frames) were exercised in Tk. The real figure at primary
  frame 109 was visually inspected (`/tmp/umi_frame_viewer_108.png`). Full suite:
  138 passed, 2 skipped, 2 pre-existing missing-h5py failures. Build, touched
  flake8 and diff checks pass. Visual judgment of alignment remains with the
  operator, and no raw data was rewritten.

## D-041: Two image streams with current and next TCP poses

> **Current representation:** The amendment below retains XYZ + XYZW (seven
> values) for state/action and supersedes the original six-value proposal.

- **Status:** User requirements recorded on 2026-10-02. This turn verifies
  source representation and illustrates the timeline; no processing code is
  changed. See `tasks/active/raw-to-dataset.md` for unresolved details.
- **Scope:** Change raw-to-HDF5/LeRobot processing only. Preserve the raw
  acquisition flow, configuration, MP4/MCAP files and existing calibrations.
  URDF robot IK validation is deferred.
- **Samples:** Each final sample contains wrist image, left image, one state
  and one action. State is the current TCP pose; action is the next pose in
  the same episode reference frame.
- **Rates:** After applying each camera's own accepted image-to-pose offset,
  repeat each 30 fps image into three output samples to accompany the 90 Hz
  pose stream. Three is the total number of occurrences. The illustration
  interprets next pose as the next 90 Hz step (nominally 11.111 ms), and holds
  an image for its three consecutive steps. Actual camera phase, timestamp
  jitter and pose gaps must be resolved before implementing this mapping.
- **Reference:** The first saved TCP pose of that episode's raw pose stream
  defines t=0 and the fixed position/orientation frame (D-038):
  `T_local_i = inverse(T_world_0) * T_world_i`. State and action use this same
  reference. Pose-only pre-roll does not acquire synthetic images; the first
  usable image sample may start later than t=0.
- **Representation:** Source-code inspection confirms raw `/vive/pose` is
  `geometry_msgs/msg/PoseStamped`, written unchanged to MCAP after the node
  applies the Tracker-to-TCP extrinsic. Positions are XYZ and orientations are
  XYZW quaternions. Convert relative transforms to six output values: three
  position and three orientation components. Orientation representation,
  convention and units are still to be confirmed; do not silently choose RPY
  or a rotation vector.
- **Compatibility:** This target supersedes D-021's no-action export target.
  Existing code still exports one image stream and seven pose values without
  action; its schemas remain unchanged until implementation. Define new
  intermediate/export versions when that work begins.
- **Open:** Confirm the demonstrated image-hold phase and next-pose step;
  select six-value orientation encoding; specify actual timestamp handling,
  dual-view pairing, missing-frame/gap behavior and final-sample behavior.
  Never fabricate a next pose or join transitions across invalid gaps or
  episode boundaries.

### D-041 amendment: Retain quaternion TCP poses

- **Status:** Explicitly confirmed by the user on 2026-10-02. The user accepts
  the illustrated three-occurrence image timeline and current/next 90 Hz pose
  interpretation, and requests completion of the processing steps while
  deferring URDF/IK. The current turn explains implementation before coding.
- **Pose encoding:** Both state and action retain
  `[x, y, z, qx, qy, qz, qw]` (seven stored values for six degrees of freedom).
  No Euler-angle or rotation-vector conversion is required. Normalize
  quaternions and keep their signs continuous across the episode.
- **Coordinates and targets:** Continue using the raw episode's first saved
  TCP pose as the fixed reference. State is current relative TCP pose; action
  is next relative TCP pose in the same reference frame.
- **Scope:** Only the processing contract, dual-view alignment, relative-pose
  transformation, state/action assembly, HDF5/LeRobot exporters and their
  orchestration/verification are affected. Acquisition code/configuration,
  raw files and existing calibration estimates remain unchanged. URDF/IK is
  deferred. Real timestamp mapping and exclusion/boundary policies are to be
  made explicit in the implementation plan and reports.

### D-041 amendment: Implement expansion as a standalone stage

- **Status:** Implementation choices recorded before coding on 2026-10-02.
  The user requests file-by-file processing modules, starting with expansion
  after the already-completed temporal calibration; integrate them into
  `build_dataset` later. The standalone stage is now implemented and verified:
  24 new tests pass; full suite is 162 passed, 2 skipped, 2 pre-existing
  missing-h5py failures. Build, touched-file flake8 and diff checks pass.
- **Boundary:** Add a NumPy-only `postprocess/frame_expansion.py` algorithm
  and a file/CLI adapter `postprocess/expand_session.py`. Consume existing
  per-camera accepted offsets and actual video PTS; never rerun calibration
  or change acquisition/raw files. Existing alignment, transformation,
  exporters and `build_dataset` retain their current behavior in this step.
- **Clock:** Use a fixed 90 Hz grid anchored at the first corrected wrist
  frame, cropped to the usable common range. Each three-sample group begins
  on its 30 Hz subgrid. Independently select the closest wrist/left source
  image at the group start, with a default maximum error of 1/60 s (half a
  30 fps frame); ties select the earlier image. A source image may belong to
  at most one valid group. Repeat each group's selected source indices three
  times, without copying/re-encoding raw MP4 files. The later exporter will
  materialize these image repetitions. Unselected/cropped source frames are
  explicitly counted rather than silently claiming all raw frames appear.
- **Pose:** Interpolate world TCP XYZ and XYZW at all 90 Hz queries using
  existing linear/SLERP math, without extrapolation or crossing pose gaps
  over 0.1 s. Preserve the original first saved raw TCP reference as separate
  metadata. Local-coordinate transformation and action assembly are later
  modules. Preserve quaternion unit length and consecutive valid signs.
- **Invalidity:** Retain the uncompressed clock and camera/pose validity
  diagnostics. All three samples of a group are marked invalid if either
  image pairing or any of its pose queries fails. Cropping keeps complete
  groups; the final selected image can be held over its three samples only
  while pose coverage remains valid. No future action is generated here.
- **Contract:** Write a distinct expansion contract v1:
  `expanded_frames.npz`, `expanded_frames.csv`, `expansion.json`, and session
  `expansion_summary.json`. Include source frame indices, PTS, corrected
  image times, pairing errors, 90 Hz relative/absolute query times, world
  pose, validity and the raw start reference. Official exports, quality
  exclusion and `build_dataset` integration remain subsequent work.
- **Real-file verification:** Session `online_session_20260930_212318_104281`
  yields 3234 candidate samples, 3138 valid (1046 complete image groups,
  97.0315%), 96 invalid samples retained on the clock and no invalid pose
  query. Wrist/left source frame counts are 1080/1081; each selected image
  appears exactly three times, with 34/35 unused source frames reported.
  SHA-256 of all 24 raw session files is unchanged. Outputs are under
  `/tmp/umi_expansion90_validation_20261002`; durable evidence is
  `reports/expansion90-20261002.json`. This verifies expansion on real files,
  not a new capture or final state/action training dataset acceptance.

### D-041 amendment: Localize expanded poses without state/action

- **Status:** Explicit user instruction and implementation choices recorded
  before coding on 2026-10-02. Implement only the fixed episode-start pose
  transformation now; state/action assembly remains a later step. The stage
  is implemented and verified: 23 new tests pass; full suite is 185 passed,
  2 skipped, 2 pre-existing missing-h5py failures. Build, flake8, installed
  CLI help and diff checks pass; both modules import without ROS in LeRobot's
  independent environment.
- **Boundary:** Add NumPy-only `postprocess/local_pose.py` and the independent
  file/CLI adapter `postprocess/localize_session.py`. Read expansion v1 for
  one episode or an expanded session. Leave acquisition, raw recordings,
  calibration, the expansion algorithm and the legacy dataset chain unchanged.
  No URDF/IK or `build_dataset` integration in this step.
- **Reference:** Require the expansion's saved first raw TCP pose, including
  pose-only pre-roll. Never substitute the first image, the first expanded
  sample or the previous pose. Each episode has its own reference. Compute
  `p_local_i = R_start.T * (p_world_i - p_start)` and
  `q_local_i = conjugate(normalize(q_start)) * normalize(q_world_i)`.
- **Validity:** Transform every `pose_valid` sample, including samples whose
  images are invalid. Invalid pose queries stay NaN. Preserve sample count,
  90 Hz clock, source-image references, diagnostics and all validity masks.
  Normalize output XYZW quaternions and choose equivalent signs continuously
  across successive valid poses; do not force every quaternion's w positive.
- **Contract:** Write separate local-pose contract v1 (`local_frames.npz`,
  `local_frames.csv`, `local_pose.json`, `local_pose_summary.json`). Retain
  world poses and the world start reference for traceability; `position_xyz`
  and `orientation_xyzw` become episode-start-relative. No `state` or `action`.
  Report the source expansion's accepted/rejected status without upgrading it.
  Refuse missing/invalid references and output paths overlapping raw or input.
- **Real-file verification:** All 3234 pose queries from the existing expanded
  episode are converted using the reference verified against its first raw
  MCAP TCP message. Image validity stays 3138 valid / 96 invalid. Independent
  rotation matrices and inverse roundtrips agree within 2.23e-16; quaternions
  are unit length with continuous signs. All 24 raw files and all four
  expansion files retain their SHA-256 and file lists. Evidence:
  `reports/local-pose-20261002.json`; output:
  `/tmp/umi_local_pose_validation_20261002`. This is software verification on
  existing files; operator coordinate-frame acceptance remains pending.
