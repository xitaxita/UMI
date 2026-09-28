# 多任务 session 重构（交接文档）

- **任务标识：** `multi-task-sessions`
- **状态：** 阶段 1～4 代码完成，均已软件验证；阶段 3 待真机验收；阶段 4 待用真实多任务 episode 数据验收；分支未合并、未推送
- **决策来源：** D-021（2026-09-28 已写入 `DECISIONS.md`）
- **分支：** `feature/multi-task-sessions`
- **交接日期：** 2026-09-28

> 给接手的会话：开始前先读 `AGENTS.md`、`coding_context.md` 和本文件，再看相关源码及
> `git status`。本文件是和用户讨论后确认的方案，除非用户另有要求，否则照做；遇到本文件
> 没有覆盖到的决定，先问用户。

## 背景与目标

用户要重建在线采集流程：

1. **一个 session 对应一个任务**，里面可以有多条 episode；换任务就开新的 session。
2. 每个 session 在 `session.yaml` 里维护一个 **`task` 字段**（自然语言指令，之后直接作为
   LeRobot 的语言 task）。
3. 导出 HDF5 或 LeRobot v3 时，**可以把多个 session 合并成同一个 dataset**。
4. **删除离线采集模式。**

## 工作规则（用户明确要求）

- **先开新分支**，建议名为 `feature/multi-task-sessions`。开分支前先用 `git status` 检查未提交的
  改动（工作区里有 9 月 23 日之后的改动，例如 URDF 诊断）。和用户确认后，把需要保留的改动
  先提交成一个快照。**不要**把根目录的 `DJI_20260917130727_0009_D.MP4`（约 158 MB）加进 git，
  可以建议写进 `.gitignore`。
- **每完成一个阶段的代码就提交一次 git**（阶段划分见下文）。
- 按 `AGENTS.md` 的要求：动手前先把决策写进 `DECISIONS.md`；每个阶段完成后同步
  `coding_context.md` 和 `project.md`；区分“已实现”“软件已验证”“真机已验收”这三种状态；
  保留用户已有的改动。
- 每个阶段都要跑 `colcon build` 和完整 `pytest`，另外对改动过的文件跑 flake8 和
  `git diff --check`。ROS 环境是 `~/umi_ros_venv`（ROS 2 Jazzy）；LeRobot 0.4.4 装在独立的
  `~/umi_lerobot_venv312` 中，不要把 LeRobot 装进 ROS 的 venv。

## 已确认的设计决定

| 项目 | 决定 |
| --- | --- |
| 离线模式 | 整体删除，不保留兼容入口 |
| session 与任务 | 一个 session 只对应一个 task；每个 session 都是自包含的，**session 之间没有任何运行时或后处理依赖** |
| task 写在哪里 | 只写在 `session.yaml` 里；**session 目录名不带 task**，仍是 `online_session_<时间戳>` |
| launch 时的 task | `task:=` 参数**可以不填**；不填时终端给出警告，之后用工具补上。补填方法写进 README |
| 切换 session | 同一个 launch 里用键盘切换（`n` 命令），相机、Vive 和 pose 订阅都不重启；也可以 Ctrl+C 后带新的 `task:=` 重新启动。两种方式得到的 session 结构完全一样 |
| 同一个 launch 内的标定 | 切换 session 时，把上一个 session 的 calibration **原始数据复制**到新 session，然后在新 session 里重新运行 `calibrate_time`。**不共享 offset，也不在后处理时跨 session 查找标定** |
| 跨 launch 的标定 | 不复制；重新启动后必须重新录 calibration（沿用现有规则） |
| 数据集合并 | 每个 session 独立完成标定、`align_session` 和 `transform_session`，只在导出这一步合并；每次都按给定的 session 列表**从头重建**，不做增量追加 |

## 分阶段计划

### 阶段 1：删除离线采集

1. 在 `DECISIONS.md` 顶部新增 **D-021**，内容覆盖本文件中已确认的全部决定；其中写明取消离线
   模式，并替代 D-010。后面的阶段可以追加 amendment。
2. 全仓搜索 `offline`、`create_offline_session`、`offline_record`、`offline.rviz` 和
   `offline_session`，列出所有涉及的地方，然后删除或改写：
   - `umi_ros2/launch/offline_record.launch.py`
   - `umi_ros2/umi_ros2/session/layout.py` 中的 `create_offline_session()`
   - `setup.py` 中对应的安装项
   - `umi_ros2/rviz/offline.rviz`：**先确认**回放或其他 launch、`launch_support.py`
     有没有引用它，被引用就保留或改名，没有被引用就删除
   - 回放 resolver、`calibrate_time` 以及其他代码中专门处理离线 session 布局的分支
   - `test/` 中离线相关的用例，重点看 `test_launch_contracts.py` 和 `test_session_layout.py`
3. 文档：
   - `docs/project/tasks/active/offline-acquisition.md` 用 `git mv` 移到 `tasks/archive/`
   - README 中“离线模式”一节（约第 489–530 行）
   - `project.md` 中的离线部分（能力表中的“离线采集”行、“离线模式现状”一节、待办第 4 条）
   - `REQUIREMENTS.md`、`ARCHITECTURE.md` 和 `coding_context.md` 中的离线描述
4. 构建、测试，然后提交：`Remove offline acquisition mode`。

**阶段 1 结果（2026-09-28）：** 已完成。`offline.rviz` 只被离线 launch 和 `launch_support.py` 引用，
已删除；回放 resolver、`calibrate_time`、`align_session` 中没有专门处理离线布局的分支。
验证：colcon symlink build 通过（需手动删除 `build/`、`install/` 中指向已删文件的失效符号链接），
安装后的 launch 列表不再含离线入口；pytest 52/52 通过；改动文件 flake8 仅剩未改动行的既有
D100/I201 警告；`git diff --check` 通过。开分支前按用户要求改写了未推送的 `data` 提交以移除
DJI 原始 MP4，并把工作区改动提交为快照。

### 阶段 2：session.yaml v2 与 task 字段

1. 将 `schema_version` 升为 2，新增顶层字段 `task`（字符串，可以为空）。`register_recording()`
   在每条 recording 记录里写入当时的 `task` 快照。v1 的 session 必须仍然可读（读到没有 `task`
   的 v1 时，视为 task 为空）。
2. `online_record.launch.py` 新增 `task` 参数（默认为空），传入相机节点
   `h264_capture_node.py`（新增 ROS 参数 `task`），再写进 `create_online_session()`。
   task 为空时，在终端给出清楚的警告。
3. 新增一次性工具 `set_session_task <session> "<task>"`，注册为 `setup.py` 的入口。它只修改
   `session.yaml`（用 layout 里已有的原子写入方式），不改动任何 MP4 或 MCAP；可用于补填和
   修改 task，也可以把 v1 的 session 升级为 v2。是否同时更新每条 recording 里的 task 快照，
   由实现者决定并写进文档。
4. README 写明两种填写 task 的方法：launch 时用 `task:=` 传入，或者事后用
   `set_session_task` 补填。
5. 补充测试：v2 字段、v1 兼容、`set_session_task`、launch 合约中的 `task` 参数。
6. 构建、测试，然后提交。

**阶段 2 结果（2026-09-28）：** 已完成。实现选择写入 D-021 amendment：`set_session_task` 只改顶层
`task`（并记录 `task_updated_at`），**不改写** recording 中的 task 快照；`status: active` 的 session
默认拒绝，需 `--force`。未知 `schema_version` 读取时报错。验证：pytest 58/58；改动文件 flake8
通过；`git diff --check` 通过；构建后 `set_session_task --help`、launch `--show-args` 正常；
launch 参数替换对 `''`、`123`、`true`、中文、`a: b` 都以字符串传给节点；无相机时运行相机节点，
能创建带空 task（有警告）和中文 task 的 v2 session；用真实 v1 `session.yaml` 的副本验证升级正确，
原始数据未改动。

### 阶段 3：在同一个 launch 里切换 session，并复制标定数据

1. `episode_keyboard` 新增 `n` + 回车：提示输入新 task（允许为空），然后请求相机节点切换
   session。
   - 实现时注意：`ament_python` 包不能生成自定义 srv。建议的做法是，键盘程序先设置相机节点的
     参数（例如 `next_task`），再调用新增的 `std_srvs/Trigger` 服务 `new_session`。
     **先读现有的 `episode_keyboard.py` 和相机节点的服务实现**，沿用原有风格。
2. 相机节点处理 `new_session` 的流程：
   - 如果正在录制，拒绝切换，并返回明确的错误信息。
   - 把旧 session 标记为 `status: complete` 并写入 `ended_at`；新建 `online_session_<时间戳>`
     和它的 `session.yaml`（写入新 task），episode 编号从 0001 重新开始。
   - 相机 worker 和常驻 pose recorder 都**不重启、不重新预热**；之后的录制写进新 session 的
     目录。要检查 capture worker 和 pose recording worker 是否把 session 路径写死在了进程里
     （例如状态文件 `.online_camera_status.json`、`.online_pose_status.json` 放在 session 根目录
     下），必要时改为每次录制都传入路径。
3. 复制标定数据：
   - 把旧 session 中 `calibration/calibration_*` 下的全部条目复制到新 session 的
     `calibration/`，编号保持不变。
   - **只复制原始数据**：`video.mp4`、`video.timing.json`、`video.validation.json` 和 `pose/`。
     **不复制**派生结果：`time_offset.json`、`alignment_report.png`、`trajectory_*.png` 等。
     新 session 的 `temporal_calibration.status` 为 `not_calibrated`。
   - 先复制到临时目录（例如 `calibration_001.partial`），全部完成后再改名；复制完成之前不接受
     新的录制请求。
   - 在新 session 的 `recordings` 里登记这条 calibration，并加上
     `copied_from: <旧session名>/calibration/calibration_001`。这个字段**只用于追溯，任何
     后处理都不读取它**。
   - 如果旧 session 没有 calibration：不复制，并在终端提示“本 session 没有标定数据，请录一条”。
   - 旧 session 中的 calibration 本身也是复制来的：照样复制，这样一次 launch 里只需要录一次标定。
   - 在新 session 里再录一条 calibration 时，编号接着往下排（002…）。
4. 选择用哪条标定：`process_session --run-calibration` 现在用 `_first_calibration()` 取编号
   最小的一条，**要改为默认取编号最大（也就是最新）的一条**，并允许显式指定使用哪一条。
   `calibrate_time` 直接以某一条 calibration 目录作为输入，这一点保持不变。
5. 补充测试：录制中拒绝切换；复制的文件清单正确，派生结果没有被复制；复制保证完整（中途失败
   时不留下半个目录）；没有标定可复制的情况；复制链传递；新旧 calibration 的编号和默认选择。
6. 构建、测试，然后提交。**需要用户用真机验收**：在同一个 launch 中连续切换两到三个 session，
   每个 session 都录几条 episode，并检查各 session 的目录和 `session.yaml`。

**阶段 3 结果（2026-09-28）：** 已实现，软件已验证，**真机未验收**。实现细节写入 D-021 第二条
amendment。“需要先核实”各项的结论：`episode_keyboard` 原本只用三个 `std_srvs/Trigger` 服务；两个
worker 的录制输出路径本来就是每次 start 命令传入，只有状态文件写死在 session 根目录，现已移到
每次 launch 的临时目录；回放 resolver 按 `calibration_*` 名称和数字顺序列出条目，复制来的标定
可以正常回放，隐藏的 `.partial` 目录不会被识别。验证：pytest 70/70（新增 `test_session_switch.py`：
录制中拒绝、复制清单与派生结果排除、中途失败回滚、隐藏临时目录、无标定、复制链、编号与默认
选择、`--calibration` 参数检查、键盘 `n` 录制中不停止）；改动文件 flake8、`git diff --check`、
构建通过；另用真实节点 + 两个真实 worker + `videotestsrc` + 合成 `/vive/pose` 做了端到端运行
（见 `coding_context.md`）。注意：复制在服务回调中同步进行，复制大文件时 RViz 预览会暂停。

### 阶段 4：多 session 合并导出

1. 新增 `build_dataset` 入口：
   ```bash
   ros2 run umi_ros2 build_dataset <session...> | <包含多个session的目录> \
       --format hdf5|lerobot|both --output <数据集路径> [--repo-id owner/name] \
       [--run-calibration] [--overwrite]
   ```
   - 对每个 session 依次处理：标定（使用它自己已 accepted 的结果；如果传了 `--run-calibration`，
     就用最新的一条 calibration 现场跑），然后运行 `align_session` 和 `transform_session`。
     中间结果放在 `processed/<session名>/` 下。
   - task 从各自的 `session.yaml` 读取，不再使用 `--task` 参数。
2. 导出前的统一检查，任何一项不满足都要**整体失败**，并指出是哪个 session、什么原因：
   task 不为空；标定为 accepted；图像尺寸和 fps 一致；中间结果的 contract 版本一致。
3. HDF5：
   - episode 在整个数据集中统一编号（`episode_0000…`）。
   - 每个 episode 组的 attrs 包括：`task`、`task_index`、`source_session`、`source_episode`、
     `video_to_pose_offset_seconds`。
   - 根目录下新增 `tasks` 表（task_index → task 字符串），并去掉根目录上单一的 `task` 属性；
     `format_version` 加 1。
4. LeRobot v3：`_add_episode()` 的 `task` 改为从所属 session 读取，LeRobot 会自动生成
   `tasks.parquet` 和 `task_index`。每一帧新增字段 `umi.source_session`；`umi_export.json`
   中列出所有来源 session、task 以及各自的 offset。继续**不生成** `action` 字段。
5. 保留 `process_session`，作为只处理一个 session 的用法（可以改为调用 `build_dataset` 的内部
   > 2026-09-28：D-022 已删除 `process_session`，单个 session 也用 `build_dataset`。
   函数），保证老命令仍然可用。
6. 补充测试：多 session 的 HDF5 合并（编号、task_index 和 tasks 表都正确）；各项检查失败时报出
   正确的原因；单 session 的行为与原来一致。
7. 构建、测试，用真实的 session 做一次合并导出，并用 LeRobot 回读检查，然后提交。

**阶段 4 结果（2026-09-28）：** 已实现并软件验证。实现选择写入 D-021 第三条 amendment（输出目录
结构、`--run-calibration` 只对未 accepted 的 session 运行、帧率由真实 PTS 间隔测得等）。验证：pytest
83/83（新增 `test_build_dataset.py`：多 session HDF5 编号/task_index/tasks 表/属性、预检整体失败
并列出原因、`--run-calibration` 选最新、尺寸与帧率不一致、contract 版本不一致、对齐被拒、
`--overwrite` 安全、session 解析、`process_session` 默认 task、LeRobot 计划与逐帧 task/来源、
venv 解释器符号链接）；改动文件 flake8、`git diff --check`、构建通过。真实数据：工作区唯一的
真实 session 没有 episode，因此在临时目录把它的 accepted calibration 录像复制为两个不同 task
的测试 session 的 episode，用 `build_dataset --format both` 合并导出，HDF5 与 LeRobot 0.4.4 回读
均正确（详见 `coding_context.md`）；原始数据未被修改。过程中发现并修复：OpenCV 报告的帧率为
29.969（改用 PTS 间隔）；LeRobot 解释器路径被 `resolve()` 到系统 Python（`process_session` 同样
受影响，已一并修复）。

### 收尾

- [x] `project.md`（能力表、在线文件结构、操作流程、待办）和 `coding_context.md` 已更新（2026-09-28）。
- [x] 本文件状态与各阶段验证证据已写明。
- [ ] 用户真机验收阶段 3，并用真实多任务 episode 验收阶段 4。
- [ ] 分支 `feature/multi-task-sessions` 由用户决定何时合并/推送。

## 需要先核实的地方（交接时尚未读过相关源码）

- 列出 `offline.rviz` 的全部引用，确认删除后不会影响回放。
- `episode_keyboard.py` 现在用什么方式和相机节点通信（服务名和服务类型）。
- `capture_worker.py` 和 `pose_recording_worker.py` 在切换 session 时能否在不重启进程的情况下
  更换输出路径。
- 回放的 resolver（`visualization/replay_source.py`）遇到带有复制来的 calibration 的 session，
  是否能正常按顺序回放。

## 当前数据现状（供参考）

- `recordings/` 中只有 `online_session_20260921_181056_923446`：里面有 1 条 calibration，
  状态为 accepted，offset 为 -95.01 ms；`episodes/` 是空的。它是 v1 session，没有 task。
