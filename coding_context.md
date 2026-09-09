# UMI — Coding context

## Current execution goal

- **Goal:** Complete hardware acceptance of Vive pose, path, and TF.
- **Status:** In progress; live pose accepted, while path/TF validation remains pending.
- **Task:** [Build the first Vive ROS 2 node](docs/project/tasks/active/vive-ros2-node.md)
- **Working copy:** `/home/xing/Documents/UMI`, with pre-existing user deletions and README changes preserved.

## Scope

Current work covers one configurable pysurvive device, ROS `PoseStamped`, bounded
`nav_msgs/Path`, optional TF, pose adaptation, node-plus-RViz launch/configuration,
tests, and documentation. It
does not cover cameras, synchronization, calibration, rosbag orchestration,
multi-device publication, diagnostics, or LeRobot conversion.

## Effective constraints and decisions

| Rule | Effective behavior | Source |
| --- | --- | --- |
| ROS 2 interface | Publish timestamped Vive pose and make it usable in RViz/TF. | [Requirements](docs/project/REQUIREMENTS.md) |
| Vive backend | Use pysurvive directly; do not depend on SteamVR/OpenVR. | User decision [D-001](docs/project/DECISIONS.md) |
| Coordinates | Retain libsurvive's calibrated right-handed pose and reorder quaternion `wxyz` to ROS `xyzw`. | [Architecture](docs/project/ARCHITECTURE.md) |
| Dependency boundary | Keep pysurvive and ROS integration separate; pose adaptation remains hardware-independent. | [Architecture](docs/project/ARCHITECTURE.md) |
| Existing worktree | Do not alter or restore unrelated deleted files. | Working-tree evidence at task start |

## Current state and verification

Implemented files are under `vive_ros2/`; runtime parameters select libsurvive
name/serial/index, libsurvive arguments, frames, topic, rate, and TF publication.
The node also publishes `/vive/path`, retaining at most `max_path_points`, and
`vive_with_rviz.launch.py` opens RViz with that path and TF configured.
`vive.launch.py` starts only the pose node. `vive_with_rviz.launch.py` starts the
pose node and RViz2 with the path and TF configured. The experimental drift
monitor was removed at the user's request on 2026-09-09.

- `PYTHONPATH=vive_ros2 python3 -m pytest -q vive_ros2/test`: 4 passed after rollback.
- `python3 -m compileall` and `py_compile`: passed.
- `flake8 --jobs 1`: passed after formatting.
- `git diff --check`: passed.
- ROS 2 Jazzy `colcon build --packages-select vive_ros2`: passed in a temporary workspace.
- ROS 2 Jazzy `colcon test` and `colcon test-result --verbose`: 7 tests,
  0 errors, 0 failures, 0 skipped.
- Installed `vive_with_rviz.launch.py` parses successfully with
  `ros2 launch ... --show-args`.
- Physical Vive/libsurvive pose: user-verified as correct on 2026-09-08; no
  captured topic log or device identity is recorded.
- RViz path rendering and pose/TF agreement: not yet confirmed.
- Tracking-loss and recovery behavior: not yet hardware-tested.
- User combined-launch log on 2026-09-09: the pose node detected `WM0`, RViz2
  opened, and one libsurvive `MP_MAXITER` warning occurred. The experimental
  drift monitor also started in that run but has since been removed.

The pose portion of hardware acceptance is satisfied by the user's report.
Remaining acceptance covers path rendering, TF agreement, loss/recovery,
and timestamp suitability. The current stamp is ROS publication time rather than
the libsurvive pose time, which matters for later camera synchronization.

## Open items

- Exact Vive device/model, selected name/serial, and calibration configuration
  used in the successful run are not recorded. Configure a stable name or serial
  rather than relying on the first detected object before repeatable collection.
- Moving a lighthouse or clearing libsurvive configuration can change the world
  frame and requires recalibration.
- `/vive/path` is capped but republishes the growing path at pose rate, can use
  substantial bandwidth, and resets on node restart.
- There is no explicit tracking-status/confidence topic or pose covariance.
- Sustained topic rates and path visibility are not recorded.
- Clean SIGINT shutdown should be checked because the latest launch log reports
  the Python pose node exiting with code 1 after Ctrl-C.
- Supported ROS 2 distribution range is unconfirmed; local build used Jazzy.

## Read-on-demand entries

- [Requirements](docs/project/REQUIREMENTS.md) for confirmed project scope.
- [Architecture](docs/project/ARCHITECTURE.md) for module boundaries.
- [Decisions](docs/project/DECISIONS.md) for the accepted pysurvive backend.
- [Active task](docs/project/tasks/active/vive-ros2-node.md) for detailed evidence.
- `README.md` for operator build and launch instructions.

User-facing status is in [project.md](project.md).

## Synchronization note

On 2026-09-09, drift diagnostics were rolled back at the user's request. The
active delivery is again pose/path/TF only. Four tests, ROS 2 build/test, launch
argument parsing, and installed executable inspection all pass; only
`vive_pose_node` remains installed. The existing upstream Git repository is now
used for local checkpoints; colcon and Python generated outputs are ignored.
