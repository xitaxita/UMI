"""Estimate one camera's Vive latency from ArUco and TCP translation."""

import argparse
import json
import subprocess
from pathlib import Path

import cv2

import numpy as np

from umi_ros2.postprocess.episode_transform import poses_in_reference_frame
from umi_ros2.postprocess.pose_io import read_vive_poses
from umi_ros2.session.layout import (
    now_text,
    resolve_calibration_camera,
    resolve_video_path,
    update_temporal_calibration,
)

from .temporal_alignment import align_feature_trajectories


OFFSET_CONVENTION = (
    'pose_time_seconds = video_frame_time_seconds + '
    'video_to_pose_offset_seconds'
)


def video_frame_times(path):
    """Read actual MP4 frame PTS with ffprobe."""
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json',
        str(path),
    ], capture_output=True, text=True, check=True, timeout=120)
    frames = json.loads(result.stdout).get('frames', [])
    times = [float(frame['best_effort_timestamp_time']) for frame in frames
             if 'best_effort_timestamp_time' in frame]
    if not times or not np.all(np.diff(times) > 0):
        raise ValueError('video has no strictly increasing frame timestamps')
    return np.asarray(times, dtype=np.float64)


def aruco_trajectory(video_path, frame_times, dictionary_name, marker_id):
    """Return times and centre/scale features for one marker."""
    aruco = cv2.aruco
    if not hasattr(aruco, dictionary_name):
        raise ValueError(f'unknown ArUco dictionary {dictionary_name}')
    dictionary = aruco.getPredefinedDictionary(
        getattr(aruco, dictionary_name))
    parameters = aruco.DetectorParameters_create()
    capture = cv2.VideoCapture(str(video_path))
    detected_times = []
    features = []
    frame_index = 0
    try:
        while True:
            available, frame = capture.read()
            if not available:
                break
            if frame_index >= len(frame_times):
                raise ValueError(
                    'decoded frames exceed probed frame timestamps')
            corners, identifiers, _ = aruco.detectMarkers(
                frame, dictionary, parameters=parameters)
            if identifiers is not None:
                matches = np.flatnonzero(identifiers.reshape(-1) == marker_id)
                if len(matches):
                    points = corners[int(matches[0])].reshape(-1, 2)
                    center = np.mean(points, axis=0)
                    area = abs(float(cv2.contourArea(points)))
                    if area > 1.0:
                        detected_times.append(frame_times[frame_index])
                        features.append((
                            center[0] / frame.shape[1],
                            center[1] / frame.shape[0],
                            np.log(area / (frame.shape[0] * frame.shape[1])),
                        ))
            frame_index += 1
    finally:
        capture.release()
    if frame_index != len(frame_times):
        raise ValueError(
            f'decoded {frame_index} frames but ffprobe reported '
            f'{len(frame_times)}')
    return (
        np.asarray(detected_times, dtype=np.float64),
        np.asarray(features, dtype=np.float64),
        frame_index,
    )


def read_vive_pose_bag(pose_directory, topic='/vive/pose'):
    """Read world TCP poses and unchanged header times from an MCAP bag."""
    times, positions, orientations = read_vive_poses(pose_directory, topic)
    if len(times) < 3:
        raise ValueError(f'{topic} contains fewer than three poses')
    return times, positions, orientations


def save_plot(path, video_times, video_features, pose_times, pose_features,
              result, window_offsets):
    """Write source, aligned and search-error plots for operator review."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt

    video_values = np.linalg.norm(
        np.gradient(video_features, video_times, axis=0), axis=1)
    pose_values = np.linalg.norm(
        np.gradient(pose_features, pose_times, axis=0), axis=1)
    aligned = np.interp(
        video_times + result.offset_seconds, pose_times, pose_values)
    video_normalized = (
        video_values - np.mean(video_values)) / np.std(video_values)
    pose_normalized = (aligned - np.mean(aligned)) / np.std(aligned)
    relative_time = video_times - video_times[0]

    figure, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
    axes[0].plot(relative_time, video_normalized, label='ArUco motion energy')
    axes[0].plot(relative_time, pose_normalized, label='Aligned TCP motion')
    axes[0].set_xlabel('Video time (s)')
    axes[0].set_ylabel('Normalized position')
    axes[0].legend()
    axes[0].grid(True)
    axes[1].plot(result.offsets, result.errors)
    axes[1].axvline(result.offset_seconds, color='red', linestyle='--')
    axes[1].set_xlabel('Video-to-pose offset (s)')
    axes[1].set_ylabel('Fused alignment score')
    axes[1].grid(True)
    figure.suptitle(
        f'offset={result.offset_seconds:.6f}s, score={result.mse:.4f}, '
        f'window std={np.std(window_offsets) * 1000:.2f}ms')
    figure.savefig(path, dpi=160)
    plt.close(figure)


def calibrate(args):
    """Run one calibration and write reviewable results."""
    episode = Path(args.calibration_episode).expanduser().resolve()
    camera_id = resolve_calibration_camera(
        episode, getattr(args, 'camera_id', None))
    video_path = resolve_video_path(episode, camera_id)
    timing_path = video_path.with_suffix('.timing.json')
    pose_directory = episode / 'pose'
    timing = json.loads(timing_path.read_text(encoding='utf-8'))
    if timing.get('camera_id', camera_id) != camera_id:
        raise ValueError('video timing camera_id differs from selected camera')
    video_anchor = timing.get('first_receive_unix_ns')
    if video_anchor is None:
        raise ValueError('video timing has no first_receive_unix_ns')
    frame_times = video_frame_times(video_path)
    marker_times, marker_features, decoded_frames = aruco_trajectory(
        video_path, frame_times, args.aruco_dictionary, args.marker_id)
    detection_ratio = len(marker_times) / decoded_frames
    if len(marker_times) < args.minimum_detections:
        raise ValueError('too few ArUco detections for calibration')
    if detection_ratio < args.minimum_detection_ratio:
        raise ValueError('ArUco detection ratio is below the required minimum')

    video_absolute_times = marker_times + video_anchor / 1_000_000_000
    pose_times, positions, orientations = read_vive_pose_bag(pose_directory)
    reference_position = positions[0]
    reference_orientation = orientations[0]
    pose_features, _ = poses_in_reference_frame(
        positions, orientations, reference_position, reference_orientation)
    reference_orientation = (
        reference_orientation / np.linalg.norm(reference_orientation))
    pose_motion_metres = float(np.linalg.norm(np.ptp(pose_features, axis=0)))
    if pose_motion_metres < args.minimum_pose_motion:
        raise ValueError('Vive calibration motion is too small')
    result = align_feature_trajectories(
        video_absolute_times, marker_features, pose_times, pose_features,
        minimum_offset=args.minimum_offset,
        maximum_offset=args.maximum_offset,
        step=args.search_step,
        minimum_overlap=args.minimum_overlap,
        ambiguity_exclusion=args.ambiguity_exclusion,
    )
    window_offsets = []
    boundaries = np.linspace(
        0, len(marker_times), args.validation_windows + 1, dtype=int)
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        if stop - start < 12:
            continue
        try:
            window_result = align_feature_trajectories(
                video_absolute_times[start:stop], marker_features[start:stop],
                pose_times, pose_features,
                minimum_offset=args.minimum_offset,
                maximum_offset=args.maximum_offset,
                step=args.search_step,
                minimum_overlap=args.minimum_window_overlap,
                ambiguity_exclusion=args.ambiguity_exclusion)
            window_offsets.append(window_result.offset_seconds)
        except ValueError:
            continue
    window_std = (float(np.std(window_offsets))
                  if len(window_offsets) >= 2 else float('inf'))
    accepted = (
        result.mse <= args.maximum_mse
        and result.uniqueness_margin >= args.minimum_uniqueness_margin
        and len(window_offsets) >= args.minimum_valid_windows
        and window_std <= args.maximum_window_std
    )
    output = {
        'schema_version': 2,
        'method': 'translation_only_aruco_start_tcp_temporal_alignment_v4',
        'camera_id': camera_id,
        'image_field': timing.get('image_field', f'{camera_id}_image'),
        'accepted': accepted,
        'offset_convention': OFFSET_CONVENTION,
        'video_to_pose_offset_seconds': result.offset_seconds,
        'video_to_pose_offset_milliseconds': result.offset_seconds * 1000,
        'normalized_mse': result.mse,
        'second_best_mse': result.second_best_mse,
        'uniqueness_margin': result.uniqueness_margin,
        'overlap_ratio': result.overlap_ratio,
        'aruco_dictionary': args.aruco_dictionary,
        'aruco_marker_id': args.marker_id,
        'aruco_detections': len(marker_times),
        'decoded_video_frames': decoded_frames,
        'aruco_detection_ratio': detection_ratio,
        'video_features': ['center_x', 'center_y', 'log_area'],
        'pose_features': ['x', 'y', 'z'],
        'pose_frame': 'recording_start_tcp',
        'pose_reference': {
            'definition': 'first_recorded_tcp_pose_after_start',
            'pose_time_seconds': float(pose_times[0]),
            'position_xyz': reference_position.tolist(),
            'orientation_xyzw': reference_orientation.tolist(),
            'transform_convention': (
                'T_start_i = inverse(T_world_start) * T_world_i'),
        },
        'video_time_anchor_unix_ns': video_anchor,
        'recording_pose_lead_seconds': float(
            video_anchor / 1e9 + frame_times[0] - pose_times[0]),
        'time_basis': (
            'Video first host receipt + PTS; pose header timestamps. '
            'The 500 ms pose lead is retained, not subtracted as latency.'),
        'pose_motion_metres': pose_motion_metres,
        'window_offsets_seconds': window_offsets,
        'window_offset_std_seconds': window_std,
        'search': {
            'minimum_offset_seconds': args.minimum_offset,
            'maximum_offset_seconds': args.maximum_offset,
            'step_seconds': args.search_step,
        },
        'acceptance_thresholds': {
            'maximum_normalized_mse': args.maximum_mse,
            'minimum_uniqueness_margin': args.minimum_uniqueness_margin,
            'minimum_detection_ratio': args.minimum_detection_ratio,
            'minimum_pose_motion_metres': args.minimum_pose_motion,
            'minimum_valid_windows': args.minimum_valid_windows,
            'maximum_window_std_seconds': args.maximum_window_std,
        },
        'accuracy_note': (
            'This is a software-estimated constant offset. It is not a '
            'hardware synchronization or exposure-time accuracy claim.'),
    }
    output_path = episode / 'time_offset.json'
    report_path = episode / 'alignment_report.png'
    output_path.write_text(
        json.dumps(output, indent=2) + '\n', encoding='utf-8')
    save_plot(
        report_path, video_absolute_times, marker_features,
        pose_times, pose_features, result, window_offsets)
    session = episode.parent.parent
    if (session / 'session.yaml').is_file():
        calibration = {
            'status': 'accepted' if accepted else 'rejected',
            'result': str(output_path.relative_to(session)),
            'calibrated_at': now_text(),
            'video_to_pose_offset_seconds': result.offset_seconds,
            'camera_id': camera_id,
            'image_field': output['image_field'],
        }
        update_temporal_calibration(session, camera_id, calibration)
    print(json.dumps(output, indent=2))
    return 0 if accepted else 2


def argument_parser():
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description='Calibrate one camera/Vive time offset using translation')
    parser.add_argument('calibration_episode')
    parser.add_argument('--camera-id', default=None,
                        help='infer the camera for a single-stream recording')
    parser.add_argument('--aruco-dictionary', default='DICT_4X4_50')
    parser.add_argument('--marker-id', type=int, default=4)
    parser.add_argument('--minimum-offset', type=float, default=-1.0)
    parser.add_argument('--maximum-offset', type=float, default=1.0)
    parser.add_argument('--search-step', type=float, default=0.001)
    parser.add_argument('--minimum-overlap', type=float, default=0.8)
    parser.add_argument('--ambiguity-exclusion', type=float, default=0.05)
    parser.add_argument('--minimum-detections', type=int, default=30)
    parser.add_argument('--minimum-detection-ratio', type=float, default=0.6)
    parser.add_argument('--minimum-pose-motion', type=float, default=0.05)
    parser.add_argument('--maximum-mse', type=float, default=0.5)
    parser.add_argument(
        '--minimum-uniqueness-margin', type=float, default=0.05)
    parser.add_argument('--validation-windows', type=int, default=3)
    parser.add_argument('--minimum-valid-windows', type=int, default=2)
    parser.add_argument('--minimum-window-overlap', type=float, default=0.6)
    parser.add_argument('--maximum-window-std', type=float, default=0.020)
    return parser


def main(argv=None):
    """CLI entry point."""
    try:
        return calibrate(argument_parser().parse_args(argv))
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        print(f'time calibration failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
