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
| Camera image acquisition | DJI Action 4 and the Vive Tracker are rigidly mounted on the gripper. Online mode (the only mode; offline removed by D-021) uses USB at a target 1080p/30 fps, records image and pose through ROS 2, and displays both in RViz. EIS is off. | Online implemented |
| Data recording | Every session `online_session_<timestamp>/` has a root `session.yaml` and holds one task (D-021). Calibration and episodes each store `video.mp4` and an independent Vive pose/TF MCAP under `pose/`. `/vive/path` is displayed but not recorded. | Current delivery; software and hardware verification pending |
| Online episodes | Keep one `online_session_<timestamp>`, camera stream, and pose subscriptions alive while recording dedicated calibration and ordinary episodes. Warm camera/pose once, open an independent MCAP per item, and require its first pose before MP4 starts. | Current delivery; hardware acceptance pending |
| Data synchronization | Record one ArUco calibration per uninterrupted session, estimate a signed offset, then use a non-ROS Python tool to apply it and interpolate one Vive pose per actual MP4 frame. Invalid coverage/gaps remain explicit and raw files stay unchanged. | Estimator and alignment tool implemented; accepted real calibration validation pending |
| Dataset conversion | Accepted calibration feeds frame/pose alignment; each episode is rebased to its first valid pose and exported through independent HDF5 and native LeRobot v3 adapters. | Current implementation task |

## Current delivery boundary

The current delivery includes repeated online episode control; offline acquisition
was removed by D-021. Online uses MJPEG UVC input, H.264 MP4 output, best-effort
preview, camera-stream warmup, and pose pre-roll.
The temporal-offset estimator and decoupled alignment, episode-coordinate and
HDF5 export stages are implemented, but no real calibration result has yet been
accepted for final dataset validation. Camera intrinsic calibration remains outside the delivered implementation.
Multi-session dataset merging (D-021, `build_dataset`) is implemented and
software-verified; real multi-task data acceptance is pending.

Current delivery acceptance requires a successful ROS 2 build, passing software
tests, and a hardware run showing a changing pose, TF, and trajectory path for
the selected tracker.

Action 4 USB/UVC behavior and an initial 1080p/30 camera-only stream were
validated on Linux on 2026-09-10. The next online delivery must publish the
image through ROS 2, display it with pose data, and validate recording plus
simultaneous Vive operation.
Full online acceptance still requires sustained
1080p/30 fps USB image capture, image-plus-pose recording, and live RViz display.
`/vive/path` is never recorded to the dataset.

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
- [Architecture](ARCHITECTURE.md)
- [Development decisions](DECISIONS.md)
