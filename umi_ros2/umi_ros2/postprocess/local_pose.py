"""Express timestamped TCP poses in their fixed recording-start frame."""

import numpy as np

from .episode_transform import poses_in_reference_frame


def localize_poses(
        positions, orientations, pose_valid,
        reference_position, reference_orientation):
    """Return local XYZ/XYZW, preserving pose gaps and continuous signs.

    The caller supplies the first saved raw TCP pose explicitly. Image
    validity does not determine whether a pose can be transformed.
    """
    positions = np.asarray(positions, dtype=np.float64)
    orientations = np.asarray(orientations, dtype=np.float64)
    pose_valid = np.asarray(pose_valid, dtype=bool)
    if (positions.ndim != 2 or positions.shape[1] != 3
            or orientations.shape != (len(positions), 4)
            or pose_valid.shape != (len(positions),)):
        raise ValueError('pose arrays and validity have incompatible shapes')
    indices = np.flatnonzero(pose_valid)
    # This also validates the fixed reference when every query is invalid.
    local_positions, local_orientations = poses_in_reference_frame(
        positions[indices], orientations[indices],
        reference_position, reference_orientation)
    previous = np.array([0.0, 0.0, 0.0, 1.0])
    for quaternion in local_orientations:
        if np.dot(previous, quaternion) < 0:
            quaternion *= -1
        previous = quaternion
    output_positions = np.full(positions.shape, np.nan, dtype=np.float64)
    output_orientations = np.full(
        orientations.shape, np.nan, dtype=np.float64)
    output_positions[indices] = local_positions
    output_orientations[indices] = local_orientations
    return output_positions, output_orientations
