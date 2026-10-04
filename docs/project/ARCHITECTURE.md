# UMI — Architecture

This document describes the current system only. Why each choice was made is in
[DECISIONS.md](DECISIONS.md); history is in git.

## Overview

A DJI Action 4 and a Vive Tracker are rigidly mounted on one gripper; a D435i
provides a left color view. Online acquisition (the only mode, D-021) records
each demonstration as two separate MP4 files plus one Vive pose MCAP.
Post-processing currently uses the wrist MP4 only. It estimates that video's
offset to pose, assigns pose to frames, rebases pose to the episode start, and
exports HDF5 and/or LeRobot v3 datasets from single-task sessions. Left-view
calibration and export are planned next.

```text
 Acquisition (ROS 2, online_record.launch.py)
 ─────────────────────────────────────────────────────────────────────────
 Vive ─ libsurvive ─ vive_pose_node ──/vive/pose, /tf (90 Hz)──▶ RViz
                         │ (Tracker pose ∘ Tracker→TCP extrinsic, vive.yaml)
                         └─/vive/pose─▶ vive_path_node (30 Hz) ─/vive/path─▶ RViz
 Action 4 ─UVC MJPEG─▶ capture_worker ─▶ Action4Source ─┐
                  └─▶ cameras/wrist/video.mp4 + metadata ├─▶ h264_capture_node ─▶ RViz (two previews)
 D435i ─UVC YUYV─▶ capture_worker ─▶ RealSenseSource ────┘       │ services: start/stop,
                  └─▶ cameras/left/video.mp4 + metadata          │ calibration, new_session
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

- `visualization/frame_alignment.py` and `frame_alignment_viewer.py` provide
  manual local inspection (D-040), independent of ROS topic replay. A Tk and
  Matplotlib window decodes selected MP4 frames, looks up actual frame PTS and
  accepted per-camera offsets, interpolates MCAP TCP poses in the fixed
  recording-start frame, and updates paired images/path/axes/XYZ in one draw.
  The secondary image is nearest in corrected time with an explicit delta and
  its own pose marker. No realtime clock, live camera or publisher is used.
- `vive_pose_node` reads the selected Tracker through pysurvive (no SteamVR,
  D-001), reorders quaternions to ROS XYZW, composes the Tracker pose with the
  Tracker→TCP extrinsic, and publishes `/vive/pose` (TCP) plus TF
  `vive_world→vive_tracker` and `vive_world→gripper_tcp` at the configured
  90 Hz timer. The acquisition callback does not assemble or publish Path.
  The extrinsic exists only in `config/vive.yaml`; it is validated at startup
  and can be updated live through ROS parameters (D-020, D-022).
- `vive_path_node` runs in a separate process alongside the pose source in
  `vive`, `online_view` and `online_record` (D-034). A best-effort depth-one
  subscriber caches only the latest `/vive/pose`; its 30 Hz timer appends one
  fresh sample and publishes a bounded `/vive/path`. Paused input does not
  add duplicate points; frame changes clear visualization history. Headers
  and TCP coordinates come from the sampled source pose. Path settings are
  in their own node block in `config/vive.yaml`; the cap stays 10,000 points.
  Whole-history publication occurs in this display process, independently of
  pose/TF publication and the full-rate raw recorder.
- `h264_capture_node` coordinates two required `CameraSource` implementations
  (`Action4Source` and `RealSenseSource`) and the pose recorder. Each camera
  owns a persistent GStreamer worker; both cameras and pose warm once per
  launch (D-012, D-018, D-029):
  - `camera/capture_worker.py`: Action 4 MJPEG 1920×1080/30 and D435i YUYV
    640×480/30 each use a disposable BGR preview branch (320×180 wrist,
    320×240 left at up to 10 Hz) and a separate H.264 MP4 recording branch.
    Preview `ImageFrame`s retain source PTS and host receive time.
  - `vive/pose_recording_worker.py`: keeps `/vive/pose`, `/tf` and
    `/tf_static` subscriptions and writes one MCAP per recording.
- A recording opens its pose MCAP first and starts its MP4 writers only after
  the first pose is written and a further 500 ms lead has elapsed (D-033).
  Stop finalizes and validates the selected videos before closing the MCAP.
  Ordinary episodes record both streams; D-036 calibrations record only the
  chosen camera. The node then runs `calibrate_time` immediately and returns
  green `accept` or red `reject`. A rejected calibration deletes its raw and
  derived files, preserves its directory and reserves it for the same camera's
  retry. Registration replaces the previous entry for that path. Each result
  is stored under `temporal_calibrations[camera_id]`, with the wrist result
  mirrored into singular `temporal_calibration` for existing consumers.
  Workers return to waiting and are never restarted between recordings or
  sessions.
- After an ordinary episode's MCAP closes, `camera/episode_quality.py` reuses
  saved video validations and reads pose headers once. D-035 gates acceptance
  on both images' frame counts/increasing PTS/no gap over 50 ms, full raw
  host-time pose coverage, and average pose rate at least 88 Hz. It writes
  `quality.json` and returns a colored verdict to launch/keyboard terminals.
  Quality rejection does not change successful file completion or block the
  next episode. Calibration follows its existing separate path.
- Action 4 is `wrist` / `wrist_image` and writes `cameras/wrist/video.*`;
  D435i color is `left` / `left_image` and writes `cameras/left/video.*`.
  Readers still accept historical root `video.*` wrist files. Their
  Action 4 configuration uses a serial-based V4L2 link. D435i selects its
  configured serial's RGB USB interface `03`, capture index `0`, through
  sysfs (D-039), avoiding an ambiguous by-id index shared with depth/IR;
  `video_device:=...` and `left_video_device:=...` can override them at launch.
  No depth or infrared stream is captured. Independent wrist/left-to-pose
  calibration is implemented; multi-image alignment/export remains planned.
- Worker status files live in a per-launch temp directory, not in a session.
- `episode_keyboard` is a separate service client: Enter starts or stops an
  episode, `c` lists numbered cameras then starts the selected calibration,
  and `n` switches to a new session with a
  new task. A switch copies the previous session's completed raw calibrations
  and is refused while recording (D-021).
- `replay.launch.py` replays a session or one recording: `session_replay_node`
  decodes every recorded camera MP4 to its preview topic against rosbag
  `/clock`, and `replay_path_node` rebuilds `/vive/path` (D-016). Optional
  `use_calibration:=true` applies each camera's accepted constant offset to
  its first-receipt-plus-PTS frame time; `loop:=true` repeats for review (D-037).
  Single-camera calibrations select their camera video automatically; session
  replay skips indexed rejected calibration folders with deleted inputs.

## Session layout

```text
recordings/online_session_<time>/          # one session = one task (D-021)
├── session.yaml                          # schema v2: task, recordings[].image_streams
├── calibration/calibration_<nnn>/        # cameras/<selected>/video.*, pose/
│                                         # + time_offset.json/report after accept
└── episodes/episode_<nnnn>/              # cameras/{wrist,left}/video.*, pose/, quality.json
```

`session/layout.py` is the only code that writes `session.yaml`, always with an
atomic replace. Raw recordings are never modified by post-processing, except
that `calibrate_time` records its result in `session.yaml`.

## Post-processing pipeline

| Stage | Module | Input → output |
| --- | --- | --- |
| Temporal calibration | `synchronization/calibrate_time.py` | ArUco centre/scale matched to XYZ in the fixed first-recorded TCP frame; initial orientation sets axes, no rotation motion features (D-038) |
| Alignment | `postprocess/align_session.py` (`pose_io`, `alignment`) | accepted offset → world frame poses interpolated at PTS queries, plus first-recorded TCP reference |
| 90 Hz expansion (standalone, D-041) | `postprocess/expand_session.py` (`frame_expansion`) | per-camera accepted offsets + actual PTS + raw pose → tripled image references and interpolated world XYZ/XYZW on a fixed 90 Hz clock; expansion contract v1 |
| Local poses (standalone, D-041) | `postprocess/localize_session.py` (`local_pose`, existing `episode_transform` math) | expansion v1 → local-pose v1, fixed first raw TCP reference, XYZ + normalized/sign-continuous XYZW; preserve world poses, clock, images and masks; no state/action |
| Episode transform | `postprocess/transform_session.py` (`episode_transform`) | aligned → `episode_frames.npz` (contract v1), `T_episode = T_start⁻¹ · T_world`; reference precedes images |
| Plan | `postprocess/dataset_plan.py` | transformed episodes → ordered list with task, source session and offset |
| Export | `postprocess/export_hdf5.py`, `postprocess/export_lerobot.py` | plan → HDF5 format v2 / LeRobot v3 (per-frame `umi.source_session`, no `action`) |
| Orchestration | `postprocess/build_dataset.py` | sessions → `<out>/{processed/, dataset.hdf5, lerobot/, build_manifest.json}` |

Stages communicate only through versioned files, so each stage can be run
alone or replaced. `build_dataset` holds no algorithms. It runs each session
separately, checks task, calibration, episodes, alignment, image size, frame
rate and contract version for the whole build, and swaps a finished
`<out>.partial` into place. LeRobot runs in `~/umi_lerobot_venv312`. The ROS
venv must not import it (D-019).

The D-041 expansion and local-pose stages are independently runnable and are
not yet part of `build_dataset`, legacy transformation or export. The
expansion NumPy algorithm pairs each
camera to the 30 Hz group-start subgrid (default tolerance 1/60 s), repeats
each selected source index three times and marks an entire group invalid when
image pairing or a pose query fails. Source images are selected at most once
per valid group sequence; unused raw frames are counted. Invalid clock slots
remain present. The file adapter carries the first raw TCP reference without
rebasing world poses or creating action. It writes `expanded_frames.npz`,
CSV and `expansion.json`, plus `expansion_summary.json` at the session output
root, without decoding/re-encoding images or rewriting calibration/raw files.

`localize_session` consumes this expansion contract for one episode or all
indexed session episodes. It requires each episode's carried first raw TCP
reference, never falling back to the first image or previous sample. The
initial position and orientation define fixed axes for every later pose.
All `pose_valid` queries are transformed, even when images are invalid;
invalid pose queries stay NaN. Source clock/image/mask arrays and world poses
are preserved, and each output XYZW quaternion is normalized with continuous
signs across successive valid queries. Outputs are `local_frames.npz`, CSV,
`local_pose.json` and CLI `local_pose_summary.json`; rejected expansion status
is retained separately. This stage does not read MP4/MCAP, generate
state/action, rerun calibration or change raw files.

## Package map (`umi_ros2`, ament_python)

| Path | Responsibility |
| --- | --- |
| `umi_ros2/vive/` | pysurvive backend (no ROS), pose node, separate live path node, persistent pose recorder |
| `umi_ros2/camera/` | ROS-free camera source interface, Action 4 adapter, GStreamer worker and pipeline, capture node, keyboard client |
| `umi_ros2/session/` | session layout, calibration copy/switch, `set_session_task` |
| `umi_ros2/synchronization/` | ArUco marker generation, temporal calibration |
| `umi_ros2/postprocess/` | alignment, transform, plan, exporters, `build_dataset` |
| `umi_ros2/visualization/` | session replay and replay path |
| `umi_ros2/common/` | small ROS-free helpers shared by both venvs |
| `launch/` | `online_record`, `online_view`, `replay`, `vive`, `camera`, `urdf_path_diagnostic` |
| `config/` | `vive.yaml` (device, frames, extrinsic, separate path settings), `action4.yaml`, `realsense_left.yaml` |
| `rviz/` | `online.rviz`, `urdf_path_diagnostic.rviz` |
| `test/` | unit, contract and in-process integration tests (pytest) |

## Rules

- Only components that continuously take part in ROS communication are ROS
  nodes. One-shot processing is a plain CLI that needs no running ROS graph.
  Reading MCAP still uses ROS Python message libraries.
- The pysurvive backend and ROS-free helpers do not import ROS. Launch and
  config files hold deployment defaults, not logic.
- `/vive/path` is visualization only and is never recorded.
- Build and runtime use ROS 2 Jazzy with the project `.venv` (`setuptools==68.1.2`,
  D-005).

## Known limitations

- Time offset is one constant per camera per session. There is no drift model, hardware
  trigger or exposure timing, and no camera intrinsics or camera-to-Tracker
  extrinsic.
- Recording guards against deliberate drops but does not prove source
  completeness (`source_completeness: not_verified`).
- `/vive/path` samples and publishes at 30 Hz in its own process, retaining
  up to 10,000 poses. Full-history serialization and display cost still grow
  up to that cap. There is no tracking-quality topic or covariance.
- A session switch copies calibration synchronously inside the camera node's
  service call, so the preview pauses during a large copy.
