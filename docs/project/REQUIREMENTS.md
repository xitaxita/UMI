# UMI — Requirements and scope

- **Scope source:** Current `README.md` and the user's 2026-09-07 request to first build a ROS 2 node for Vive.
- **Last scope update:** 2026-09-13, shared session-level storage selected.

## Goal and success criteria

The UMI software system collects timestamped camera images and gripper poses for
VLA datasets, synchronizes those streams, and converts the result to LeRobot
format. The primary users are operators collecting manipulation demonstrations.

## Confirmed requirements

| Requirement | Expected behavior and acceptance | Delivery scope |
| --- | --- | --- |
| Vive pose acquisition | ROS 2 reads a Vive device and publishes its timestamped pose, bounded path, and optional TF for ROS tools and RViz. | Current delivery |
| Camera image acquisition | DJI Action 4 and the Vive Tracker are rigidly mounted on the gripper. Offline mode records 4K/60 fps to microSD and shows pose/path/TF in RViz; online mode uses USB at a target 1080p/30 fps, records image and pose through ROS 2, and displays both in RViz. EIS is off in both modes. | Online implemented; offline pending |
| Data recording | Every acquisition has a root `session.yaml`. Offline capture creates `offline_session_<timestamp>/` with reserved `calibration/` and Vive pose/TF MCAP under `pose/`; the operator later adds `video.mp4`. `/vive/path` is displayed but not recorded. | Current delivery; software and hardware verification pending |
| Online episodes | Keep one `online_session_<timestamp>` and the online ROS system/preview running while the operator records dedicated items under `calibration/` and ordinary items under `episodes/`. Each item contains MP4, timing/validation metadata, and pose/TF MCAP. | Current delivery; hardware acceptance pending |
| Data synchronization | The first implementation records one ArUco calibration episode per uninterrupted acquisition session, aligns interpolated video-marker and Vive trajectories by minimum normalized MSE, saves the signed video-to-pose offset and a reviewable quality report, then applies that offset to the session episodes. Accuracy must be measured locally and is not inherited from exUMI. | Estimator implemented; real calibration and offset application pending |
| LeRobot conversion | Synchronized demonstrations are converted to a valid LeRobot dataset. Detailed schema and validation are not yet defined. | Not yet scheduled |

## Current delivery boundary

The current delivery includes pose-only offline acquisition and repeated online
episode control. Online uses MJPEG UVC input, H.264 MP4 output, best-effort
preview, camera-stream warmup, and pose pre-roll.
The temporal-offset estimator is implemented but not yet accepted on a real
calibration episode or consumed by frame-to-pose interpolation. Camera/extrinsic
calibration, detailed offline episode/calibration behavior, and LeRobot
conversion remain outside the delivered implementation.

Current delivery acceptance requires a successful ROS 2 build, passing software
tests, and a hardware run showing a changing pose, TF, and trajectory path for
the selected tracker.

Action 4 USB/UVC behavior and an initial 1080p/30 camera-only stream were
validated on Linux on 2026-09-10. The next online delivery must publish the
image through ROS 2, display it with pose data, and validate recording plus
simultaneous Vive operation.
Offline acceptance requires 4K/60 fps SD recording alongside a Vive pose bag and
live RViz pose visualization. Full online acceptance still requires sustained
1080p/30 fps USB image capture, image-plus-pose recording, and live RViz display.
Neither mode records `/vive/path` to the dataset.

## Constraints and unresolved details

- ROS 2 is required. The repository environment currently provides ROS 2 Jazzy;
  the project's supported distribution range is not yet confirmed.
- libsurvive/pysurvive and suitable Linux USB permissions are required; SteamVR
  is not required and should be closed to avoid competing for devices.
- Vive model, tracker serial, libsurvive calibration, synchronization accuracy,
  online image transport, and final LeRobot schema remain to be confirmed.
- Before synchronized data collection, the project must decide whether ROS
  publish time is accurate enough or whether libsurvive source timestamps must
  be propagated. Robot/world-frame calibration and acceptable tracking-loss
  behavior also remain undefined.

## Related entries

- [Project board](../../project.md)
- [Current Vive task](tasks/active/vive-ros2-node.md)
- [Development decisions](DECISIONS.md)
