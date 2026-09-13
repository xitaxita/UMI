"""Interpolate timestamped poses at corrected video-frame times."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class InterpolatedPoses:
    """Per-query pose values and interpolation diagnostics."""

    valid: np.ndarray
    positions: np.ndarray
    orientations: np.ndarray
    left_indices: np.ndarray
    right_indices: np.ndarray
    alphas: np.ndarray
    gaps: np.ndarray


def prepare_pose_samples(times, positions, orientations):
    """Sort poses, keep the last duplicate, and normalize quaternions."""
    times = np.asarray(times, dtype=np.float64)
    positions = np.asarray(positions, dtype=np.float64)
    orientations = np.asarray(orientations, dtype=np.float64)
    if (times.ndim != 1 or positions.shape != (len(times), 3)
            or orientations.shape != (len(times), 4)):
        raise ValueError('pose arrays have incompatible shapes')
    if len(times) < 2 or not all(
        np.isfinite(values).all()
        for values in (times, positions, orientations)
    ):
        raise ValueError('pose arrays need at least two finite samples')
    order = np.argsort(times, kind='stable')
    times = times[order]
    positions = positions[order]
    orientations = orientations[order]
    keep = np.r_[times[1:] != times[:-1], True]
    times = times[keep]
    positions = positions[keep]
    orientations = orientations[keep]
    if len(times) < 2 or not np.all(np.diff(times) > 0):
        raise ValueError('pose timestamps do not provide a valid time range')
    norms = np.linalg.norm(orientations, axis=1)
    if np.any(norms < 1e-12):
        raise ValueError('pose data contains a zero quaternion')
    return times, positions, orientations / norms[:, None]


def slerp(left, right, alpha):
    """Shortest-path spherical interpolation for XYZW unit quaternions."""
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    alpha = float(alpha)
    dot = float(np.dot(left, right))
    if dot < 0:
        right = -right
        dot = -dot
    dot = np.clip(dot, -1.0, 1.0)
    if dot > 0.9995:
        value = left + alpha * (right - left)
        return value / np.linalg.norm(value)
    angle = np.arccos(dot)
    scale = np.sin(angle)
    value = (
        np.sin((1.0 - alpha) * angle) / scale * left
        + np.sin(alpha * angle) / scale * right
    )
    return value / np.linalg.norm(value)


def interpolate_poses(
        query_times, pose_times, positions, orientations,
        maximum_gap_seconds=0.1):
    """Interpolate poses without extrapolating or crossing large gaps."""
    if maximum_gap_seconds <= 0:
        raise ValueError('maximum pose gap must be greater than zero')
    query_times = np.asarray(query_times, dtype=np.float64)
    if query_times.ndim != 1 or not np.isfinite(query_times).all():
        raise ValueError('query timestamps must be a finite vector')
    pose_times, positions, orientations = prepare_pose_samples(
        pose_times, positions, orientations)
    right = np.searchsorted(pose_times, query_times, side='left')
    right = np.clip(right, 1, len(pose_times) - 1)
    left = right - 1
    gaps = pose_times[right] - pose_times[left]
    valid = (
        (query_times >= pose_times[0])
        & (query_times <= pose_times[-1])
        & (gaps <= maximum_gap_seconds)
    )
    alphas = (query_times - pose_times[left]) / gaps
    alphas = np.clip(alphas, 0.0, 1.0)
    output_positions = np.full((len(query_times), 3), np.nan)
    output_orientations = np.full((len(query_times), 4), np.nan)
    output_positions[valid] = (
        positions[left[valid]] * (1.0 - alphas[valid, None])
        + positions[right[valid]] * alphas[valid, None]
    )
    for index in np.flatnonzero(valid):
        output_orientations[index] = slerp(
            orientations[left[index]], orientations[right[index]],
            alphas[index])
    return InterpolatedPoses(
        valid=valid,
        positions=output_positions,
        orientations=output_orientations,
        left_indices=left,
        right_indices=right,
        alphas=alphas,
        gaps=gaps,
    )
