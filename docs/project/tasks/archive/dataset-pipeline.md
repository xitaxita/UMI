# Build the raw-to-dataset pipeline

> **Archived 2026-09-28 (D-022).** Implementation is complete; remaining hardware or real-data acceptance items are tracked in the checklist in `project.md`.

- **Task identity:** `dataset-pipeline`
- **Status:** HDF5 and LeRobot v3 software-verified; accepted-offset acceptance pending
- **Decision source:** D-019

## Goal

Turn one online raw session into frame-aligned, episode-relative training data
and a self-contained HDF5 dataset without starting a ROS graph or changing raw
recordings.

## Stages and contracts

1. Reuse `calibrate_time` and accepted `time_offset.json`.
2. Reuse `align_session` and its `aligned_frames.npz` world-frame contract.
3. Add `transform_session`; use the first valid aligned frame as the episode
   origin and write a separate versioned `episode_frames.npz` contract.
4. Add an HDF5 exporter that stores synchronized JPEG frames, relative pose,
   timestamps and episode metadata; invalid frames are explicitly counted and
   omitted from the final sample arrays.
5. Add a thin orchestration CLI. Each stage remains independently runnable.

## Acceptance

- Quaternion and translation rebasing are covered by deterministic tests.
- Invalid aligned frames stay invalid and are excluded from exported samples by
  default.
- Exported image count, pose count and timestamps agree for every episode.
- Source MP4, MCAP and alignment outputs are not modified.
- Missing optional export dependencies fail with a specific installation hint.
- The full test suite, focused lint and package build pass.

## Implemented extension

- A native local LeRobot v3 exporter uses the official
  `LeRobotDataset.create/add_frame/save_episode/finalize` API.
- LeRobot runs in a separate Python 3.12 environment so its NumPy and
  setuptools dependencies cannot modify the ROS 2 Jazzy environment.
- Hub upload stays outside the exporter. The local dataset is reloaded as the
  acceptance check. No `action` field is fabricated before its semantics are
  agreed.

## Deferred

- Hugging Face Hub upload.
- Robot action/gripper labels, task-language schema and camera extrinsics.
- Automatic repair of pose jumps or dropped source frames.

## Verification

- 51 package tests pass, including coordinate math, invalid-prefix behavior,
  versioned intermediate output, orchestration order and HDF5 image/pose count
  consistency.
- Focused flake8, ROS 2 Jazzy venv symlink build, installed CLI help and
  `git diff --check` pass.
- A zero-offset diagnostic on `online_session_20260916_185704_823701` exported
  both ordinary episodes (174 + 222 samples) to an 80.3 MiB HDF5 file. The file
  reopened successfully, first relative poses were identity, and JPEG payloads
  decoded to 1920×1080. This proves the software path, not temporal accuracy.
- The same transformed diagnostic exported as native LeRobot v3 with 2
  episodes and 396 frames. LeRobot 0.4.4 reloaded a 7-value state and a
  3×1080×1920 image; the first state was identity. The local dataset occupied
  about 9.31 MB. It used the same diagnostic zero offset.
