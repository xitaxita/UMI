# Consolidate project-owned ROS runtime

- **Task identity:** `consolidate-ros-package`
- **Status:** Complete on 2026-09-11
- **Decision source:** D-007
- **Working copy:** `/home/xing/Documents/UMI`; unrelated user changes preserved.

## Goal

Replace `vive_ros2`, `action4_ros2`, and `umi_bringup` with one project-owned
`umi_ros2` package. Keep focused executables, organize shared versus
offline-only versus online-only behavior, and reserve ordinary command-line
tools for non-realtime processing.

## Delivered

- Consolidated all project-owned nodes into `umi_ros2`, organized under
  `vive`, `camera`, `common`, and `visualization` modules.
- Centralized launch, configuration, mode-specific RViz assets, and tests.
- Added shared Vive and camera-only entry points, online view/record, offline
  pose-only record, and online replay.
- Preserved all existing ROS topic names and the online MCAP topic contract.
- Removed the three superseded source packages and their stale build/install
  artifacts after the unified package passed verification.
- Updated README, architecture, decisions, coding context, and project board.

## Verification

- `colcon list`: only `umi_ros2` is discovered.
- `colcon build --packages-select umi_ros2 --symlink-install`: passed.
- `colcon test` / `colcon test-result --verbose`: 12 tests, 0 errors, 0
  failures, 0 skipped.
- `vive`, `camera`, `online_view`, `online_record`, `offline_record`, and
  `replay` installed launch files all parse with `--show-args`.
- Four installed executables are discoverable under `umi_ros2`.
- Existing `online_20260910_205248` bag remains readable with `ros2 bag info`.
- `git diff --check`: passed.

## Remaining outside this task

- Hardware acceptance of the final Action 4 JPEG bridge.
- Offline SD-video import and temporal synchronization.
- Camera intrinsics/extrinsics and LeRobot conversion.
