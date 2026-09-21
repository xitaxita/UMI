"""Transform aligned world poses into an episode-local coordinate frame."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EpisodeFrameData:
    """Versioned arrays consumed by dataset format exporters."""

    frame_index: np.ndarray
    video_pts_seconds: np.ndarray
    video_time_seconds: np.ndarray
    pose_query_time_seconds: np.ndarray
    valid: np.ndarray
    position_xyz: np.ndarray
    orientation_xyzw: np.ndarray
    reference_frame_index: int
    reference_position_xyz: np.ndarray
    reference_orientation_xyzw: np.ndarray


def quaternion_conjugate(quaternion):
    """Return the conjugate of one normalized XYZW quaternion."""
    quaternion = np.asarray(quaternion, dtype=np.float64)
    return np.array([
        -quaternion[0], -quaternion[1], -quaternion[2], quaternion[3],
    ])


def quaternion_multiply(left, right):
    """Multiply XYZW quaternions."""
    lx, ly, lz, lw = np.asarray(left, dtype=np.float64)
    rx, ry, rz, rw = np.asarray(right, dtype=np.float64)
    return np.array([
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    ])


def rotate_vector(quaternion, vector):
    """Rotate a 3-vector with one normalized XYZW quaternion."""
    vector_quaternion = np.r_[np.asarray(vector, dtype=np.float64), 0.0]
    return quaternion_multiply(
        quaternion_multiply(quaternion, vector_quaternion),
        quaternion_conjugate(quaternion),
    )[:3]


def transform_to_episode_frame(
        frame_index, video_pts_seconds, video_time_seconds,
        pose_query_time_seconds, valid, positions, orientations):
    """Rebase valid poses to the first valid aligned video-frame pose."""
    frame_index = np.asarray(frame_index, dtype=np.int64)
    video_pts_seconds = np.asarray(video_pts_seconds, dtype=np.float64)
    video_time_seconds = np.asarray(video_time_seconds, dtype=np.float64)
    pose_query_time_seconds = np.asarray(
        pose_query_time_seconds, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    positions = np.asarray(positions, dtype=np.float64)
    orientations = np.asarray(orientations, dtype=np.float64)
    count = len(frame_index)
    expected_vectors = (
        video_pts_seconds, video_time_seconds, pose_query_time_seconds, valid,
    )
    if any(values.shape != (count,) for values in expected_vectors):
        raise ValueError('aligned scalar arrays have incompatible shapes')
    if positions.shape != (count, 3) or orientations.shape != (count, 4):
        raise ValueError('aligned pose arrays have incompatible shapes')
    valid_indices = np.flatnonzero(valid)
    if not len(valid_indices):
        raise ValueError('episode contains no valid aligned frame')
    reference_index = int(valid_indices[0])
    reference_position = positions[reference_index]
    reference_orientation = orientations[reference_index]
    norm = np.linalg.norm(reference_orientation)
    if not np.isfinite(norm) or norm < 1e-12:
        raise ValueError('episode reference orientation is invalid')
    reference_orientation = reference_orientation / norm
    inverse_reference = quaternion_conjugate(reference_orientation)

    local_positions = np.full((count, 3), np.nan, dtype=np.float64)
    local_orientations = np.full((count, 4), np.nan, dtype=np.float64)
    for index in valid_indices:
        orientation = orientations[index]
        orientation_norm = np.linalg.norm(orientation)
        if not np.isfinite(orientation_norm) or orientation_norm < 1e-12:
            raise ValueError(f'frame {index} orientation is invalid')
        orientation = orientation / orientation_norm
        local_positions[index] = rotate_vector(
            inverse_reference, positions[index] - reference_position)
        local_orientation = quaternion_multiply(
            inverse_reference, orientation)
        local_orientation /= np.linalg.norm(local_orientation)
        if local_orientation[3] < 0:
            local_orientation = -local_orientation
        local_orientations[index] = local_orientation

    return EpisodeFrameData(
        frame_index=frame_index,
        video_pts_seconds=video_pts_seconds,
        video_time_seconds=video_time_seconds,
        pose_query_time_seconds=pose_query_time_seconds,
        valid=valid,
        position_xyz=local_positions,
        orientation_xyzw=local_orientations,
        reference_frame_index=reference_index,
        reference_position_xyz=reference_position.copy(),
        reference_orientation_xyzw=reference_orientation.copy(),
    )
