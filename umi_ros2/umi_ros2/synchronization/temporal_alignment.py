"""ROS-independent trajectory alignment inspired by exUMI.

Reference: https://github.com/silicx/exUMI, particularly
``scripts_slam_pipeline/AR_01_arcap_latency_align.py``. This implementation is
project-specific and does not copy exUMI's pipeline or data structures.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AlignmentResult:
    """Result of searching ``pose_time = video_time + offset``."""

    offset_seconds: float
    mse: float
    second_best_mse: float
    uniqueness_margin: float
    overlap_ratio: float
    direction_sign: int
    offsets: np.ndarray
    errors: np.ndarray


def normalize_trajectory(values, minimum_std=1e-9):
    """Remove scalar offset and scale while rejecting stationary data."""
    values = np.asarray(values, dtype=np.float64)
    standard_deviation = float(np.std(values))
    if not np.isfinite(values).all() or standard_deviation < minimum_std:
        raise ValueError('trajectory has insufficient finite motion')
    return (values - np.mean(values)) / standard_deviation


def scalar_pose_trajectory(positions, axis='auto'):
    """Project XYZ poses onto a configured axis or their principal axis."""
    positions = np.asarray(positions, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError('positions must have shape (N, 3)')
    centered = positions - np.mean(positions, axis=0)
    if axis == 'auto':
        _, singular_values, components = np.linalg.svd(
            centered, full_matrices=False)
        if not len(singular_values) or singular_values[0] < 1e-9:
            raise ValueError('Vive trajectory has insufficient motion')
        return centered @ components[0], components[0]
    try:
        index = {'x': 0, 'y': 1, 'z': 2}[axis]
    except KeyError as error:
        raise ValueError('pose axis must be auto, x, y, or z') from error
    direction = np.zeros(3)
    direction[index] = 1.0
    return centered[:, index], direction


def align_trajectories(
        video_times, video_values, pose_times, pose_values,
        minimum_offset=-1.0, maximum_offset=1.0, step=0.001,
        minimum_overlap=0.8, ambiguity_exclusion=0.05):
    """Find the normalized-MSE offset using the exUMI convention.

    The returned offset follows ``pose_time = video_time + offset``. Both
    trajectory signs are tested because image and tracker axes may be reversed.
    """
    video_times = np.asarray(video_times, dtype=np.float64)
    pose_times = np.asarray(pose_times, dtype=np.float64)
    video_values = normalize_trajectory(video_values)
    pose_values = np.asarray(pose_values, dtype=np.float64)
    if (len(video_times) != len(video_values)
            or len(pose_times) != len(pose_values)):
        raise ValueError('trajectory time and value lengths differ')
    if len(video_times) < 3 or len(pose_times) < 3:
        raise ValueError('at least three samples are required per trajectory')
    if (not np.all(np.diff(video_times) > 0)
            or not np.all(np.diff(pose_times) > 0)):
        raise ValueError('trajectory timestamps must be strictly increasing')
    if step <= 0 or maximum_offset <= minimum_offset:
        raise ValueError('invalid offset search range or step')

    offsets = np.arange(
        minimum_offset, maximum_offset + step * 0.5, step,
        dtype=np.float64)
    errors = np.full((2, len(offsets)), np.inf, dtype=np.float64)
    overlaps = np.zeros(len(offsets), dtype=np.float64)
    for offset_index, offset in enumerate(offsets):
        query = video_times + offset
        mask = (query >= pose_times[0]) & (query <= pose_times[-1])
        overlap = float(np.mean(mask))
        overlaps[offset_index] = overlap
        if overlap < minimum_overlap or np.count_nonzero(mask) < 3:
            continue
        interpolated = np.interp(query[mask], pose_times, pose_values)
        try:
            interpolated = normalize_trajectory(interpolated)
            observed = normalize_trajectory(video_values[mask])
        except ValueError:
            continue
        errors[0, offset_index] = np.mean((observed - interpolated) ** 2)
        errors[1, offset_index] = np.mean((observed + interpolated) ** 2)

    flat_index = int(np.argmin(errors))
    sign_index, offset_index = np.unravel_index(flat_index, errors.shape)
    best_error = float(errors[sign_index, offset_index])
    if not np.isfinite(best_error):
        raise ValueError('no offset has sufficient trajectory overlap')
    best_offset = float(offsets[offset_index])
    exclusion = np.abs(offsets - best_offset) <= ambiguity_exclusion
    competitors = errors.copy()
    competitors[:, exclusion] = np.inf
    second_best = float(np.min(competitors))
    margin = (
        (second_best - best_error) / max(second_best, 1e-12)
        if np.isfinite(second_best) else 1.0
    )
    return AlignmentResult(
        offset_seconds=best_offset,
        mse=best_error,
        second_best_mse=second_best,
        uniqueness_margin=float(margin),
        overlap_ratio=float(overlaps[offset_index]),
        direction_sign=1 if sign_index == 0 else -1,
        offsets=offsets,
        errors=np.min(errors, axis=0),
    )
