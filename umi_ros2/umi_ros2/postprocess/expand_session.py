"""Write 90 Hz expansion intermediates from calibrated raw recordings."""

import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from umi_ros2.session.layout import read_session, resolve_video_path

from .align_session import (
    OFFSET_CONVENTION, resolve_episodes, video_frame_times)
from .frame_expansion import (
    CAMERA_IDS, IMAGE_FPS, IMAGE_REPEATS, SAMPLE_FPS, expand_frames)
from .pose_io import read_vive_poses


CONTRACT_VERSION = 1
CONTRACT_NAME = 'umi_frame_expansion'


def load_camera_offset(session, camera_id):
    """Read this camera's accepted result; only wrist has a legacy fallback."""
    metadata = read_session(session)
    calibration = metadata.get('temporal_calibrations', {}).get(camera_id)
    if calibration is None and camera_id == 'wrist':
        calibration = metadata.get('temporal_calibration')
    if not calibration or calibration.get('status') != 'accepted':
        raise ValueError(f'session has no accepted {camera_id} calibration')
    if not calibration.get('result'):
        raise ValueError(
            f'accepted {camera_id} calibration has no result path')
    result_path = session / calibration['result']
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if (result.get('accepted') is not True
            or result.get('camera_id', camera_id) != camera_id):
        raise ValueError(f'referenced {camera_id} calibration is not accepted')
    offset = float(result['video_to_pose_offset_seconds'])
    if not np.isfinite(offset):
        raise ValueError(f'{camera_id} calibration offset is not finite')
    return offset, str(result_path)


def _check_output(
        destination, session, overwrite, report_name='expansion.json'):
    if (destination == session or session in destination.parents
            or destination in session.parents):
        raise ValueError('expansion output must be separate from raw session')
    if destination.exists():
        if not overwrite:
            raise FileExistsError(
                f'output exists; use --overwrite: {destination}')
        report_path = destination / report_name
        if (not report_path.is_file() or json.loads(report_path.read_text(
                encoding='utf-8')).get('contract') != CONTRACT_NAME):
            raise ValueError(f'refusing to overwrite non-expansion output: '
                             f'{destination}')


def _read_camera(episode, session, camera_id):
    video = resolve_video_path(episode, camera_id)
    timing_path = video.with_suffix('.timing.json')
    for required in (video, timing_path):
        if not required.is_file():
            raise ValueError(f'{camera_id} input is missing: {required}')
    timing = json.loads(timing_path.read_text(encoding='utf-8'))
    if timing.get('camera_id', camera_id) != camera_id:
        raise ValueError(f'{camera_id} timing has a different camera_id')
    image_field = timing.get('image_field', f'{camera_id}_image')
    if not isinstance(image_field, str) or not image_field.strip():
        raise ValueError(f'{camera_id} timing has no valid image_field')
    offset, source = load_camera_offset(session, camera_id)
    pts = video_frame_times(video)
    anchor_ns = int(timing['first_receive_unix_ns'])
    times = anchor_ns / 1_000_000_000 + pts + offset
    return pts, times, {
        'camera_id': camera_id, 'image_field': image_field,
        'source_video': str(video), 'source_timing': str(timing_path),
        'first_receive_unix_ns': anchor_ns,
        'video_to_pose_offset_seconds': offset, 'offset_source': source,
        'source_frame_count': len(pts),
    }


def _write_csv(path, arrays):
    fields = [
        'sample_index', 'group_index', 'repeat_index', 'timestamp',
        'pose_query_time_seconds', 'valid', 'pose_valid',
        'wrist_frame_index', 'left_frame_index',
        'wrist_pairing_delta_seconds', 'left_pairing_delta_seconds',
    ]
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(fields + ['x', 'y', 'z', 'qx', 'qy', 'qz', 'qw'])
        for index in range(len(arrays['sample_index'])):
            writer.writerow([
                *(arrays[field][index] for field in fields),
                *arrays['position_xyz'][index],
                *arrays['orientation_xyzw'][index],
            ])


def expand_episode(
        episode, destination, maximum_image_delta_seconds=1 / 60,
        maximum_pose_gap_seconds=0.1, minimum_valid_ratio=0.95,
        overwrite=False):
    """Load two corrected cameras and pose once; persist expansion v1."""
    episode = Path(episode).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    session = episode.parent.parent
    if (episode.parent.name != 'episodes'
            or not (session / 'session.yaml').is_file()):
        raise ValueError('expansion input must be an ordinary session episode')
    if (not np.isfinite(minimum_valid_ratio)
            or not 0 <= minimum_valid_ratio <= 1):
        raise ValueError('minimum valid ratio must be between zero and one')
    _check_output(destination, session, overwrite)
    pose_path = episode / 'pose'
    if not (pose_path / 'metadata.yaml').is_file():
        raise ValueError(f'pose input is missing: {pose_path}')
    pts, times, cameras = {}, {}, {}
    for camera_id in CAMERA_IDS:
        pts[camera_id], times[camera_id], cameras[camera_id] = _read_camera(
            episode, session, camera_id)
    pose_times, positions, orientations = read_vive_poses(pose_path)
    result = expand_frames(
        times, pose_times, positions, orientations,
        maximum_image_delta_seconds, maximum_pose_gap_seconds)
    reference_orientation = np.array(
        orientations[0], dtype=np.float64, copy=True)
    reference_orientation /= np.linalg.norm(reference_orientation)
    arrays = {
        'contract_version': np.asarray(CONTRACT_VERSION),
        'fps': np.asarray(SAMPLE_FPS),
        'image_repeats': np.asarray(IMAGE_REPEATS),
        'sample_index': np.arange(len(result.timestamp), dtype=np.int64),
        'group_index': result.group_index, 'repeat_index': result.repeat_index,
        'timestamp': result.timestamp,
        'pose_query_time_seconds': result.query_times,
        'episode_time_seconds': result.query_times - pose_times[0],
        'valid': result.valid, 'pose_valid': result.poses.valid,
        'position_xyz': result.poses.positions,
        'orientation_xyzw': result.poses.orientations,
        'pose_left_index': result.poses.left_indices,
        'pose_right_index': result.poses.right_indices,
        'interpolation_alpha': result.poses.alphas,
        'pose_gap_seconds': result.poses.gaps,
        'reference_position_xyz': np.asarray(positions[0]),
        'reference_orientation_xyzw': reference_orientation,
        'reference_pose_time_seconds': np.asarray(pose_times[0]),
    }
    for camera_id in CAMERA_IDS:
        indices = result.frame_indices[camera_id]
        arrays.update({
            f'{camera_id}_frame_index': indices,
            f'{camera_id}_video_pts_seconds': pts[camera_id][indices],
            f'{camera_id}_image_time_seconds': result.image_times[camera_id],
            f'{camera_id}_pairing_delta_seconds': (
                result.pairing_deltas[camera_id]),
            f'{camera_id}_image_age_seconds': (
                result.query_times - result.image_times[camera_id]),
            f'{camera_id}_valid': result.camera_valid[camera_id],
        })
        selected = len(np.unique(indices[result.valid]))
        cameras[camera_id].update({
            'selected_source_frame_count': selected,
            'unused_source_frame_count': len(pts[camera_id]) - selected,
            'invalid_group_count': int(np.count_nonzero(
                ~result.camera_valid[camera_id][::IMAGE_REPEATS])),
            'maximum_accepted_pairing_delta_seconds': (
                float(np.max(np.abs(
                    result.pairing_deltas[camera_id][result.valid])))
                if result.valid.any() else None),
        })
    count = len(result.timestamp)
    valid_count = int(np.count_nonzero(result.valid))
    ratio = valid_count / count
    report = {
        'contract': CONTRACT_NAME, 'schema_version': CONTRACT_VERSION,
        'status': ('accepted' if valid_count and ratio >= minimum_valid_ratio
                   else 'rejected'),
        'source_episode': str(episode), 'source_session': str(session),
        'source_pose': str(pose_path), 'cameras': cameras,
        'fps': SAMPLE_FPS, 'image_fps': IMAGE_FPS,
        'image_repeats': IMAGE_REPEATS, 'sample_count': count,
        'group_count': count // IMAGE_REPEATS,
        'valid_sample_count': valid_count,
        'invalid_sample_count': count - valid_count,
        'valid_group_count': valid_count // IMAGE_REPEATS,
        'valid_sample_ratio': ratio,
        'minimum_valid_ratio': minimum_valid_ratio,
        'clock_anchor_seconds': result.clock_anchor,
        'first_query_time_seconds': float(result.query_times[0]),
        'last_query_time_seconds': float(result.query_times[-1]),
        'maximum_image_delta_seconds': maximum_image_delta_seconds,
        'maximum_pose_gap_seconds': maximum_pose_gap_seconds,
        'invalid_pose_query_count': int(np.count_nonzero(~result.poses.valid)),
        'pose_reference_definition': 'first_recorded_tcp_pose_after_start',
        'reference_pose_time_seconds': float(pose_times[0]),
        'pose_coordinate_frame': 'raw_world',
        'pose_layout': 'x y z qx qy qz qw',
        'offset_convention': OFFSET_CONVENTION,
        'images_materialized': False, 'raw_data_modified': False,
    }
    destination.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination / 'expanded_frames.npz', **arrays)
    _write_csv(destination / 'expanded_frames.csv', arrays)
    (destination / 'expansion.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8')
    return report


def expand(args):
    """Expand ordinary episodes while leaving current dataset exports alone."""
    session, episodes = resolve_episodes(args.input_path)
    if session is None:
        raise ValueError('expansion requires a containing calibrated session')
    output = (Path(args.output).expanduser().resolve() if args.output else
              Path.cwd() / 'processed' / session.name / 'expanded')
    _check_output(output, session, args.overwrite, 'expansion_summary.json')
    reports = []
    for episode in episodes:
        destination = output / episode.relative_to(session)
        try:
            report = expand_episode(
                episode, destination, args.maximum_image_delta,
                args.maximum_pose_gap, args.minimum_valid_ratio,
                args.overwrite)
        except (OSError, ValueError, KeyError,
                subprocess.SubprocessError) as error:
            report = {'source_episode': str(episode), 'status': 'failed',
                      'error': str(error), 'raw_data_modified': False}
        reports.append(report)
        if report['status'] == 'failed':
            print(f'{episode.name}: failed: {report["error"]}')
        else:
            print(f'{episode.name}: {report["valid_sample_count"]}/'
                  f'{report["sample_count"]} valid at {SAMPLE_FPS} Hz '
                  f'({report["status"]}) -> {destination}')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'expansion_summary.json').write_text(json.dumps({
        'contract': CONTRACT_NAME, 'schema_version': CONTRACT_VERSION,
        'source_session': str(session), 'fps': SAMPLE_FPS,
        'episode_count': len(reports), 'episodes': reports,
        'raw_data_modified': False,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if any(report['status'] == 'failed' for report in reports):
        return 1
    return 0 if all(
        report['status'] == 'accepted' for report in reports) else 2


def argument_parser():
    """Build the independently runnable expansion CLI."""
    parser = argparse.ArgumentParser(
        description='Expand corrected wrist/left images and TCP pose to 90 Hz')
    parser.add_argument(
        'input_path', help='Calibrated session or ordinary episode')
    parser.add_argument('--output', help='Separate expansion output directory')
    parser.add_argument('--maximum-image-delta', type=float, default=1 / 60)
    parser.add_argument('--maximum-pose-gap', type=float, default=0.1)
    parser.add_argument('--minimum-valid-ratio', type=float, default=0.95)
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run expansion without camera devices or a running ROS graph."""
    try:
        return expand(argument_parser().parse_args(argv))
    except (OSError, ValueError, KeyError,
            subprocess.SubprocessError) as error:
        print(f'expansion failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
