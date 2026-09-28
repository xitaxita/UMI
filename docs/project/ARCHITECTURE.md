# UMI — Architecture

This document describes the current system only. Why each choice was made is in
[DECISIONS.md](DECISIONS.md); history is in git.

## Overview

A DJI Action 4 and a Vive Tracker are rigidly mounted on one gripper. Online
acquisition (the only mode, D-021) records each demonstration as an MP4 plus an
independent Vive pose MCAP. Post-processing, which is plain Python and not ROS
nodes (D-017, D-019), estimates the video-to-pose time offset, gives every video
frame a pose, rebases poses to the episode start, and exports HDF5 and/or
LeRobot v3 datasets from one or more single-task sessions.

```text
 Acquisition (ROS 2, online_record.launch.py)
 ─────────────────────────────────────────────────────────────────────────
 Vive ─ libsurvive ─ vive_pose_node ──/vive/pose, /vive/path, /tf──▶ RViz
                         │ (Tracker pose ∘ Tracker→TCP extrinsic, vive.yaml)
                         ▼
 Action 4 ─UVC MJPEG─▶ capture_worker (GStreamer) ──preview──▶ h264_capture_node ─▶ RViz
                         │ H.264 MP4                     │ services: start/stop,
                         ▼                               │ start_calibration, new_session
                    video.mp4 + timing/validation        │
                                                         ▼
 /vive/pose,/tf ─▶ pose_recording_worker ─▶ pose/ (MCAP)   episode_keyboard (Enter, c, n)

 recordings/online_session_<time>/ {session.yaml, calibration/, episodes/}

 Post-processing (plain Python, build_dataset)
 ─────────────────────────────────────────────────────────────────────────
 per session: calibrate_time ─▶ align_session ─▶ transform_session
                (offset)          (world pose       (episode-start
                                   per MP4 frame)     coordinates)
 all sessions: dataset_plan (episode → task, source) ─▶ export_hdf5
                                                     └▶ export_lerobot (separate venv)
```

## Acquisition runtime

- `vive_pose_node` reads the selected Tracker through pysurvive (no SteamVR,
  D-001), reorders quaternions to ROS XYZW, composes the Tracker pose with the
  Tracker→TCP extrinsic, and publishes `/vive/pose` and a bounded `/vive/path`
  (both the TCP) plus TF `vive_world→vive_tracker` and `vive_world→gripper_tcp`.
  The extrinsic exists only in `config/vive.yaml`; it is validated at startup
  and can be updated live through ROS parameters (D-020, D-022).
- `h264_capture_node` owns two long-lived child processes, each started and
  warmed once per launch (D-012, D-018):
  - `camera/capture_worker.py`: GStreamer UVC MJPEG 1920×1080/30 → tee → a
    leaky preview branch (640×360 BGR on stdout → `/action4/image_preview`)
    and, while recording, a non-leaky branch encoded with x264 into MP4 (D-011).
  - `vive/pose_recording_worker.py`: keeps `/vive/pose`, `/tf` and
    `/tf_static` subscriptions and writes one MCAP per recording.
- A recording opens its pose MCAP first and starts the MP4 only after the first
  pose is written. Stop finalizes the MP4, writes `video.timing.json` and
  `video.validation.json`, and then closes the MCAP. Workers return to
  waiting and are never restarted between recordings or sessions.
- Worker status files live in a per-launch temp directory, not in a session.
- `episode_keyboard` is a separate service client: Enter starts or stops an
  episode, `c` starts a calibration, and `n` switches to a new session with a
  new task. A switch copies the previous session's completed raw calibrations
  and is refused while recording (D-021).
- `replay.launch.py` replays a session or one recording: `session_replay_node`
  decodes MP4 to the preview topic against rosbag `/clock`, and
  `replay_path_node` rebuilds `/vive/path` (D-016). Replay does not apply the
  time offset.

## Session layout

```text
recordings/online_session_<time>/          # one session = one task (D-021)
├── session.yaml                          # schema v2: task, status, recordings, temporal_calibration
├── calibration/calibration_<nnn>/        # video.mp4, video.timing.json, video.validation.json, pose/
│                                         # + time_offset.json, alignment_report.png after calibrate_time
└── episodes/episode_<nnnn>/              # video.mp4, video.timing.json, video.validation.json, pose/
```

`session/layout.py` is the only code that writes `session.yaml`, always with an
atomic replace. Raw recordings are never modified by post-processing, except
that `calibrate_time` records its result in `session.yaml`.

## Post-processing pipeline

| Stage | Module | Input → output |
| --- | --- | --- |
| Temporal calibration | `synchronization/calibrate_time.py` | one calibration recording → `time_offset.json`; ArUco + TCP multi-feature matching (D-014) |
| Alignment | `postprocess/align_session.py` (`pose_io`, `alignment`) | session + accepted offset → `aligned_frames.npz` per episode (world frame, PTS-based, SLERP, invalid outside coverage) |
| Episode transform | `postprocess/transform_session.py` (`episode_transform`) | aligned → `episode_frames.npz` (contract v1), `T_episode = T_ref⁻¹ · T_world` |
| Plan | `postprocess/dataset_plan.py` | transformed episodes → ordered list with task, source session and offset |
| Export | `postprocess/export_hdf5.py`, `postprocess/export_lerobot.py` | plan → HDF5 format v2 / LeRobot v3 (per-frame `umi.source_session`, no `action`) |
| Orchestration | `postprocess/build_dataset.py` | sessions → `<out>/{processed/, dataset.hdf5, lerobot/, build_manifest.json}` |

Stages communicate only through versioned files, so each stage can be run
alone or replaced. `build_dataset` holds no algorithms. It runs each session
separately, checks task, calibration, episodes, alignment, image size, frame
rate and contract version for the whole build, and swaps a finished
`<out>.partial` into place. LeRobot runs in `~/umi_lerobot_venv312`. The ROS
venv must not import it (D-019).

## Package map (`umi_ros2`, ament_python)

| Path | Responsibility |
| --- | --- |
| `umi_ros2/vive/` | pysurvive backend (no ROS), pose node, persistent pose recorder |
| `umi_ros2/camera/` | capture node, GStreamer worker and pipeline, keyboard client |
| `umi_ros2/session/` | session layout, calibration copy/switch, `set_session_task` |
| `umi_ros2/synchronization/` | ArUco marker generation, temporal calibration |
| `umi_ros2/postprocess/` | alignment, transform, plan, exporters, `build_dataset` |
| `umi_ros2/visualization/` | session replay and replay path |
| `umi_ros2/common/` | small ROS-free helpers shared by both venvs |
| `launch/` | `online_record`, `online_view`, `replay`, `vive`, `camera`, `urdf_path_diagnostic` |
| `config/` | `vive.yaml` (device, frames, extrinsic), `action4.yaml` (camera) |
| `rviz/` | `online.rviz`, `urdf_path_diagnostic.rviz` |
| `test/` | unit, contract and in-process integration tests (pytest) |

## Rules

- Only components that continuously take part in ROS communication are ROS
  nodes. One-shot processing is a plain CLI that needs no running ROS graph.
  Reading MCAP still uses ROS Python message libraries.
- The pysurvive backend and ROS-free helpers do not import ROS. Launch and
  config files hold deployment defaults, not logic.
- `/vive/path` is visualization only and is never recorded.
- Build and runtime use ROS 2 Jazzy with `~/umi_ros_venv` (`setuptools==68.1.2`,
  D-005).

## Known limitations

- Time offset is one constant per session. There is no drift model, hardware
  trigger or exposure timing, and no camera intrinsics or camera-to-Tracker
  extrinsic.
- Recording guards against deliberate drops but does not prove source
  completeness (`source_completeness: not_verified`).
- `/vive/path` republishes up to 10,000 poses at the pose rate. It has no
  tracking-quality topic or covariance.
- A session switch copies calibration synchronously inside the camera node's
  service call, so the preview pauses during a large copy.
