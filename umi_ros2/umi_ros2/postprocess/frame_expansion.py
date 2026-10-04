"""Expand corrected 30 Hz camera groups onto one fixed 90 Hz pose clock."""

from dataclasses import dataclass

import numpy as np

from .alignment import (
    InterpolatedPoses, interpolate_poses, prepare_pose_samples)


CAMERA_IDS = ('wrist', 'left')
IMAGE_FPS = 30
SAMPLE_FPS = 90
IMAGE_REPEATS = 3


@dataclass(frozen=True)
class ExpandedFrames:
    """Source-image references and world poses for every uncompressed tick."""

    group_index: np.ndarray
    repeat_index: np.ndarray
    timestamp: np.ndarray
    query_times: np.ndarray
    frame_indices: dict
    image_times: dict
    pairing_deltas: dict
    camera_valid: dict
    poses: InterpolatedPoses
    valid: np.ndarray
    clock_anchor: float


def _camera_times(values, camera_id):
    times = np.asarray(values, dtype=np.float64)
    if (times.ndim != 1 or not len(times) or not np.isfinite(times).all()
            or not np.all(np.diff(times) > 0)):
        raise ValueError(
            f'{camera_id} needs finite, strictly increasing image times')
    return times


def _nearest_unique(times, queries, maximum_delta, epsilon):
    """Pair nearest images, preferring earlier ties and no valid reuse."""
    right = np.clip(np.searchsorted(times, queries), 0, len(times) - 1)
    left = np.maximum(right - 1, 0)
    indices = np.where(
        np.abs(times[right] - queries) < np.abs(times[left] - queries),
        right, left)
    deltas = times[indices] - queries
    valid = np.abs(deltas) <= maximum_delta + epsilon
    previous = -1
    for group in np.flatnonzero(valid):
        if indices[group] <= previous:
            valid[group] = False
        else:
            previous = int(indices[group])
    return indices.astype(np.int64), deltas, valid


def expand_frames(
        camera_times, pose_times, positions, orientations,
        maximum_image_delta_seconds=1 / 60, maximum_pose_gap_seconds=0.1):
    """Repeat each paired image three times and interpolate world TCP poses.

    Camera inputs already include their individual accepted offsets. The
    wrist's first corrected image anchors a 90 Hz clock; images are chosen on
    its 30 Hz subgrid. Invalid groups remain present, preserving clock gaps.
    Local coordinates, action targets and image serialization are later stages.
    """
    for name, value in (
        ('maximum image delta', maximum_image_delta_seconds),
        ('maximum pose gap', maximum_pose_gap_seconds),
    ):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and greater than zero')
    if set(camera_times) != set(CAMERA_IDS):
        raise ValueError('expansion requires wrist and left image timelines')
    cameras = {
        camera_id: _camera_times(camera_times[camera_id], camera_id)
        for camera_id in CAMERA_IDS
    }
    pose_times, positions, orientations = prepare_pose_samples(
        pose_times, positions, orientations)
    anchor = float(cameras['wrist'][0])
    epsilon = max(float(np.spacing(abs(anchor))) * 4, 1e-12)
    lower = max(anchor, pose_times[0], *(
        times[0] - maximum_image_delta_seconds for times in cameras.values()))
    upper = min(pose_times[-1] - (IMAGE_REPEATS - 1) / SAMPLE_FPS, *(
        times[-1] + maximum_image_delta_seconds for times in cameras.values()))
    first = max(0, int(np.ceil((lower - anchor - epsilon) * IMAGE_FPS)))
    last = int(np.floor((upper - anchor + epsilon) * IMAGE_FPS))
    if last < first:
        raise ValueError('no complete three-sample group has common coverage')
    groups = np.arange(first, last + 1, dtype=np.int64)
    group_times = anchor + groups / IMAGE_FPS
    frame_indices, image_times, pairing_deltas, camera_valid = {}, {}, {}, {}
    group_valid = np.ones(len(groups), dtype=bool)
    for camera_id, times in cameras.items():
        indices, deltas, valid = _nearest_unique(
            times, group_times, maximum_image_delta_seconds, epsilon)
        frame_indices[camera_id] = np.repeat(indices, IMAGE_REPEATS)
        image_times[camera_id] = np.repeat(times[indices], IMAGE_REPEATS)
        pairing_deltas[camera_id] = np.repeat(deltas, IMAGE_REPEATS)
        camera_valid[camera_id] = np.repeat(valid, IMAGE_REPEATS)
        group_valid &= valid
    group_index = np.repeat(groups, IMAGE_REPEATS)
    repeat_index = np.tile(np.arange(IMAGE_REPEATS), len(groups))
    ticks = group_index * IMAGE_REPEATS + repeat_index
    timestamp = (ticks - ticks[0]) / SAMPLE_FPS
    queries = anchor + ticks / SAMPLE_FPS
    poses = interpolate_poses(
        queries, pose_times, positions, orientations,
        maximum_gap_seconds=maximum_pose_gap_seconds)
    group_valid &= poses.valid.reshape(-1, IMAGE_REPEATS).all(axis=1)
    previous = None
    for index, valid in enumerate(poses.valid):
        if not valid:
            previous = None
        else:
            quaternion = poses.orientations[index]
            if previous is not None and np.dot(previous, quaternion) < 0:
                poses.orientations[index] *= -1
            previous = poses.orientations[index]
    return ExpandedFrames(
        group_index, repeat_index, timestamp, queries,
        frame_indices, image_times, pairing_deltas, camera_valid,
        poses, np.repeat(group_valid, IMAGE_REPEATS), anchor)
