# Raw → HDF5 / LeRobot 双视角 state/action

- **决策：** D-041，2026-10-02。
- **状态：** 用户要求逐文件实现后处理模块，最后接入 `build_dataset`。双图像 90 Hz 展开与起点坐标变换均已独立实现并通过软件及真实文件验证。用户明确本步骤暂不生成 state/action；新版导出与编排接入留给后续步骤。
- **范围：** 数据集任务仅后处理。采集流程、raw MP4/MCAP、已有标定保持不动；URDF IK 暂缓。采集配置仍冻结，唯 2026-10-04 用户明确指定的 Tracker→TCP 外参数值更新按 D-020 修订执行，不改变采集算法。

## 已确认的要求

1. 每条最终样本含两路 image（wrist、left）、一路 state 和一路 action。
2. state 为当前 pose；action 为下一帧 pose。两者使用同一个 episode 起点参考系。
3. 标定之后，30 fps 图像各出现三次以配合 90 Hz pose；不是额外增加三份。
4. t=0 为本 episode 原始 pose 流的首条保存 TCP pose。后续变换为
   `T_local_i = inverse(T_world_0) * T_world_i`，初始朝向决定固定坐标轴。
5. 最终 state/action 保留 `[x, y, z, qx, qy, qz, qw]` 七个数值（六自由度），无需转换为欧拉角或旋转向量；四元数归一化并保持时间上的符号连续。
6. 暂不实现 URDF 机器人 IK 校验。

## 源码核实

- `vive/pose_node.py` 将 Tracker pose 经固定外参转换成 TCP pose，发布
  `geometry_msgs/msg/PoseStamped`；位置为 XYZ，姿态为 XYZW 四元数。
- `vive/pose_recording_worker.py` 将 `/vive/pose` 消息序列化原样写入 MCAP。
- `postprocess/pose_io.py` 读取 pose header 时间、XYZ 和 XYZW，不是从 TF
  推断训练状态。现有 exporter 输出七值 pose，只有 wrist，无 action。
- 原始 pose 早于图像开始，前置缓冲不属于具有两路图像的完整训练样本；首个
  可导出样本可晚于 t=0，仍使用 t=0 的参考变换。

## 已确认的时间轴理解

图示用理想等间隔、两路校正后相位一致的局部片段说明三次复制。令片段从 τ
开始，对应原始 pose 的第 k 个采样；τ 不是原始 pose 的起点 t=0。S 表示转换
到起点参考系并编码为 XYZ + XYZW 七值后的 pose。此前示意图中 6D 的数值编码
说明已由用户最新要求替代，图像重复与当前/下一 pose 的时序含义保持一致。

| 相对 τ 的时间 (ms) | 0 | 11.111 | 22.222 | 33.333 | 44.444 | 55.556 |
| --- | --- | --- | --- | --- | --- | --- |
| wrist 图像 | W0 | W0 | W0 | W1 | W1 | W1 |
| left 图像 | L0 | L0 | L0 | L1 | L1 | L1 |
| state | S_k | S_(k+1) | S_(k+2) | S_(k+3) | S_(k+4) | S_(k+5) |
| action | S_(k+1) | S_(k+2) | S_(k+3) | S_(k+4) | S_(k+5) | S_(k+6) |

用户已确认下一 pose 指下一 90 Hz 步（名义约 11.111 ms）。图片内容在三个
样本内复用，state 和 action 每步变化。最后一个 action 可以对应当前图像三次
复用范围之后的 pose，只需该下一 pose 有效且属于同一 episode。

## 实施顺序

1. 升级中间数据契约，保存两路视频映射、逐路 accepted offset、图像来源帧号、
   采样时间、起点参考 pose、state/action 及有效性，让两种 exporter 读取同一结果。
2. 扩展逐路图像对齐，在每路实际 PTS + 接收锚点 + accepted offset 的基础上
   形成双图像组，再按图示展开三次。明确共同 90 Hz 时间轴及真实抖动处理，
   用 pose header 时间查询位置/四元数，保留实际来源时间和配对误差。
3. 使用 `inverse(T_start) * T_world` 转换 pose，保留 XYZ + XYZW，保证固定
   初始坐标轴、单位四元数及时间连续的四元数符号。
4. 以当前/下一步 relative pose 生成 state/action；处理完整三份图像组、起止
   覆盖和相邻 pose 有效性。落实 `quality.json` 的 dataset 排除标记并报告原因。
5. 更新 HDF5 与 LeRobot v3 的双图像、七值 state/action、90 Hz 时间语义和
   来源信息；允许两种相机分辨率不同，分别验证同一 image field 跨 episode
   的尺寸一致性，保留多 session/task 合并。
6. 接入 `build_dataset`，新增相关测试、完整软件检查及真实已标定 session
   的独立输出导出/回读核对。同步 README、架构、上下文、看板和验证证据。

## 实现需要落实的细节

- 展开阶段使用固定 90 Hz 网格，锚定 wrist 首张校正后的图像。每三个样本组成
  一个 30 Hz 图像组；两路按各自校正时刻选最近源帧，默认容差 1/60 秒，相同
  距离选较早帧。每张源图像最多进入一个有效组，组内以帧号重复三次表示；未
  选中/边界裁掉的源帧在报告中统计。真实 pose 按 header 时间插值到网格。
- 任一路配帧无效或组内任一 pose 查询无效，则整组三条标记 invalid；保留原
  时间轴和诊断，不压缩间隔。保存 world XYZ + XYZW 和首条 raw TCP 参考，
  `localize_session` 已单独完成起点参考系转换。尚不生成 action。
- 图像有效范围、配帧容差、pose 缺口、quality 排除标记与无效相邻 transition。
- 末条没有下一 pose 时的策略（候选为不导出该条）；不得伪造下一 pose、跨
  episode 接续，或将缺口两侧 pose 直接当作相邻时间步。
- 新版中间契约及 HDF5 / LeRobot schema；原始时间与图像来源索引的追溯字段。

## 验证状态

### 起点坐标变换（2026-10-02，实施前记录及完成证据）

- 新增 `local_pose.py` 算法及 `localize_session.py` CLI，读取展开 v1，不重新
  读取或写入 raw，不重新标定或展开图像。单 episode 和展开 session 分别可运行。
- 固定参考必须是展开结果中携带的该 episode 原始 pose 流首条 TCP pose；
  位置和初始朝向共同定义参考系。缺少参考时报错，不回退到首图像或首展开 pose。
- 对每个 `pose_valid` 样本输出起点相对 XYZ + XYZW，保留 NaN pose 缺口和
  image-invalid 样本的有效 pose；保留原样本数、90 Hz 时间轴、帧号和各有效性标记。
- 单独输出 local-pose v1 NPZ/CSV/JSON，保留 world pose、world 参考和逐路来源；
  四元数归一化并维持符号连续，不生成 state/action，不接入 exporter/build_dataset。
- 已实现并注册 `localize_session <expanded session|episode> --output <local>`。
  每条 episode 输出 `local_frames.npz`、`local_frames.csv` 和 `local_pose.json`，
  CLI 输出 `local_pose_summary.json`。不需要重新读取图像或 MCAP；只消费展开契约。
- 23 项新增测试通过：固定初始位置/朝向、首图像前位移、不同 episode 参考、
  世界坐标变换不变性、跨 180° 的四元数符号连续、NaN pose 缺口、图像无效但
  pose 有效、参考缺失拒绝/不回退、输入及 raw 路径保护、拒绝状态保留和重试。
- 全套 185 通过、2 跳过、2 失败（已有 HDF5 测试缺少 `h5py`）；构建与 flake8
  通过，安装后 CLI help 和 `git diff --check` 通过；算法及文件适配模块在独立
  LeRobot 环境可导入且不导入 ROS。旧 `transform_session`/exporter/`build_dataset`
  行为未改变。
- 真实展开输入的全部 3234 个 pose 查询成功转换；样本有效性仍为 3138 valid /
  96 invalid。参考与原 MCAP 首条 TCP 核对一致；独立旋转矩阵和世界坐标反向
  还原误差不超过 2.23e-16，四元数单位长度及符号连续。24 个 raw 文件、4 个
  展开文件的 SHA-256 和清单均不变。
- [坐标变换验证证据](../../reports/local-pose-20261002.json)；输出位于
  `/tmp/umi_local_pose_validation_20261002/episodes/episode_0001/`。本次为已有
  真实文件上的软件验证，没有启动硬件；用户对坐标系的验收待进行。

### 90 Hz 展开（2026-10-02，前一阶段证据）

2026-10-02：新增 `postprocess/frame_expansion.py`（NumPy 算法）与
`postprocess/expand_session.py`（文件适配/CLI），注册 `expand_session` 入口。
输出独立 expansion contract v1，包含 NPZ/CSV/JSON 和 session 汇总。当前
`transform_session`、两个 exporter 与 `build_dataset` 继续使用旧契约，尚未
接入此模块；本阶段不变换到 local、不组装 state/action、不执行 quality 排除。

- 新增 24 项测试全部通过，覆盖逐路 offset、三次源帧复用、固定时钟、缺帧、
  pose 缺口、边界裁剪、四元数单位长度/符号连续、文件契约与 raw 不变。
- 全套：162 通过、2 跳过、2 失败，失败仍是已有 HDF5 测试缺少 `h5py`。
- colcon build、相关文件 flake8、`git diff --check` 与安装后的 CLI help 通过。
  算法在独立 LeRobot 环境可导入，未导入 ROS。
- 真实 session `online_session_20260930_212318_104281`：3234 个候选样本，
  3138 个有效（1046 组，97.0315%），96 个 invalid 保留；pose 查询全部有效。
  两路 source 为 1080/1081 帧，各选中 1046 帧且每帧恰好出现三次，34/35 个未
  使用源帧已报告。wrist/left 有 31/1 组配对或复用限制失败；这不是新判定的
  raw 掉帧。24 个 raw 文件 SHA-256 与文件清单不变。
- [真实文件验证证据](../../reports/expansion90-20261002.json)；输出位于
  `/tmp/umi_expansion90_validation_20261002/episodes/episode_0001/`。

新版导出、端到端 state/action 与训练侧真实双视角数据验收均待后续模块实施。
时间轴示意已检查桌面与窄屏排版，文档补丁 `git diff --check` 通过。
