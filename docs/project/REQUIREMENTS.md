# UMI — Requirements and scope

- **Scope source:** Current `README.md` and the user's 2026-09-07 request to first build a ROS 2 node for Vive.
- **Last scope update:** 2026-09-09, drift diagnostics deferred and the delivery returned to pose/path/TF.

## Goal and success criteria

The UMI software system collects timestamped camera images and gripper poses for
VLA datasets, synchronizes those streams, and converts the result to LeRobot
format. The primary users are operators collecting manipulation demonstrations.

## Confirmed requirements

| Requirement | Expected behavior and acceptance | Delivery scope |
| --- | --- | --- |
| Vive pose acquisition | ROS 2 reads a Vive device and publishes its timestamped pose, bounded path, and optional TF for ROS tools and RViz. | Current delivery |
| Camera image acquisition | DJI or GoPro images and timestamps are published/recorded through ROS 2 and viewable in RViz. Exact camera remains unconfirmed. | Not yet scheduled |
| Data synchronization | Camera and pose data are synchronized; the README proposes an exUMI-style calibration video. Detailed acceptance is not yet defined. | Not yet scheduled |
| LeRobot conversion | Synchronized demonstrations are converted to a valid LeRobot dataset. Detailed schema and validation are not yet defined. | Not yet scheduled |

## Current delivery boundary

The current delivery contains only Vive pose acquisition through `pysurvive`:
device selection, pose adaptation, a timestamped `PoseStamped` topic, a bounded
`nav_msgs/Path`, optional TF output, and a provisional launch that starts the
pose node with RViz. Camera work,
synchronization, calibration, rosbag orchestration, and LeRobot conversion are
outside this task.

Current delivery acceptance requires a successful ROS 2 build, passing software
tests, and a hardware run showing a changing pose, TF, and trajectory path for
the selected tracker.

## Constraints and unresolved details

- ROS 2 is required. The repository environment currently provides ROS 2 Jazzy;
  the project's supported distribution range is not yet confirmed.
- libsurvive/pysurvive and suitable Linux USB permissions are required; SteamVR
  is not required and should be closed to avoid competing for devices.
- Vive model, tracker serial, libsurvive calibration, camera model, synchronization
  accuracy, recording format, and final LeRobot schema remain to be confirmed.
- Before synchronized data collection, the project must decide whether ROS
  publish time is accurate enough or whether libsurvive source timestamps must
  be propagated. Robot/world-frame calibration and acceptable tracking-loss
  behavior also remain undefined.

## Related entries

- [Project board](../../project.md)
- [Current Vive task](tasks/active/vive-ros2-node.md)
- [Development decisions](DECISIONS.md)
