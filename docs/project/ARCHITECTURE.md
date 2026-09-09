# UMI — Architecture and structure responsibilities

- **Basis:** `README.md` plus the Vive ROS 2 package implemented and inspected on 2026-09-07.
- **Last structure check:** 2026-09-09, drift-monitor experiment removed; pose/path/TF structure verified.

## Current structure

| Path | Responsibility |
| --- | --- |
| `vive_ros2/vive_ros2/vive_pose_node.py` | ROS parameters, polling, `PoseStamped` and bounded `Path` publication, and optional TF broadcast. |
| `vive_ros2/vive_ros2/pysurvive_backend.py` | libsurvive lifecycle, device selection, pose validation, and ROS quaternion ordering. |
| `vive_ros2/config/` and `vive_ros2/launch/` | Runtime defaults, node-only launch, and provisional node-plus-RViz launch. |
| `vive_ros2/rviz/` | Provisional RViz view of the Vive path and TF frames. |
| `vive_ros2/test/` | Hardware-independent coordinate conversion tests. |

## Vive data flow

Vive USB/lighthouse data → libsurvive calibration and pose → selected-device
backend → ROS quaternion ordering and timestamp → `/vive/pose` and optional TF.
Each published pose is also appended to a bounded `/vive/path` history for RViz.

## Structure contract

The ROS node may depend on `rclpy`, ROS messages, TF, the backend, and conversion
utilities. The pysurvive backend owns the third-party binding and must not depend
on ROS. Pose validation and quaternion adaptation remain independent of ROS and
hardware so they can be tested in plain Python. Launch and configuration files
set deployment defaults but do not contain acquisition logic.

Future camera, synchronization, recording, and dataset-conversion modules should
be separate ROS packages or clearly bounded modules; they must not be folded into
the Vive hardware adapter.

## Technical components and open questions

- `ament_python` provides the ROS 2 package and console entry point.
- libsurvive's high-level `SimpleContext` API supplies tracked-device poses
  directly without SteamVR.
- `geometry_msgs/PoseStamped` and TF expose ROS-compatible data.
- `nav_msgs/Path` exposes recent trajectory history; `max_path_points` bounds
  memory and message size, with a current default of 10,000 poses.
- Multi-device publication, pose covariance, tracking diagnostics, exact clock
  synchronization, and calibrated-world alignment to the robot are not yet designed.
- The current path republishes an increasingly large message at the pose update
  rate. Its 10,000-point cap bounds memory, but path sampling or a lower path
  publication rate should be considered before long recording sessions.
- Path history is process-local and resets whenever the node restarts. Tracking
  loss pauses pose/path updates but is not exposed on a dedicated status topic.

## Related entries

- [Requirements](REQUIREMENTS.md)
- [Current Vive task](tasks/active/vive-ros2-node.md)
- [Development decisions](DECISIONS.md)
