# UMI software system design

## 1. Collect Raw Data

This system is used for VLA data collection. The data main record is the images and the pose of the gripper. Images are captured by the camera of DJI or GoPro which is not sure right. But the two device will all connect to this linux and serviced as a ROS2 node to record the images data. Meanwhile, the timestamp data is useful and should be recorded. For the pose, we use vive and pysurvive to get it, and also use ROS2 to publish it. Rviz show the pose got through vive and image got through camera.

## 2. Data Synchronization Method

With the raw data collected from the UMI, we should synchronize the two different types of data. Here we reference the exUMI method which record another video for calibrate.

## 3. Data Processing

We should process the data to LeRobot format for further use.

## Vive ROS 2 node (pysurvive)

The `vive_ros2` package uses libsurvive through its Python package `pysurvive`.
It does not use OpenVR or require SteamVR. It publishes a selected tracked
object as `geometry_msgs/PoseStamped` on `/vive/pose` and broadcasts the
`vive_world -> vive_tracker` transform by default.

First install libsurvive's Linux build dependencies and USB permission rules by
following the current [libsurvive instructions](https://github.com/collabora/libsurvive).
Install the Python binding into the same Python environment used by ROS 2:

```bash
python3 -m pip install pysurvive
python3 -c "import pysurvive; print(pysurvive.__file__)"
```

SteamVR should be closed while using libsurvive because both programs can
compete for the Vive USB devices.

Build and launch from a ROS 2 workspace:

```bash
cd ~/umi_ws
colcon build --packages-select vive_ros2
source install/setup.bash
ros2 launch vive_ros2 vive.launch.py
```

For the current provisional visualization, launch the pose node and RViz2
together:

```bash
ros2 launch vive_ros2 vive_with_rviz.launch.py
```

RViz uses `vive_world` as its fixed frame and displays the accumulated tracker
trajectory from `/vive/path`. The path keeps at most `max_path_points` poses
(10,000 by default) to bound memory use. This launch/configuration is an early
development view, not the final UMI visualization.

Configure `vive_ros2/config/vive.yaml` to select an object by its libsurvive
name (for example `HMD`, `WM0`, or a tracker codename), hardware serial, or
zero-based non-lighthouse device index. Name takes precedence over serial,
which takes precedence over index. With all selectors empty/default, the first
tracked non-lighthouse object to report a pose is used.

Additional libsurvive command-line options can be placed in the
`libsurvive_args` string, for example:

```yaml
libsurvive_args: "--force-calibrate --v 10"
```

Inspect output with:

```bash
ros2 topic echo /vive/pose
ros2 topic echo /vive/path
ros2 run tf2_ros tf2_echo vive_world vive_tracker
```

The pose is libsurvive's object-to-world transform in its calibrated,
right-handed world frame. Libsurvive returns quaternions as `w,x,y,z`; the node
reorders them to ROS `x,y,z,w`. The ROS message uses the node clock at the time
the update is published.

### Before recording data

- Set a stable `device_name` or `device_serial`; the default first-device choice
  can select a different object after reconnecting hardware.
- Save the libsurvive calibration/configuration and recalibrate whenever a
  lighthouse moves. The `vive_world` frame is only as stable as that calibration.
- Confirm `/vive/pose`, TF, and `/vive/path` agree in RViz, then test temporary
  tracking loss and recovery. The current node has no separate tracking-status
  or confidence topic.
- Decide whether ROS publication time is accurate enough for camera
  synchronization. The current node does not publish libsurvive's pose time.
- The path resets when the node restarts. Although limited to 10,000 poses, the
  complete growing path is republished at pose rate and may consume significant
  CPU/network bandwidth during long sessions.
