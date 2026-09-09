# Build the first Vive ROS 2 node

- **Task identity:** `vive-ros2-node`
- **Project and delivery:** UMI, first ROS 2 acquisition delivery
- **Status:** In progress; live pose is user-verified, while path/TF and robustness acceptance remain.
- **Scope source:** User request and the raw-data section of `README.md`.
- **Working copy:** `/home/xing/Documents/UMI`; pre-existing README modification and file deletions are user changes and were preserved.

## Goal and boundary

Deliver a configurable ROS 2 node that reads one Vive tracked device through
pysurvive/libsurvive and publishes a timestamped pose, bounded path, and optional
TF. A provisional launch starts the pose node and RViz. This task does
not include camera acquisition, synchronization, recording orchestration,
calibration, or LeRobot conversion.

## Acceptance and evidence

| Acceptance item | Check | Current conclusion | Evidence |
| --- | --- | --- | --- |
| Package builds as ROS 2 | Build with `colcon` under ROS 2 Jazzy | Pass | `colcon build --packages-select vive_ros2`, 2026-09-07 |
| Backend adaptation and selection are deterministic | Run direct pytest and ROS-native `colcon test` | Pass | 4 tests passed in both workflows, 2026-09-07 |
| Python/style checks pass | Compile files, `flake8 --jobs 1`, and `git diff --check` | Pass | All passed after formatting, 2026-09-07 |
| Provisional visualization launch resolves | Build package and parse installed launch with `ros2 launch --show-args` | Pass | Node and RViz launch resolved on ROS 2 Jazzy, 2026-09-08 |
| Path history remains bounded | Inspect node behavior and configured limit | Implemented, hardware visualization pending | `/vive/path` retains at most 10,000 poses by default |
| Selected Vive device publishes a correct changing pose | Run against libsurvive/Vive and inspect behavior | Pass by user acceptance | User reported on 2026-09-08 that the Vive pose is correct with no problem; no captured log was supplied |
| Published TF matches the pose | Compare `/vive/pose` with `vive_world -> vive_tracker` | Pending | Not explicitly covered by the user report |
| RViz shows the accumulated path | Launch provisional RViz view and move the tracker | Pending | Not explicitly covered by the user report |
| Invalid tracking does not publish stale data | Exercise invalid/recovered hardware state | Pending hardware acceptance | Behavior is implemented but not integration-tested |
| Timestamp is suitable for camera synchronization | Compare ROS publish time with required capture/source time | Pending design/measurement | Current message stamp is ROS time at publication, not libsurvive pose time |
| Combined launch starts on hardware | Run `vive_with_rviz.launch.py` with the connected WM0 device | Pass for startup; visual output still unconfirmed | User log from 2026-09-09 shows pose node and RViz2 started and `WM0` was detected |

## Current execution state

The live pose has now been exercised successfully and accepted by the user. The
package, pysurvive backend, pose adaptation, bounded path publication,
node-only launch, provisional node-plus-RViz launch, RViz path configuration,
tests, and README instructions are
implemented. The next step is to
verify `/vive/path` in RViz, compare TF against `/vive/pose`, and test temporary
tracking loss/recovery. Before camera synchronization work, determine whether
the current ROS publish timestamp is sufficiently accurate.

Libsurvive's native calibrated right-handed world coordinates are retained. Its
`w,x,y,z` quaternion is reordered to ROS `x,y,z,w`. The node uses ROS clock time
when publishing the newest libsurvive update.

## Blockers and unresolved items

The hardware prerequisites are now demonstrably available because the user
obtained a correct live pose. Still unrecorded are the selected device identity,
libsurvive calibration/configuration used, TF/path observations, behavior during
tracking loss, and timestamp error relative to future camera capture. The prior
OpenVR path-registry failure remains irrelevant because OpenVR was removed by
[D-001](../../DECISIONS.md).

The 2026-09-09 combined-launch run detected `WM0` and a Lighthouse generation 2
system. Libsurvive emitted one `MP_MAXITER` pose-solver warning. The run was
stopped by Ctrl-C after about eight seconds, so it does not establish sustained
pose rate or path visibility. The Python pose node was logged with exit code 1
after SIGINT; clean shutdown handling remains to be checked. The experimental
drift monitor from that run was removed at the user's request.

## Latest checkpoint

- **Date/event:** 2026-09-09, experimental drift diagnostics rolled back; pose/path/TF delivery retained.
- **Rollback verification:** 4 tests pass, ROS 2 build/test passes, the RViz
  launch parses, and the install exposes only `vive_pose_node`.
- **Core records:** Root `coding_context.md` and `project.md` reflect this state.
- **Next completion marker:** A real tracker produces changing `/vive/pose` and
  `/vive/path` data, a matching TF, and a visible trajectory in RViz.
- **Archive state:** Not archived because hardware acceptance is outstanding.
