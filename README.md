# UMI 数据采集系统使用手册

本系统使用 DJI Action 4 采集视频，使用 Vive Tracker 采集夹爪位姿，并在
RViz2 中显示相机预览、Tracker 位姿和运动路径。

系统只提供在线采集：Action 4 通过 USB 连接电脑；一次系统启动建立一个
session，其中可以连续保存标定数据和多条普通 episode。（原离线采集模式已按
D-021 删除。）

## 1. 已验证的运行环境

当前项目在以下环境中开发和验证：

- Ubuntu 24.04 LTS（当前机器为 24.04.5）。
- ROS 2 Jazzy Desktop。
- Python 3.12。
- Python 虚拟环境：`~/umi_ros_venv`，创建时启用系统 Python 包。
- `colcon-common-extensions==0.3.0`。
- `setuptools==68.1.2`。不要直接升级到新版；当前 ROS 2 Python 构建链与
  `setuptools==84.0.0` 不兼容。
- `pysurvive==1.1.204`，底层使用 libsurvive，不使用 OpenVR/SteamVR。
- GStreamer 1.24、OpenCV 4.6、FFmpeg 6.1 和 rosbag2 MCAP。

其他 ROS 2 发行版、Ubuntu 版本或 Python 主版本尚未经过本项目验证。

## 2. 安装系统依赖

先按照 ROS 2 官方方式安装 ROS 2 Jazzy Desktop，然后安装项目运行与检查工具：

```bash
sudo apt update
sudo apt install \
  ros-jazzy-desktop \
  ros-jazzy-rosbag2 \
  ros-jazzy-rosbag2-storage-mcap \
  python3-venv \
  python3-rosdep \
  python3-gi \
  python3-opencv \
  python3-h5py \
  python3-matplotlib \
  python3-yaml \
  gir1.2-gstreamer-1.0 \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav \
  ffmpeg \
  v4l-utils
```

如果尚未初始化 rosdep：

```bash
sudo rosdep init
rosdep update
```

`sudo rosdep init` 在一台电脑上通常只需执行一次；如果提示已经初始化，可跳过。

## 3. 创建 Python 虚拟环境

本项目必须让 venv 访问 ROS 2 和 GStreamer 安装到系统 Python 中的包，因此
必须带 `--system-site-packages`：

```bash
python3 -m venv --system-site-packages ~/umi_ros_venv
source /opt/ros/jazzy/setup.bash
source ~/umi_ros_venv/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  setuptools==68.1.2 \
  colcon-common-extensions==0.3.0 \
  PyYAML==6.0.1 \
  h5py==3.16.0 \
  pysurvive==1.1.204
```

确认当前终端确实使用 venv：

```bash
which python
which colcon
python --version
python -c "import rclpy, gi, cv2, pysurvive; print('environment OK')"
```

前两个路径都应位于 `~/umi_ros_venv/bin/`，Python 应为 3.12。以后始终先
source ROS 2，再激活 venv；顺序不要颠倒。

### LeRobot v3 独立环境

LeRobot 的 NumPy、setuptools 和深度学习依赖与当前 ROS 2 Jazzy 环境不同，
不要把 LeRobot 安装进 `~/umi_ros_venv`。需要导出 LeRobot v3 时，另建一个
Python 3.12 环境：

```bash
/usr/bin/python3 -m venv ~/umi_lerobot_venv312
source ~/umi_lerobot_venv312/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  torch==2.10.0 torchvision==0.25.0 \
  --index-url https://download.pytorch.org/whl/cpu
python -m pip install --no-cache-dir lerobot==0.4.4
```

本项目调用该环境中的解释器完成最后的 LeRobot 序列化；标定、MCAP 读取、
对齐和坐标变换仍在 ROS 环境中运行。这样不会破坏 `rclpy`、NumPy 1.x 或
ROS 的构建工具链。

## 4. 安装项目依赖并构建

```bash
cd ~/Documents/UMI
source /opt/ros/jazzy/setup.bash
source ~/umi_ros_venv/bin/activate
rosdep install --from-paths umi_ros2 --ignore-src -r -y
python -m colcon build --packages-select umi_ros2 --symlink-install
source install/setup.bash
```

构建后可以检查安装是否成功：

```bash
ros2 pkg executables umi_ros2
ros2 launch umi_ros2 online_record.launch.py --show-args
```

每次修改 Python 或 launch/config 文件后，建议重新执行 build 和
`source install/setup.bash`。`--symlink-install` 会让 Python 源码修改更方便，
但新文件、入口点和安装资源仍需要重新构建。

## 5. 每个新终端的环境准备

每次打开终端都执行：

```bash
cd ~/Documents/UMI
source /opt/ros/jazzy/setup.bash
source ~/umi_ros_venv/bin/activate
source install/setup.bash
```

推荐把上面四行保存为自己的 shell alias，但不要直接修改 `install/` 中自动
生成的 setup 文件；重新构建时这些文件可能被覆盖。

## 6. 硬件与权限准备

确认以下事项：

1. Action 4 和 Vive Tracker 已刚性固定在同一个夹爪上。
2. 采集过程中不要改变相机和 Tracker 的相对位置。
3. Action 4 的电子防抖已经关闭。
4. 两个 Vive 基站已开启、固定牢靠并且没有明显遮挡。
5. SteamVR 已关闭，避免占用 Vive USB 设备。
6. libsurvive 的 USB/udev 规则已经安装，当前用户能够访问 Tracker、接收器和
   基站设备；修改规则后需要重新插拔设备，必要时重新登录。
7. 在线模式下，当前用户能够读取相机对应的 `/dev/video*`；可用下面的命令
   检查设备和格式：

```bash
v4l2-ctl --list-devices
v4l2-ctl --device=/dev/video0 --list-formats-ext
```

当前 Action 4 已验证的 Webcam 输入是 MJPEG 1920×1080/30 fps；系统将其编码
为 H.264 MP4。相机若不是 `/dev/video0`，需要修改
`umi_ros2/config/action4.yaml`。

可以用以下命令做一次环境级自检：

```bash
gst-inspect-1.0 v4l2src jpegdec x264enc h264parse mp4mux
ffmpeg -version
ros2 bag --help
```

## 7. 检查 Vive Tracker

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

## 8. 在线采集前准备

1. 用 USB 将 Action 4 连接电脑。
2. 在相机上选择 Webcam 模式。
3. 运行下面的命令确认相机设备：

```bash
v4l2-ctl --list-devices
```

4. 确认相机是 `/dev/video0`。如果不是，修改
   `umi_ros2/config/action4.yaml` 中的 `video_device`。
5. 在线采集期间不要让 Action 4 同时向 microSD 录像。

## 9. 启动在线采集

一个 session 只对应一个任务（task），session 中可以录多条 episode；换任务就
开新的 session。task 是一句自然语言指令，之后会直接作为 LeRobot 数据集的语言
task。推荐启动时就用 `task:=` 写明：

```bash
ros2 launch umi_ros2 online_record.launch.py task:="pick up the red cube and place it in the box"
```

`task:=` 可以不填：

```bash
ros2 launch umi_ros2 online_record.launch.py
```

不填时终端会给出黄色警告，并打印补填命令；此时 `session.yaml` 中的
`task` 为空，导出数据集前必须补上（见下文“补填或修改 task”）。task 只写在
`session.yaml` 里，session 目录名不包含 task，仍是 `online_session_<时间>`。

系统会启动 Action 4、Vive、常驻 pose recorder 和 RViz2。相机与 pose
recorder 在本次启动中同时预热一次，默认至少 5 秒。等待 RViz2 中同时出现
相机画面、Tracker 和路径后再开始采集。

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

等待状态下，图像只用于 RViz2 预览，pose recorder 维持订阅但不保存；录制
状态下，每条记录仍写入自己目录内独立的 `video.mp4` 和 `pose/`。开始时先
确认新 pose bag 已写入第一条 pose，再开始写视频。切换 episode 不会重启或
重新预热相机和 pose recorder。

## 10. 生成时间标定图案

第一次使用前生成 ArUco 标记：

```bash
ros2 run umi_ros2 generate_aruco_marker \
  --output ~/Documents/UMI/aruco_id4.png
```

打印时保持正方形，建议黑色标记区域约为 60 mm × 60 mm，并在周围保留
白边。打印后可以长期重复使用。

## 11. 录制时间标定 episode

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

移动时应有明显转折，但不要快到画面严重模糊。当前标定器会同时利用标记的
水平/垂直中心、面积和画面内角度，以及 TCP 的三维平移和旋转；建议动作同时
包含左右、上下、前后和两到三个方向的旋转，并使用不同幅度、速度和停顿，避免
完全周期重复。短暂遮挡可以接受，但应尽量让标记持续完整可见。

## 12. 计算并检查时间差

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

1. 打开 `alignment_report.png`，确认两条运动能量曲线在主要启动、停止和转折
   位置上对齐。
2. 打开 `time_offset.json`，确认 `accepted` 为 `true`。
3. 检查 `window_offsets_seconds` 相互接近，并确认
   `window_offset_std_seconds` 不超过验收阈值（默认 20 ms）。
4. 如果命令失败、`accepted` 为 `false`，或者曲线明显没有对齐，应重新录制
   标定 episode，不要继续使用该结果。

当前版本会计算并保存时间差，但还不会自动修改普通 episode。请保留标定
记录及其结果，等待后续统一对齐工具使用。标定程序也会把结果路径和状态写入
本次 session 的 `session.yaml`。

## 13. 录制普通在线 episode

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

## 14. 结束在线采集

推荐先结束当前 episode 并等待 `episode complete`，然后在 Launch 终端按
`Ctrl+C`。等待所有进程退出后再关闭终端、拔出相机或关闭电源。

采集结束后至少检查：

1. 每条 episode 都有 `video.mp4` 和 `pose/`。
2. `video.mp4` 可以正常播放。
3. `video.validation.json` 中没有明显失败信息。
4. `session.yaml` 已登记各条记录，标定目录包含 `time_offset.json` 和
   `alignment_report.png`。

### 补填或修改 task

采集结束（launch 已退出）后，用下面的命令补填或修改某个 session 的 task：

```bash
ros2 run umi_ros2 set_session_task recordings/online_session_<时间> "pick up the red cube"
```

- 只修改 `session.yaml`（原子写入），不会改动任何 MP4 或 MCAP。
- 旧版（`schema_version: 1`、没有 `task`）的 session 会同时升级为
  `schema_version: 2`。
- 传入 `""` 可以清空 task。
- 顶层 `task` 是后处理和导出唯一使用的 task。`recordings` 中每条记录的
  `task` 只是登记当时的快照，这个命令**不会改写**这些快照；快照为空说明
  task 是事后补填的。
- `status: active` 的 session 会被拒绝，因为可能还有 launch 正在写入。
  如果确认 launch 已经异常退出（状态没能改成 `complete`），可以加 `--force`。

## 15. 对齐在线 session

完成采集并获得通过验收的 `time_offset.json` 后，运行普通 Python 对齐工具：

```bash
python -m umi_ros2.postprocess.align_session \
  recordings/online_session_<时间>
```

它会处理 session 中所有普通 episode，不处理 calibration，并默认写入：

```text
processed/online_session_<时间>/
├── alignment_summary.json
└── episodes/
    └── episode_0001/
        ├── aligned_frames.npz
        ├── aligned_frames.csv
        └── alignment.json
```

工具以 MP4 的真实帧时间为主轴，应用已接受的时间差，对位置进行线性插值、
对姿态进行四元数 SLERP。超出 pose 覆盖范围或相邻 pose 间隔超过 0.1 秒的帧
会标为 invalid，不会外推。默认要求至少 95% 的视频帧有效。

`--offset-seconds` 只用于诊断尚未标定的数据。正式数据应读取 session 中
`accepted` 的标定结果。输出位于独立目录，不会修改 raw session。

## 16. 生成 episode 相对坐标、HDF5 或 LeRobot v3 数据集

正式处理已经通过验收时间差的在线 session 时，直接运行完整流程：

```bash
ros2 run umi_ros2 process_session \
  recordings/online_session_<时间> \
  --task "任务描述" \
  --format hdf5
```

如果 `session.yaml` 还没有 accepted 标定结果，可以加
`--run-calibration`，程序会先处理编号最小的 calibration；标定不通过时流程
会停止，不会继续生成正式数据。`--offset-seconds` 仅供诊断，不能代替正式标定。

默认输出结构：

```text
processed/online_session_<时间>/
├── aligned/                       # 世界坐标下逐视频帧 pose
│   ├── alignment_summary.json
│   └── episodes/episode_0001/
├── transformed/                   # episode 起点坐标下逐帧 pose
│   ├── transform_summary.json
│   └── episodes/episode_0001/
│       ├── episode_frames.npz
│       ├── episode_frames.csv
│       └── transform.json
├── dataset.hdf5                   # 选择 hdf5/both 时生成
└── lerobot/                       # 选择 lerobot/both 时生成
    ├── meta/                      # LeRobot v3 元数据与 episode 索引
    ├── data/                      # Parquet 状态、时间戳和索引
    ├── videos/                    # 按 episode 保存的视频
    └── umi_export.json            # 本项目补充的导出说明
```

每条 episode 的第一条有效视频帧 pose 被定义为原点。后续位置和姿态都表示为
相对于该原点的变换。无效帧不会被补值，默认不写入最终 HDF5。HDF5 中每个
episode 包含逐帧 JPEG 图像、`[x,y,z,qx,qy,qz,qw]` pose、原视频帧号、视频
PTS 和 pose 查询时间。可以用 `--jpeg-quality` 调整图像压缩质量。

同时生成 HDF5 和 LeRobot v3：

```bash
ros2 run umi_ros2 process_session \
  recordings/online_session_<时间> \
  --task "任务描述" \
  --format both \
  --repo-id local/umi_demo
```

只生成 LeRobot 时使用 `--format lerobot`。默认会调用
`~/umi_lerobot_venv312/bin/python`；环境在其他位置时增加
`--lerobot-python /实际路径/bin/python`。LeRobot 输出使用官方 v3 API，图像
保存为视频，状态为 episode 起点坐标系下的
`[x,y,z,qx,qy,qz,qw]`。同时保留源视频帧号、真实视频 PTS 和 pose 查询时间。
LeRobot 自身的 `timestamp` 是按导出帧序号和 `--fps` 生成的固定频率时间轴。

当前没有可靠的机器人 action/夹爪控制量，因此导出器不会伪造 `action` 字段；
后续确定 action 语义后再独立扩展 schema。

需要单独调试某个阶段时，可分别运行：

```bash
ros2 run umi_ros2 align_session <raw_session> --output <aligned_dir>
ros2 run umi_ros2 transform_session <aligned_dir> --output <transformed_dir>
ros2 run umi_ros2 export_hdf5 <transformed_dir> --output <dataset.hdf5>
PYTHONPATH=~/Documents/UMI/umi_ros2 \
  ~/umi_lerobot_venv312/bin/python -m umi_ros2.postprocess.export_lerobot \
  <transformed_dir> --output <lerobot_dir> \
  --repo-id local/umi_demo --task "任务描述"
```

三个阶段通过磁盘文件契约连接，不会相互调用内部算法。修改时间标定、插值、
坐标变换或导出格式时，可以只替换对应阶段。HDF5 与原生 LeRobot v3 exporter
都读取同一份 `transformed/` 契约，互不依赖。

## 17. 检查 pose 记录

每条标定或 episode 的 pose 都可以使用下面的命令检查：

```bash
ros2 bag info recordings/<会话目录>/episodes/episode_<编号>/pose
```

正常情况下应包含：

```text
/vive/pose
/tf
/tf_static
```

`/vive/path` 只用于 RViz2 显示，不会保存到数据中。

## 18. 回放 session 或单条数据

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

回放预览默认是 1280×720。若电脑性能足够，可以改为原视频的 1920×1080：

```bash
ros2 launch umi_ros2 replay.launch.py \
  input_path:=recordings/online_session_<时间> \
  preview_width:=1920 preview_height:=1080
```

如果 RViz 播放卡顿，可改用 `preview_width:=640 preview_height:=360`。
预览分辨率只影响回放显示，不会修改 MP4 或实时采集设置。回放默认按视频原有
约 30 fps 展示；不能通过调高预览参数生成原视频没有的帧。

回放会直接读取每条数据的 `video.mp4`，同时播放对应的 `pose/`，在 RViz2
显示图像、Vive 路径和 TF。切换到下一条数据前会清空上一条路径。当前回放
保留原始视频与 pose 的记录起点关系，但不会自动应用 `time_offset.json`。

## 19. 只观察，不录制

只检查在线相机和 Vive 显示：

```bash
ros2 launch umi_ros2 online_view.launch.py
```

只检查 Vive：

```bash
ros2 launch umi_ros2 vive.launch.py
```

## 20. 常见问题

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

## 21. 当前限制

- 在线连续 episode 和时间标定仍需 Action 4 真机验收。
- 正式后处理会自动读取 accepted 时间差并应用到普通 episode；回放显示仍不
  应用该时间差。
- 相机内参和相机到 Tracker 的刚性外参尚未完成。
- 回放尚未自动应用标定得到的 `time_offset.json`。
- HDF5 和 LeRobot v3 导出已经实现并完成软件级真实数据诊断，但尚未使用
  accepted 时间差的数据完成训练侧验收；LeRobot 中暂时没有 `action` 字段。

项目当前进度见 [project.md](project.md)。
