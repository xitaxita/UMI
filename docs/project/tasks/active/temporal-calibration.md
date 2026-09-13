# Implement exUMI-style temporal calibration

## Goal

Estimate one reviewable constant video-to-Vive time offset for an uninterrupted
online acquisition session using the exUMI ArUco trajectory-alignment method.

## Confirmed scope

- Record or designate one calibration episode after the camera's one-time warmup.
- Use a fixed ArUco marker and repeated horizontal left/right assembly motion,
  bracketed by stationary intervals.
- Extract a scalar marker trajectory from MP4 and a corresponding scalar Vive
  trajectory from the pose MCAP.
- Interpolate both, normalize nuisance scale/offset, search a configured latency
  interval, and minimize MSE with an explicit offset sign convention.
- Save `time_offset.json` and a trajectory/alignment plot with enough evidence
  for operator acceptance or rejection.
- Associate one accepted result with the same uninterrupted online session and
  make later frame-to-pose interpolation consume it.

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

Pending: record one real calibration episode, tune acceptance thresholds from
its evidence, quantify repeatability, and implement consumption of an accepted
offset during frame-to-pose interpolation. The current code does not alter or
synchronize ordinary episode data yet.

Session organization was implemented on 2026-09-13. A dedicated calibration is
started through `start_calibration` and stored under
`online_session_<timestamp>/calibration/calibration_<sequence>`. The estimator
updates that session's `session.yaml` with accepted/rejected status, the result
path, and signed offset. Ordinary recordings are indexed under `episodes/`.
