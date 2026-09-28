# UMI — Coding context

Entry point for anyone about to change code. It describes the **current** state
only. History is in git, rationale in
[DECISIONS.md](docs/project/DECISIONS.md), and the user-facing board in
[project.md](project.md).

- **Last synchronized:** 2026-09-28
- **Branch:** `feature/multi-task-sessions` (not merged, not pushed). It holds
  the D-021 multi-task-session work and the D-022 simplification.

## Where things are

| Document | Use |
| --- | --- |
| [project.md](project.md) | Progress board, capabilities, acceptance checklist |
| [README.md](README.md) | Operator setup and step-by-step use (Chinese) |
| [REQUIREMENTS.md](docs/project/REQUIREMENTS.md) | Confirmed scope |
| [ARCHITECTURE.md](docs/project/ARCHITECTURE.md) | Current structure and data flow |
| [DECISIONS.md](docs/project/DECISIONS.md) | Decisions with a status index (D-001…D-022) |
| [tasks/active/](docs/project/tasks/active/) | `multi-task-sessions`, `temporal-calibration`, `urdf-path-diagnostic` |
| [tasks/archive/](docs/project/tasks/archive/) | Completed tasks with their original evidence |

## Environment

- Ubuntu 24.04, ROS 2 Jazzy, `/home/xing/umi_ros_venv` (system site packages,
  `setuptools==68.1.2`). Source ROS under **bash**: sourcing
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
| Vive | `vive/backend.py`, `vive/pose_node.py`, `vive/pose_recording_worker.py` | Backend has no ROS. The pose node publishes the TCP pose, path and both TFs. Extrinsic parameters `tracker_to_tcp_translation_m` / `_rotation_xyzw` exist **only** in `config/vive.yaml`, have no default, are validated at startup, and accept live `ros2 param set` updates |
| Camera | `camera/h264_capture_node.py`, `capture_worker.py`, `capture_pipeline.py`, `episode_keyboard.py` | Node owns the GStreamer worker and the pose worker. Services `~/start_episode`, `~/start_calibration`, `~/stop_episode`, `~/new_session`; parameters `task`, `next_task` |
| Session | `session/layout.py`, `session/set_session_task.py` | Only writer of `session.yaml` (atomic replace). Schema v2; v1 readable. Also `copy_calibration_raw`, `switch_session`, `latest_calibration` |
| Calibration | `synchronization/calibrate_time.py`, `temporal_alignment.py`, `generate_marker.py` | ArUco DICT_4X4_50 id 4; multi-feature offset. Writes `time_offset.json` and updates `session.yaml` |
| Post-processing | `postprocess/align_session.py`, `transform_session.py`, `dataset_plan.py`, `export_hdf5.py`, `export_lerobot.py`, `build_dataset.py` (+ `pose_io`, `alignment`, `episode_transform`) | Plain Python, no ROS graph. `dataset_plan` and `common/` must stay importable from the LeRobot venv (NumPy only) |
| Replay | `visualization/session_replay_node.py`, `replay_source.py`, `replay_path_node.py` | Does not apply the time offset |
| Shared | `common/ordering.py` | `natural_key` |

Launch files: `online_record`, `online_view`, `replay`, `vive`, `camera`,
`urdf_path_diagnostic`. Console entry points: `vive_pose_node`,
`h264_capture_node`, `episode_keyboard`, `set_session_task`,
`calibrate_time`, `generate_aruco_marker`, `align_session`,
`transform_session`, `export_hdf5`, `export_lerobot`, `build_dataset`,
`session_replay_node`, `replay_path_node`.

## Contracts to keep

- **Session** (`online_session_<time>/`): `session.yaml` schema v2 with a
  top-level `task` (the only task used by export), `status`, `recordings[]`
  (each with a `task` snapshot and optional provenance-only `copied_from`) and
  `temporal_calibration`. The directory name never contains the task.
  Unknown schema versions are rejected.
- **Recording** (`calibration/calibration_<nnn>/`, `episodes/episode_<nnnn>/`):
  `video.mp4`, `video.timing.json` (`first_receive_unix_ns`, source PTS),
  `video.validation.json` (`source_completeness: not_verified`), `pose/` MCAP
  with `/vive/pose`, `/tf`, `/tf_static`. The pose MCAP opens before the MP4 and
  closes after it.
- **Session switch** (`n`): refused while recording. Only complete
  calibrations are copied, and only their raw files, staged as hidden
  `.calibration_<n>.partial`. It is all-or-nothing. Episodes renumber from
  0001; calibrations continue after the highest copy.
- **Offset convention:** `pose_time = video_time + video_to_pose_offset_seconds`.
  One constant per session.
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

## Current state (2026-09-28)

- **Tests:** 84 pytest pass.
- **Software-verified end to end:**
  - `n` switching, with the real node, both workers, `videotestsrc` and a
    synthetic `/vive/pose`.
  - `build_dataset --format both` on two scratch sessions built from the real
    accepted calibration recording (1080p, -95.01 ms offset). This gave
    2 × 1332 frames; LeRobot 0.4.4 reload is correct.
- **Real data in `recordings/`:** only `online_session_20260921_181056_923446`,
  with one accepted calibration and no episodes. It is still v1 and has no
  task.
- **Hardware acceptance is still open** for the items in the `project.md`
  checklist.

## Open issues

- Ctrl+C on the Vive launch ends with a `KeyboardInterrupt` inside
  `backend.stop()` / `simple_close`. This predates D-022 and was flagged as a
  separate task.
- A session switch copies synchronously in the service callback, so preview
  pauses during a large copy.
- Live extrinsic updates set translation and rotation separately, so for about
  one frame only one of them is new. Do not adjust while recording.
