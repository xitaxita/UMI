# UMI 数据采集系统使用手册

本系统使用 DJI Action 4 和左侧 RealSense D435i 采集两路彩色视频，使用
Vive Tracker 采集夹爪位姿，并在 RViz2 中显示两路预览、Tracker 位姿和路径。

系统只提供在线采集：两台相机通过 USB 连接电脑；一次系统启动建立一个
session，其中可以连续保存标定数据和多条普通 episode。（原离线采集模式已按
D-021 删除。）

## 1. 已验证的运行环境

当前项目在以下环境中开发和验证：

- Ubuntu 24.04 LTS（当前机器为 24.04.5）。
- ROS 2 Jazzy Desktop。
- Python 3.12。
- Python 虚拟环境：`~/Documents/UMI/.venv`，创建时启用系统 Python 包。
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
cd ~/Documents/UMI
python3 -m venv --system-site-packages .venv
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
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
python --version
python -m colcon --help >/dev/null
python -c "import rclpy, gi, cv2, pysurvive; print('environment OK')"
command -v ffprobe
```

`which python` 应指向 `~/Documents/UMI/.venv/bin/python`，Python 应为 3.12。以后始终先
source ROS 2，再激活 venv；顺序不要颠倒。
`command -v ffprobe` 应返回可执行文件路径；它由系统 `ffmpeg` 软件包提供，
时序标定需要它读取 MP4 每帧时间戳。

### LeRobot v3 独立环境

LeRobot 的 NumPy、setuptools 和深度学习依赖与当前 ROS 2 Jazzy 环境不同，
不要把 LeRobot 安装进项目 `.venv`。需要导出 LeRobot v3 时，另建一个
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
source .venv/bin/activate
rosdep install --from-paths umi_ros2 --ignore-src -r -y
python -m colcon build --packages-select umi_ros2 --symlink-install
source install/setup.bash
```

构建后可以检查安装是否成功：

```bash
ros2 pkg executables umi_ros2
ros2 launch umi_ros2 online_record.launch.py --show-args
head -n 1 install/umi_ros2/lib/umi_ros2/vive_pose_node
```

最后一行应显示项目 `.venv/bin/python`。如果显示 `/usr/bin/python3`，请确认
激活 `.venv` 后重新运行上面的 `python -m colcon build`；仅显示 `(.venv)` 的
终端提示符不会改变已经生成的 ROS 节点脚本的解释器。

每次修改 Python 或 launch/config 文件后，建议重新执行 build 和
`source install/setup.bash`。`--symlink-install` 会让 Python 源码修改更方便，
但新文件、入口点和安装资源仍需要重新构建。

## 5. 每个新终端的环境准备

每次打开终端都执行：

```bash
cd ~/Documents/UMI
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
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

当前 Action 4 输入是 MJPEG 1920×1080/30 fps，D435i 左侧彩色输入是 YUYV
640×480/30 fps；两路分别编码为 H.264 MP4。默认配置使用各设备序列号对应的
`/dev/v4l/by-id` 链接，避免插拔后 `/dev/videoN` 变化。

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

`vive.launch.py`、`online_view.launch.py` 和 `online_record.launch.py` 都会
分别启动 `vive_pose_node` 与 `vive_path_node` 两个进程。pose 和 TF 的目标
发布频率为 90 Hz；Path 节点缓存最新 pose，每秒采样并更新轨迹 30 次，
最多保留 10000 个显示点。显示抽样不会降低 MCAP 中原始 pose 的记录频率。

轨迹配置位于同一 `vive.yaml` 的 `vive_path_node` 部分：

```yaml
vive_path_node:
  ros__parameters:
    pose_topic: vive/pose
    path_topic: vive/path
    sample_hz: 30.0
    max_path_points: 10000
```

修改采样频率后重启 launch 生效。没有新 pose 时不会重复追加轨迹点。

确认 pose 持续更新后，按 `Ctrl+C` 结束检查。

正常采集不需要使用 `--force-calibrate`。只有首次配置、移动过基站、标定文件
丢失或明确需要重建世界坐标系时，才在 `vive.yaml` 中临时设置：

```yaml
libsurvive_args: "--force-calibrate"
```

重新标定完成后，应将它恢复为空字符串。

### Tracker 到夹爪 TCP 的外参

`/vive/pose`、`/vive/path` 和 `gripper_tcp` TF 都是在 Tracker 位姿上叠加一个
固定外参得到的。这个外参**只写在** `umi_ros2/config/vive.yaml` 中：

```yaml
tracker_to_tcp_translation_m: [0.0, -0.194899844, 0.080510987]   # 米
tracker_to_tcp_rotation_xyzw: [0.457263310, 0.0, 0.0, 0.889331359]
```

当前值于 2026-10-04 按
`/media/xing/zijun/User/Documents/课题组/UMI/3Dprint/UMI/co2_in_co1.txt`
更新，co1 对应 `vive_tracker`、co2 对应 `gripper_tcp`，直接使用文件的
`translation_m` 和 `quaternion_xyzw`。项目根目录同名 txt 是历史测量文件。
配置更新只对重启后的新 TCP 发布生效，已录制 raw pose 不会自动改成新外参。

- 节点启动时读取并检查：缺少、个数不对、不是有限数或四元数不是单位长度时，
  节点直接报错退出，不会用默认值。每个数都要写成带小数点的形式。
- 重新标定后修改 `vive.yaml` 并重启 Vive 即可（`--symlink-install` 构建时无需
  重新 build）。启动日志会打印 `Loaded vive_tracker->gripper_tcp extrinsic`。
- 运行中也可以临时调整，通过检查后下一帧起生效：

```bash
ros2 param set /vive_pose_node tracker_to_tcp_translation_m "[0.0, -0.194899844, 0.080510987]"
```

  这样修改**不会写回** `vive.yaml`，重启后恢复文件中的值；不合法的值会被拒绝，
  继续使用原值。平移和旋转是分两次设置的，两次之间会有一帧左右只更新了其中一个，
  所以不要在录制时调整。

## 8. 在线采集前准备

1. 用 USB 连接 Action 4 和 D435i；D435i 使用 USB 3 连接。
2. 在 Action 4 上选择 Webcam 模式。
3. 运行下面的命令确认两台相机设备：

```bash
v4l2-ctl --list-devices
```

4. 核对 `umi_ros2/config/action4.yaml` 的设备链接，以及
   `umi_ros2/config/realsense_left.yaml` 的 `serial` 和
   `color_usb_interface`（D435i 彩色接口为 `03`）。RealSense 默认按序列号
   和接口自动寻找彩色端口，避免 `by-id ...video-index0` 误指向深度流。
   启动时可分别用
   `video_device:=/dev/videoN` 和 `left_video_device:=/dev/videoM` 临时覆盖。
5. 在线采集期间不要让 Action 4 同时向 microSD 录像。

## 9. 启动在线采集

一个 session 只对应一个任务（task），session 中可以录多条 episode；换任务就
开新的 session。task 是一句自然语言指令，之后会直接作为 LeRobot 数据集的语言
task。推荐启动时就用 `task:=` 写明：

```bash
ros2 launch umi_ros2 online_record.launch.py task:="pick up the red cube and place it in the box"
```

Action 4 标记为 `wrist` / `wrist_image`，D435i 彩色流标记为 `left` /
`left_image`。两路图像写入不同视频文件和 timing；录制索引中的
`image_streams` 保存字段与路径的对应关系。不采集深度或红外。

`task:=` 可以不填：

```bash
ros2 launch umi_ros2 online_record.launch.py
```

不填时终端会给出黄色警告，并打印补填命令；此时 `session.yaml` 中的
`task` 为空，导出数据集前必须补上（见下文“补填或修改 task”）。task 只写在
`session.yaml` 里，session 目录名不包含 task，仍是 `online_session_<时间>`。

系统会启动 Action 4、D435i 彩色流、Vive、常驻 pose recorder 和 RViz2。
两台相机与 pose recorder 在本次启动中各预热一次，默认至少 5 秒。等待
RViz2 中出现两路画面、Tracker 和路径后再开始采集。在线预览为 Action 4
320×180、D435i 320×240；预览分辨率不会降低录制视频分辨率。

在第二个准备好的终端运行：

```bash
ros2 run umi_ros2 episode_keyboard
```

按键规则：

- 按 Enter：开始一条新 episode。
- 在等待状态输入 `c` 后按 Enter：列出相机；输入编号后开始该路标定。
- 再按 Enter：结束并保存当前 episode。
- 再按 Enter：开始下一条新 episode。
- 在等待状态输入 `n` 后按 Enter：结束当前 session，开始一个新 session（换
  任务）。程序会提示输入新 task，直接回车则 task 为空（之后用
  `set_session_task` 补填）。详见下文“在同一次启动中切换任务”。
- 输入 `q` 后按 Enter：只退出按键控制器，不停止整个系统。
- 在 Launch 终端按 `Ctrl+C`：结束整个在线系统。

结束普通 episode 后，等待终端显示 `episode complete`，再开始下一条。结束
标定记录后，系统立即运行**所选相机与 pose** 的时序标定。当前编号为
`1: wrist / wrist_image`、`2: left / left_image`（列表来自当前注册相机）。
通过时绿色显示 `accept` 和偏移量；失败时红色显示 `reject`，删除本次标定
视频、timing、validation、pose 和派生结果，保留目录。按 Enter 即在原目录
重录当前相机；`c` 可重新选择相机。每路标定结果独立保存。

等待状态下，图像只用于 RViz2 预览，pose recorder 维持订阅但不保存；录制
状态下，每条普通 episode 写入 wrist 的 `cameras/wrist/video.mp4`、左侧的
`cameras/left/video.mp4` 和一个共享的 `pose/`。开始时先确认新 pose bag
已写入第一条 pose，再等待 500 ms 后启动两路视频；这段时间只保存 pose，
相机保持打开。标定只录所选一路，其他相机继续预览。结束时视频完成封装和验证才登记为
`complete`。切换 episode 不会重启或重新预热相机和 pose recorder。

每条普通 episode 结束后自动诊断，终端显示绿色 `accept` 或红色 `reject`。
接受条件：两路 MP4 解码正常、帧数匹配、时间戳完整且递增、无超过 50 ms 的
帧间隔；pose 完整覆盖两路图像的原始时间范围，且平均频率至少 88 Hz。
零星 pose 间隔缺帧不会单独导致拒绝。结果保存在该 episode 的 `quality.json`，
拒绝时标记 `exclude_from_dataset: true`；目前该标记供后续整理使用，导出器
尚未自动过滤。无需增加启动参数，停止服务返回后即可开始下一条。

### 在同一次启动中切换任务

换任务时有两种方式，得到的 session 结构完全一样：

1. **不重启**：在按键控制器的等待状态输入 `n` 并回车，再输入新任务的
   task。相机、Vive 和 pose 订阅都不重启、不重新预热。
2. **重启**：在 Launch 终端按 `Ctrl+C`，再用新的 `task:=` 重新启动。

按 `n` 切换时：

- 正在录制时不能切换：按键控制器会提示“Recording continues”，录制继续，
  需要先按 Enter 结束录制。
- 旧 session 标记为 `complete`；新建 `online_session_<时间>/`，episode 编号
  从 `episode_0001` 重新开始。
- 旧 session 中所有已完成的标定录制会把**原始数据**（wrist 的
  `cameras/wrist/video.*`、左侧的 `cameras/left/video.*`、`pose/`）按原编号复制到新
  session，并在 `session.yaml` 中用 `copied_from` 注明来源（仅供追溯）。
  `time_offset.json`、`alignment_report.png` 等结果**不会复制**，新 session
  的标定状态为 `not_calibrated`，需要在新 session 里重新标定（见第 12 节）。
  因为复制会一直传下去，一次启动中每路相机只需要录制一次通过的标定；
  新 session 需对复制来的每路原始标定分别重新计算结果。
- 如果旧 session 没有标定数据，终端会提示本 session 没有标定，需要录一条。
- 在新 session 里再录标定时，编号接着往下排（例如 `calibration_002`）。
- 复制期间命令会等待，复制完成之前不会开始新的录制。复制失败时不会留下
  新 session，程序继续使用旧 session。

用 `Ctrl+C` 重启时不会复制任何标定，必须重新录制标定。

## 10. 生成时间标定图案

第一次使用前生成 ArUco 标记：

```bash
ros2 run umi_ros2 generate_aruco_marker \
  --output ~/Documents/UMI/aruco_id4.png
```

打印时保持正方形，建议黑色标记区域约为 60 mm × 60 mm，并在周围保留
白边。打印后可以长期重复使用。

## 11. 录制时间标定 episode

每次重新启动在线采集系统后，分别为 wrist、left 录制专用时间标定。
同一次 Launch 持续运行期间，普通 episode 不需要重复标定。

操作步骤：

1. wrist：将 ArUco 标记固定在桌面上，移动相机与 Tracker 组件；
   left：固定相机，将标记固定在 Tracker/夹爪上，标记与 Tracker 一起移动。
2. 确认标记在 RViz2 相机画面中完整、清晰可见。
3. 在按键控制器中输入 `c` 后按 Enter，选择相机编号并回车，开始标定。
4. 保持夹爪静止约 2 秒。
5. 让夹爪左右往返移动 3～5 次。
6. 再沿前后方向往返移动几次，然后沿上下方向往返移动几次。
7. 移动过程中保持标记完整可见，避免手遮挡标记。
8. 再次保持静止约 2 秒。
9. 按 Enter 结束，并等待即时标定结果。
10. 通过时绿色显示 `accept` 和 video-to-pose 偏移量；失败时红色显示
    `reject`、清除本次记录并要求重录。直接 Enter 在同一目录重录；`c` 选择
    另一相机。本相机旧的 accepted 状态会失效，其他相机的结果保留。

每次标定仍先保存 pose，再等待 500 ms 开始该路视频。标定使用 pose header
绝对时间和“首帧接收时间 + 视频 PTS”，保留实际的起始差；500 ms 仅是录制
缓冲，不会被强行加到或从标定延迟中减去。

移动时应有明显转折，但不要快到画面严重模糊。当前标定器只使用标记的
水平/垂直中心与面积，以及 TCP 的 X/Y/Z 平移，不使用标记角度或 TCP 旋转。
建议左右、前后、上下三个方向都做几次不同幅度和速度的往返，并穿插停顿，避免
完全周期重复。短暂遮挡可以接受，但应尽量让标记持续完整可见。

## 12. 检查时间差结果

新录制的标定会自动运行估计器，并在按键控制终端显示结果。通过时目录保留：

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
4. 如果显示 rejected/failed、`accepted` 为 `false`，或者曲线明显没有对齐，应
   重新录制标定 episode，不要继续使用该结果。

如果需要对 `n` 切换 session 复制来的标定单独计算，可在另一个终端手动运行：

```bash
ros2 run umi_ros2 calibrate_time \
  recordings/online_session_<时间>/calibration/calibration_001
```

标定程序会把结果路径和状态写入本次 session 的 `session.yaml`。之后的对齐和
数据集导出（第 15、16 节）目前仍处理 wrist，会自动读取其 accepted 时间差。
每路结果分别保存于 `temporal_calibrations.<camera_id>`；原来的
`temporal_calibration` 保留为 wrist 的兼容字段。单路录像自动识别相机，也可
用 `--camera-id left` 显式选择；多视角对齐与数据集导出尚待后续阶段。
每个 session 都要有自己 accepted 的结果：用 `n` 切换出来的新 session 带有复制
来的标定录像，但仍需在新 session 里对它运行一次标定（新录制 calibration
会自动完成；复制来的每路 calibration 分别使用上面的手动命令）。

## 13. 录制普通在线 episode

时间标定通过后，可以重复采集普通任务：

1. 整理场景，并将夹爪放到起始位置。
2. 按 Enter 开始 episode。
3. 完成一次完整操作。
4. 按 Enter 结束 episode。
5. 等待 `episode complete`。
6. 检查终端没有相机、Vive 或写盘错误。
7. 整理下一次场景，然后重复以上步骤。

一个 session 的完整数据结构为（一次启动中用 `n` 切换会依次产生多个这样的 session）：

```text
recordings/online_session_<时间>/
├── session.yaml
├── calibration/
│   ├── calibration_001/                # wrist 独立标定
│   │   ├── cameras/wrist/              # video.mp4 + timing + validation
│   │   ├── time_offset.json
│   │   ├── alignment_report.png
│   │   └── pose/
│   └── calibration_002/                # left 独立标定
│       ├── cameras/left/
│       │   ├── video.mp4
│       │   ├── video.timing.json
│       │   └── video.validation.json
│       ├── time_offset.json
│       ├── alignment_report.png
│       └── pose/
└── episodes/
    ├── episode_0001/
    │   ├── cameras/wrist/               # video.mp4 + timing + validation
    │   ├── cameras/left/                # video.mp4 + timing + validation
    │   ├── quality.json                 # accept/reject 与排除标记
    │   └── pose/
    └── episode_0002/
```

## 14. 结束在线采集

推荐先结束当前 episode 并等待 `episode complete`，然后在 Launch 终端按
`Ctrl+C`。等待所有进程退出后再关闭终端、拔出相机或关闭电源。

采集结束后至少检查：

1. 每条 episode 都有 `cameras/wrist/video.mp4`、
   `cameras/left/video.mp4` 和 `pose/`。
2. 两个 MP4 都可以正常播放。
3. 两份 `video.validation.json` 中都没有明显失败信息。
4. `session.yaml` 已登记各条记录，`task` 不为空（为空时用
   `set_session_task` 补填，见下文）。
5. 运行 `calibrate_time`（第 12 节）后，标定目录包含 `time_offset.json` 和
   `alignment_report.png`。

当前回放可显示两路图像，时间标定可分别处理 wrist 和 left；数据集导出
目前仍只使用 wrist 图像。旧录制仍可读取根目录 `video.mp4`。
`left_image` 的多视角数据集导出将在后续阶段接入。

用 `n` 切换过任务时，一次启动会产生多个 session，每个都要按上面检查。

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

正式生成数据集时，`build_dataset`（第 16 节）会自动完成对齐，不需要单独运行
本节命令。本节用于单独检查某个 session 的对齐结果。

完成采集并获得通过验收的 `time_offset.json` 后，运行对齐工具：

```bash
ros2 run umi_ros2 align_session \
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

### 独立展开到 90 Hz（D-041，当前分模块实现阶段）

两路相机已有 accepted 时差后，可单独运行：

```bash
ros2 run umi_ros2 expand_session \
  recordings/online_session_<时间> \
  --output processed/online_session_<时间>/expanded
```

也可输入该 session 的一条普通 episode。工具按每路首帧接收时间 + 视频实际
PTS + 各自 offset 配对图像，每组三个 90 Hz 样本各引用同一 wrist/left 源帧，
对真实 pose 时间进行位置线性插值和四元数 SLERP。默认图像配对容差为
16.667 ms；无效整组保留时间槽，报告配对误差、有效比例和未使用的源帧。
图像重复目前用源帧号表示，raw MP4 不复制或重编码。

输出含 `expansion_summary.json`，每条 episode 下有 `expanded_frames.npz`、
`expanded_frames.csv` 和 `expansion.json`。Pose 暂保留世界系 XYZ + XYZW，
同时保存 raw 首条 TCP 参考；下面的独立模块做相对坐标变换，state/action 留给后续。
**本阶段尚未接入 `build_dataset` 和两个 exporter**；下文现有导出命令继续使用
旧单视角契约，不能直接读取该展开结果。URDF IK 暂不实施。

### 独立转换到 episode 起点坐标系（D-041）

完成上一步展开后运行：

```bash
ros2 run umi_ros2 localize_session \
  processed/online_session_<时间>/expanded \
  --output processed/online_session_<时间>/local
```

也可直接输入 `expanded/episodes/episode_0001`，此时 `--output` 指定该条 episode
的输出目录。输入为展开结果，不是 raw session；无需重新读取图像或 pose MCAP。
不指定输出时，会在输入旁生成 `<输入目录名>_local`。

每条 episode 使用其原始 pose 流首条保存的 TCP pose 定义固定参考：
`T_local_i = inverse(T_world_start) * T_world_i`。初始位置决定原点，初始朝向
决定 XYZ 轴，后续旋转不会改变参考。t=0 参考早于图像开始，因此首条展开 pose
可以非零。缺少起点参考时报错，不回退到首图像或首展开样本。

输出 `local_pose_summary.json`；每条 episode 有 `local_frames.npz`、
`local_frames.csv` 和 `local_pose.json`。NPZ 的 `position_xyz` 和
`orientation_xyzw` 是相对 XYZ + XYZW，单位为米；四元数归一化且符号连续。
保留 `world_position_xyz`、`world_orientation_xyzw`、world 起点参考、90 Hz
时间轴、两路源帧号及有效性标记。图像 invalid 但 pose 有效时仍转换该 pose；
pose 缺口保留 NaN，不删条目或压缩时间。CLI 返回 0 表示成功，1 表示失败，
2 表示坐标转换完成但源展开被 rejected。`--overwrite` 只允许覆盖该模块自己的
输出。**本步骤不生成 state/action，尚未接入新版导出和 `build_dataset`。**

### 多个 session 合并成一个数据集（推荐）

每个 session 对应一个任务。用 `build_dataset` 可以把多个 session（可以是不同
任务）合并成同一个数据集：

```bash
ros2 run umi_ros2 build_dataset \
  recordings/online_session_<时间1> recordings/online_session_<时间2> \
  --format both --repo-id local/umi_demo \
  --output datasets/umi_demo
```

- 输入可以是具体的 session 目录，也可以是包含多个 session 的目录（例如整个
  `recordings/`，按目录名即时间顺序处理）。
- task 从各自的 `session.yaml` 读取，没有 `--task` 参数。
- 每个 session 独立完成标定、对齐和坐标变换，只在导出这一步合并；不会跨
  session 使用标定结果。
- 每次运行都会按给定的 session 列表**从头重建**，不做增量追加。先在
  `<output>.partial` 中生成，全部成功后才替换 `<output>`；已存在的输出需要加
  `--overwrite`，且只会替换之前由 `build_dataset` 生成（含
  `build_manifest.json`）的目录。
- `--run-calibration`：对还没有 accepted 标定的 session，用它**编号最大（最新）**
  的一条 calibration 现场运行 `calibrate_time`；已经 accepted 的 session 直接用
  自己的结果。
- 帧率从视频的真实帧间隔测得，LeRobot 使用该帧率。

导出前会做统一检查，任何一项不满足都会**整体失败**，并指出是哪个 session、
什么原因：task 不为空；标定为 accepted；至少有一条普通 episode；每条 episode
对齐结果为 accepted；所有 episode 的图像尺寸和帧率一致；中间结果的 contract
版本一致。失败时中间结果保留在 `<output>.partial` 中便于检查。

输出结构：

```text
datasets/umi_demo/
├── build_manifest.json            # 来源 session、task、offset、帧率等
├── processed/
│   ├── dataset_plan.json          # 导出计划（episode → task / 来源）
│   └── online_session_<时间>/
│       ├── aligned/
│       └── transformed/
├── dataset.hdf5                   # 选择 hdf5/both 时生成
└── lerobot/                       # 选择 lerobot/both 时生成
```

HDF5（`format_version` 2）中 episode 在整个数据集中统一编号
（`episode_0000`…），每个 episode 组的属性包括 `task`、`task_index`、
`source_session`、`source_episode` 和 `video_to_pose_offset_seconds`；根目录的
`tasks` 数据集按 `task_index` 存放 task 字符串（按首次出现顺序），根目录不再有
单一的 `task` 属性。LeRobot v3 中每帧的 `task` 来自所属 session，LeRobot 自动
生成 `tasks.parquet` 和 `task_index`；每帧另有 `umi.source_session`；
`umi_export.json` 列出所有来源 session、task 和各自的 offset。

### 只处理一个 session

同样使用 `build_dataset`，只给一个 session 即可：

```bash
ros2 run umi_ros2 build_dataset \
  recordings/online_session_<时间> \
  --format hdf5 --output datasets/<名称>
```

- 需要指定用哪一条 calibration 时，先对该目录直接运行 `calibrate_time`（见第 12
  节），再运行 `build_dataset`。
- 需要修改 task 时，用 `set_session_task`。
- 需要用手动 offset 诊断时，按下文分阶段运行 `align_session --offset-seconds`；
  这种结果不能代替正式标定。

### 数据内容

每条 episode 以 Enter 开始录制后首条保存的 TCP pose 定义参考坐标系，
位置设定原点、初始朝向设定固定轴。参考 pose 在图像延迟 500 ms 之前，
因此首张图像对应的相对 pose 可以非零。标定也使用这个参考系下的 XYZ；
初始朝向只用于坐标转换，不作为旋转运动特征。Raw bag 保留世界系源数据。
无效帧不会被补值，也不会写入最终数据。HDF5 中每个
episode 包含逐帧 JPEG 图像、`[x,y,z,qx,qy,qz,qw]` pose、原视频帧号、视频
PTS 和 pose 查询时间。可以用 `--jpeg-quality` 调整图像压缩质量。

LeRobot 导出默认调用 `~/umi_lerobot_venv312/bin/python`；环境在其他位置时增加
`--lerobot-python /实际路径/bin/python`。LeRobot 输出使用官方 v3 API，图像
保存为视频，状态为 episode 起点坐标系下的 `[x,y,z,qx,qy,qz,qw]`。同时保留源视频
帧号、真实视频 PTS 和 pose 查询时间。LeRobot 自身的 `timestamp` 是按导出帧序号和
视频实测帧率生成的固定频率时间轴。

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

回放读取每条数据的 `cameras/<camera_id>/video.mp4`（旧录制可在根目录
`video.mp4`），同时播放对应的 `pose/`，在 RViz2 显示各路图像、当前
Vive TCP pose、路径和 TF。切换到下一条数据前会清空上一条路径。默认按原始
记录时间回放；如需按逐相机已接受的标定时差显示，可运行：

```bash
ros2 launch umi_ros2 replay.launch.py \
  input_path:=recordings/online_session_<时间>/episodes/episode_0001 \
  use_calibration:=true loop:=true preview_width:=640 preview_height:=360
```

此模式要求该 session 中每路相机都有 accepted 标定；短 episode 会循环播放，
按原视频实际帧时间（约 30 fps）显示。按 Ctrl+C 结束回放。

### 逐帧视觉检查 image / pose 对齐

在项目根目录运行：

```bash
ros2 run umi_ros2 frame_alignment_viewer recordings/online_session_<时间>
```

省略路径时打开 `recordings/` 下最新 session。窗口默认显示第一条 episode；
顶部可切换 episode、各相机的 calibration 和逐帧参考相机。

- **Space / → / 下一帧按钮**：前进一张参考相机的图像。
- **← / 上一帧按钮**：后退一帧；拖动滑条可跳到任意帧。
- 勾选“应用标定时差”默认启用；取消可对比未经校正的原始时间。
- 两路图像、三维 TCP 轨迹/姿态坐标轴、XYZ 曲线游标在同一次绘制中更新。

查看器直接读取 MP4 和 pose MCAP，不发布 ROS 图像或 pose 话题。
每张参考图像按 `first_receive_unix_ns + 实际 PTS + 该相机标定时差`
插值得到 pose，坐标系使用录制起点的首条 pose；500 ms 前置缓冲保留在
原始时间戳中。另一相机选校正时间最接近的一帧，标题的 `delta` 表示两图
时间差，三维图中两种颜色的圆点各对应自身图像的 pose。超出相机时间范围
显示空白；pose 无覆盖或采样间隔超过 100 ms 时明确标为无效。
要求所展示的相机已有 accepted 标定；关闭窗口结束查看，不修改 raw 文件。

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

1. 确认 Action 4 已选择 Webcam 模式，D435i 接在 USB 3 端口。
2. 运行 `v4l2-ctl --list-devices`，确认两个彩色流对应的设备路径。
3. 检查 `action4.yaml` 的设备链接，以及 `realsense_left.yaml` 的序列号
   和 RGB 接口。若传入 `left_video_device`，它会覆盖自动识别，须指向
   支持 YUYV 的彩色端口。
4. 确认没有其他程序正在占用任一相机。
5. 启动后如果相机进程提示 `No frames from /dev/videoN`，表示 V4L2
   没有收到首帧。重新在 Action 4 上选择 Webcam 模式并重连 USB，再启动。
   可用 `timeout 8s v4l2-ctl -d /dev/videoN --stream-mmap
   --stream-count=30 --stream-to=/dev/null` 独立检查是否真的送帧。
6. 如果 `/action4/image_preview` 已有消息但 RViz 没有画面，检查 RViz
   进程是否退出；图形界面崩溃与相机无帧应分别排查。
   左侧相机的话题是 `/realsense/left/image_preview`。

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

如果提示 `ffprobe` 不存在，先安装系统软件包 `ffmpeg`，然后对刚保存的标定目录
重新运行 `ros2 run umi_ros2 calibrate_time <标定目录>`。这一类工具缺失不会
损坏 MP4 或 MCAP，也不需要先重新录制。若录制时生成的
`video.validation.json` 因缺少 `ffprobe` 标为 `decode_ok: false`，该字段仅反映
当时未完成验证；补齐工具后可用 `ffprobe` 检查已保存的视频。

```bash
sudo apt-get install ffmpeg
ffprobe -version
```

1. 确认 ArUco ID 4 在大部分画面中完整可见。
2. 增加左右移动距离，并确保存在 3～5 个明显往返。
3. 降低运动速度，避免标记模糊。
4. 确认标定 episode 同时包含视频和 pose。
5. 重新录制标定 episode，不要手工修改失败结果。

### Ctrl+C 退出时 Vive 报 `KeyboardInterrupt`

按 `Ctrl+C` 结束后，终端可能显示 `vive_pose_node` 的 `KeyboardInterrupt`
（位于 `simple_close`）和 `process has died ... exit code -2`。这是已知的退出
问题，只发生在关闭阶段，不影响已保存的视频和 pose 数据。请始终先按 Enter
结束录制、等到 `episode complete` 后再按 `Ctrl+C`。

### `build_dataset` 失败

错误信息会逐个列出不满足条件的 session 和原因，例如 task 为空、标定不是
accepted、没有 episode、对齐有效帧不足、图像尺寸或帧率不一致。按提示修正后
重新运行即可；中间结果保留在 `<output>.partial` 中，可用于检查。

## 21. 当前限制

- 在线连续 episode、`n` 切换 session 和时间标定都已完成软件验证，但仍需
  Action 4 + Vive 真机验收。
- `build_dataset` 已用真实标定录像完成软件级合并导出验证，但还没有真实的多任务
  episode 数据，也没有完成训练侧验收；LeRobot 中暂时没有 `action` 字段。
- 每路相机在一个 session 中使用一个常数时间差，不建模时钟漂移。回放可用
  `use_calibration:=true` 应用逐路差值；当前数据集对齐和导出仍只处理 wrist。
- 相机内参和相机到 Tracker 的刚性外参尚未标定。
- 录制分支不会主动丢帧，但无法证明相机源端没有丢帧
  （`source_completeness: not_verified`）。

项目当前进度见 [project.md](project.md)。
