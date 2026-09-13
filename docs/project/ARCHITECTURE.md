# UMI — Architecture and structure responsibilities

## Planned temporal calibration boundary (D-014)

Temporal calibration is offline processing around one dedicated calibration
episode; it is not part of the Vive hardware adapter or the recording-critical
camera path. Acquisition stores the original MP4, pose MCAP and timing metadata.
A separate calibration executable decodes video frames, detects the configured
ArUco marker, reads Vive poses, constructs/interpolates normalized scalar motion
trajectories, searches the bounded video-to-pose offset by MSE, and writes a
machine-readable result plus an alignment plot. A later synchronization stage
uses the accepted offset to interpolate pose at each video-frame time.

The first version estimates one constant offset for one uninterrupted online
session. It does not estimate clock-rate drift, camera-to-Tracker extrinsics,
rolling shutter, exposure time, or hardware-trigger timing. Recording and RViz
must remain usable when calibration processing is absent or fails.

## Current session and online episode architecture (D-013, D-015)

`online_record.launch.py` creates one `online_session_<timestamp>` containing
`session.yaml`, `calibration/`, and `episodes/`, then keeps Vive, RViz and the
camera control node alive.
The camera worker opens UVC once, warms once, and then stays in `waiting` or
`recording`. Waiting frames feed RViz preview but are not saved. Ordinary start
creates `episodes/episode_<sequence>` and calibration start creates
`calibration/calibration_<sequence>`. Both start pose rosbag2 and attach a fresh H.264/MP4 encoder
to the running stream. Recording frames feed both the encoder and preview. Stop
detaches and finalizes the encoder, flushes MCAP, writes timing and validation
reports, and returns to waiting without reopening the camera. The keyboard
executable is a separate service client so launch does not depend on child
process stdin. Online UVC exposes no project-accessible Action 4 IMU stream.

Offline currently creates `offline_session_<timestamp>/session.yaml` and an
empty `calibration/` reservation before rosbag2 creates `pose/`. Its detailed
episode and calibration layout remains deliberately unspecified.

## Current online update (D-010)

Superseded by D-011: v4l2src MJPEG → tee; non-leaky JPEG recording queue →
jpegdec → I420 → x264enc ultrafast, 12000 kbps → h264parse → MP4.
Preview uses a separate leaky JPEG queue → jpegdec → scaled BGR → ROS.
Unlike H264, individual JPEG frames can be discarded safely before decoding.
The external process retains no dependency on ROS image transport for recording.
The native-H264 description below is historical.

Native H.264 UVC → parser → tee → non-leaky queue → MP4 mux/file.
The preview branch decodes H.264 before a bounded leaky raw-frame queue,
then scales to BGR. One Python ROS node drains stdout and publishes only the
latest image at 15 fps. Decoder throughput remains a resource constraint;
non-leaky queues prevent intentional recording drops but cannot guarantee
source continuity under sustained overload. Stop drains previews until EOF,
finalizes MP4, and checks the file with ffprobe. Preview receive timestamps
are not saved as video timestamps. Earlier CSV descriptions are superseded.

- **Basis:** `README.md` plus the Vive ROS 2 package implemented and inspected on 2026-09-07.
- **Last structure check:** 2026-09-11, all project-owned ROS runtime consolidated into `umi_ros2`.

## Current structure

| Path | Responsibility |
| --- | --- |
| `umi_ros2/umi_ros2/vive/` | Shared Vive backend and real-time pose node used by both modes. |
| `umi_ros2/umi_ros2/camera/` | Online-only Action 4 JPEG bridge and replay preview node. |
| `umi_ros2/umi_ros2/session/` | ROS-independent shared session layout and metadata updates. |
| `umi_ros2/umi_ros2/common/` | ROS-independent image helpers reused by live and replay paths. |
| `umi_ros2/umi_ros2/visualization/` | Replay-time path reconstruction. |
| `umi_ros2/launch/` | Shared, online-only, offline-only, and replay entry points. |
| `umi_ros2/config/` and `umi_ros2/rviz/` | Device defaults and mode-specific visualization assets. |
| `umi_ros2/test/` | Backend, image-helper, and launch-contract tests. |

## Vive data flow

Vive USB/lighthouse data → libsurvive calibration and pose → selected-device
backend → ROS quaternion ordering and timestamp → `/vive/pose` and optional TF.
Each published pose is also appended to a bounded `/vive/path` history for RViz.

## Structure contract

The ROS node may depend on `rclpy`, ROS messages, TF, the backend, and conversion
utilities. The pysurvive backend owns the third-party binding and must not depend
on ROS. Pose validation and quaternion adaptation remain independent of ROS and
hardware so they can be tested in plain Python. Launch and configuration files
set deployment defaults but do not contain acquisition logic.

Future camera, synchronization, recording, and dataset-conversion modules should
be separate ROS packages or clearly bounded modules; they must not be folded into
the Vive hardware adapter.

## Planned camera acquisition boundary

The rigid gripper assembly contains both the DJI Action 4 and Vive Tracker. The
two camera modes are separate deployments:

- Offline: Action 4 → 4K/60 fps MP4 on microSD; Vive → `/vive/pose` and TF →
  rosbag2; RViz consumes pose/path/TF. No camera USB connection is used.
- Online: Action 4 → USB/UVC → camera ROS 2 node at a target 1080p/30 fps;
  source images → H.264 MP4 plus frame timestamps, while Vive pose/TF → a
  separate MCAP rosbag2 directory in the same session; RViz consumes image and
  pose/path/TF. The camera does not record to microSD.

EIS remains disabled so image geometry is not changed by electronic motion
compensation. `/vive/path` is visualization-only and excluded from recordings;
processing reconstructs trajectories from `/vive/pose`.

Planned camera acquisition, session recording, temporal synchronization, and
dataset conversion are separate responsibilities. The synchronization algorithm
and required accuracy are deliberately unresolved and are not specified here.

The superseded online path used the ROS 2 `usb_cam` driver in its
`raw_mjpeg` mode for UVC capture.
`umi_ros2` supplies the Action 4 configuration and launch integration, then
extracts the JPEG payload from `/action4/image_raw`, republishes it without
recompression as `/action4/image_raw/compressed`, and decodes a 640×360
best-effort `/action4/image_preview` for RViz. The preview may drop frames
without affecting the recording publication.
`CameraInfo` remains uncalibrated until intrinsic calibration is completed. The
package does not own Vive capture, recording orchestration, or synchronization.

The active online architecture under D-009 replaces that MJPEG path with one
Python ROS node and one external GStreamer child. GStreamer remuxes native H.264 into
MP4 and emits decoded 640×360 BGR frames through stdout. Python continuously
drains the pipe, retains only the newest frame, and publishes a small ROS
`Image` for RViz. RViz does not consume MJPEG or H.264 directly. This path is
implemented but not yet hardware-accepted.

`online_view.launch.py` is the online observation entry point: it starts
`vive_pose_node`, the native-H.264 camera process, and RViz2. Its RViz
configuration displays `/vive/path`, TF, and `/action4/image_preview`. It does
not start recording.

`umi_ros2/launch/online_record.launch.py` is the online recording entry point. It
starts both sensor nodes, RViz, an H.264 MP4 recorder subscribed to the source
JPEG stream, and pose-only rosbag2 MCAP storage. Both outputs share one session
directory; the video recorder also writes a frame-index/ROS-timestamp CSV.
Preview, source image, CameraInfo, and path topics are excluded from the pose
bag. If either hardware or recording process exits unexpectedly, the launch
shuts down so an incomplete session is not silently continued.
The recorder starts after a configurable warm-up delay (five seconds by
default), allowing the camera, Vive, RViz, and DDS discovery to stabilize before
the accepted bag interval begins.

`umi_ros2/launch/offline_record.launch.py` reuses Vive and pose/path RViz but
starts no USB camera. It records only Vive pose and TF under
`offline_session_<timestamp>/pose/`. The operator later copies the corresponding SD-card
recording to `offline_session_<timestamp>/video.mp4`, matching the online session's
top-level video-plus-pose boundary.

`umi_ros2/launch/replay.launch.py` accepts either an online session root or one
calibration/episode directory. The session-aware replay node orders calibration
items before ordinary episodes, decodes each `video.mp4` into
`/action4/image_preview`, and starts rosbag2 playback for the matching `pose/`.
Rosbag `/clock` schedules absolute video timestamps so process startup latency
does not shift the two streams. `replay_path_node` reconstructs `/vive/path` and
clears it between items. The accepted temporal offset is not yet applied.

## Technical components and open questions

- `ament_python` provides the ROS 2 package and console entry point.
- libsurvive's high-level `SimpleContext` API supplies tracked-device poses
  directly without SteamVR.
- `geometry_msgs/PoseStamped` and TF expose ROS-compatible data.
- `nav_msgs/Path` exposes recent trajectory history; `max_path_points` bounds
  memory and message size, with a current default of 10,000 poses.
- Multi-device publication, pose covariance, tracking diagnostics, exact clock
  synchronization, and calibrated-world alignment to the robot are not yet designed.
- The current path republishes an increasingly large message at the pose update
  rate. Its 10,000-point cap bounds memory, but path sampling or a lower path
  publication rate should be considered before long recording sessions.
- Path history is process-local and resets whenever the node restarts. Tracking
  loss pauses pose/path updates but is not exposed on a dedicated status topic.

## Consolidated online/offline structure

The three former project-owned ROS packages are consolidated into one `umi_ros2`
application package. Focused runtime executables remain separate inside that
package, while launch, configuration, RViz assets, and tests gain one owner.
External packages such as GStreamer, RViz, and rosbag2 remain dependencies.

Responsibilities are organized by mode rather than duplicated:

| Layer | Shared by both modes | Offline only | Online only |
| --- | --- | --- | --- |
| Hardware | Vive pose acquisition and stable device selection | Action 4 records to microSD without USB | Action 4 native H.264 UVC capture through GStreamer |
| Runtime | Pose/TF publication, session identity, metadata, health checks | Pose-only recording and pose/path RViz | JPEG bridge, live image preview, MP4 writer, and pose-only MCAP orchestration |
| Data | Pose schema, calibration metadata, validation result, normalized session contract | MP4 import and offline image/pose alignment | H.264 MP4, frame timestamps, pose/TF MCAP, and live continuity checks |
| User entry | Common naming, output layout, validation/reporting conventions | `offline_record` workflow | `online_view`, `online_record`, and online `replay` workflows |

Only components that continuously participate in ROS communication remain ROS
nodes. One-shot video import, bag inspection, gap analysis, synchronization,
quality reports, and dataset conversion belong to ordinary command-line tools.
The migration must preserve topic names and existing recordings.

## Related entries

- [Requirements](REQUIREMENTS.md)
- [Current Vive task](tasks/active/vive-ros2-node.md)
- [Development decisions](DECISIONS.md)
