"""Tests for per-video-frame Vive pose interpolation."""

import json

import numpy as np

import pytest

from umi_ros2.postprocess.align_session import load_offset, resolve_episodes
from umi_ros2.postprocess.alignment import (
    interpolate_poses,
    prepare_pose_samples,
    slerp,
)


def test_interpolates_position_and_orientation():
    """Use linear XYZ interpolation and shortest-path quaternion SLERP."""
    times = np.array([0.0, 1.0])
    positions = np.array([[0.0, 0.0, 0.0], [2.0, 4.0, 6.0]])
    orientations = np.array([
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
    ])
    result = interpolate_poses(
        np.array([0.5]), times, positions, orientations,
        maximum_gap_seconds=2.0)
    assert result.valid.tolist() == [True]
    assert result.positions[0] == pytest.approx([1.0, 2.0, 3.0])
    assert result.orientations[0] == pytest.approx(
        [0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)])


def test_rejects_extrapolation_and_large_pose_gaps():
    """Mark unavailable frame poses invalid instead of inventing values."""
    result = interpolate_poses(
        np.array([-0.1, 0.5, 1.1]),
        np.array([0.0, 1.0]),
        np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]),
        np.array([[0.0, 0.0, 0.0, 1.0]] * 2),
        maximum_gap_seconds=0.2)
    assert result.valid.tolist() == [False, False, False]
    assert np.isnan(result.positions).all()


def test_pose_preparation_keeps_last_duplicate_and_normalizes():
    """Make recorded duplicate timestamps deterministic."""
    times, positions, orientations = prepare_pose_samples(
        [1.0, 1.0, 2.0],
        [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
        [[0.0, 0.0, 0.0, 2.0]] * 3)
    assert times.tolist() == [1.0, 2.0]
    assert positions[:, 0].tolist() == [2.0, 3.0]
    assert orientations[:, 3].tolist() == [1.0, 1.0]


def test_slerp_handles_equivalent_opposite_quaternion_signs():
    """Avoid a long rotation when quaternion signs differ."""
    value = slerp(
        np.array([0.0, 0.0, 0.0, 1.0]),
        np.array([0.0, 0.0, 0.0, -1.0]), 0.5)
    assert value == pytest.approx([0.0, 0.0, 0.0, 1.0])


def test_resolves_only_ordinary_session_episodes(tmp_path):
    """Exclude calibration recordings from dataset episode alignment."""
    session = tmp_path / 'online_session_example'
    (session / 'episodes' / 'episode_0010').mkdir(parents=True)
    (session / 'episodes' / 'episode_0002').mkdir()
    (session / 'calibration' / 'calibration_001').mkdir(parents=True)
    (session / 'session.yaml').write_text('mode: online\n', encoding='utf-8')
    _, episodes = resolve_episodes(session)
    assert [episode.name for episode in episodes] == [
        'episode_0002', 'episode_0010']


def test_loads_only_accepted_calibration_result(tmp_path):
    """Require both session and referenced result acceptance."""
    session = tmp_path / 'online_session_example'
    result = session / 'calibration/calibration_001/time_offset.json'
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({
        'accepted': True,
        'video_to_pose_offset_seconds': 0.123,
    }), encoding='utf-8')
    (session / 'session.yaml').write_text(
        'temporal_calibration:\n'
        '  status: accepted\n'
        '  result: calibration/calibration_001/time_offset.json\n',
        encoding='utf-8')
    offset, source = load_offset(session)
    assert offset == pytest.approx(0.123)
    assert source == str(result)
