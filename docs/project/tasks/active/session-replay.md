# Replay session or individual recording

- **Task identity:** `session-replay`
- **Status:** Implemented and software-verified; full RViz acceptance pending
- **Decision source:** D-016

## Goal

Use one replay launch entry for the separated MP4 + pose layout. Detect whether
the input is a session or one calibration/episode, sequence session recordings
as calibration first and ordinary episodes second, and retain RViz image,
Vive-path, and TF display.

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
