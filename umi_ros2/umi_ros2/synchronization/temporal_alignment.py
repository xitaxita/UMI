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


def _standardize_columns(values, minimum_std=1e-8):
    """Standardize informative columns and discard constant channels."""
    values = np.asarray(values, dtype=np.float64)
    deviations = np.std(values, axis=0)
    mask = np.isfinite(deviations) & (deviations >= minimum_std)
    if not np.any(mask) or not np.isfinite(values).all():
        raise ValueError('feature trajectory has insufficient finite motion')
    selected = values[:, mask]
    return (selected - np.mean(selected, axis=0)) / np.std(
        selected, axis=0)


def _motion_features(times, values):
    """Return standardized values plus signed velocity and motion energy."""
    normalized = _standardize_columns(values)
    velocity = np.gradient(normalized, times, axis=0)
    if len(velocity) >= 5:
        kernel = np.ones(5) / 5
        velocity = np.column_stack([
            np.convolve(velocity[:, index], kernel, mode='same')
            for index in range(velocity.shape[1])
        ])
    velocity = _standardize_columns(velocity)
    energy = np.sqrt(np.mean(np.square(velocity), axis=1))[:, None]
    energy = _standardize_columns(energy)
    return np.column_stack((normalized, velocity)), energy[:, 0]


def _regression_error(observed, predictors, ridge=1e-3):
    """Score held-out prediction without fitting the validation set."""
    count = len(observed)
    training = np.arange(count) % 3 != 0
    validation = ~training
    if np.count_nonzero(training) < predictors.shape[1] + 2:
        training[:] = True
        validation[:] = True
    design = np.column_stack((predictors, np.ones(count)))
    gram = design[training].T @ design[training]
    regularizer = np.eye(gram.shape[0]) * ridge
    regularizer[-1, -1] = 0
    coefficients = np.linalg.solve(
        gram + regularizer, design[training].T @ observed[training])
    residual = observed[validation] - design[validation] @ coefficients
    return float(np.mean(np.square(residual)))


def _quadratic_minimum(offsets, errors, index):
    """Refine an interior sampled minimum with a local parabola."""
    if index == 0 or index == len(errors) - 1:
        return float(offsets[index])
    left, middle, right = errors[index - 1:index + 2]
    denominator = left - 2 * middle + right
    if not np.isfinite([left, middle, right]).all() or denominator <= 0:
        return float(offsets[index])
    adjustment = 0.5 * (left - right) / denominator
    return float(offsets[index] + np.clip(adjustment, -1, 1)
                 * (offsets[index + 1] - offsets[index]))


def align_feature_trajectories(
        video_times, video_features, pose_times, pose_features,
        minimum_offset=-1.0, maximum_offset=1.0, step=0.001,
        minimum_overlap=0.8, ambiguity_exclusion=0.05):
    """Align and robustly fuse informative marker/TCP channel pairs."""
    video_times = np.asarray(video_times, dtype=np.float64)
    pose_times = np.asarray(pose_times, dtype=np.float64)
    video_motion = _standardize_columns(video_features)
    pose_motion = _standardize_columns(pose_features)
    _, video_energy = _motion_features(video_times, video_features)
    _, pose_energy = _motion_features(pose_times, pose_features)
    candidates = []
    for video_column in range(video_motion.shape[1]):
        for pose_column in range(pose_motion.shape[1]):
            candidate = align_trajectories(
                video_times, video_motion[:, video_column],
                pose_times, pose_motion[:, pose_column],
                minimum_offset, maximum_offset, step, minimum_overlap,
                ambiguity_exclusion)
            if candidate.mse <= 0.8 and candidate.uniqueness_margin >= 0.03:
                candidates.append(candidate)
    energy_candidate = align_trajectories(
        video_times, video_energy, pose_times, pose_energy,
        minimum_offset, maximum_offset, step, minimum_overlap,
        ambiguity_exclusion)
    if (energy_candidate.mse <= 0.8
            and energy_candidate.uniqueness_margin >= 0.03):
        candidates.append(energy_candidate)
    if len(candidates) < 2:
        raise ValueError('fewer than two informative motion channels agree')

    weights = np.asarray([
        item.uniqueness_margin / max(item.mse, 0.02)
        for item in candidates
    ])
    candidate_offsets = np.asarray([
        item.offset_seconds for item in candidates
    ])
    agreement_radius = max(0.030, step * 3)
    support = np.asarray([
        np.sum(weights[np.abs(candidate_offsets - offset)
                       <= agreement_radius])
        for offset in candidate_offsets
    ])
    center = candidate_offsets[int(np.argmax(support))]
    agreed = np.abs(candidate_offsets - center) <= agreement_radius
    if np.count_nonzero(agreed) < 2:
        raise ValueError('informative motion channels do not agree on offset')
    candidates = [item for item, keep in zip(candidates, agreed) if keep]
    weights = weights[agreed]
    candidate_offsets = candidate_offsets[agreed]
    order = np.argsort(candidate_offsets)
    cumulative = np.cumsum(weights[order])
    median_index = order[np.searchsorted(cumulative, cumulative[-1] / 2)]
    best_offset = float(candidate_offsets[median_index])
    offsets = candidates[0].offsets
    normalized_curves = []
    for item in candidates:
        finite = item.errors[np.isfinite(item.errors)]
        scale = np.percentile(finite, 75) - np.min(finite)
        normalized_curves.append(
            np.clip((item.errors - np.min(finite)) / max(scale, 1e-9),
                    0, 10))
    errors = np.average(normalized_curves, axis=0, weights=weights)
    best_index = int(np.argmin(np.abs(offsets - best_offset)))
    exclusion = np.abs(offsets - best_offset) <= ambiguity_exclusion
    competitors = errors.copy()
    competitors[exclusion] = np.inf
    second_best = float(np.min(competitors))
    fused_best = float(errors[best_index])
    margin = ((second_best - fused_best) / max(second_best, 1e-12)
              if np.isfinite(second_best) else 1.0)
    return AlignmentResult(
        offset_seconds=best_offset,
        mse=fused_best,
        second_best_mse=second_best,
        uniqueness_margin=float(margin),
        overlap_ratio=float(np.average(
            [item.overlap_ratio for item in candidates], weights=weights)),
        direction_sign=1,
        offsets=offsets,
        errors=errors,
    )


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
    best_offset = _quadratic_minimum(
        offsets, errors[sign_index], offset_index)
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
