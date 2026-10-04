# Multi-camera acquisition and image-to-pose alignment

**Status:** Action 4 and D435i color are registered in `online_record` and
`online_view`. Two real image streams were previewed and recorded together
with synthetic pose, then one user episode recorded both alongside real Vive
pose. Per-camera translation-only calibration is implemented under D-036;
multi-image alignment/export and live per-camera calibration acceptance remain
open.

**Post-processing target (D-041, 2026-10-02):** The user specifies wrist and
left images repeated three times at the nominal 90 Hz pose rate, current/next
TCP poses as XYZ + XYZW state/action, and each episode's raw pose-start reference.
See [raw-to-dataset.md](raw-to-dataset.md) for the illustrated interpretation and
confirmed timeline and real timing/boundary policy. Standalone 90 Hz expansion
is implemented and verified (24 new tests; 3234 candidate/3138 valid real-file
samples, unchanged raw hashes). Independent local-pose transformation is also
implemented and verified (23 new tests; all 3234 real pose queries converted
with unchanged raw/input hashes). State/action, export and `build_dataset`
integration remain pending. Acquisition/raw files are frozen
for this work, and URDF IK is deferred.

**Manual alignment inspection (D-040):** `frame_alignment_viewer` reads files
directly, with manual forward/backward steps, seeking, recording/camera choice
and a raw-versus-corrected toggle. Use each camera's actual PTS/anchor/accepted
offset to interpolate recording-start TCP pose. Pair the other view by nearest
corrected time, report its delta and draw its own pose marker. Current session
`online_session_20260930_212318_104281` has 1080/1081 valid paired episode pose
queries and accepted wrist/left offsets -112.143/-6.703 ms; both calibration
clips load. Five new tests, real backward seeking and Tk GUI redraw/switching
pass; the real rendered layout was inspected. Full suite: 138 passed, 2 skipped,
2 existing missing-h5py failures; build/static checks pass. No raw files or
capture processes are changed; operator visual alignment acceptance is pending.

**RGB endpoint selection (D-039):** D435i's by-id `video-index0` can collide
across UVC interfaces and point to Z16 depth. The source now selects serial
`254343064631`, RGB interface `03` and V4L2 index `0` through sysfs; an explicit
launch device override or synthetic source bypasses discovery. Selection tests
pass, including reordered nodes and missing/ambiguous endpoints. Full suite:
133 passed, 2 skipped, 2 existing missing-h5py failures; build and static checks
pass. Real dual-camera workers completed warmup. The interrupted diagnostic
launch was stopped to release both cameras; the user confirmed their own
launch now runs. This is startup acceptance, with no new recorded episode.

**Selected camera calibration (D-036):** `c` lists registered camera numbers;
the chosen camera alone records with shared pose, preserving other previews.
Stop immediately runs the existing XYZ translation estimator and prints a
colored accept/reject. Reject removes that attempt's raw and derived inputs
but keeps its folder for Enter to retry; camera changes retain independent
retry slots, offsets and accepted data. Session indexing replaces retries.
Results use `temporal_calibrations[camera_id]`, with wrist compatibility in
`temporal_calibration`. The 500 ms lead stays in absolute timestamps and is
not interpreted as latency. Tests recover both signed offsets with real MCAP
and synthetic image features, and verify cleanup, index replacement, camera
isolation, raw copying and keyboard retries. Real per-camera acceptance is
pending. Full pytest: 125 passed, 2 skipped, 2 existing missing-h5py failures;
build, touched-file flake8 and diff checks passed. Multi-view export remains
subsequent work.

**Recording-start coordinates (D-038):** Calibration v4 and derived dataset
poses use the first saved TCP pose after the start command, before image delay,
as a fixed position/orientation reference. Raw world pose/TF remains the source.
Only local XYZ enters the ArUco matcher; no orientation motion features. Tests
recover known signed offsets with 90-degree/arbitrary initial rotations and
verify that first-image pre-roll displacement remains represented. Full suite:
130 passed, 2 skipped, 2 existing missing-h5py failures; build and static
checks pass. Existing results were not recalculated; new real motion acceptance
is pending.

**Automatic episode diagnostics (D-035, supersedes D-032):** Every ordinary
episode is diagnosed after MP4s and MCAP close. Reuse existing video checks;
require decode/count/timestamp integrity, no video gap over 50 ms, full raw
host-time image coverage by pose headers and average pose rate at least 88 Hz.
Small pose gaps alone do not reject. Print green `accept` or red `reject` in
both terminals and persist `quality.json` with an exclusion marker. Rejection
does not block the next recording. No new launch parameters or worker changes.
Build, flake8 and 19 focused tests passed; full suite 115 passed, 2 skipped,
2 existing missing-h5py failures. Four real episodes/eight MP4s plus MCAP took
6.511 s to check: newest three accept, prior 51.899 Hz episode rejects.
New live automatic-stop acceptance remains pending; raw files were unchanged.
Dataset export enforcement of the exclusion marker remains future work.

**Pose lead (D-033):** Episode and calibration starts now wait 500 ms after
the first saved pose is confirmed before issuing either camera start command.
The pose worker writes throughout that wait. Ordering tests for both kinds and
the missing-first-pose failure path passed; build and flake8 passed. Hardware
acceptance passed in `online_session_20260930_145919_328592`: episode 0001
wrist/left first images arrive 584.85/601.23 ms after the first saved pose,
and episode 0002 586.49/613.42 ms. Both episodes use the symmetric camera
directories and correct stream mappings. Four MP4s decode with matching
accepted counts and have no PTS intervals over 50 ms.

**Sampling-rate observation:** This session's pose average rate changes from
89.73 Hz in episode 0001 to 51.90 Hz in episode 0002. Second-episode
five-second windows fall from 55.14 to 47.86 Hz, with maximum adjacent gap
22.68 ms and finite poses. The diagnosis below identifies accumulating path
publication as the high-confidence main bottleneck. D-034 removes that work
from the pose callback; three short real episodes now maintain about 90 Hz,
while longer recordings remain unverified,
separately from the verified image start
delay. Subsequent D-035 adds recurring episode acceptance diagnostics.

### Pose slowdown diagnosis before D-034 (2026-09-30)

User requested analysis of whether episode 0001 finalization affects episode
0002. Acquisition code and raw files were left unchanged.

- Finalization stops both encoders, synchronously validates both videos,
  closes the pose writer and clears recording state. Normal episode stop
  does not trigger calibration. The next episode gets a fresh MCAP writer;
  camera capture and pose subscriptions remain alive. Logs show episode 0001
  completion at 15:00:00.408 CST and the first episode 0002 pose at
  15:00:48.639 CST: about 48.23 s later, with no pending video validation.
- `VivePoseNode` keeps its Path across episode boundaries and during waiting.
  Each 90 Hz callback reads the latest backend pose, publishes PoseStamped,
  appends to the path, publishes the entire Path (up to 10,000 points), then
  publishes TF. Increasing path conversion/publication cost can exceed the
  11.11 ms timer period. This state belongs to the ongoing Vive node rather
  than the per-episode MCAP writer.
- Actual pose record minus header lag medians are 0.363 ms in episode 0001
  and 0.423 ms in episode 0002 (episode 0002 maximum 1.025 ms). Corresponding
  TF record minus header lag medians are 6.677 and 19.384 ms. In episode 0002
  TF lag rises from 18.334 to 21.060 ms across five-second windows and its
  correlation with the next pose header gap is 0.9957. This localizes the
  large delay to work after pose publication and before TF, consistent with
  full Path publication, rather than an MCAP writer backlog. There are 1,357
  matched pose/TF stamps in episode 0002; one TF precedes its first pose and
  the final pose's TF falls outside the writer interval, consistent with the
  callback publication order and recording boundaries.
- Read-only isolated reproduction used the unmodified `VivePoseNode` with a
  fake always-ready backend, real ROS publishers and TF enabled, no RViz or
  camera load, and a separate ROS domain. Thirty direct callbacks per path
  size (discard first five) gave median callback durations of 2.35/6.76/
  11.34/13.43/15.77/18.04/22.24 ms at 1,000/3,000/5,000/6,000/7,000/8,000/
  10,000 initial points. At 8,000 points Path publication alone took 17.97 ms
  while PoseStamped publication took 0.008 ms.
- Four-second executor runs with 7,000 initial points measured 61.47 Hz with
  Path publication and 89.98 Hz when only that publication was suppressed;
  the path still accumulated and TF remained enabled. This reproduces the
  mechanism and makes it the high-confidence main cause. It does not measure
  the real Tracker's internal sample rate or constitute a repaired hardware
  acceptance run.

Recommended next change: remove full-history visualization publication from
the high-frequency pose callback; use a separate visualization node or other
decoupled processing with downsampled, bounded path points and lower-rate Path
publication. A separate timer in the same single-threaded executor alone can
still block pose while publishing a large Path; lowering its rate alone does
not guarantee 90 Hz. Clearing the path only on episode boundaries also leaves
long recordings vulnerable. The user subsequently authorized implementation
as D-034, described below.

Temporary diagnostic script/report:
`/tmp/umi_pose_slowdown_diagnostic.py` and
`/tmp/umi_pose_slowdown_diagnostic_20260930.json`.

### Independent live Path node (D-034, 2026-09-30)

Implemented `vive/path_node.py` and the installed `vive_path_node` console
entry point. The acquisition node no longer owns path history or publication.
A separate process caches the latest pose using best-effort depth-one QoS;
its 30 Hz timer appends one fresh sample and publishes the bounded path.
Incoming receipt callbacks may run at the pose rate, but do no history work;
trajectory sampling/publication run at 30 Hz. Source headers and coordinates
are preserved, paused input adds no repeated points, and frame changes clear
history. The existing 10,000-point cap is retained. Path configuration moved
to a separate node block in `config/vive.yaml`. Live `vive`, `online_view`,
and `online_record` launch files now start both processes. Replay and raw
pose/TF recording behavior are unchanged.

Verification:

- Build and touched-file flake8 passed. Eight new tests verify latest-sample
  behavior, source pauses, bounded history, frame changes, pose/TF independence
  and all three launch entry points. Alongside pose-extrinsic/launch tests,
  22 focused tests passed. Full pytest: 101 passed, 2 skipped, 2 existing HDF5
  failures caused by missing `h5py`; no new failure.
- A 12 s isolated concurrent probe used the unmodified current pose node with
  a fake always-ready Tracker, the current path node prefilled to its 10,000
  point cap, and a C++ DDS Path subscriber. Each ran in its own process;
  a parent observed pose/TF. It measured 1,080 poses at 90.002 Hz, max gap
  11.915 ms, median receive lag 0.430 ms and 1,080 TF messages. Three four-second
  windows each stayed around 90 Hz. Path emitted 360 messages and C++ received
  359 around the measurement boundaries, both about 29.916 Hz by source
  header stamps, with exactly 10,000 points and increasing headers throughout.
  All processes exited cleanly. Path serialization itself still took a median
  21.22 ms, but it did not block the pose process.
- An initial Python Path observer measured only about 8.52 Hz at the same
  full-size history. The C++ probe above verified DDS receipt using the
  language interface used by RViz rather than that slower Python observer.
  These probes do
  not validate actual RViz rendering or real Tracker/camera sustained behavior.

Software report: `/tmp/umi_vive_path_separation_probe_cpp_20260930.json`.
Probe script: `/tmp/umi_vive_path_separation_probe.py`; temporary C++ receiver
sources/build: `/tmp/umi_path_cpp_probe/`. Actual long-running multi-episode
Tracker plus dual-camera and RViz hardware acceptance is still open; the
three short real episodes checked below provide bounded rate/coverage evidence.

### Three-episode real recording check after D-034 (2026-09-30)

User requested pose/image coverage, pose gaps and image gaps for the latest
session. Selected `online_session_20260930_160029_092182`, the newest session
with three complete episodes. It ran for about 117 s and is `not_calibrated`.
Logs confirm the real Tracker pose source and separate Path process configured
at 30 Hz started and exited cleanly. No runtime or raw recording changes were
made during that check; D-035 subsequently adds recurring episode QC.

| Episode | Pose samples | Average Hz | Max gap ms | Gaps >16.667 ms | Wrist/left frames | Wrist/left max video gap ms |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| 0001 | 1988 | 89.774 | 22.313 | 5 | 585/583 | 40.000/33.667 |
| 0002 | 1342 | 89.799 | 22.210 | 3 | 391/391 | 40.666/34.000 |
| 0003 | 1240 | 89.856 | 22.380 | 2 | 357/355 | 39.000/33.667 |

Five-second pose window rates stay within 89.398–90.009 Hz, without the prior
progressive fall to about 52 Hz. The 5/3/2 gaps are isolated approximately
two-period gaps, suggesting a missing update relative to the nominal 90 Hz
timer. There is no gap over 100 ms, timestamp reversal or non-finite pose;
pose/TF counts and source header stamps match one-to-one. These files do not
establish whether the isolated missing update originated in Tracker hardware,
backend availability, ROS scheduling/transport or recording.

All six MP4s decode without error and match worker accepted counts; all PTS
increase. Effective rates from first/last PTS are 29.971–29.979 fps. None has
an interval over the 50 ms image screening threshold. This supports no obvious
image gap or accepted-to-encoded loss; absent native per-frame camera sequence
numbers, source completeness remains `not_verified`.

Every decoded image PTS, anchored at `first_receive_unix_ns`, lies within the
pose header range. First image leads from first pose record timestamp:

| Episode | Wrist/left lead ms | Wrist/left tail s |
| --- | --- | --- |
| 0001 | 588.563/589.548 | 2.044/2.115 |
| 0002 | 599.191/550.501 | 1.324/1.373 |
| 0003 | 607.932/655.260 | 1.302/1.324 |

All pass the 500 ms host-side lead. Coverage is raw host/source-timestamp
coverage, not exposure-time or calibrated-offset acceptance. Stream identity,
paths, timing self-paths and metadata counts are correct. The joint pose/MP4
analysis took 1.985 s, excluding preparation and reporting. Saved evidence:
`docs/project/reports/raw-recording-check-20260930-160029.md`, `.json` and
an unexecuted rerunnable companion `.ipynb` containing the exact analysis code.
Actual Path publish rate and RViz rendering were not recorded and remain
outside this raw-data check.

**Subsequent implemented work:** D-035 adds frame-gap statistics, colored
episode verdicts and the JSON exclusion marker; D-036 adds independent camera
calibration. These were separate changes after the pose-lead implementation.

## Action 4 + D435i online integration (2026-09-30)

The user replaced the earlier D435 with a D435i (D-030). Its YUYV color stream
is the new `left` / `left_image` source. `config/realsense_left.yaml` now uses
serial `254343064631` and RGB USB interface `03` for sysfs selection (D-039),
currently `/dev/video4`. Action 4 uses its own by-id link (`/dev/video8` in
the latest startup check).
The numeric nodes are not configuration contracts. Depth and infrared remain
outside this work.

`online_record` and `online_view` publish Action 4 at 320×180 and D435i at
320×240 (10 Hz preview timer), while recording the source streams at their
configured capture sizes and frame rates. `online_record` requires both camera
workers and one pose worker before each episode. It writes wrist data to the
`cameras/wrist/video.*` files and left data to `cameras/left/video.*`, with one
`pose/` MCAP. `session.yaml` indexes both identities and relative paths.
Session switching copies each completed raw calibration stream. D-036 adds
independent immediate calibration and single-camera replay resolution, with
legacy root `video.*` wrist recordings readable. Multi-image alignment and
dataset export remain subsequent work.

**D-031 layout correction:** New episodes and calibrations place every
camera's MP4, timing and validation in `cameras/<camera_id>/`. The real
`online_session_20260930_133225_127556/episode_0001` wrist files were
migrated to `cameras/wrist/`, its index and timing self-path updated, and
the MP4 SHA-256 stayed
`c3e8e204c14cc3c5658b039a24a47d5403e359bb3b3a2443053d8b77276479de`.
Older recordings remain in their original location and are read by fallback.

**Verification:** With both real cameras connected, `online_record.launch.py`
published BGR8 preview messages on both topics (320×180 wrist and 320×240
left). A test episode with a synthetic `/vive/pose` saved two decodable
78-frame MP4 files, complete per-camera timing/validation, and one pose MCAP.
Both videos have matching accepted and decoded frame counts. RViz stayed alive
and exited cleanly in that run. Direct D435i V4L2 at 640×480/30 delivered 10
frames on a 5000M USB 3 link. Actual Vive pose did not arrive during that
earlier hardware run; a subsequent user recording is checked below.

**Real episode diagnosis:**
`recordings/online_session_20260930_133225_127556/episodes/episode_0001`
contains 2053 `/vive/pose` messages with header stamps from 13:32:44.310 to
13:33:07.199 CST. The largest adjacent pose gap is 22.50 ms. The wrist MP4
decodes 612 frames at 29.970 fps from first/last PTS, with a maximum interval
of 41.33 ms. The left MP4 decodes 613 frames at 29.978 fps, with a maximum
interval of 33.67 ms. Both decoded counts equal worker accepted counts; no
frame interval exceeds 50 ms. Anchoring frame PTS to each video timing file's
first host-receive timestamp puts all frames within the pose header range.
The pose lead at the first wrist/left frame is 73.33/80.86 ms, and the pose
continues roughly 2.4 s after the last frames. This session has no accepted
temporal calibration, so coverage after per-camera offset correction and
source-side frame completeness are not established by this check.

## Previous D435 color adapter verification (2026-09-30)

`RealSenseSource` uses the same `CameraSource` lifecycle and shared
`WorkerCameraSource` process transport as `Action4Source`. The earlier D435
exposed a color endpoint at `/dev/video6` after USB 3 reconnection, with YUYV
640×480/30 fps. The worker maps this
to GStreamer YUY2, keeps a BGR preview, and attaches an H.264 MP4 encoder for
each recording. The adapter uses `camera_id: left` and
`image_field: left_image`; depth and infrared streams are outside this step.
The adapter is now registered for the replacement D435i in `online_record`;
the observations below describe the earlier D435 only.

**Software verification:** Build passed; six focused adapter/worker tests
passed; synthetic YUYV input warmed up, produced preview frames, and wrote a
decodable 48-frame MP4 whose timing metadata identifies `left` /
`left_image`. The MJPEG Action 4 path produced another 48-frame MP4 in the
same smoke test. Full pytest: 85 passed, 2 skipped, 2 pre-existing HDF5
failures because `.venv` lacks `h5py`.

**Hardware verification:** On the initial USB 2 (480M) connection, direct
V4L2 requests at 640×480/30 and 424×240/30 timed out with zero frames, as did
the live adapter. After the user moved the D435 to a USB 3 connection,
`lsusb -t` reported 5000M and direct V4L2 delivered 10 color frames. The
adapter completed warmup in about five seconds and delivered 103 preview
frames during a 10-second probe. A two-second standalone recording wrote a
decodable 63-frame 640×480 H.264 MP4 and complete YUYV timing metadata with
`left` / `left_image`; BGR preview continued after recording stopped. This
verifies standalone color acquisition, not concurrent Action 4 + RealSense
recording or multi-camera session behavior.

## First implementation: Action 4 adapter (2026-09-30)

- Introduce a ROS-free camera source interface for identity, latest preview
  frame, readiness/health, recording start/stop and shutdown. The Action 4
  implementation owns its existing long-lived GStreamer worker process.
- A preview frame carries `camera_id`, `image_field`, image encoding/size,
  source PTS when available and host receive time. This interface describes
  frames without making a full-resolution ROS Image topic the transport.
- The Action 4 instance is registered as `camera_id: wrist`,
  `image_field: wrist_image`. Its configured `/dev/video*` is the default;
  `online_record` can override it via a separate launch argument.
- Write the camera identity and image field as additive timing metadata. Keep
  the existing single-camera `video.mp4` layout and schema v2 consumers in
  this step; multi-camera storage and dataset export are later work.

**Implementation:** `camera/source.py` defines the camera lifecycle and
`ImageFrame`. `camera/action4_source.py` implements it using the existing
persistent worker. The worker now frames each preview with source PTS and host
receive time; `h264_capture_node` publishes those previews and coordinates
recordings through the adapter. The configured default port remains in
`action4.yaml`; `video_device:=...` can override it in the launch files.

**Verification:** ROS package build passed. The Action 4 and related launch /
session tests passed (22/22). A synthetic GStreamer camera completed warmup,
produced timestamped preview images, and wrote a 33-frame MP4 plus timing
metadata with `camera_id: wrist` and `image_field: wrist_image`. Full pytest:
82 passed, 2 skipped, 2 unrelated HDF5 tests failed because this checkout's
`.venv` lacks `h5py`. Real Action 4 frame delivery and ROS preview publication
were subsequently verified; sustained recording and dataset acceptance remain
open.

## Confirmed direction (D-027)

- `online_record` registers cameras through one common camera interface.
  Camera-specific adapters read their default device from configuration;
  launch arguments may override it.
- Each stream declares a stable `camera_id` and a dataset `image_field`, such
  as `wrist_image`, `left_image` or `right_image`. The recording metadata keeps
  this mapping, and each image stream has its own video and timing data.
- The Vive pose stream is shared. Temporal calibration estimates one offset
  per camera against that pose stream; no camera inherits another camera's
  offset.
- Cameras continue streaming for preview while waiting. Recording enables
  per-camera file writing without reopening or warming the camera each time.

## Proposed implementation sequence

1. Specify the camera interface, registration format and raw recording schema.
   Include source PTS, stable IDs, field names, device override precedence and
   a path for existing single-camera sessions.
2. Separate session/recording coordination from the Action 4 acquisition
   backend. Add multiple camera instances and independent MP4/timing writers,
   retaining one pose MCAP per recording.
3. Extend session indexing, calibration copy, validation and replay to resolve
   every registered camera. Keep historical single-camera recordings readable.
4. Run temporal calibration separately for each camera against the same pose
   recording. Store each result and its quality status by `camera_id`.
5. Align streams on a defined dataset time axis; export every declared
   `image_field` with pose to HDF5 and LeRobot, with explicit missing-frame
   behavior.

## Decisions needed before implementation

- Whether the common camera stream crosses a ROS topic boundary or remains in
  the capture process. Full-resolution raw images may be costly to move through
  ROS; the interface must retain source timing either way.
- Whether every registered camera is required for a recording, and how an
  individual camera failure affects the other raw files and session status.
- Dataset reference timeline, frame pairing tolerance and handling of missing
  frames or a rejected calibration for one camera.
- Whether every camera sees the calibration marker in each calibration
  recording, or cameras need separate calibration recordings.

## Acceptance boundary

Software verification should cover two synthetic cameras with distinct
`image_field` values, per-camera file/index integrity, independent offsets,
multi-image export and backwards reading of a single-camera session. Hardware
acceptance requires the real camera combination, sustained multi-view capture,
preview, and repeatable per-camera calibration against the Vive Tracker.

## 2026-09-30 live preview diagnostic

The user's `online_view` terminal showed RViz exiting with a futex error. The
camera worker remained in `warming_up`. A direct 13-second Action 4 probe
returned no preview frame. Direct GStreamer and V4L2 probes of `/dev/video2`
also timed out without a frame at supported MJPEG 1080p and 720p settings;
`/dev/video3` exposes no capture format. The device is enumerated and not held
open by another process. This isolated that initial missing image to device
frame delivery before the ROS preview path.

The worker now warns after five seconds with zero source frames and reports a
specific no-frame timeout error. Frames that arrive but fail warmup retain
their separate diagnostic; recording admission and timeout are unchanged.
The ROS preview path was independently exercised with a synthetic camera:
`/action4/image_preview` delivered five valid `sensor_msgs/Image` messages.
After the user re-entered Webcam mode on the Action 4, a direct real-camera
probe delivered continuous preview frames and completed warmup in about five
seconds. The real ROS node then published five valid 640×360 BGR8 Image
messages on `/action4/image_preview`. A full `online_view.launch.py` run kept
RViz running throughout a 15-second observation and completed camera warmup;
RViz's image topic and best-effort QoS match the publisher. The earlier futex
failure did not recur during this run. The user then confirmed the RViz
preview image works. RViz threw `std::system_error` during the forced SIGINT
shutdown; that is separate from the verified camera frame path.
