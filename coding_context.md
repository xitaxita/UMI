# UMI — Coding context

Entry point for anyone about to change code. It describes the **current** state
only. History is in git, rationale in
[DECISIONS.md](docs/project/DECISIONS.md), and the user-facing board in
[project.md](project.md).

- **Last synchronized:** 2026-10-04 (Tracker-to-TCP extrinsic refresh; standalone expansion/local-pose evidence retains 2026-10-02)
- **Branch:** `feature/multi-task-sessions` (not merged, not pushed). It holds
  the D-021 multi-task-session work and the D-022 simplification.

## Where things are

| Document | Use |
| --- | --- |
| [project.md](project.md) | Progress board, capabilities, acceptance checklist |
| [README.md](README.md) | Operator setup and step-by-step use (Chinese) |
| [REQUIREMENTS.md](docs/project/REQUIREMENTS.md) | Confirmed scope |
| [ARCHITECTURE.md](docs/project/ARCHITECTURE.md) | Current structure and data flow |
| [DECISIONS.md](docs/project/DECISIONS.md) | Decisions with a status index (D-001…D-041) |
| [tasks/active/](docs/project/tasks/active/) | `raw-to-dataset`, `multi-task-sessions`, `temporal-calibration`, `urdf-path-diagnostic`, `multi-camera-acquisition` |
| [tasks/archive/](docs/project/tasks/archive/) | Completed tasks with their original evidence |

## Environment

- Ubuntu 24.04, ROS 2 Jazzy, `/home/xing/Documents/UMI/.venv` (system site
  packages, `setuptools==68.1.2`, `pysurvive==1.1.204`). Source ROS under
  **bash**: sourcing
  `/opt/ros/jazzy/setup.bash` from zsh fails.
- Build: `python -m colcon build --packages-select umi_ros2 --symlink-install`.
  Colcon never removes deleted launch, rviz, config or console scripts from
  `build/` and `install/`. Delete stale links by hand, or the build fails on a
  dangling link.
- LeRobot 0.4.4 is only in `/home/xing/umi_lerobot_venv312`. Never install it
  into the ROS venv. Call that interpreter by its unresolved path
  (`Path.absolute()`, not `resolve()`), because `bin/python` is a symlink to
  the system Python.
- Verification per change: colcon build, full `pytest umi_ros2/test`, flake8 on
  touched files, `git diff --check`. Some untouched files carry pre-existing
  D1xx and import-order warnings (`setup.py`, `launch_support.py`,
  `test_vive_backend.py`, `online_record.launch.py`).
- The flake8 import-order style sorts `umi_ros2` alphabetically among
  third-party imports: `pytest`, then `umi_ros2…`, then `yaml`.

## Package `umi_ros2`

| Area | Files | Notes |
| --- | --- | --- |
| Vive | `vive/backend.py`, `vive/pose_node.py`, `vive/path_node.py`, `vive/pose_recording_worker.py` | Backend has no ROS. The pose node publishes TCP pose and both TFs at its 90 Hz timer. A separate path process samples the latest pose and publishes Path at 30 Hz. Extrinsic parameters `tracker_to_tcp_translation_m` / `_rotation_xyzw` exist **only** in `config/vive.yaml`, have no default, are validated at startup, and accept live `ros2 param set` updates |
| Camera | `camera/source.py`, `worker_source.py`, `action4_source.py`, `realsense_source.py`, `stream_protocol.py`, `h264_capture_node.py`, `capture_worker.py`, `capture_pipeline.py`, `episode_keyboard.py` | ROS-free source interface with shared worker transport; Action 4 and D435i color adapters both registered in online launch. One node owns two camera workers, the pose worker and session control. Services `~/start_episode`, `~/start_calibration`, `~/stop_episode`, `~/new_session`; parameters `task`, `next_task` |
| Session | `session/layout.py`, `session/set_session_task.py` | Only writer of `session.yaml` (atomic replace). Schema v2; v1 readable. Also `copy_calibration_raw`, `switch_session`, `latest_calibration` |
| Calibration | `synchronization/calibrate_time.py`, `temporal_alignment.py`, `generate_marker.py` | ArUco DICT_4X4_50 id 4 centre/scale matched to XYZ in the fixed recording-start TCP frame; initial orientation defines axes, no rotation motion features. Runs automatically on calibration stop |
| Post-processing | `postprocess/align_session.py`, `expand_session.py` (+ `frame_expansion`), `localize_session.py` (+ `local_pose`), `transform_session.py`, `dataset_plan.py`, `export_hdf5.py`, `export_lerobot.py`, `build_dataset.py` (+ `pose_io`, `alignment`, `episode_transform`) | Plain Python, no ROS graph. Expansion/localization are standalone, pending downstream integration. NumPy algorithms, `localize_session`, `dataset_plan` and `common/` remain importable from the LeRobot venv |
| Replay | `visualization/session_replay_node.py`, `replay_source.py`, `replay_path_node.py`, `frame_alignment.py`, `frame_alignment_viewer.py` | Accepted per-camera offsets in ROS replay or a manual Tk/Matplotlib file viewer with paired images and recording-start pose |
| Shared | `common/ordering.py` | `natural_key` |

Launch files: `online_record`, `online_view`, `replay`, `vive`, `camera`,
`urdf_path_diagnostic`. Console entry points: `vive_pose_node`, `vive_path_node`,
`h264_capture_node`, `episode_keyboard`, `set_session_task`,
`calibrate_time`, `generate_aruco_marker`, `align_session`, `expand_session`,
`localize_session`, `transform_session`, `export_hdf5`, `export_lerobot`, `build_dataset`,
`session_replay_node`, `replay_path_node`, `frame_alignment_viewer`.

## Contracts to keep

- **Session** (`online_session_<time>/`): `session.yaml` schema v2 with a
  top-level `task` (the only task used by export), `status`, `recordings[]`
  (each with a `task` snapshot and optional provenance-only `copied_from`) and
  `temporal_calibration`. The directory name never contains the task.
  Unknown schema versions are rejected.
- **Recording** (`calibration/calibration_<nnn>/`, `episodes/episode_<nnnn>/`):
  Action 4 uses `cameras/wrist/video.{mp4,timing.json,validation.json}`;
  D435i color uses `cameras/left/video.{mp4,timing.json,validation.json}`.
  Readers also accept historical wrist `video.*` files at recording root.
  Each timing file
  carries its `camera_id` / `image_field` (`wrist` / `wrist_image` or `left` /
  `left_image`). Session and recording index entries map streams through
  `image_streams`. Both validation files report
  `source_completeness: not_verified`. Calibration records only its selected camera; ordinary episodes record both.
  One `pose/` MCAP holds `/vive/pose`,
  `/tf`, `/tf_static`; after confirming the first saved pose, wait 500 ms
  before camera MP4 start commands. Pose closes after the selected MP4s.
  The layout remains schema v2.
- **Session switch** (`n`): refused while recording. Only complete
  calibrations are copied, and only their raw files, staged as hidden
  `.calibration_<n>.partial`, including both camera files and stream mappings.
  It is all-or-nothing. Episodes renumber from
  0001; calibrations continue after the highest copy.
- **Offset convention:** `pose_time = video_time + video_to_pose_offset_seconds`.
  One constant per camera per session. `temporal_calibrations[camera_id]`
  stores independent results; singular `temporal_calibration` is the wrist
  compatibility view consumed by current dataset export.
- **Standalone expansion contract v1** (`expanded_frames.npz`,
  `expanded_frames.csv`, `expansion.json`, session `expansion_summary.json`):
  fixed 90 Hz clock; nearest per-camera corrected images at each three-tick
  group start, default 1/60 s tolerance; selected source indices repeated
  three times, no valid image reused across groups. Full-group validity,
  world XYZ/XYZW pose and original raw reference are retained. Invalid groups
  keep their clock slots. `localize_session` now consumes this contract;
  legacy transformation, exporters and `build_dataset` do not. Raw MP4 image
  repetitions are not re-encoded. Input still requires an ordinary episode
  with both cameras; calibration and single-camera expansion are unsupported.
- **Standalone local-pose contract v1** (`local_frames.npz`,
  `local_frames.csv`, `local_pose.json`, CLI `local_pose_summary.json`):
  consumes expansion v1; `position_xyz` / `orientation_xyzw` are expressed in
  the fixed first raw TCP frame. Preserves all sample/clock/image/validity
  fields, raw reference and `world_position_xyz` / `world_orientation_xyzw`.
  Transforms every `pose_valid` query, even with invalid images; invalid pose
  queries stay NaN. Requires an explicit raw-start reference with no fallback.
  XYZW is normalized with continuous signs across successive valid poses.
  No state/action; no video/MCAP read required; legacy exports do not consume it.
- **Transformed contract v1** (`episode_frames.npz`, `transform.json` with
  `source_video`, `source_episode`, offset): consumed by both exporters.
- **HDF5 format v2:** episodes `episode_0000…` across the dataset; attributes
  `task`, `task_index`, `source_session`, `source_episode`,
  `video_to_pose_offset_seconds`; a root `tasks` string dataset; no root
  `task`.
- **LeRobot v3:** per-frame session `task`, `umi.source_session` (string),
  `umi.source_frame_index`, `umi.video_pts_seconds`,
  `umi.pose_query_time_seconds`; `umi_export.json` schema 2. There is no
  `action` field.
- **build_dataset output:** `<out>/{build_manifest.json, processed/<session>/…,
  processed/dataset_plan.json (relative paths), dataset.hdf5, lerobot/}`,
  built in `<out>.partial`. `--overwrite` only replaces a directory holding
  `build_manifest.json`. Frame rate is the median PTS interval, not OpenCV's
  `CAP_PROP_FPS`, which read 29.969 on real 30 fps files.

## Current state (2026-10-04)

- **Tracker-to-TCP refresh (D-020 amendment, 2026-10-04):** The user explicitly
  authorizes replacing the outdated values in `config/vive.yaml`, a
  parameter-only exception to the acquisition-configuration freeze.
  Current source is `/media/xing/zijun/User/Documents/课题组/UMI/3Dprint/UMI/co2_in_co1.txt`
  (the supplied `Use` directory was a typo). Co1 = `vive_tracker`, co2 =
  `gripper_tcp`; use the supplied transform directly. Translation is
  `[0.0, -0.194899844, 0.080510987]` m and XYZW quaternion is
  `[0.457263310, 0.0, 0.0, 0.889331359]`. The root `co2_in_co1.txt` remains
  the older source artifact. File matrix/quaternion/metre/mm values agree;
  installed config matches the current source and its SHA-256 is unchanged.
  Eight existing extrinsic tests pass; full suite 185 passed, 2 skipped,
  2 pre-existing missing-h5py failures. Build, touched-test flake8 and diff
  checks pass. Acquisition algorithms/raw files/calibration results are
  unchanged; no running hardware or live parameters were updated. Restart
  Vive to publish the new TCP definition. Existing raw pose messages and
  their derived results retain their original TCP definition; prior D-041
  real-file evidence does not validate the new physical TCP geometry.
  Hardware direction/geometry acceptance remains pending.
  Subsequent comparison: the user reports changing only co2 axes; old/new
  translations retain length 210.874295 mm but their difference is
  161.909664 mm. A child-axis rotation alone cannot change translation in an
  unchanged parent frame with the same child origin. CAD origin/parent/export
  definitions need checking; numerical file consistency does not prove them.
  Config remains the user-requested latest source; no further correction or
  live hardware update has been made.

- **Post-processing target (D-041):** Active focus is
  [raw-to-dataset](docs/project/tasks/active/raw-to-dataset.md). Preserve all
  acquisition code/configuration and raw files. User specifies wrist + left
  images, current relative TCP pose as state, next relative TCP pose as action,
  and three occurrences per 30 fps image to accompany 90 Hz pose. The user
  confirms the timeline and retains XYZ + XYZW (seven stored values) for both
  state/action, superseding the six-value proposal. The raw reference is each
  episode's first saved TCP pose, including
  pose-only pre-roll (D-038). Source inspection confirms XYZ + XYZW quaternion
  `PoseStamped`; keep normalized, temporally sign-continuous quaternions.
  URDF IK is deferred. User requests modules implemented separately and joined
  in `build_dataset` last. Standalone 90 Hz expansion and local transformation
  are complete; state-action/export/integration remain subsequent steps. The
  user explicitly requests no state/action in the localization step.
  Existing dataset exporters still use single-image, 7D/no-action
  transformed v1; final training dataset acceptance is pending.

- **Local-pose stage (D-041):** `local_pose.py` reuses existing fixed-frame
  math and maintains normalized, continuous quaternion signs;
  `localize_session` reads the carried first raw TCP reference for each
  episode and writes the distinct local-pose contract. 23 new tests pass;
  full suite 185 passed, 2 skipped, 2 pre-existing missing-h5py failures.
  Build, touched-file flake8, installed CLI help and diff checks pass. Both
  localization modules import in the LeRobot venv without ROS. Existing real
  expanded episode has all
  3234 pose queries localized, retaining 3138 valid / 96 invalid image
  samples. Reference agrees with the first MCAP TCP message; independent
  rotation matrices and inverse world-coordinate roundtrips agree within
  2.23e-16. All 24 raw and four expansion file hashes/lists are unchanged.
  Evidence: `docs/project/reports/local-pose-20261002.json`; output:
  `/tmp/umi_local_pose_validation_20261002`. No state/action, hardware run,
  calibration rerun, legacy transform/export modification or build integration.
  Operator coordinate-frame acceptance remains pending.

- **90 Hz expansion (D-041):** `frame_expansion.py` implements NumPy-only
  pairing/tripling/interpolation; `expand_session` reads accepted per-camera
  results, actual PTS and one pose bag, then writes the independent contract
  above. 24 new tests pass; full suite 162 passed, 2 skipped, 2 pre-existing
  missing-h5py failures. Build, touched-file flake8, CLI help and diff checks
  pass; algorithm imports in the LeRobot venv without ROS. Real session
  `online_session_20260930_212318_104281`: 3234 candidate samples, 3138 valid
  (1046 groups, 97.0315%), 96 invalid retained; all pose queries are valid.
  Source wrist/left has 1080/1081 frames, each selected frame appears exactly
  three times, with 34/35 unused frames reported. All 24 source-file hashes
  and their file list are unchanged. Evidence:
  `docs/project/reports/expansion90-20261002.json`; scratch output:
  `/tmp/umi_expansion90_validation_20261002`. No capture code, calibration
  estimate, old algorithm or exporter was modified by this step.

- **Manual alignment viewer (D-040):** `frame_alignment_viewer [input]`
  reads MP4/MCAP directly, defaulting to the newest local session and its first
  episode. Space/Right/Left, buttons and a seek bar change the exact primary
  frame; recording/camera selection and raw/corrected comparison are available.
  Every primary image uses actual PTS + receipt anchor + accepted camera
  offset to interpolate pose in the fixed recording-start TCP frame. The
  second image is nearest in corrected time, has a reported delta and its own
  pose marker. A single local redraw updates images, XYZ cursor, path and
  orientation axes. No ROS publishers or camera devices are used. Uncovered
  frames/poses remain invalid instead of clamping. Current real session
  `online_session_20260930_212318_104281` has 1080 wrist / 1081 left episode
  images, all with valid corrected pose queries; accepted offsets are
  -112.143/-6.703 ms. Both calibration clips also load (987/1325 frames).
  Five alignment tests pass; full suite 138 passed, 2 skipped, 2 existing
  missing-h5py failures. Build, touched-file flake8 and diff checks pass.
  Real frame seek/back roundtrips and GUI redraw/recording switch were checked;
  rendered artifact `/tmp/umi_frame_viewer_108.png` was visually inspected.
  Keyboard steps on canvas/slider/button each advance exactly once. The
  installed viewer is open on this session's first episode for the operator;
  close its window to exit. Operator alignment judgment is pending; raw data
  is unchanged.
- **RGB endpoint selection (D-039):** The D435i by-id `video-index0` alias
  can select Z16 depth instead of color. `RealSenseSource` now resolves serial
  `254343064631`, USB interface `03`, V4L2 index `0` from sysfs; numeric video
  nodes and USB port may change. Explicit `left_video_device` overrides bypass
  discovery, as do synthetic sources. Missing/ambiguous RGB fails clearly.
  Full pytest: 133 passed, 2 skipped, 2 existing missing-h5py failures; build,
  touched-file flake8 and diff checks pass. A real dual-camera launch completed
  warmup without errors; its temporary diagnostic process was stopped to free
  both cameras. The user confirmed their own launch now runs. This verifies
  startup, not a newly recorded episode or source completeness.
- **Recording-start frame (D-038):** Calibration v4 converts world TCP poses
  with the first pose saved after the start command, before the 500 ms image
  delay: `T_start_i = inverse(T_world_start) * T_world_i`. Its fixed axes use
  the initial orientation. Only local XYZ enters matching; orientation motion
  is not a feature. Results identify the reference pose and its header time.
  Alignment now carries this reference into dataset transformation; the first
  image pose can be nonzero. Older aligned outputs read their source MCAP if
  available, otherwise identify the legacy first-image reference explicitly.
  Raw world pose/TF and existing calibration results are retained. Known-delay
  tests pass under 90-degree/arbitrary initial rotations and a 500 ms lead.
  Full pytest: 130 passed, 2 skipped, 2 existing missing-h5py failures; build,
  touched-file flake8 and diff checks pass. Real v4 calibration is pending.
- **Calibrated RViz review (D-037):** `replay.launch.py` now plays both recorded
  camera videos when present. With `use_calibration:=true`, it requires each
  camera's accepted session offset and publishes frames at first receipt +
  actual MP4 PTS + that offset on rosbag `/clock`; `loop:=true` repeats a short
  episode. The RViz config displays two images, current TCP pose and path.
  The user's `online_session_20260930_193959_496910/episode_0001` launched
  successfully: 99/99 image frames published per loop, accepted offsets
  -93.77/-10.07 ms, `/vive/pose` and `/vive/path` published in `vive_world`.
  Twelve focused tests, flake8 and build passed. Raw files are unchanged;
  visual alignment review by the user is pending.
- **Per-camera calibration (D-036):** `c` lists registered cameras with
  numbers and starts only the chosen camera plus pose. Other cameras keep
  previewing; ordinary episodes still record all streams. Stop immediately
  runs the translation-only estimator in the D-038 recording-start frame; returns green
  `accept` or red `reject`. Reject deletes the attempt's video/timing/validation,
  pose and derived results while preserving the directory. Enter retries the
  same camera/path, `c` reselects; registration replaces that path's old entry.
  Only that camera's result is invalidated. Preserve absolute pose headers
  and first image receipt + PTS: the 500 ms lead is a buffer, never a forced
  latency correction. CLI supports `--camera-id` and infers single-camera
  recordings; raw session copying supports left-only calibration. Legacy
  default calibration selection remains wrist; replay handles left-only
  input and skips indexed rejected folders. Multi-view alignment/export is
  subsequent work. Build/flake8 and focused tests passed; known-delay tests
  using real MCAP and synthetic image features recover -137.4/+127.4 ms with
  a 500 ms lead and varying, unused orientations (within 4 ms of the known
  values). Full pytest: 125 passed, 2 skipped, 2 existing missing-h5py failures;
  touched-file flake8, colcon build and `git diff --check` passed.
  Real per-camera motion,
  marker visibility, repeated latency estimates and live retry remain hardware
  acceptance; existing user recordings were not changed.
- **Independent live path (D-034):** `VivePoseNode` now publishes only TCP
  pose and both TFs. `VivePathNode` runs in a separate process, caches the
  latest pose via best-effort depth-one subscription, and samples/appends/
  publishes at a 30 Hz timer. Receipt callbacks do not assemble history;
  30 Hz describes display sampling, not DDS arrival rate. No new pose means
  no duplicate point/publication. Source headers/coordinates are retained;
  frame changes clear history. The existing 10,000-point cap and topic remain.
  `config/vive.yaml` has separate pose/path node blocks; `path_topic`,
  `max_path_points` and `sample_hz: 30.0` belong to the path node. `vive`,
  `online_view` and `online_record` launch both independent processes.
  Recording still saves full-rate pose/TF and retains the 500 ms image lead.
  Build, touched-file flake8, 22 focused tests and `git diff --check` passed;
  full pytest: 101 passed, 2 skipped, 2 existing HDF5 failures (missing
  `h5py`). A 12 s saturated-path software probe (10,000 points, real DDS,
  C++ Path subscriber, fake Tracker, separate processes/domain) measured
  pose 90.002 Hz, max gap 11.915 ms, Path publication/receipt about 29.916 Hz.
  Report: `/tmp/umi_vive_path_separation_probe_cpp_20260930.json`.
  Three short real Tracker/dual-camera episodes are now checked below;
  longer recordings and actual Path frequency/RViz rendering remain open.
- **Three-episode hardware check after D-034 (2026-09-30):** User session
  `online_session_20260930_160029_092182` and all three episodes are complete.
  Launch logs confirm separate real Vive pose and 30 Hz Path processes,
  both cleanly exiting. Pose counts are 1,988/1,342/1,240; average rates
  89.774/89.799/89.856 Hz, max gaps 22.313/22.210/22.380 ms. Five-second
  windows stay around 89.398–90.009 Hz without the earlier progressive
  decline to 52 Hz. There are 5/3/2 double-period gaps over 16.667 ms,
  suggesting isolated missing updates at nominal 90 Hz, with no gap over
  100 ms. Their origin and physical loss count are not established. Pose/TF
  counts and header stamps match; all pose values are finite and timestamps
  increase. Six videos decode and match accepted counts: wrist/left
  585/583, 391/391, 357/355 frames; effective rates 29.971–29.979 fps;
  max gaps wrist 40.000/40.666/39.000 ms, left 33.667/34.000/33.667 ms.
  No video interval exceeds 50 ms. Every saved image falls within pose's
  header range using `first_receive_unix_ns + PTS`; image leads from first
  saved pose are 550.50–655.26 ms, with tails 1.30–2.12 s. This passes the
  500 ms raw host-time lead and coverage checks; the session remains
  `not_calibrated` and camera-source completeness `not_verified`.
  This was a one-time check; subsequent D-035 adds automatic episode QC.
  Analysis took about 1.99 s excluding preparation/reporting. Report, JSON
  and rerunnable unexecuted companion notebook are under
  `docs/project/reports/raw-recording-check-20260930-160029.*`.
- **Pose lead (D-033):** Each episode/calibration start saves pose first,
  confirms `recording_ready`, then waits the fixed
  `IMAGE_RECORDING_DELAY_SECONDS = 0.5` before starting both cameras. Pose
  keeps recording in its worker during this delay. Actual first-frame lead
  can exceed 500 ms due to readiness polling and camera/encoder startup.
  Ordering and missing-first-pose tests pass. Two real episodes in
  `online_session_20260930_145919_328592` have wrist/left leads of
  584.85/601.23 ms and 586.49/613.42 ms from first pose bag timestamp to
  first image receipt, passing hardware acceptance. Per-recording frame-gap
  statistics, colored verdicts and JSON dataset exclusion markers are now
  implemented under D-035 below.
- **Two-episode hardware check (2026-09-30):** The above session is complete;
  both episodes have correct `cameras/wrist/`, `cameras/left/`, timing,
  validation and `image_streams` mappings. All four MP4s decode without errors
  and match accepted counts: episode 0001 wrist/left 576/574 frames,
  29.962/29.979 fps, max gaps 44.67/33.67 ms; episode 0002 693/691 frames,
  29.971/29.979 fps, max gaps 40.67/33.67 ms. No interval exceeds 50 ms.
  Pose has 1954 and 1358 samples, covering both camera ranges with about
  2.0 and 2.5 s tail. Pose average frequency changed from 89.73 Hz to
  51.90 Hz; second-episode five-second windows fall from 55.14 to 47.86 Hz,
  while the maximum gap stays below 22.69 ms. The diagnosis below identifies
  accumulating path publication as the high-confidence main bottleneck;
  D-034 has removed that callback work, and the three short user episodes
  above do not reproduce this decline. Longer recording acceptance remains
  open. D-035 subsequently adds per-episode acceptance diagnostics.
- **Pose slowdown diagnosis before D-034 (2026-09-30):** The old
  `VivePoseNode._publish_pose` published pose, the entire accumulated Path,
  then TF in one callback. Its
  10,000-point path persists and grows during recording and waiting; episode
  finalization only closes per-recording files. The first episode finishes
  about 48 s before the second begins; synchronous video validation has
  already finished. Actual episode 0002 pose receive/write lag has median
  0.423 ms, but corresponding TF lag is 19.384 ms and correlates with the
  next pose gap at 0.9957. Isolated execution of the unmodified node with a
  fake backend and real ROS publishers (TF enabled, no RViz/cameras) measures
  callback medians of 11.34/18.04/22.24 ms at 5,000/8,000/10,000 initial path
  points, exceeding the 11.11 ms budget for 90 Hz. At 7,000 initial points,
  a four-second executor comparison gives 61.47 Hz with path publication and
  89.98 Hz when only that publication is suppressed. This is publisher-side
  slowing, with no evidence of an MCAP writer backlog. D-034 implements path
  decoupling and lower-rate visualization; three short real episodes pass
  the rate/coverage retest above, with longer recordings still unverified.
  Diagnostic script/report: `/tmp/umi_pose_slowdown_diagnostic.py` and
  `/tmp/umi_pose_slowdown_diagnostic_20260930.json`; raw data untouched.
- **Automatic episode diagnostics (D-035, supersedes D-032):** After both
  MP4s and MCAP close, reuse each video's existing ffprobe pass and scan pose
  once. Accept only when both videos decode with matching accepted counts,
  complete increasing PTS and no gap over 50 ms, pose covers both raw host-time
  image ranges, and average pose rate is at least 88 Hz. Isolated pose gaps
  alone do not reject. Print green `accept` or red `reject` in launch and
  keyboard terminals, with short image/pose gap status or rejection reasons;
  save `quality.json` with `exclude_from_dataset`. Completion status remains
  separate, and rejected quality does not prevent the next episode. No new
  launch arguments, workers or changes to calibration. Dataset export does
  not yet enforce this marker. Build, flake8 and 19 focused tests passed;
  full pytest: 115 passed, 2 skipped, 2 existing missing-h5py failures.
  Read-only checks of four real episodes/eight MP4s plus MCAP took 6.511 s:
  all three latest episodes accept, the old 51.899 Hz second episode rejects.
  Automatic end-of-recording orchestration is software verified; a new live
  recording with this version remains hardware acceptance.
- **Dual camera acquisition (2026-09-30):** D-027–D-030 define the common
  `CameraSource` interface, per-stream IDs/fields, online dual recording and
  replacement of D435 with D435i. Action 4 uses `wrist` / `wrist_image`, D435i
  color uses `left` / `left_image`; depth and IR are unused. Both launch files
  enable two low-resolution ROS/RViz previews, while recording separate MP4s
  and timing/validation files against one pose bag. Action 4 uses a by-id link;
  D435i uses serial + RGB interface discovery under D-039 because its by-id
  index is ambiguous. In the latest check D435i color is `/dev/video4` at
  USB 3 (5000M), Action 4 is `/dev/video8`; these numbers may change.
  Direct D435i V4L2 capture delivered ten frames. A complete
  `online_record` run with both real cameras and synthetic `/vive/pose` yielded
  two valid 78-frame H.264 MP4s, both preview topics and a complete session
  index. Real Vive pose was absent in the earlier hardware run; one subsequent
  user-recorded episode contains all three real streams, as described below.
  Calibration now processes each selected camera; replay resolves a
  single-camera recording, while dataset export still processes wrist. See
  `tasks/active/multi-camera-acquisition.md`.
- **Symmetric raw camera layout (2026-09-30):** D-031 puts new wrist files
  under `cameras/wrist/`. `session/layout.py` resolves the new path before
  legacy root wrist files; calibration, replay, alignment, and raw calibration
  copying use that resolver or copy the `cameras/` tree. The user-recorded
  `online_session_20260930_133225_127556/episode_0001` was migrated without
  changing MP4 bytes or pose. Its recording-level `image_streams` and wrist
  timing self-path now point at `cameras/wrist/`.
- **Real dual-camera episode check (2026-09-30):** In
  `recordings/online_session_20260930_133225_127556/episodes/episode_0001`,
  the MCAP contains 2053 real `/vive/pose` messages from 13:32:44.310 to
  13:33:07.199 CST, with maximum header-stamp gap 22.50 ms. Decoded wrist
  video has 612 frames (29.970 fps from PTS, maximum gap 41.33 ms); decoded
  left video has 613 frames (29.978 fps, maximum gap 33.67 ms). Neither MP4
  has a PTS interval over 50 ms, and decoded counts match worker accepted
  counts. All frames fall between first and last pose header stamps when each
  MP4 PTS is anchored at `first_receive_unix_ns`; the pose lead at the first
  wrist/left frame is only 73.33/80.86 ms. This session is `not_calibrated`:
  exposure-time alignment and coverage after per-camera offset correction are
  unverified. Capture-side dropped frames cannot be ruled out by MP4 PTS.
- **Latest verification (pose lead):** colcon build passed; start-sequence
  tests for both recording kinds and missing first pose passed; full pytest:
  93 passed, 2 skipped, 2 existing HDF5 failures from missing `h5py` in `.venv`;
  touched-file flake8 and `git diff --check` passed. The migrated real episode
  resolves in replay and
  alignment, has unchanged wrist MP4 SHA-256 and still decodes 612 wrist /
  613 left frames with 2053 Vive poses. The earlier two-camera hardware
  integration run used synthetic pose as stated above.
- **Action 4 verification (2026-09-30):** colcon build passed; focused camera,
  launch and session tests passed (22/22); synthetic Action 4 worker recorded
  33 frames and delivered timestamped previews; full pytest: 82 passed,
  2 skipped, 2 failed because `.venv` lacks `h5py` for unrelated HDF5 tests.
- **Live preview diagnostic (2026-09-30):** The initial `online_view` run had
  an RViz futex exit while the Action 4 worker stayed in `warming_up`. Direct
  GStreamer and V4L2 reads of `/dev/video2` yielded zero frames at MJPEG
  1080p and 720p. After the user re-entered Webcam mode, the real Action 4
  delivered continuous preview frames, completed warmup in about five seconds,
  and its ROS node published five valid 640×360 BGR8 Images on
  `/action4/image_preview`. A complete `online_view` run kept RViz alive for
  15 seconds and completed camera warmup; the configured image topic and QoS
  match. The user then confirmed that the RViz preview works. RViz threw
  `std::system_error` only during the forced SIGINT shutdown. The worker
  now warns when no first frame arrives after five seconds and gives a
  specific no-frame timeout error.

- **Previous verification (2026-09-29):** colcon build passed; temporal
  alignment tests passed (6/6); the missing-`ffprobe` feedback test passed;
  full pytest collected 84 tests (80 passed, 2 skipped, 2 failed because this
  checkout's Python environment lacks `h5py` for HDF5 export tests);
  touched-file flake8 and `git diff --check` passed at that point. Subsequent
  real calibrations have accepted estimates; repeatability and downstream
  episode processing still need hardware acceptance.
- **Software-verified end to end:**
  - `n` switching, with the real node, both workers, `videotestsrc` and a
    synthetic `/vive/pose`.
  - `build_dataset --format both` on two scratch sessions built from the real
    accepted calibration recording (1080p, -95.01 ms offset). This gave
    2 × 1332 frames; LeRobot 0.4.4 reload is correct.
- **Real data in `recordings/`:** `online_session_20260929_171213_710643`
  was rejected for window offsets -61.75/-105.41 ms (21.83 ms standard
  deviation, above 20 ms). `online_session_20260929_174955_015048` was
  accepted at -83.71 ms, with 1302/1356 marker detections and 1.80 ms window
  standard deviation. `online_session_20260929_175149_425293` was rejected
  before matching because marker ID 4 appeared in only 644/1338 frames
  (48.1%, below 60%); the gripper obscures the marker's lower edge/corners in
  sampled frames near the start and end. In
  `online_session_20260929_175651_544205`, calibration_001 failed the same
  detection-ratio check but calibration_002 was accepted at -91.45 ms with
  1613/1648 detections and 2.37 ms window standard deviation. Two intervening
  sessions remain `not_calibrated`. The old -95.01 ms result was from the
  previous estimator and is not in the current `recordings/` tree.
- **Hardware acceptance is still open** for the items in the `project.md`
  checklist.

## Open issues

- The second episode of `online_session_20260930_145919_328592` has pose
  frequency around 52 Hz despite the nominal 90 Hz publish timer, with gradual
  decline across the recording. There are no long timestamp gaps or non-finite
  poses in this check. Accumulated Path publication in the same callback is
  the high-confidence main bottleneck, reproduced in an isolated synthetic
  test. D-034 removes it and passes saturated-path software verification;
  the three short real episodes above maintain about 90 Hz. They still have
  5/3/2 isolated approximately 22 ms gaps, whose origin is unverified.
  Longer recordings and actual Path/RViz performance remain open.
- Ctrl+C on the Vive launch ends with a `KeyboardInterrupt` inside
  `backend.stop()` / `simple_close`. This predates D-022 and was flagged as a
  separate task.
- A session switch copies synchronously in the service callback, so preview
  pauses during a large copy.
- Live extrinsic updates set translation and rotation separately, so for about
  one frame only one of them is new. Do not adjust while recording.
- Immediate translation-only calibration has produced accepted real recordings;
  repeatability across launches and downstream real-episode acceptance remain
  open.
- On 2026-09-29, `online_record` exited at startup because the generated
  `vive_pose_node` used `/usr/bin/python3`, which could not import `pysurvive`
  from `.venv`. Rebuilding with `.venv/bin/python -m colcon` regenerated the
  Vive, camera and keyboard entry points with `.venv/bin/python` shebangs.
  Python and ROS imports were checked. A later hardware session reached a
  complete calibration recording.
- The first live calibration in `online_session_20260929_165924_452278`
  saved MP4 and MCAP but analysis failed because `ffprobe` is absent from the
  host at that time. `video.validation.json` recorded the missing tool, not a
  proven decoding failure. FFmpeg has since been installed; the next hardware
  session completed analysis. Hardware acceptance is still open.
- A later recording in `online_session_20260929_171213_710643` ran with
  `ffprobe` available. It detected 971/993 marker frames and 0.45 m TCP motion;
  only the per-window consistency criterion failed. The third window yielded
  no agreeing motion-channel offsets. This is a quality rejection, not an
  environment failure; thresholds still need repeated hardware evidence.
- A later accepted retry left an earlier failure's `error` string in
  `session.yaml`. D-026 makes completed estimates replace prior result fields;
  the accepted session's stale error was removed without changing raw data.
