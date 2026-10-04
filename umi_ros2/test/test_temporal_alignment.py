"""Tests for exUMI-style trajectory time alignment."""

import numpy as np

import pytest

from umi_ros2.synchronization.temporal_alignment import (
    align_feature_trajectories,
    align_trajectories,
    scalar_pose_trajectory,
)


@pytest.mark.parametrize('expected_offset', (-0.173, 0.127))
def test_recovers_signed_offset(expected_offset):
    """Recover known positive and negative video-to-pose offsets."""
    video_times = np.arange(2.0, 9.0, 1 / 30)
    pose_times = np.arange(1.0, 10.0, 1 / 90)

    def motion(time_values):
        return (np.sin(time_values * 2.1)
                + 0.35 * np.sin(time_values * 5.3))

    video_values = motion(video_times)
    pose_values = motion(pose_times - expected_offset)
    result = align_trajectories(
        video_times, video_values, pose_times, pose_values,
        step=0.001)

    assert result.offset_seconds == pytest.approx(expected_offset, abs=0.002)
    assert result.mse < 0.001
    assert result.direction_sign == 1


def test_recovers_reversed_axis_direction():
    """Image and Vive axes may point in opposite directions."""
    video_times = np.arange(0.5, 5.5, 1 / 30)
    pose_times = np.arange(0.0, 6.0, 1 / 90)
    video_values = np.sin(video_times * 2.3)
    pose_values = -np.sin((pose_times - 0.083) * 2.3)
    result = align_trajectories(
        video_times, video_values, pose_times, pose_values)

    assert result.offset_seconds == pytest.approx(0.083, abs=0.002)
    assert result.direction_sign == -1


def test_auto_axis_finds_dominant_motion():
    """Automatic projection follows the largest 3D movement direction."""
    values = np.linspace(-1, 1, 30)
    positions = np.column_stack((0.01 * values, values, 0.02 * values))
    projected, direction = scalar_pose_trajectory(positions)

    assert np.ptp(projected) > 1.9
    assert abs(direction[1]) > 0.99


def test_stationary_trajectory_is_rejected():
    """A calibration without motion cannot produce a valid offset."""
    times = np.arange(10, dtype=float)
    with pytest.raises(ValueError, match='insufficient'):
        align_trajectories(times, np.ones(10), times, np.ones(10))


def test_multifeature_alignment_recovers_substep_offset():
    """Fuse ArUco translation and TCP XYZ channels at one latency."""
    expected = 0.1374
    video_times = np.arange(2.0, 10.0, 1 / 30)
    pose_times = np.arange(1.0, 11.0, 1 / 90)

    def source(times):
        return np.column_stack((
            np.sin(times * 1.7) + 0.2 * np.sin(times * 4.1),
            np.cos(times * 1.1) + 0.15 * np.sin(times * 3.3),
            np.sin(times * 0.7 + 0.4),
        ))

    pose = source(pose_times - expected)
    latent = source(video_times)
    mapping = np.diag([0.8, 0.7, 0.8])
    video = latent @ mapping
    result = align_feature_trajectories(
        video_times, video, pose_times, pose, step=0.002)

    assert result.offset_seconds == pytest.approx(expected, abs=0.003)
    assert result.mse < 0.1
