# Align video frames to Vive poses

- **Task identity:** `align-session`
- **Status:** In progress
- **Decision source:** D-017

## Goal

Provide a non-ROS Python CLI that consumes an online session or one episode,
applies an accepted constant video-to-pose offset, and produces one interpolated
Vive pose per actual MP4 frame timestamp without modifying raw recordings.

## Output contract

Each processed episode writes `aligned_frames.npz`, an inspectable
`aligned_frames.csv`, and `alignment.json` under a separate output root. Samples
contain frame index/PTS, absolute video time, corrected pose query time,
interpolation bracket/gap, validity, XYZ position, and XYZW quaternion.

## Acceptance

- Session input processes ordinary episodes in numeric order; episode input
  processes only itself.
- Offset is loaded only from an accepted session calibration unless explicitly
  overridden for diagnostics.
- Positions use linear interpolation and unit quaternions use shortest-path
  SLERP.
- Frames outside pose coverage or spanning an excessive pose gap are invalid,
  never extrapolated.
- Raw files remain unchanged and existing output is not overwritten unless the
  operator explicitly requests it.
