# Implement exUMI-style temporal calibration

## Goal

Estimate one reviewable constant offset per camera for an uninterrupted
online acquisition session using the exUMI ArUco trajectory-alignment method.

**Current flow (D-036, 2026-09-30):** `c` in the keyboard lists camera numbers;
select one to record its video and pose, with the existing 500 ms pose lead.
Stop immediately estimates its offset using only ArUco centre/scale and TCP
XYZ translation. Print green `accept` or red `reject`. Reject removes that
attempt's raw/derived files and asks for Enter to rerecord in the same folder.
Results are independent in `temporal_calibrations[camera_id]`; wrist retains
the singular compatibility view. Preserve absolute pose/image anchors without
subtracting the 500 ms buffer. This supersedes historical failed-input retention
guidance below. Software tests pass; real per-camera calibration/retry and
cross-launch repeatability remain hardware acceptance.

**Recording-start frame (D-038):** The v4 estimator expresses TCP XYZ in the
fixed frame of the first pose saved after the start command, before the 500 ms
image delay. Apply the inverse initial position/orientation transform; only
the resulting translation channels enter matching. Initial orientation defines
axes, and subsequent orientation is not a motion feature. Results record the
reference pose/time. Dataset conversion uses the same recording-start rule.
Signed-offset tests with initial 90-degree/arbitrary world rotations pass;
full suite has 130 passes, 2 skips and 2 existing missing-h5py failures. Build
and static checks pass; real calibration under this frame remains acceptance.

The current estimator uses only ArUco image centre/scale and recording-start
TCP XYZ translation to estimate the offset. Calibration motion uses left/right,
forward/back, and up/down translation; deliberate rotation is not needed.

## Confirmed scope

- Record or designate one calibration episode after the camera's one-time warmup.
- Use a fixed ArUco marker and repeated assembly translation along left/right,
  forward/back, and up/down axes, bracketed by stationary intervals.
- Extract a scalar marker trajectory from MP4 and a corresponding scalar Vive
  trajectory from the pose MCAP.
- Interpolate both, normalize nuisance scale/offset, search a configured latency
  interval, and minimize MSE with an explicit offset sign convention.
- Save `time_offset.json` and a trajectory/alignment plot with enough evidence
  for operator acceptance or rejection.
- Associate one accepted result with the same uninterrupted online session and
  make later frame-to-pose interpolation consume it.
- Run calibration as soon as a dedicated calibration recording is finalized;
  show the result in the operator terminal and prompt for a new calibration if
  the estimate fails acceptance checks.

## Excluded from the first version

- Optical-flow fallback or per-episode automatic correction.
- Action 4 IMU extraction/alignment.
- Hardware trigger, PTP, PPS or camera timecode integration.
- Joint camera intrinsic, extrinsic and temporal optimization.
- A claimed accuracy target before repeated local measurements.

## Acceptance

1. Synthetic trajectories with known positive and negative offsets recover the
   offset within the configured numerical tolerance.
2. Missing detections, insufficient motion and ambiguous minima fail visibly.
3. A real calibration episode produces source diagnostics, an alignment plot,
   signed offset, residual and acceptance status without altering raw data.
4. Repeated real calibrations quantify repeatability in frames and milliseconds.
5. Session restart/reconnect invalidates reuse; episode boundaries do not.

## Status

Initial estimator implemented on 2026-09-12. `calibrate_time` reads MP4 frame
PTS, detects `DICT_4X4_50` marker ID 4, anchors video time with
`video.timing.json`, reads `/vive/pose` from MCAP, projects pose onto a selected
or automatic principal axis, tests both signs, and performs normalized-MSE
offset search. It writes `time_offset.json` and `alignment_report.png` and
returns a distinct status for rejected fits. `generate_aruco_marker` creates the
printable marker without copying exUMI assets.

Software evidence: five new alignment tests cover positive/negative offsets,
reversed axes, automatic projection and stationary rejection; all 26 package
tests pass. Focused flake8, `git diff --check`, venv package build and installed
CLI help pass. OpenCV detected ID 4 in the generated marker. The MCAP reader
loaded 2,821 `/vive/pose` messages from the existing offline recording.

Pending: repeat calibration across multiple launches, tune acceptance
thresholds from that evidence, and quantify repeatability. Accepted offsets are
already consumed by the separate `align_session` stage; raw recordings remain
immutable.

Multi-feature v2 was implemented on 2026-09-21. It extracted normalized ArUco
centre X/Y, log area and unwrapped in-plane angle, and compared every
informative channel against TCP XYZ, continuous rotation-vector channels and
motion energy. Weak pairs were discarded; agreeing offsets were clustered and
robustly fused. The discrete minimum was quadratically refined and three
temporal windows had to agree. On
`online_session_20260921_181056_923446/calibration/calibration_001`, 1279/1332
frames detected the marker (96.0%); the accepted estimate was approximately
-95.01 ms and the three window estimates were -98.58/-89.40/-90.27 ms (4.14 ms standard
deviation). This is one real run, not yet a repeated-session accuracy claim.

On 2026-09-29, the estimator was simplified to use only ArUco centre X/Y and
log area against TCP position X/Y/Z. ArUco in-plane angle and TCP orientation
are excluded from estimation, and operators need not rotate the assembly.
Synthetic alignment coverage now exercises three translation channels. Real
recording acceptance under the translation-only method remains pending.

Session organization was implemented on 2026-09-13. A dedicated calibration is
started through `start_calibration` and stored under
`online_session_<timestamp>/calibration/calibration_<sequence>`. The estimator
updates that session's `session.yaml` with accepted/rejected status, the result
path, and signed offset. Ordinary recordings are indexed under `episodes/`.

On 2026-09-29, the camera node was changed to invoke the existing estimator
immediately after finalizing and registering a calibration recording. The
keyboard stop response reports the accepted offset and plot path, or a rejection
or failure with a prompt to record again. A failed attempt clears any previous
accepted result from the session index. Software verification and hardware
acceptance are pending.

The first live attempt recorded a complete MP4 and MCAP but could not analyze
them because `ffprobe` was not installed. This is an environment failure, not
a quality rejection. The capture node now reports how to install FFmpeg and
rerun `calibrate_time` on the same recording; it marks the session
`not_calibrated` until analysis succeeds. Acceptance of that recording remains
open; the dependency was subsequently installed and a later recording ran the
estimator.

In the next live recording,
`online_session_20260929_171213_710643/calibration/calibration_001`, the
translation-only estimator ran with `ffprobe` available. It found 971 markers
in 993 frames (97.8%), 0.450 m of TCP motion and a whole-recording offset of
-98.07 ms. The result was rejected solely by window consistency: windows 1
and 2 estimated -61.75 and -105.41 ms, giving a 21.83 ms population standard
deviation against the configured 20 ms limit. Window 3 failed because its
informative motion channels did not agree. A read-only rerun reproduced these
per-window outcomes; no result files or thresholds were changed.

Two subsequent real sessions have accepted translation-only estimates.
`online_session_20260929_174955_015048/calibration/calibration_001` yielded
-83.71 ms with 1302/1356 marker detections (96.0%) and 1.80 ms standard
deviation across two valid windows. In
`online_session_20260929_175651_544205`, the first calibration was rejected
for marker detection ratio, then `calibration_002` was accepted at -91.45 ms
with 1613/1648 detections (97.9%) and 2.37 ms window standard deviation.
These are accepted estimates, not yet a measured hardware synchronization
accuracy or downstream real-episode validation.

`online_session_20260929_175149_425293/calibration/calibration_001` was
rejected before trajectory matching: marker ID 4 was detected in 644/1338
frames (48.1%, below the 60% requirement). The video decoded and its frame
count matched acquisition. Detections were absent continuously during
0-8.81 s and 36.00-44.61 s; sampled frames show the gripper crossing the
marker's lower edge and corners in those intervals, while the middle segment
is mostly detectable. Preserve the full marker and its border in the camera
view throughout recording, including the stationary intervals.

D-026 corrects a misleading metadata state observed after the second attempt
was accepted: `session.yaml` still contained the first attempt's `error`.
Completed estimates now replace previous result fields. The stale error was
also removed from that accepted session's metadata; raw recordings and offset
files were not changed.
