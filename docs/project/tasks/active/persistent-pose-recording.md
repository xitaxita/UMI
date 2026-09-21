# Persist online pose subscriptions across episodes

- **Task identity:** `persistent-pose-recording`
- **Status:** Implemented and software-verified; hardware acceptance pending
- **Decision source:** D-018

## Goal

Warm the pose recorder with the camera once per session, retain ROS
subscriptions while waiting, and write each calibration/episode to its own
`pose/` MCAP only after an explicit start.

## Acceptance

- Pose subscriptions are established once and survive episode boundaries.
- Camera and pose warmup both last at least the configured session warmup.
- Every recording still owns a separate `pose/metadata.yaml` and MCAP.
- Camera recording starts only after the new pose bag has written its first
  `/vive/pose` sample.
- Waiting messages are not stored; stopping one episode does not terminate the
  persistent recorder.

## Current evidence

- The online controller no longer launches `ros2 bag record` per episode. It
  starts one internal pose-recorder process before the camera worker, waits for
  both `waiting` states, opens pose first, waits for `recording_ready`, and then
  opens video.
- An integration test reused one live ROS subscription node while writing and
  finalizing two independent MCAP directories. Both produced `metadata.yaml`
  and an MCAP file.
- All 42 package tests, focused flake8, ROS 2 Jazzy venv build, installed launch
  parsing, and `git diff --check` pass. Real Action 4 + Vive multi-episode
  acceptance remains pending.
