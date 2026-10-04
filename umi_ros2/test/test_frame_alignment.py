"""Check manual image-to-pose lookup without a ROS playback clock."""

from pathlib import Path

import numpy as np

import pytest

from umi_ros2.visualization import frame_alignment as alignment
from umi_ros2.visualization.replay_source import ReplayItem, ReplayVideo


class FakeFrames:
    """Stand in for decoding while testing physical time/pose associations."""

    def __init__(self, _path):
        """Track cleanup without accessing a file."""
        self.closed = False

    def close(self):
        """Record release of the file handle."""
        self.closed = True


def recording(monkeypatch, wrist_offset=-0.1, left_offset=0.1):
    """Start pose first with rotated axes and unequal image times."""
    pose_times = np.arange(10.0, 11.01, 0.01)
    initial = np.array([0, 0, np.sin(np.pi / 4), np.cos(np.pi / 4)])
    positions = np.column_stack([
        np.full(len(pose_times), 4), 5 + pose_times - 10,
        np.full(len(pose_times), 6)])
    orientations = np.tile(initial, (len(pose_times), 1))
    monkeypatch.setattr(alignment, 'read_vive_poses', lambda _path: (
        pose_times, positions, orientations))
    monkeypatch.setattr(alignment, 'video_frame_times', lambda path: (
        np.array([0, 0.1, 0.2]) if path.name == 'wrist.mp4' else
        np.array([0, 0.04, 0.13, 0.24])))
    monkeypatch.setattr(alignment, 'VideoFrames', FakeFrames)
    videos = (
        ReplayVideo('wrist', Path('wrist.mp4'), 10_500_000_000,
                    wrist_offset, '/wrist'),
        ReplayVideo('left', Path('left.mp4'), 10_350_000_000,
                    left_offset, '/left'),
    )
    item = ReplayItem(Path('episode'), videos[0].video_path, Path('pose'),
                      videos[0].start_ns, 10_000_000_000, videos)
    return alignment.AlignedRecording(item)


def test_signed_offsets_and_start_reference_retain_500ms_buffer(monkeypatch):
    """Apply signed latency to real anchors; first image is not the origin."""
    data = recording(monkeypatch)
    wrist = data.cameras['wrist']
    left = data.cameras['left']
    assert data.reference_time == 10
    np.testing.assert_allclose(wrist.query_times[True], [10.4, 10.5, 10.6])
    np.testing.assert_allclose(
        left.query_times[True], [10.45, 10.49, 10.58, 10.69])
    np.testing.assert_allclose(wrist.poses[True].positions[0], [0.4, 0, 0],
                               atol=1e-12)
    np.testing.assert_allclose(wrist.poses[True].orientations[0], [0, 0, 0, 1],
                               atol=1e-12)
    np.testing.assert_allclose(wrist.poses[False].positions[0], [0.5, 0, 0],
                               atol=1e-12)
    data.close()
    assert all(camera.reader.closed for camera in data.cameras.values())


def test_other_camera_pairs_by_time_not_frame_number(monkeypatch):
    """Select the other camera's nearest corrected time and expose edges."""
    data = recording(monkeypatch)
    target, chosen = data.selection('wrist', 2)
    assert target == pytest.approx(10.6)
    assert chosen == {'wrist': 2, 'left': 2}
    # Left frame 3 at 10.69 s corresponds to wrist's final image at 10.6 s;
    # there is no wrist image at the requested time, so do not reuse the last.
    _, chosen = data.selection('left', 3)
    assert chosen == {'wrist': None, 'left': 3}
    _, chosen = data.selection('wrist', 1)
    assert chosen == {'wrist': 1, 'left': 1}
    _, chosen = data.selection('wrist', 1, calibrated=False)
    assert chosen == {'wrist': 1, 'left': None}


def test_uncovered_pose_is_invalid_instead_of_clamped(monkeypatch):
    """Never show a plausible but incorrect pose outside the saved range."""
    data = recording(monkeypatch, wrist_offset=-0.7)
    wrist = data.cameras['wrist']
    assert not wrist.poses[True].valid[0]
    assert np.isnan(wrist.poses[True].positions[0]).all()
    assert wrist.poses[True].valid[-1]


def test_missing_update_gap_remains_invalid(monkeypatch):
    """Do not interpolate across more than 100 ms without a saved pose."""
    data = recording(monkeypatch)
    monkeypatch.setattr(alignment, 'read_vive_poses', lambda _path: (
        np.array([10.0, 10.1, 10.7, 10.8]), np.zeros((4, 3)),
        np.tile([0, 0, 0, 1], (4, 1))))
    with_gap = alignment.AlignedRecording(data.item)
    assert not with_gap.cameras['wrist'].poses[True].valid.any()


def test_nearest_frame_follows_irregular_timestamps():
    """Irregular spacing and deterministic ties are handled explicitly."""
    times = np.array([0, 0.03125, 0.125, 0.15625])
    assert alignment.nearest_frame(times, 0.078125) == 1
    assert alignment.nearest_frame(times, 0.11) == 2
    assert alignment.nearest_frame(times, 0.15625) == 3
    assert alignment.nearest_frame(times, -0.01) is None
    assert alignment.nearest_frame(times, 0.16) is None
