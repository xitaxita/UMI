# Implement pose-only offline acquisition

- **Task identity:** `offline-acquisition`
- **Status:** Archived 2026-09-28 — offline mode removed by D-021 (code deleted; never hardware-accepted)
- **Decision source:** D-010

## Goal

Provide one offline-named entry point that records only Vive pose and TF on the
computer, keeps RViz pose/path/TF visualization available, and creates a session
layout compatible with later Action 4 video placement.

## Session contract

```text
recordings/offline_session_<timestamp>/
├── session.yaml
├── calibration/    # reserved; detailed offline use is not yet defined
├── video.mp4       # copied here later by the operator; absent during capture
└── pose/
    ├── metadata.yaml
    └── *.mcap
```

The pose bag records `/vive/pose`, `/tf`, and `/tf_static`. `/vive/path` remains
visualization-only. No Action 4 USB process or image topic participates.

## Acceptance

- `offline_record.launch.py` uses `session_output` and defaults to an
  `offline_session_<timestamp>` directory.
- The launch creates `session.yaml` and `calibration/` before recording.
- The rosbag2 output is `<session_output>/pose`.
- Runtime process names remain `umi_offline_pose_recorder` and
  `umi_offline_rviz`.
- Vive or recorder failure stops the whole session.
- RViz displays pose/path/TF while recording.
- Hardware run produces a readable pose MCAP; operator-added `video.mp4` shares
  the same session root.

## Current evidence

- Launch implementation and static contracts are complete.
- Session-layout implementation is complete; current verification is recorded
  in `coding_context.md`.
- Hardware recording and manual video placement are not yet accepted.
