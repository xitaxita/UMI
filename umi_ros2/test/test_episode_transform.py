"""Tests for episode-local coordinate conversion."""

import numpy as np

import pytest

from umi_ros2.postprocess.episode_transform import (
    quaternion_multiply,
    transform_to_episode_frame,
)


def _inputs(positions, orientations, valid=None):
    count = len(positions)
    if valid is None:
        valid = np.ones(count, dtype=bool)
    return (
        np.arange(count), np.arange(count, dtype=float) / 30,
        100.0 + np.arange(count, dtype=float) / 30,
        100.1 + np.arange(count, dtype=float) / 30,
        valid, np.asarray(positions, dtype=float),
        np.asarray(orientations, dtype=float),
    )


def test_reference_pose_becomes_identity():
    """The first valid aligned frame defines episode coordinate zero."""
    half = np.sqrt(0.5)
    data = transform_to_episode_frame(*_inputs(
        [[1.0, 2.0, 3.0], [1.0, 3.0, 3.0]],
        [[0.0, 0.0, half, half], [0.0, 0.0, half, half]],
    ))
    assert data.reference_frame_index == 0
    assert data.position_xyz[0] == pytest.approx([0.0, 0.0, 0.0])
    assert data.orientation_xyzw[0] == pytest.approx([0.0, 0.0, 0.0, 1.0])
    assert data.position_xyz[1] == pytest.approx([1.0, 0.0, 0.0])


def test_first_valid_frame_is_reference_and_invalid_stays_nan():
    """Do not use or repair invalid prefix frames."""
    data = transform_to_episode_frame(*_inputs(
        [[np.nan] * 3, [4.0, 5.0, 6.0], [5.0, 5.0, 6.0]],
        [[np.nan] * 4, [0.0, 0.0, 0.0, 1.0],
         [0.0, 0.0, 0.0, 1.0]],
        valid=np.array([False, True, True]),
    ))
    assert data.reference_frame_index == 1
    assert np.isnan(data.position_xyz[0]).all()
    assert data.position_xyz[1] == pytest.approx([0.0, 0.0, 0.0])
    assert data.position_xyz[2] == pytest.approx([1.0, 0.0, 0.0])


def test_relative_orientation_uses_inverse_reference():
    """Compute q_relative = inverse(q_reference) * q_world."""
    half = np.sqrt(0.5)
    reference = np.array([0.0, 0.0, half, half])
    delta = np.array([half, 0.0, 0.0, half])
    world_second = quaternion_multiply(reference, delta)
    data = transform_to_episode_frame(*_inputs(
        [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        [reference, world_second],
    ))
    assert data.orientation_xyzw[1] == pytest.approx(delta)


def test_requires_at_least_one_valid_frame():
    """Reject an episode that cannot define a reference pose."""
    with pytest.raises(ValueError, match='no valid aligned frame'):
        transform_to_episode_frame(*_inputs(
            [[np.nan] * 3], [[np.nan] * 4],
            valid=np.array([False]),
        ))
