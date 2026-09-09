# UMI — Project progress

- **Goal:** Collect synchronized camera images and gripper poses for VLA demonstrations, then convert them to LeRobot format.
- **Current stage:** First ROS 2 acquisition component.
- **Current focus:** Finish Vive path/TF visualization and robustness checks.
- **Current acceptance:** Live Vive pose is user-verified. The experimental drift feature has been rolled back; ROS build and all 4 remaining tests pass.
- **Remaining overall work:** Camera acquisition, synchronization/calibration, recording workflow, and LeRobot conversion are not implemented in the current worktree.
- **Last checked:** 2026-09-09 after rolling back the experimental drift feature.
- **Version control:** Existing Git history retained; the current ROS 2 baseline
  is saved locally, while generated build/install/log files are ignored.

## Current delivery

| Capability | Implementation | Verification | How to use / limitation |
| --- | --- | --- | --- |
| Vive pose topic | Implemented with pysurvive | User reports the live pose is correct; ROS build and all 4 package tests pass after rollback | Currently usable with the configured Vive system. Device identity and run details are not yet recorded. |
| Vive TF | Implemented and enabled by default | Build/static checks pass; hardware test pending | Inspect `vive_world -> vive_tracker`. |
| Device configuration | Implemented | Code/build checked | Select by libsurvive name, serial, or index in `vive_ros2/config/vive.yaml`. |
| Vive trajectory path | Implemented with a 10,000-point default limit | Build/static checks pass; live rendering pending | Launch `vive_with_rviz.launch.py` to show `/vive/path`. |
| Provisional RViz launch | Implemented | Hardware run started the pose node and RViz | RViz opened successfully; path visibility was not confirmed before Ctrl-C. |

## ROS 2 node design

| Node | What it does |
| --- | --- |
| `vive_pose_node` | Reads the selected Vive device pose from pysurvive, publishes the current pose on `/vive/pose`, publishes the traveled path on `/vive/path`, and broadcasts `vive_world -> vive_tracker` TF. |
| `rviz2` | Displays the Vive path and TF frames using the provisional `vive_path.rviz` configuration. |

`vive.launch.py` starts the pose node.
`vive_with_rviz.launch.py` starts the pose node and `rviz2`.

## Confirmed requirements not yet delivered

| Requirement | Current gap | Scheduling/dependency |
| --- | --- | --- |
| Vive integration acceptance | Live pose passes, but TF/path display, tracking-loss recovery, and timestamp suitability are not confirmed. | Verify with the existing hardware and RViz launch. |
| Camera acquisition | No current camera ROS 2 package. Camera model is not settled. | Not yet scheduled. |
| Data synchronization | Synchronization and exUMI-style calibration flow are not designed or implemented. | Not yet scheduled; accuracy target is unknown. |
| LeRobot conversion | No current converter or validated output schema. | Not yet scheduled. |

## Current issues and decisions

The user selected pysurvive and has now confirmed that its live pose is correct.
Before data collection, record the selected device identity and calibration,
verify TF and the RViz path, test tracking interruption/recovery, and decide how
accurate timestamps must be for camera synchronization. Long path messages may
also become expensive even with the 10,000-point cap.
The latest run also showed one libsurvive `MP_MAXITER` solver warning. It is not
a launch failure by itself, but repeated warnings may interrupt valid pose updates.

## Next step

Launch `vive_with_rviz.launch.py` and verify path/TF and
tracking recovery before deciding timestamp requirements for the camera node.

## Project map

| Area | Responsibility |
| --- | --- |
| `vive_ros2/` | Vive/libsurvive pose acquisition, bounded path publication, and provisional RViz launch. |
| `docs/project/` | Confirmed requirements, architecture, and active task evidence. |
| `README.md` | System intent and operator build/run instructions. |

- Coding basis: [coding_context.md](coding_context.md)
- Requirements: [docs/project/REQUIREMENTS.md](docs/project/REQUIREMENTS.md)
- Architecture: [docs/project/ARCHITECTURE.md](docs/project/ARCHITECTURE.md)
- Decisions: [docs/project/DECISIONS.md](docs/project/DECISIONS.md)
- Active task: [docs/project/tasks/active/vive-ros2-node.md](docs/project/tasks/active/vive-ros2-node.md)
