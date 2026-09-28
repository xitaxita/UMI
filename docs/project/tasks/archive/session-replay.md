# Replay session or individual recording

> **Archived 2026-09-28 (D-022).** Implementation is complete; remaining hardware or real-data acceptance items are tracked in the checklist in `project.md`.

- **Task identity:** `session-replay`
- **Status:** Implemented and software-verified; full RViz acceptance pending
- **Decision source:** D-016

## Goal

Use one replay launch entry for the separated MP4 + pose layout. Detect whether
the input is a session or one calibration/episode, sequence session recordings
as calibration first and ordinary episodes second, and retain RViz image,
Vive-path, and TF display.

## Replay preview improvement (2026-09-16)

The user requested a clearer, smoother RViz replay. Current code reduces the
1920x1080 MP4 to 640x360 and advances rosbag `/clock` at 30 Hz, while skipping
frames more than one 30-fps period late. Scope this change to playback only:
default the replay preview to 1280x720, expose width/height in the replay
launch for operator choice up to the source resolution, and raise replay clock
updates to 120 Hz to reduce scheduling quantization. Preserve recorded MP4,
pose bag, timestamp mapping, frame-rate ceiling, and live preview defaults.
Verify launch arguments, frame dimensions and code style; actual RViz smoothness
still needs visual acceptance on the host.

Implemented: replay defaults to 1280x720, width/height are launch arguments,
and rosbag `/clock` is published at 120 Hz. The old live-preview dimensions
and recording files are unchanged. Current software evidence: all 43 package
tests pass, focused flake8 and Jazzy symlink build pass, and the installed
replay launch exposes both preview arguments. Playback of real data and visual
frame delivery were then checked headlessly as described below; actual RViz
visual smoothness remains to be checked.

The first 1x run on existing 468-frame episode 0001 published 442 previews and
skipped 26 frames with the old one-period late threshold. The replay-only late
allowance was widened to two nominal frame periods (about 67 ms at 30 fps).
After rebuilding, the same 1x run published 443/468 and skipped 25. The old
recording begins video about 0.347 s before its pose bag, so some skips are
expected even with a faster clock. This is a modest frame-delivery improvement,
not full-rate or visual RViz acceptance. At 5x, many preview frames are skipped
because playback compresses wall time.

## Acceptance

- A recording directory containing `video.mp4`, `video.timing.json`, and
  `pose/metadata.yaml` resolves to one replay item.
- An online session resolves natural-sort calibration items before natural-sort
  episode items.
- Incomplete or unsupported input fails with a clear error.
- MP4 preview and matching pose bag run together at the requested playback rate.
- The displayed path resets between session items.

## Current evidence

- Four resolver tests cover direct recording selection, session ordering,
  natural numeric ordering, and incomplete input rejection.
- The real `online_session_20260913_165851_183241` resolves as calibration 001,
  then episodes 001, 002, and 003; its episode 001 resolves independently.
- Installed episode replay opened the real MP4, received matching MCAP `/clock`,
  and exited successfully at 5x. All 32 package tests, focused flake8, build,
  launch parsing, and `git diff --check` pass. Full session/RViz visual
  acceptance is pending.
