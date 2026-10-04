# UMI 项目看板

> 最近同步：2026-10-04（用户指定的 Tracker→TCP 外参更新；独立展开/坐标变换及其他证据保留各自日期）。ROS 包版本：`umi_ros2 0.2.0`。

## 项目目标与当前重点

DJI Action 4 与 Vive Tracker 刚性安装在同一夹爪上，左侧 RealSense D435i 提供第二路彩色视角；两路图像与六自由度位姿将分别校正时间差并整理为机器人学习数据。只使用在线采集；原离线（microSD）模式已按 D-021 删除。

**当前重点：**[Raw → 双视角 state/action 数据集](docs/project/tasks/active/raw-to-dataset.md)（D-041）。用户要求分文件完成子模块，最后由 `build_dataset` 编排。双路图像三次复用、固定 90 Hz pose 展开和起点参考系变换均已独立实现并通过软件及真实文件验证；当前输出为七值 `[x,y,z,qx,qy,qz,qw]` 相对 pose，按本步骤要求暂不生成 state/action。后续再组装 state/action、更新两个 exporter 并接入总流程。**采集流程与 raw 文件保持不动，URDF IK 暂不实现。当前 `build_dataset` 与 exporter 尚未使用新结果，最终训练数据集尚未验收。**

**进行中：**[多任务 session 重构](docs/project/tasks/active/multi-task-sessions.md)（分支 `feature/multi-task-sessions`）——一个 session 对应一个 task、同一 launch 内切换 session、多 session 合并导出。四个阶段的代码都已完成并通过软件验证：阶段 1 删除离线采集；阶段 2 `session.yaml` v2 与 `task` 字段、`set_session_task`；阶段 3 同一 launch 内 `n` 切换 session 并复制标定原始数据；阶段 4 `build_dataset` 多 session 合并导出 HDF5/LeRobot v3。**阶段 3 待用户真机验收**；阶段 4 待用真实多任务数据验收。

**分阶段推进：**[多相机采集与逐路标定](docs/project/tasks/active/multi-camera-acquisition.md)（D-027–D-030）。统一接口及两路 `image_field` 已落地；`online_record` 现同时预览并录制 Action 4 的 `wrist_image` 与 D435i 的 `left_image`，分别保存 MP4、timing、validation，并共享一份 Vive pose MCAP。双相机与真实 Vive 的单条 episode 联录已通过时间范围和帧间隔检查。逐路时间标定已按 D-036 实现；左侧单路标定可读取回放，真机逐路标定验收与多视角数据集导出待推进。

**预览复测（2026-09-30）：** 此前 `online_view` 的 RViz 曾因 futex 错误退出，且 Action 4 worker 停在预热中；直接读取 `/dev/video2` 也没有帧。用户重新进入 Webcam 模式后，真机持续出帧，约 5 秒完成预热；真实相机 ROS 节点在 `/action4/image_preview` 发布了 5 条有效 640×360 BGR8 Image 消息。完整 `online_view.launch.py` 运行 15 秒期间 RViz 未异常退出、相机完成预热，用户随后确认预览画面正常。强制结束 launch 时 RViz 曾报 `std::system_error`，与出帧路径分开跟踪。worker 已增加“无首帧”的明确提示。

**D435i 双路联录（2026-09-30）：** 用户以 D435i 替换原 D435。已重新识别 USB 3（5000M）彩色流，使用序列号对应的稳定设备链接；Action 4 也改用稳定链接，避免 `/dev/videoN` 变化。完整 `online_record` 真机测试中，两路 ROS 预览分别为 320×180、320×240；同一测试 episode 各录得可解码的 78 帧 H.264 MP4，`session.yaml` 中映射了 `wrist_image` 与 `left_image`。该测试使用合成 pose。

**真实 episode 诊断（2026-09-30）：** `online_session_20260930_133225_127556/episode_0001` 含真实 `/vive/pose` 2053 条，header 时间为 13:32:44.310–13:33:07.199，最大相邻间隔 22.50 ms。Action 4 MP4 为 612 帧、29.970 fps（按首末 PTS），最大帧间隔 41.33 ms；D435i MP4 为 613 帧、29.978 fps，最大帧间隔 33.67 ms。两路均可解码、录入帧数与解码帧数一致，无超过 50 ms 的 PTS 间隔。以首帧主机接收时间加视频 PTS 估算，两路所有帧都落在 pose header 时间范围内；起始余量分别仅 73.33 ms、80.86 ms，尚无本 session 的逐路时间标定，故物理时间对齐及校正后首帧覆盖未验收。相机源端完整性仍为 `not_verified`。

**目录修正（D-031，2026-09-30）：** 新录制把每路 `video.mp4`、timing 和 validation 分别放在 `cameras/wrist/`、`cameras/left/`。上述真实 episode 的 wrist 文件已迁移到新目录，MP4 字节哈希不变，`session.yaml` 路径和 timing 自身路径已更新。标定、回放、对齐及 session 切换读取新布局，也兼容旧录制根目录的 wrist 文件；27 项相关测试通过，构建和静态检查通过。逐路标定与多视角导出尚未实现。

当前已有从一个或多个在线 raw session 到 HDF5 和原生 LeRobot v3 的模块化单视角软件链路；已有真实 accepted 时间标定。新的双视角三次图像复用/90 Hz 展开及固定起点相对 pose 已完成，state/action、新版导出和总流程接入尚待实现，跨次重复性和训练侧真实数据集验收仍待完成。

## 现在可以做什么

**外参坐标定义待核对（2026-10-04）：** 用户说明仅调整 co2 的轴。若 co1 和 co2 原点均未改变，平移本应保持不变；但两份文件的平移差为约 161.910 mm，长度均为 210.874295 mm。这不是数值舍入误差，需要核对 CAD 中 co1 定义、co2 原点及导出表达坐标系。文件内部矩阵/四元数一致性与配置测试通过，不等于确认 TCP 物理原点相同；配置仍为用户指定的新文件值，未再擅自修正或启动硬件。

**Tracker→TCP 外参更新（D-020，2026-10-04）：** 按用户指定的 3Dprint/UMI 最新 `co2_in_co1.txt` 更新 `config/vive.yaml`，平移为 `[0.0,-0.194899844,0.080510987]` 米，XYZW 为 `[0.457263310,0.0,0.0,0.889331359]`。实际源目录为 `.../User/Documents/...`；项目根目录同名 txt 保留为历史测量文件。co1/co2 仍对应 Tracker/TCP，直接应用，无需取逆；米/毫米、矩阵与四元数一致性通过，安装配置与源文件一致。8 项现有外参测试通过；全套 185 通过、2 跳过、2 因已有 h5py 缺失失败，构建与静态检查通过。该参数更新为用户明确授权的配置冻结例外，采集算法、已有 raw 和标定未改；重启 Vive 后新 TCP 发布生效，既有 raw/后处理结果不会自动重算。新几何定义的真机验收待进行。

**独立起点坐标变换（D-041，2026-10-02）：** `localize_session <展开输出> --output <local 输出>` 对每条 episode 使用其原始 pose 流首条 TCP pose 的位置与朝向定义固定参考，计算 `inverse(T_start) * T_world`，输出相对 XYZ + XYZW。读取展开契约即可，不需重新读取图像或 MCAP；缺少参考时报错，不回退到首图像。保留完整时间轴、两路帧号、world pose 和有效性标记；图像无效但 pose 有效的样本仍可变换，pose 缺口保留 NaN。四元数单位长度并保持符号连续，尚不生成 state/action。23 项新增测试通过；全套 185 通过、2 跳过、2 因已有 h5py 缺失失败，构建与静态检查通过。真实输入的 3234 条 pose 均已转换，3138 valid / 96 invalid 样本标记不变；独立旋转矩阵及反向还原误差不超过 2.23e-16，24 个 raw 文件和 4 个展开文件哈希不变。[验证证据](docs/project/reports/local-pose-20261002.json)。用户对坐标系的验收待进行。

**独立 90 Hz 展开（D-041，2026-10-02）：** `expand_session <session|episode>` 读取两路 accepted offset、视频 PTS 和一份 pose MCAP。固定 90 Hz 时钟上，每三个样本各复用同一 wrist/left 源帧，按真实 pose header 插值世界系 XYZ + XYZW；保留 raw 首条 TCP 参考，交给 `localize_session` 转换坐标，state/action 留给后续步骤。配帧默认最大误差 16.667 ms，源帧不跨有效组重复；整组 invalid 保留时间槽和原因相关诊断。24 项新测试通过；全套 162 通过、2 跳过、2 因已有 h5py 缺失失败，构建、静态检查、安装入口通过。真实 session `online_session_20260930_212318_104281` 生成 3234 候选/3138 有效样本（1046 组，97.0315%），96 invalid 保留、pose 查询全部有效；每路选中的源帧均恰好三次，未使用的 34/35 帧已报告。24 个 raw 文件 SHA-256 不变。[验证证据](docs/project/reports/expansion90-20261002.json)。当前输出为独立 NPZ/CSV/JSON 契约，尚不生成新的 HDF5/LeRobot 数据集。

**逐帧对齐查看器（D-040）：** 新增 `frame_alignment_viewer`，直接读视频和 pose 文件，在同一窗口同步显示两路图像、录制起点相对坐标的三维轨迹/姿态轴及 XYZ 曲线游标。Space / → 逐帧前进，← 后退，滑条跳帧；可切换 episode、标定视频、参考相机，并比较校正前后。另一视角按校正后的最近时间配对，明确显示时间差。当前 session `online_session_20260930_212318_104281` 的 wrist/left 为 1080/1081 帧，全部有有效对齐 pose，时差为 −112.143/−6.703 ms；两段标定也可查看。5 项时序关联测试、真实视频往返定位、GUI 切换和绘制通过；全套 138 通过、2 跳过、2 因已有 h5py 缺失失败，构建与静态检查通过。画面布局与键盘单次步进已检查，现已打开该 session 的第一条 episode 供用户查看；关闭窗口退出。对齐效果由用户逐帧判断，原录制未修改。

**相机启动修复（D-039）：** D435i 的 `by-id ...video-index0` 曾指向深度端口，导致彩色流 `not-negotiated`。现按序列号 `254343064631`、RGB USB 接口 `03` 自动找到彩色端口，不依赖 `/dev/videoN` 编号；显式 `left_video_device` 仍优先。双路真机预热完成，用户已确认自己的在线启动恢复。此前遗留的诊断进程已停止并释放两路设备。全套测试 133 通过、2 跳过、2 因已有 h5py 缺失失败，构建与静态检查通过；本次未录制新 episode。

**录制起点相对坐标（D-038）：** 标定现使用 Enter 开始录制后首条保存的 TCP pose 定义固定参考系，位置和初始朝向共同决定原点与 XYZ 轴；后续 pose 按 `inverse(T_start) * T_world` 转换，轴不会随中途旋转改变。参考 pose 在 image 延迟 500 ms 之前，时差计算继续保留绝对时间戳。数据集 pose 也统一使用这个起点，首张图像前发生的移动会保留。Raw MCAP 仍保存世界系源数据；标定 JSON 写明参考 pose/时刻。已知时差在初始 90° 和任意世界旋转下测试通过；全套 130 通过、2 跳过、2 因已有 h5py 缺失失败，构建与静态检查通过。真实新标定待验收，已有结果未重算。

**双视角标定回放（D-037）：** 已在 RViz2 中循环回放 `online_session_20260930_193959_496910/episode_0001`。wrist 与 left 各有 99 帧，分别应用本 session 已接受的 −93.77 ms、−10.07 ms 偏移，按 MP4 实际 PTS 以约 30 fps 显示；同时播放 Vive pose，展示当前 TCP pose 和轨迹。实测每轮两路各发布 99/99 帧，pose/path 话题均在 `vive_world` 发布；12 项针对性测试、静态检查和构建通过。录制文件未改动，画面是否符合操作员的视觉判断由本次回放检查。

**D-036 最终软件验证：** 新增 10 项场景测试；全套 125 通过、2 跳过、2 因已有 `h5py` 缺失失败。构建、相关文件静态检查与补丁格式检查通过。500 ms 缓冲下的已知正负时差恢复误差小于 4 ms；真机逐路标定和重录仍待验收。

**逐相机时序标定（D-036）：** `c` + Enter 显示编号，当前为 `1: wrist / wrist_image`、`2: left / left_image`；输入编号开始所选相机和 pose 的标定，其余相机继续预览。结束后立即运行原有 ArUco 中心/面积与 TCP XYZ 平移算法，不使用旋转。绿色 `accept` 保留结果；红色 `reject` 删除本次视频、timing、validation、pose 和派生文件，保留目录；Enter 在同一目录重录，`c` 重新选相机。每路独立保存 `temporal_calibrations.<camera_id>`，wrist 同时更新旧兼容字段；失败只清除所选相机状态。500 ms 前置缓冲保留在绝对时间戳中，不强行作为时差加减。单路选择、失败清理/原目录重录、键盘流程、目录复制以及真实 MCAP + 合成图像特征的正负时差测试通过；构建和静态检查通过。现有录制未修改，真机每路标定及现场失败重录待验收；多视角对齐/数据集导出尚待下一阶段。

**Pose 前置缓冲（D-033）：** 每条 episode 和 calibration 开始时先保存 pose，确认首条 pose 写入后等待 500 ms，再向两路相机发送录制命令；停止流程继续先关闭两路视频再关闭 pose。启动顺序和缺少首条 pose 的失败路径已通过软件测试，构建与静态检查通过；全套测试 93 通过、2 跳过、2 因缺少 `h5py` 失败。真机 session `online_session_20260930_145919_328592` 的两条 episode 已验证：wrist/left 首帧比首条 pose 写入分别晚 584.85/601.23 ms 和 586.49/613.42 ms，满足 500 ms 要求。帧间隔统计、彩色判定及 JSON 排除标记已按 D-035 实现，见下文。

**两条 episode 验收（2026-09-30）：** 上述 session 和两条记录均为 complete，目录、字段和路径映射正确；两路视频可解码且录入帧数与解码帧数相同。第一条 wrist/left 为 576/574 帧、29.962/29.979 fps，最大帧间隔 44.67/33.67 ms；第二条为 693/691 帧、29.971/29.979 fps，最大帧间隔 40.67/33.67 ms。均无超过 50 ms 的 PTS 间隔。pose 覆盖视频时间段，结束后余量约 2–2.5 秒。另发现 pose 平均采样率由第一条 89.73 Hz 降至第二条 51.90 Hz，第二条分段频率逐渐下降；最大相邻间隔仍小于 22.69 ms、数据均有限值。频率下降的诊断见下文；后续按 D-035 加入逐条自动诊断。

**Pose 降频原因分析（2026-09-30）：** 高置信主因已定位到原 Vive 节点每次 pose 回调都发布完整历史 Path，轨迹在 episode 间等待时继续累积，最多 10000 点。第一条正常收尾约 48 秒后才开始第二条，视频验证已完成；MCAP writer 每条重新创建。第二条 pose 写入延迟中位数仅 0.423 ms，但同一时间戳的 TF 延迟约 19.384 ms，与下一条 pose 的间隔高度相关（0.9957），符合 pose → 完整 Path → TF 的回调阻塞。隔离模拟测试使用修改前节点与真实 ROS publisher：8000 点时回调约 18.04 ms，超过 90 Hz 的 11.11 ms 周期；7000 点的对照测试跳过 Path 发布后由 61.47 Hz 恢复到 89.98 Hz。后续已按 D-034 完成独立节点修复，长时间、多 episode 真机验证待推进。

**独立轨迹节点（D-034，2026-09-30）：** `vive_pose_node` 专门发布 pose 和两路 TF，目标 90 Hz；新增独立进程 `vive_path_node` 订阅最新 pose，按 30 Hz 采样、整理并发布 `/vive/path`，保留源 header、坐标和 10000 点上限，没有新 pose 时不重复追加。`online_record`、`online_view`、`vive` 均已接入；参数位于 `vive.yaml` 的独立节点部分。构建、静态检查和 22 项针对性测试通过；全套测试 101 通过、2 跳过、2 因已有 `h5py` 缺失失败。10000 点轨迹的独立进程压力测试使用模拟 Tracker 和真实 DDS/C++ 订阅者，12 秒内 pose 约 90.002 Hz、最大间隔 11.915 ms，Path 发布和接收约 29.916 Hz。三条真实短 episode 的复测见下文；更长录制和 RViz 实际显示仍待验收。

**三条 episode 真机复测（2026-09-30）：** 最新 `online_session_20260930_160029_092182` 在约 117 秒 launch 中录制三条 episode，session/记录均为 complete。Pose 为 1988/1342/1240 条，平均 89.774/89.799/89.856 Hz，后续两条未再持续降频；仍有 5/3/2 处约 22 ms 的双周期间隔（疑似少一次更新），最大 22.380 ms，无超过 100 ms 的间隔，具体丢失环节未确定。Wrist/left 视频分别为 585/583、391/391、357/355 帧，均解码正常且帧数等于录入计数；约 29.971–29.979 fps，最大帧间隔 wrist 40.000/40.666/39.000 ms、left 33.667/34.000/33.667 ms，均无超过 50 ms 的间隔。两路所有已保存图像均在 pose header 时间范围内；首帧比首条 pose 写入晚 550.50–655.26 ms，末帧后 pose 余量 1.30–2.12 秒。500 ms 前置和原始时间范围覆盖通过；本 session 未标定，不能据此确认曝光时刻对齐或相机源端零丢帧。此次为用户指定的一次复查；后续 D-035 已加入逐条自动诊断。[完整结果与复算代码](docs/project/reports/raw-recording-check-20260930-160029.md)。

**逐条自动诊断（D-035，取代 D-032）：** 每条 episode 的两路 MP4 与 pose MCAP 关闭后自动检查。仅当两路视频解码正常、帧数匹配、时间戳递增且无超过 50 ms 的间隔，pose 完整覆盖两路图像原始时间范围、平均频率至少 88 Hz 时，输出绿色 `accept`；否则红色 `reject` 并简述原因。少量 pose 间隔缺帧不单独拒绝。复用原有视频检查，不新增启动参数；写入 `quality.json` 与 `exclude_from_dataset` 标记（导出器尚未自动过滤）。拒绝不阻止录制下一条。构建、静态检查、19 项针对性测试通过；全套 115 通过、2 跳过、2 因已有 `h5py` 缺失失败。只读复测四条真实记录、八个 MP4 与 MCAP 共 6.511 秒：最新三条接受，旧 51.899 Hz 第二条拒绝；新版本现场自动收尾待验收。

| 能力 | 当前实现 | 验证边界 |
| --- | --- | --- |
| Vive 定位 | pysurvive 选取 Tracker；pose 和两路 TF 由 90 Hz 节点发布；独立轨迹节点按 30 Hz 从最新 pose 构建 `/vive/path`，二者表示夹爪 TCP | 节点分离、满长度轨迹软件测试及三条真实短 episode 的约 90 Hz 采样通过；零星双周期间隔、长录制、TF/TCP 几何及 RViz 显示待进一步验收 |
| 在线观察 | `online_view.launch.py` 启动 Vive、Action 4、D435i 彩色流和 RViz2，不创建正式在线 episode | 双路 ROS 图像话题和 RViz 同时运行通过；Action 4 须处于 Webcam 模式，D435i 须使用 USB 3 |
| 在线采集 | `online_record.launch.py` 创建一个 session（可用 `task:=` 写入任务）；两路相机共同开始/结束每条 episode，分别保存视频和 timing，pose 仅保存一份；键盘服务支持 calibration、episode、`n` 换 session；标定结束后即时估计 wrist-to-pose 偏移 | 一条真实 Vive + 双相机 episode 的时间范围和帧间隔通过检查；跨条 episode、逐路时间标定及校正后边界待验收 |
| Action 4 统一接口第一阶段 | ROS-free `CameraSource` / `ImageFrame` 和 `Action4Source` 管理持续预览、状态及录制启停；预览帧含源 PTS 与主机接收时刻；新录制的 timing 带 `camera_id: wrist`、`image_field: wrist_image`；`video_device:=...` 可覆盖配置默认端口 | 已与 D435i 和真实 Vive pose 同时录制一条 episode；源端完整性未验证 |
| D435i 左侧彩色采集类 | `RealSenseSource` 通过统一接口读取 YUYV 彩色端口，提供 BGR 预览和独立 MP4 录制；标记 `left` / `left_image`；默认设备写在 `realsense_left.yaml` | 已接入在线 launch / session，并完成双路真机预览及短联录；深度流未采集 |
| 在线回放 | `replay.launch.py` 可读取一条 calibration/episode 或整个 session；双路图像按各自 MP4 PTS 回放，可选 `use_calibration:=true` 应用已接受的逐路偏移，`loop:=true` 循环检查 | 指定真实 episode 的 RViz2 回放已启动，两路每轮各 99/99 帧；整场 session 与视觉匹配仍待操作员检查 |
| 时间差估计 | `generate_aruco_marker` 和 `calibrate_time` 只用 ArUco 中心/尺度与 TCP X/Y/Z 平移估计常量时间差，不使用旋转；标定动作使用左右、前后、上下平移。标定记录停止后立即计算并在键盘终端显示偏移和报告路径，失败提示重录 | 17:49 真机标定已接受（−83.71 ms），17:56 session 第二次标定也已接受（−91.45 ms）；17:12 失败于分段一致性，17:51 及 17:56 第一次标定失败于标记检测率不足。跨次重复性和真实 episode 后处理仍待验收 |
| 逐帧对齐 | `align_session` 用 MP4 真实 PTS、已接受的 offset 和 Vive MCAP 插值得到每帧 pose | 软件测试及零 offset 真实数据诊断通过；尚未以真实 accepted offset 验证 |
| Episode 坐标变换 | `transform_session` 使用录制开始时首条保存的 TCP pose 定义固定参考系，写出版本化 NPZ/CSV/JSON | 旋转参考轴、图像前位移保留及历史输入兼容通过软件测试；真实新坐标系验收待完成 |
| 多 session 数据集 | `build_dataset <session...> --format hdf5/lerobot/both --output <dir>`：每个 session 独立标定/对齐/变换，只在导出时合并；task 取自各自 `session.yaml`；统一检查（task、accepted 标定、episode、对齐、图像尺寸/帧率、contract 版本）任何一项失败都整体失败；每次从头重建，成功后才替换输出 | 83 项测试通过；用真实 1080p calibration 录像复制成两个不同 task 的测试 session，以 accepted -95.01 ms 合并导出 HDF5（2 episodes/2664 样本）和 LeRobot v3，并由 LeRobot 0.4.4 回读 task/task_index/来源正确；尚无真实多任务 episode 数据 |
| HDF5 数据集导出 | `export_hdf5` 保存逐帧 JPEG、相对 7D pose、帧号和时间戳；格式 v2 起每个 episode 带 `task`/`task_index`/来源 session/offset，根目录 `tasks` 表 | 真实 session 两条 episode 共 396 样本导出并回读通过（零 offset，2026-09-20）；v2 格式见上行 |
| LeRobot v3 导出 | `export_lerobot` 使用官方 `LeRobotDataset` API 写 Parquet、MP4 和 metadata；每帧 task 来自所属 session，另有 `umi.source_session`；`build_dataset --format lerobot/both` 用独立环境调用 | 真实 session 两条 episode 共 396 帧导出并由 LeRobot 0.4.4 回读；零 offset 仅验证软件链路，尚无 action 字段 |
| Tracker→夹爪 TCP 外参 | 2026-10-04 按用户指定的最新 `co2_in_co1.txt` 更新固定变换，只在 `config/vive.yaml` 加载（`tracker_to_tcp_translation_m`、`tracker_to_tcp_rotation_xyzw`）；节点启动校验，支持临时参数更新；在 TCP 发布前应用 | 新源文件与配置/安装文件数值一致；8 项外参测试通过；`/tf` 同时保留原始 Tracker 和转换后的 TCP，真机新几何与方向待验收 |

## 当前在线采集怎样运行

`online_record.launch.py` 启动 Vive pose 节点、两路彩色相机采集和 RViz2。采集节点内部启动三个子进程：Action 4 与 D435i 各一个常驻 GStreamer worker，以及持续订阅 `/vive/pose`、`/tf`、`/tf_static` 的 ROS pose recorder。两台相机和 pose 都预热至少 5 秒且各只预热一次；预热中的数据不保存。随后：

1. **waiting**：两台相机持续提供 RViz 预览；pose recorder 保持订阅但不写 bag。
2. 在另一终端运行 `ros2 run umi_ros2 episode_keyboard`。Enter 开始普通 episode；`c`+Enter 开始专用 calibration。
3. 每次开始都创建新目录并打开本条独立的 `pose/` MCAP；等第一条 `/vive/pose` 实际写入后再等待 500 ms，随后启动两路 MP4。
4. 录制中继续预览；再按 Enter 时先结束并验证两路 MP4，再关闭该条 pose bag，自动输出判定并保存 `quality.json`，回到 waiting。相机和 pose 订阅都不重启。
5. waiting 状态下 `n`+Enter 输入新 task 后切换 session：旧 session 标为 complete，新建 `online_session_<时间>/`（episode 从 0001 重新编号），把旧 session 已完成 calibration 的原始数据（不含 `time_offset.json` 等结果）按原编号复制过来并记 `copied_from`；新 session 需重新运行标定（新录制会自动运行，复制来的数据可手动运行 `calibrate_time`）。录制中拒绝切换。退出 launch 结束当前 session。worker 状态文件放在每次 launch 的临时目录，不再放在 session 根目录。

Action 4 输入是 MJPEG 1920×1080/30 fps，D435i 彩色输入是 YUYV 640×480/30 fps；各自编码 H.264 MP4。预览为 320×180、320×240，定时器最多 10 Hz、best-effort。预览分支可以丢弃旧帧；录制分支没有设计为主动丢帧，但 **MP4 可解码和帧数匹配不等于相机源端绝无掉帧**。两份 `video.validation.json` 都将源端完整性标为 `not_verified`。

每路 `video.timing.json` 保存源 PTS 与主机收到首帧的时刻，并分别标明 `camera_id` 与 `image_field`：`wrist` / `wrist_image` 或 `left` / `left_image`。这不是曝光时间，也不是已经完成的硬件时钟同步。首帧“在 pose 之后开始”只建立记录边界，不能替代时间标定。

### 在线文件结构

```text
recordings/online_session_<时间>/
├── session.yaml                         # schema v2：task、状态、条目索引（含 task 快照）、标定结果索引
├── calibration/
│   └── calibration_001/
│       ├── cameras/wrist/                # Action 4 MP4、timing、validation
│       ├── cameras/left/                 # D435i 彩色 MP4、timing、validation
│       ├── pose/                        # metadata.yaml + *.mcap
│       ├── time_offset.json             # 仅运行 calibrate_time 后出现（复制来的标定不带）
│       └── alignment_report.png         # 同上
└── episodes/
    └── episode_0001/
        ├── cameras/wrist/                # Action 4 MP4、timing、validation
        ├── cameras/left/                 # D435i 彩色 MP4、timing、validation
        └── pose/                        # 每条独立 MCAP
```

一个 session 只对应一个 task；目录名不含 task。`n` 切换产生的新 session 结构相同，复制来的 calibration 在 `session.yaml` 中带 `copied_from`（仅追溯）。合并导出的数据集结构：

```text
<dataset>/
├── build_manifest.json                  # 来源 session、task、offset、帧率
├── processed/<session名>/aligned|transformed/
├── processed/dataset_plan.json
├── dataset.hdf5                         # format_version 2：episode 带 task/task_index/来源，根目录 tasks 表
└── lerobot/                             # LeRobot v3，每帧 task 与 umi.source_session；umi_export.json
```

`/vive/path` 只作 RViz 可视化，不记录；需要时可从 `/vive/pose` 重建。在线记录不保存 Action 4 内部 IMU，也不把完整原始图像逐帧写入 ROS bag。

## 标定、回放与后处理的边界

- 在线 calibration 使用固定 ArUco `DICT_4X4_50`、ID 4，配合重复左右运动；标定记录结束后自动运行 `calibrate_time`，写入 `time_offset.json`、`alignment_report.png`，并更新该在线 session 的 `session.yaml`。终端显示偏移和接受状态，失败提示重录；失败尝试会清除 session 的旧 accepted 引用。一条通过检查的结果只计划用于同一次未中断的在线 session；相机/Vive 重启、重新连接或时钟不连续后不能沿用。
- `replay.launch.py input_path:=...` 回放记录中的各路 `cameras/<camera_id>/video.mp4`（兼容旧录制根目录的 `video.mp4`）和相应 `pose/`；session 输入先按编号回放 calibration，再按编号回放普通 episode。默认按原始时间播放；`use_calibration:=true` 要求每路已有 accepted 标定，并按各自偏移对齐显示。`loop:=true` 可循环检查短 episode。
- 回放预览现默认 1280×720，可通过 `preview_width`/`preview_height` 选择 1920×1080 或较低分辨率；rosbag `/clock` 更新频率为 120 Hz。原视频约 30 fps，显示参数不会提高源帧率，也不修改在线录制/实时预览。
- `align_session` 是不启动 ROS graph 的 Python 后处理命令，但读取 MCAP 仍需 ROS Python 消息库。它只处理普通在线 episodes；默认要求 `session.yaml` 引用的真实 `time_offset.json` 标为 `accepted`。显式 `--offset-seconds` 可用于诊断，不代表标定通过。
- 对齐按视频实际 PTS 为主轴，位置线性插值，四元数最短路径 SLERP。超出 pose 覆盖或跨越默认 0.1 秒 pose 间隔的帧标为 invalid；默认至少 95% 帧有效才接受该 episode。输出在独立 `processed/<session名>/episodes/<episode名>/` 下，含 `aligned_frames.npz`、`aligned_frames.csv`、`alignment.json`，另有会话 `alignment_summary.json`；不覆盖原始记录。
- `transform_session` 使用对齐输出携带的录制开始首条 TCP pose，计算 `T_episode_i = inverse(T_world_start) * T_world_i`。旧对齐文件可从源 MCAP 获取起点，缺少源数据时在报告中明确标注旧版首图像参考。`export_hdf5` 与 `export_lerobot` 读取版本化中间结果和源 MP4；`build_dataset` 负责阶段编排。多 session 合并只发生在导出一步，各 session 的标定互不共享。
- HDF5 每条 episode 保存 JPEG 压缩图像、相对 pose、视频 PTS、pose 查询时间和源帧索引。LeRobot v3 保存视频、Parquet 状态和 metadata，并额外保留真实 PTS、pose 查询时间和源帧号。invalid 帧在两个导出器中都排除。原始 MP4、MCAP 和对齐文件不被修改。
- ROS 后处理环境使用本项目 `.venv`；LeRobot 0.4.4 使用独立的 `~/umi_lerobot_venv312`。编排器通过独立解释器执行 LeRobot 导出，避免升级 ROS 环境中的 NumPy/setuptools。当前 pose 只能作为 `observation.state`，没有足够信息定义真实 `action`，所以不伪造该字段。

## 实际包结构与入口

只有一个项目自有 ROS 2 包 `umi_ros2/`（`ament_python`，0.2.0）。结构和数据流见[架构](docs/project/ARCHITECTURE.md)。

| 目录 | 责任 |
| --- | --- |
| `umi_ros2/umi_ros2/vive/` | pysurvive 适配、Vive 发布节点（含 Tracker→TCP 外参）、常驻 pose recorder |
| `umi_ros2/umi_ros2/camera/` | 统一相机接口、Action 4 与 D435i 彩色适配器、双路采集节点、GStreamer worker、键盘控制 |
| `umi_ros2/umi_ros2/session/` | `session.yaml`、session 切换与标定复制、`set_session_task` |
| `umi_ros2/umi_ros2/synchronization/` | ArUco 标记生成、时间标定 |
| `umi_ros2/umi_ros2/postprocess/` | 对齐、坐标变换、导出、`build_dataset`；不是 ROS 节点 |
| `umi_ros2/umi_ros2/visualization/` | MP4+MCAP 回放 |
| `umi_ros2/config/`、`umi_ros2/rviz/` | `vive.yaml`（设备、坐标系、外参）、`action4.yaml`、`realsense_left.yaml`；双路预览及诊断 RViz 配置 |

| launch | 用途 |
| --- | --- |
| `online_record.launch.py` | 正式采集：Vive + Action 4 + D435i 彩色流 + RViz + 常驻 pose recorder |
| `online_view.launch.py` | 只观察，不录制 |
| `replay.launch.py` | 回放 session 或单条记录 |
| `vive.launch.py` / `camera.launch.py` | 单独排查 Vive / 相机 |
| `urdf_path_diagnostic.launch.py` | 叠加 URDF 与路径；尚未接入真实 URDF |

一次性工具（不启动 ROS graph）：`build_dataset`、`calibrate_time`、`generate_aruco_marker`、`set_session_task`，以及可单独调试的 `align_session`、`transform_session`、`export_hdf5`、`export_lerobot`。`episode_keyboard` 是单独运行的服务客户端。

## 证据与限制

- 2026-09-29：`online_session_20260929_171213_710643/calibration/calibration_001` 的标记检测 971/993 帧（97.8%），TCP 运动 0.450 m，视频验证显示可解码且帧数匹配。拒绝原因仅为分段一致性：有效窗口 −61.75/−105.41 ms，相差 43.66 ms，当前阈值允许的相差约 40 ms；第三窗口的运动通道未达成一致。只读复算重现了分段结果，未修改原始文件、结果或门限。
- 2026-09-29：`online_session_20260929_174955_015048` 的标定已接受：−83.71 ms，标记检出 1302/1356 帧（96.0%），两段有效窗口的标准差 1.80 ms。`online_session_20260929_175651_544205` 的 `calibration_002` 也已接受：−91.45 ms，检出 1613/1648 帧（97.9%），窗口标准差 2.37 ms；该 session 的第一次尝试未通过标记检测率门限。
- 2026-09-29：`online_session_20260929_175149_425293` 视频可解码 1338 帧，但固定标记 ID 4 只检出 644 帧（48.1%，低于 60% 门限）；0–8.81 秒和 36.00–44.61 秒连续漏检，抽帧可见夹爪遮住标记下缘/角。故在轨迹匹配前拒绝。另修复了标定重试成功后 `session.yaml` 留有上次失败 `error` 的问题，并清理了现有已接受 session 的过期错误文字。
- 2026-09-29：第一条新标定 `online_session_20260929_165924_452278/calibration/calibration_001` 已保存 MP4（1268 个采集帧）和 pose MCAP，但主机未安装 `ffprobe`，估计器无法读取帧 PTS；这不是标定质量结论。原始数据可在用户安装 FFmpeg 后直接重算，当前标定仍未通过验收。采集节点的缺工具提示已改为保留原数据并指引重算；反馈测试、构建、flake8 通过，全套测试 80 通过、2 跳过、2 因缺少 `h5py` 失败。
- 2026-09-29：一次真机启动在 Vive 节点导入 `pysurvive` 时退出：已生成的入口脚本使用 `/usr/bin/python3`，而依赖安装在项目 `.venv` 中。用 `.venv/bin/python -m colcon build` 重新构建后，Vive/相机/键盘入口脚本均指向项目 `.venv`，`pysurvive` 与 `rclpy` 导入成功；尚未再次启动真机流程。该次会话 `online_session_20260929_165241_117696` 已标为 complete，录制索引为空。
- 2026-09-28：完整测试 84 项通过。`n` 切换用真实节点、真实 worker、GStreamer 测试画面和合成 pose 端到端跑通。`build_dataset --format both` 用真实 1080p 标定录像复制出的两个测试 session 合并导出，并由 LeRobot 0.4.4 回读正确。以上都是**软件验证**。
- 旧的 `online_session_20260921_181056_923446`（多特征方法，−95.01 ms）已不在当前 `recordings/` 中；当前真实 session 的 accepted 结果见上。现有一条真实任务 episode，但所属 session 尚未标定，不能作为已同步数据直接合并导出。
- 2026-09-20 曾用零 offset 对旧 session 做过对齐与 HDF5/LeRobot 导出诊断（数据已不在工作区），只证明读取和插值通路可用，不代表时间同步精度。
- 录制分支不会主动丢帧，但 `video.validation.json` 的源端完整性仍为 `not_verified`，不能承诺“绝不掉帧”。

## 待验收清单

以下各项的代码都已实现，只剩真机或真实数据验收：

1. **在线多 episode 录制**：用 `online_record.launch.py` 连续录多条 episode，检查目录与索引、MP4 可解码及 `video.validation.json` 帧间隔；pose 覆盖按 D-032 使用已有验收证据。再做长时间 USB/CPU/磁盘/温度测试。
2. **`n` 切换 session**：同一次启动中用 `n` 切换 2～3 个不同 task 的 session，每个录几条 episode，检查目录、`session.yaml`、复制来的标定，以及切换时预览是否正常。
3. **时间标定**：在每个 session 运行 `calibrate_time`，检查曲线、`accepted` 状态和跨次重复性（任务：[时间标定](docs/project/tasks/active/temporal-calibration.md)）。
4. **后处理与合并导出**：按 [D-041 任务](docs/project/tasks/active/raw-to-dataset.md)，已完成独立 90 Hz 双图像展开与起点相对 pose。后续组装当前/下一 pose 的 state/action，落实质量排除与边界策略，升级两个 exporter 并接入 `build_dataset --format both`，再导出真实数据并回读。真实多任务数据与训练侧验收继续跟踪；新增最终训练契约尚未实现。
5. **Vive 与外参**：在 RViz 对比 `vive_world → vive_tracker` 和 `vive_world → gripper_tcp`，检查 TCP 位置与方向、路径显示、遮挡丢失与恢复、基站和世界系稳定性。`publish_hz=90` 只是发布频率。
6. **回放**：在 RViz 中完整回放一个 session，观察画面与路径。
7. **URDF 诊断**：接入真实 URDF 后验收（任务：[URDF 诊断](docs/project/tasks/active/urdf-path-diagnostic.md)）。

尚未开始：相机内参、相机到 Tracker 外参、Action 4 IMU 记录。分支 `feature/multi-task-sessions` 尚未合并、推送。

## 资料入口

- [README.md](README.md)：环境配置和操作步骤。
- [coding_context.md](coding_context.md)：编码入口，描述当前状态和约定。
- [需求](docs/project/REQUIREMENTS.md)、[架构](docs/project/ARCHITECTURE.md)、[决策](docs/project/DECISIONS.md)：决策文件顶部的索引列出每条决策当前是否有效。
- 进行中的任务：[多任务 session](docs/project/tasks/active/multi-task-sessions.md)、[时间标定](docs/project/tasks/active/temporal-calibration.md)、[URDF 诊断](docs/project/tasks/active/urdf-path-diagnostic.md)；已完成的任务在 `docs/project/tasks/archive/`。
