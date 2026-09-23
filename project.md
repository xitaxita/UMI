# UMI 项目看板

> 核对时间：2026-09-21。依据当前工作区源码、配置、测试和真实 session 诊断核对。ROS 包版本：`umi_ros2 0.2.0`。

## 项目目标与当前重点

DJI Action 4 与 Vive Tracker 刚性安装在同一夹爪上，分别采集视频和六自由度位姿，之后校正时间差并生成机器人学习数据。离线（相机录到 microSD）是主方案；在线（相机 USB Webcam）是独立方案，不同时使用 microSD 录像。

当前已有从在线 raw session 到 HDF5 和原生 LeRobot v3 的完整模块化软件链路；真实 accepted 时间标定、action 语义和训练侧 schema 验收仍待完成。

## 现在可以做什么

| 能力 | 当前实现 | 验证边界 |
| --- | --- | --- |
| Vive 定位 | pysurvive 选取 Tracker；`/vive/pose` 和 `/vive/path` 表示夹爪 TCP，`/tf` 同时发布 `vive_world → vive_tracker` 与 `vive_world → gripper_tcp`；默认发布定时器 90 Hz | 数学组合和软件测试通过；两个 TF 及夹爪末端位置等待用户真机检查 |
| 在线观察 | `online_view.launch.py` 启动 Vive、Action 4 和 RViz2，不创建正式在线 episode | launch/软件检查通过；设备须处于 Webcam 模式 |
| 在线采集 | `online_record.launch.py` 创建一个 session；键盘服务可依次录 calibration 和多条 episode | 软件实现与测试通过；新版常驻 pose recorder 尚未完成 Action 4 + Vive 多 episode 真机验收 |
| 离线采集 | `offline_record.launch.py` 仅记录 Vive pose/TF MCAP，RViz 显示路径；相机自行录 SD 卡 | 单次 pose-only 基础版；完整硬件和视频导入验收待做，无离线多 episode 控制 |
| 在线回放 | `replay.launch.py` 可读取一条 calibration/episode，或按 calibration→episodes 顺序读整个 session；回放预览默认 1280×720，可选原视频 1920×1080 | 1× 无 RViz 进程实测可发布 443/468 帧；RViz 实际画面和整场 session 仍待观察 |
| 时间差估计 | `generate_aruco_marker` 和多特征 `calibrate_time` 使用 ArUco 中心/尺度/角度与 TCP 平移/旋转估计常量时间差，并检查分段一致性 | 53 项测试通过；一条真实 calibration 得到 -95.01 ms、分段标准差 4.14 ms 并通过软件验收，仍需跨次重复验证 |
| 逐帧对齐 | `align_session` 用 MP4 真实 PTS、已接受的 offset 和 Vive MCAP 插值得到每帧 pose | 软件测试及零 offset 真实数据诊断通过；尚未以真实 accepted offset 验证 |
| Episode 坐标变换 | `transform_session` 将每条 episode 第一条有效帧 pose 设为原点，写出版本化 NPZ/CSV/JSON | 数学单测和真实 session 零 offset 诊断通过；未用 accepted offset 验收 |
| HDF5 数据集导出 | `export_hdf5` 保存逐帧 JPEG、相对 7D pose、帧号和时间戳；`process_session` 串联全部阶段 | 真实 session 两条 episode 共 396 样本导出并回读通过；该次使用零 offset，仅验证软件链路 |
| LeRobot v3 导出 | `export_lerobot` 使用官方 `LeRobotDataset` API 写 Parquet、MP4 和 metadata；`process_session --format lerobot/both` 用独立环境调用 | 真实 session 两条 episode 共 396 帧导出并由 LeRobot 0.4.4 回读；零 offset 仅验证软件链路，尚无 action 字段 |
| Tracker→夹爪 TCP 外参 | `gripper_extrinsics.yaml` 和 Vive pose 节点已同步 2026-09-21 重新标定的固定变换；节点在 `/vive/pose`、`/vive/path` 和 TCP TF 前应用它 | 矩阵/四元数数值一致性通过；`/tf` 同时保留原始 Tracker frame 和转换后的 TCP frame，真机方向待重新检查 |

## 当前在线采集怎样运行

`online_record.launch.py` 启动 Vive pose 节点、Action 4 采集节点和 RViz2。采集节点内部启动两个子进程：持续打开 UVC 的 GStreamer 相机 worker，以及持续订阅 `/vive/pose`、`/tf`、`/tf_static` 的 ROS pose recorder。默认相机和 pose 都预热至少 5 秒且各只预热一次；预热中的数据不保存。随后：

1. **waiting**：相机持续提供 RViz 预览；pose recorder 保持订阅但不写 bag。
2. 在另一终端运行 `ros2 run umi_ros2 episode_keyboard`。Enter 开始普通 episode；`c`+Enter 开始专用 calibration。
3. 每次开始都创建新目录并打开本条独立的 `pose/` MCAP；等第一条 `/vive/pose` 实际写入后才打开 MP4。
4. 录制中继续预览；再按 Enter 时先结束 MP4，再关闭该条 pose bag，回到 waiting。相机和 pose 订阅都不重启。退出整个 launch 才结束 session。

相机输入是 Action 4 UVC MJPEG 1920×1080/30 fps；当前 GStreamer worker 将其编码为 H.264 MP4。默认视频码率参数为 12000 kbps；预览为 640×360、最多 15 fps、best-effort。预览分支可以丢弃旧帧；录制分支没有设计为主动丢帧，但 **MP4 可解码和帧数匹配不等于相机源端绝无掉帧**。每条记录的 `video.validation.json` 将源端完整性标为 `not_verified`。

`video.timing.json` 保存源 PTS 与主机收到首帧的时刻；这不是曝光时间，也不是已经完成的硬件时钟同步。首帧“在 pose 之后开始”只建立记录边界，不能替代时间标定。

### 在线文件结构

```text
recordings/online_session_<时间>/
├── session.yaml                         # 状态、条目索引、标定结果索引
├── calibration/
│   └── calibration_001/
│       ├── video.mp4
│       ├── video.timing.json
│       ├── video.validation.json
│       ├── pose/                        # metadata.yaml + *.mcap
│       ├── time_offset.json             # 仅运行 calibrate_time 后出现
│       └── alignment_report.png         # 同上
└── episodes/
    └── episode_0001/
        ├── video.mp4
        ├── video.timing.json
        ├── video.validation.json
        └── pose/                        # 每条独立 MCAP
```

`/vive/path` 只作 RViz 可视化，不记录；需要时可从 `/vive/pose` 重建。在线记录不保存 Action 4 内部 IMU，也不把完整原始图像逐帧写入 ROS bag。

## 离线模式现状

`offline_record.launch.py` 创建新的 `offline_session_<时间>/`、`session.yaml` 和预留的 `calibration/`，等待默认 3 秒后通过 `ros2 bag record` 将 `/vive/pose`、`/tf`、`/tf_static` 记录到会话根下的 `pose/`。它只启动 Vive 和 pose/path RViz，**不接入 Action 4 USB**。相机应独立以 4K/60 fps、关闭电子防抖的设置录到 microSD，结束后由操作者把相应视频复制为根目录 `video.mp4`。代码目前没有自动 SD 导入、离线 episode 切换或离线时间标定流程。

```text
recordings/offline_session_<时间>/
├── session.yaml
├── calibration/          # 当前仅预留
├── pose/                 # MCAP，由电脑采集
└── video.mp4             # 由操作者事后复制；采集时不存在
```

## 标定、回放与后处理的边界

- 在线 calibration 使用固定 ArUco `DICT_4X4_50`、ID 4，配合重复左右运动；`calibrate_time` 写入 `time_offset.json`、`alignment_report.png`，并更新该在线 session 的 `session.yaml`。一条通过检查的结果只计划用于同一次未中断的在线 session；相机/Vive 重启、重新连接或时钟不连续后不能沿用。
- `replay.launch.py input_path:=...` 从 `video.mp4` 和相应 `pose/` 回放；session 输入先按编号回放 calibration，再按编号回放普通 episode。回放按记录时刻显示，**尚不应用 `time_offset.json`**。
- 回放预览现默认 1280×720，可通过 `preview_width`/`preview_height` 选择 1920×1080 或较低分辨率；rosbag `/clock` 更新频率为 120 Hz。原视频约 30 fps，显示参数不会提高源帧率，也不修改在线录制/实时预览。
- `align_session` 是不启动 ROS graph 的 Python 后处理命令，但读取 MCAP 仍需 ROS Python 消息库。它只处理普通在线 episodes；默认要求 `session.yaml` 引用的真实 `time_offset.json` 标为 `accepted`。显式 `--offset-seconds` 可用于诊断，不代表标定通过。
- 对齐按视频实际 PTS 为主轴，位置线性插值，四元数最短路径 SLERP。超出 pose 覆盖或跨越默认 0.1 秒 pose 间隔的帧标为 invalid；默认至少 95% 帧有效才接受该 episode。输出在独立 `processed/<session名>/episodes/<episode名>/` 下，含 `aligned_frames.npz`、`aligned_frames.csv`、`alignment.json`，另有会话 `alignment_summary.json`；不覆盖原始记录。
- `transform_session` 只读取对齐结果，以第一条有效视频帧 pose 为参考，计算 `T_episode_i = inverse(T_world_0) * T_world_i`。`export_hdf5` 与 `export_lerobot` 都只读取这一版本化中间结果和源 MP4；`process_session` 只负责依次调用阶段，不包含算法。
- HDF5 每条 episode 保存 JPEG 压缩图像、相对 pose、视频 PTS、pose 查询时间和源帧索引。LeRobot v3 保存视频、Parquet 状态和 metadata，并额外保留真实 PTS、pose 查询时间和源帧号。invalid 帧在两个导出器中都排除。原始 MP4、MCAP 和对齐文件不被修改。
- ROS 后处理环境固定为 `~/umi_ros_venv`；LeRobot 0.4.4 使用独立的 `~/umi_lerobot_venv312`。编排器通过独立解释器执行 LeRobot 导出，避免升级 ROS 环境中的 NumPy/setuptools。当前 pose 只能作为 `observation.state`，没有足够信息定义真实 `action`，所以不伪造该字段。

## 实际包结构与入口

目前只有一个项目自有 ROS 2 包：`umi_ros2/`（`ament_python`，版本 0.2.0）。它含 6 个 launch 文件；包内其他 Python 文件并非全都是节点。

| 目录/入口 | 责任 |
| --- | --- |
| `umi_ros2/umi_ros2/vive/` | pysurvive 适配、Vive 发布节点、在线常驻 pose recorder |
| `umi_ros2/umi_ros2/camera/` | Action 4 ROS 控制节点、GStreamer worker、预览和键盘控制 |
| `umi_ros2/umi_ros2/session/` | 在线/离线目录与 `session.yaml` 更新 |
| `umi_ros2/umi_ros2/synchronization/` | ArUco 标记生成和一次性时间差估计 |
| `umi_ros2/umi_ros2/postprocess/` | MCAP 读取、pose 插值、episode 坐标变换、HDF5/LeRobot v3 导出和纯编排；不是 ROS 节点 |
| `umi_ros2/umi_ros2/visualization/` | MP4+MCAP 回放协调与回放路径重建 |
| `umi_ros2/config/`、`umi_ros2/rviz/` | 设备默认参数、在线/离线 RViz 配置 |
| `umi_ros2/test/` | 单元测试、launch 合约和独立 MCAP writer 集成测试 |

| launch | 启动内容与用途 |
| --- | --- |
| `vive.launch.py` | 仅启动 Vive，排查定位 |
| `camera.launch.py` | 仅启动 Action 4 预览，排查相机；默认不创建 session |
| `online_view.launch.py` | Vive + Action 4 + RViz，仅观察 |
| `online_record.launch.py` | Vive + Action 4 + RViz + 相机节点内部常驻 pose recorder，正式在线 session |
| `offline_record.launch.py` | Vive + RViz + `ros2 bag record`，离线 pose-only |
| `replay.launch.py` | MP4/MCAP 回放节点 + 路径重建节点 + RViz |

`episode_keyboard` 是单独运行的 ROS 服务客户端，不由在线 launch 自动打开终端；`calibrate_time`、`generate_aruco_marker`、`align_session`、`transform_session`、`export_hdf5`、`export_lerobot` 和 `process_session` 都是一次性工具，不启动 ROS graph。仍保留 `compressed_preview_node` 供旧式 JPEG bag 兼容，当前 MP4+MCAP 回放不启动它。

## 本次核对的证据与限制

- 常驻 pose recorder 的 ROS 集成测试可在同一订阅生命周期内先后写入两份独立 MCAP；回放、launch 合约、对齐和数据导出都已纳入当前完整测试集。软件测试不能替代 Action 4、Vive 和 RViz 的真机视觉验收。
- 同一条旧 episode 在 1×、720p 无 RViz 回放下，迟到容忍度从一帧放宽到两帧后，发布帧数由 442/468 变为 443/468。其视频比 pose bag 早约 0.347 秒；没有证据表明仅靠提高回放清晰度就能显示所有原始帧。
- 工作区现有 `recordings/online_session_20260913_172757_796981` 含一条 calibration 和三条普通 episode；其 `session.yaml` 仍为 `temporal_calibration.status: not_calibrated`。这些数据早于当前常驻 pose recorder 修改，不能验证新版录制边界。
- 此前以显式零 offset 读取上述三条真实 episode，分别得到 457/468、393/405、240/249 个有效帧。这仅证明读取/插值通路工作，**不证明图像与 pose 时间误差或训练数据质量达标**。
- 现有 `aruco_id4.png` 是工作区未跟踪文件；当前代码可重新生成。没有已接受的真实 `time_offset.json` 或基于 accepted offset 的正式 HDF5/LeRobot 数据。
- 工作区存在未提交的功能、文档改动及旧 `vive_ros2` 删除；本次只更新项目文档，不回滚或覆盖这些工作。
- 2026-09-20 完整测试 **51 项通过**，后处理相关 flake8、symlink build、五个后处理安装入口和 `git diff --check` 通过。真实 `online_session_20260916_185704_823701` 用零 offset 诊断完成 174+222 帧对齐、坐标变换及 80.3 MiB HDF5 导出；首帧相对 pose 为单位变换，JPEG 可回读为 1920×1080。该结果位于 `/tmp`，不属于 accepted 时间同步训练数据。
- 同一份 transformed 诊断数据已由官方 LeRobot 0.4.4 API 导出为原生 v3：2 episodes、396 frames、约 9.31 MB、7 个文件；本地重载得到 7 维 state 和 3×1080×1920 图像，首帧 state 为单位位姿。它同样使用零 offset，不代表时间同步精度通过。

## 待验收与后续安排

1. **当前最重要：**用现版 `online_record.launch.py` 连续录两条以上真实 episode，检查各自 MP4 可解码、MCAP 可读、第一帧落入 pose 覆盖，观察预览与录制是否稳定，并检查 `video.validation.json` 的帧间隔。还应做更长时间的 USB/CPU/磁盘/温度测试；目前不能承诺“绝不掉帧”。
2. 录制真实在线 calibration，运行 `calibrate_time`，人工检查曲线、`accepted` 状态和重复性；再用 accepted offset 跑 `align_session`。可见图像质量、视频时间锚点与姿态对应仍需人工复核。
3. 验证 Vive TF/path 与 pose 的一致性、遮挡丢失/恢复；确认基站和世界系稳定性。默认 `publish_hz=90` 是发布定时器设置，改成 200 不保证硬件产生 200 Hz 新测量。
4. 规划并验证离线多 episode、SD 视频导入和离线时间对齐。此部分尚无确定的最终组织细节。
5. 真机对比 `vive_world → vive_tracker`、`vive_world → gripper_tcp` 两个 TF，并检查 `/vive/pose`、`/vive/path` 的 TCP 位置与方向。新录制的 pose 已是夹爪 TCP pose，之后在 accepted offset 数据上重新导出并验收 HDF5 与 LeRobot v3，确定任务/action 字段及训练代码期望。相机内参、相机到 Tracker 外参和 Action 4 IMU 记录仍未完成。

## 资料入口

- [README.md](README.md)：环境配置和操作者按步骤使用方法。
- [coding_context.md](coding_context.md)：后续编码入口、当前约束和历史验证。
- [需求](docs/project/REQUIREMENTS.md)、[架构](docs/project/ARCHITECTURE.md)、[决策](docs/project/DECISIONS.md)：正式项目记录；其中有部分历史方案段落，判断当前链路请以本页与源码、最新决定 D-011/D-015～D-018 为准。
- 当前任务：[数据处理流程](docs/project/tasks/active/dataset-pipeline.md)、[在线常驻 pose](docs/project/tasks/active/persistent-pose-recording.md)、[时间标定](docs/project/tasks/active/temporal-calibration.md)、[逐帧对齐](docs/project/tasks/active/align-session.md)、[离线采集](docs/project/tasks/active/offline-acquisition.md)、[回放](docs/project/tasks/active/session-replay.md)。
