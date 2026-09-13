# UMI 数据采集系统使用手册

本系统使用 DJI Action 4 采集视频，使用 Vive Tracker 采集夹爪位姿，并在
RViz2 中显示相机预览、Tracker 位姿和运动路径。

系统提供两种互相独立的采集方式：

- 在线采集：Action 4 通过 USB 连接电脑；一次系统启动建立一个 session，
  其中可以连续保存标定数据和多条普通 episode。
- 离线采集：Action 4 将 4K/60 fps 视频保存到 microSD，电脑只记录 pose，
  采集结束后再把视频复制到对应目录。

## 1. 开始之前

确认以下事项：

1. Action 4 和 Vive Tracker 已刚性固定在同一个夹爪上。
2. 采集过程中不要改变相机和 Tracker 的相对位置。
3. Action 4 的电子防抖已经关闭。
4. 两个 Vive 基站已开启、固定牢靠并且没有明显遮挡。
5. SteamVR 已关闭，避免占用 Vive USB 设备。
6. 电脑上已经准备好 ROS 2 Jazzy、`~/umi_ros_venv`、pysurvive、RViz2、
   rosbag2、GStreamer 和 ffmpeg。

## 2. 构建和准备终端

首次构建或代码更新后运行：

```bash
cd ~/Documents/UMI
source /opt/ros/jazzy/setup.bash
source ~/umi_ros_venv/bin/activate
python -m colcon build --packages-select umi_ros2 --symlink-install
source install/setup.bash
```

每次打开新终端时运行：

```bash
cd ~/Documents/UMI
source /opt/ros/jazzy/setup.bash
source ~/umi_ros_venv/bin/activate
source install/setup.bash
```

## 3. 检查 Vive Tracker

Vive 配置文件位于 `umi_ros2/config/vive.yaml`。如果只有一个 Tracker，可以
保留默认自动选择。正式长期采集时，建议填写稳定的 `device_name` 或
`device_serial`。

单独启动 Vive：

```bash
ros2 launch umi_ros2 vive.launch.py
```

另开一个准备好的终端检查 pose：

```bash
ros2 topic hz /vive/pose
```

确认 pose 持续更新后，按 `Ctrl+C` 结束检查。

正常采集不需要使用 `--force-calibrate`。只有首次配置、移动过基站、标定文件
丢失或明确需要重建世界坐标系时，才在 `vive.yaml` 中临时设置：

```yaml
libsurvive_args: "--force-calibrate"
```

重新标定完成后，应将它恢复为空字符串。

## 4. 在线采集前准备

1. 用 USB 将 Action 4 连接电脑。
2. 在相机上选择 Webcam 模式。
3. 运行下面的命令确认相机设备：

```bash
v4l2-ctl --list-devices
```

4. 确认相机是 `/dev/video0`。如果不是，修改
   `umi_ros2/config/action4.yaml` 中的 `video_device`。
5. 在线采集期间不要让 Action 4 同时向 microSD 录像。

## 5. 启动在线采集

在第一个终端运行：

```bash
ros2 launch umi_ros2 online_record.launch.py
```

系统会启动 Action 4、Vive 和 RViz2。相机在本次启动中只预热一次，默认约
5 秒。等待 RViz2 中同时出现相机画面、Tracker 和路径后再开始采集。

在第二个准备好的终端运行：

```bash
ros2 run umi_ros2 episode_keyboard
```

按键规则：

- 按 Enter：开始一条新 episode。
- 在等待状态输入 `c` 后按 Enter：开始一条专用标定记录。
- 再按 Enter：结束并保存当前 episode。
- 再按 Enter：开始下一条新 episode。
- 输入 `q` 后按 Enter：只退出按键控制器，不停止整个系统。
- 在 Launch 终端按 `Ctrl+C`：结束整个在线系统。

每次结束 episode 后，等待终端显示 `episode complete`，再开始下一条。

等待状态下，图像只用于 RViz2 预览，不保存视频和 pose；录制状态下，视频和
pose 会同时保存。切换 episode 不会重启或重新预热相机。

## 6. 生成时间标定图案

第一次使用前生成 ArUco 标记：

```bash
ros2 run umi_ros2 generate_aruco_marker \
  --output ~/Documents/UMI/aruco_id4.png
```

打印时保持正方形，建议黑色标记区域约为 60 mm × 60 mm，并在周围保留
白边。打印后可以长期重复使用。

## 7. 录制时间标定 episode

每次重新启动在线采集系统后，先录制一条专用时间标定 episode。同一次
Launch 持续运行期间，普通 episode 不需要重复标定。

操作步骤：

1. 将 ArUco 标记固定在桌面上，标记不能跟随夹爪移动。
2. 确认标记在 RViz2 相机画面中完整、清晰可见。
3. 在按键控制器中输入 `c` 后按 Enter，开始标定记录。
4. 保持夹爪静止约 2 秒。
5. 让夹爪水平向左、向右往返移动 3～5 次。
6. 移动过程中保持标记完整可见，避免手遮挡标记。
7. 再次保持静止约 2 秒。
8. 按 Enter 结束，并等待 `calibration complete`。
9. 记下刚生成的 `online_session_<时间>/calibration/calibration_001`
   目录名称。

移动时应有明显转折，但不要快到画面严重模糊。

## 8. 计算并检查时间差

在第三个准备好的终端运行：

```bash
ros2 run umi_ros2 calibrate_time \
  recordings/online_session_<时间>/calibration/calibration_001
```

将目录替换为刚才的真实标定 episode。完成后，该目录会增加：

```text
time_offset.json
alignment_report.png
```

检查步骤：

1. 打开 `alignment_report.png`，确认两条曲线在主要运动和转折位置上对齐。
2. 打开 `time_offset.json`，确认 `accepted` 为 `true`。
3. 如果命令失败、`accepted` 为 `false`，或者曲线明显没有对齐，应重新录制
   标定 episode，不要继续使用该结果。

当前版本会计算并保存时间差，但还不会自动修改普通 episode。请保留标定
记录及其结果，等待后续统一对齐工具使用。标定程序也会把结果路径和状态写入
本次 session 的 `session.yaml`。

## 9. 录制普通在线 episode

时间标定通过后，可以重复采集普通任务：

1. 整理场景，并将夹爪放到起始位置。
2. 按 Enter 开始 episode。
3. 完成一次完整操作。
4. 按 Enter 结束 episode。
5. 等待 `episode complete`。
6. 检查终端没有相机、Vive 或写盘错误。
7. 整理下一次场景，然后重复以上步骤。

一次在线 Launch 的完整数据结构为：

```text
recordings/online_session_<时间>/
├── session.yaml
├── calibration/
│   └── calibration_001/
│       ├── video.mp4
│       ├── video.timing.json
│       ├── video.validation.json
│       ├── time_offset.json
│       ├── alignment_report.png
│       └── pose/
└── episodes/
    ├── episode_0001/
    │   ├── video.mp4
    │   ├── video.timing.json
    │   ├── video.validation.json
    │   └── pose/
    └── episode_0002/
```

## 10. 结束在线采集

推荐先结束当前 episode 并等待 `episode complete`，然后在 Launch 终端按
`Ctrl+C`。等待所有进程退出后再关闭终端、拔出相机或关闭电源。

采集结束后至少检查：

1. 每条 episode 都有 `video.mp4` 和 `pose/`。
2. `video.mp4` 可以正常播放。
3. `video.validation.json` 中没有明显失败信息。
4. `session.yaml` 已登记各条记录，标定目录包含 `time_offset.json` 和
   `alignment_report.png`。

## 11. 离线采集

离线模式下，Action 4 不连接 USB。相机把视频保存到 microSD，电脑只记录
Vive pose 并在 RViz2 中显示路径。

操作步骤：

1. 将 Action 4 设置为 4K/60 fps，并关闭电子防抖。
2. 确认 microSD 空间、电池和相机温度正常。
3. 在 Action 4 上开始录像。
4. 在电脑终端运行：

```bash
ros2 launch umi_ros2 offline_record.launch.py
```

5. 等待 RViz2 中的 Tracker 和路径正常显示。
6. 完成采集动作。
7. 在 Launch 终端按 `Ctrl+C`，等待 pose 文件写入完成。
8. 停止 Action 4 录像。

默认目录为 `recordings/offline_session_<时间>/pose/`。会话根目录还包含
`session.yaml` 和为后续方案预留的 `calibration/`。

也可以指定一个新的输出目录：

```bash
ros2 launch umi_ros2 offline_record.launch.py \
  session_output:=/data/umi/offline_demo_01
```

不要使用已经包含数据的目录。

## 12. 导入离线视频

从 microSD 找到与该次 pose 对应的视频，复制到离线会话根目录并命名为
`video.mp4`：

```bash
cp --no-clobber /media/xing/ACTION4/DCIM/100MEDIA/DJI_0001.MP4 \
  recordings/offline_session_<时间>/video.mp4
```

最终目录应为：

```text
recordings/offline_session_<时间>/
├── session.yaml
├── calibration/
├── video.mp4
└── pose/
    ├── metadata.yaml
    └── *.mcap
```

确认复制完整且视频可以播放之前，不要删除 microSD 中的原文件。如果相机把
一次录像拆分成多个文件，应保留全部原始分段。

## 13. 检查 pose 记录

在线和离线 pose 都可以使用下面的命令检查：

```bash
ros2 bag info recordings/<会话目录>/pose
```

正常情况下应包含：

```text
/vive/pose
/tf
/tf_static
```

`/vive/path` 只用于 RViz2 显示，不会保存到数据中。

## 14. 回放 session 或单条数据

回放整个在线 session：

```bash
ros2 launch umi_ros2 replay.launch.py \
  input_path:=recordings/online_session_<时间>
```

系统会自动按以下顺序回放：

```text
calibration_001 → calibration_002 → episode_0001 → episode_0002 → ...
```

只回放一条 calibration 或 episode：

```bash
ros2 launch umi_ros2 replay.launch.py \
  input_path:=recordings/online_session_<时间>/episodes/episode_0001
```

可以通过 `playback_rate` 调整速度，例如两倍速：

```bash
ros2 launch umi_ros2 replay.launch.py \
  input_path:=recordings/online_session_<时间> playback_rate:=2.0
```

回放会直接读取每条数据的 `video.mp4`，同时播放对应的 `pose/`，在 RViz2
显示图像、Vive 路径和 TF。切换到下一条数据前会清空上一条路径。当前回放
保留原始视频与 pose 的记录起点关系，但不会自动应用 `time_offset.json`。

## 15. 只观察，不录制

只检查在线相机和 Vive 显示：

```bash
ros2 launch umi_ros2 online_view.launch.py
```

只检查 Vive：

```bash
ros2 launch umi_ros2 vive.launch.py
```

## 16. 常见问题

### 没有相机画面

1. 确认 Action 4 已选择 Webcam 模式。
2. 运行 `v4l2-ctl --list-devices`，确认设备路径。
3. 检查 `action4.yaml` 中的 `video_device`。
4. 确认没有其他程序正在占用相机。

### 没有 Vive pose

1. 关闭 SteamVR。
2. 检查 Tracker、接收器和基站供电。
3. 检查基站是否被遮挡或移动。
4. 检查 `vive.yaml` 中的设备名称或序列号。

### 位姿跳变或漂移明显

1. 确认两个基站都能看到 Tracker。
2. 排除反光表面、基站振动和人体遮挡。
3. 如果移动过基站，重新进行 Vive 标定并重新开始会话。

### 时间标定失败

1. 确认 ArUco ID 4 在大部分画面中完整可见。
2. 增加左右移动距离，并确保存在 3～5 个明显往返。
3. 降低运动速度，避免标记模糊。
4. 确认标定 episode 同时包含视频和 pose。
5. 重新录制标定 episode，不要手工修改失败结果。

## 17. 当前限制

- 在线连续 episode 和时间标定仍需 Action 4 真机验收。
- 时间差已经可以计算和保存，但尚未自动应用到普通 episode。
- 离线 SD 视频尚不能自动导入或自动完成时间标定。
- 相机内参、相机到 Tracker 的刚性外参和 LeRobot 转换尚未完成。
- 回放尚未自动应用标定得到的 `time_offset.json`。

项目当前进度见 [project.md](project.md)。
