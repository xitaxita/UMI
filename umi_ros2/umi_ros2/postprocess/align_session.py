"""Align online video frames with interpolated Vive poses."""

import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from umi_ros2.common.ordering import natural_key
from umi_ros2.postprocess.alignment import interpolate_poses
from umi_ros2.postprocess.pose_io import read_vive_poses
from umi_ros2.session.layout import read_session


OFFSET_CONVENTION = (
    'pose_time_seconds = video_frame_time_seconds + '
    'video_to_pose_offset_seconds'
)


def video_frame_times(path):
    """Read all actual MP4 frame PTS values using ffprobe."""
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json',
        str(path),
    ], capture_output=True, text=True, check=True, timeout=120)
    frames = json.loads(result.stdout).get('frames', [])
    times = np.asarray([
        float(frame['best_effort_timestamp_time']) for frame in frames
        if 'best_effort_timestamp_time' in frame
    ], dtype=np.float64)
    if not len(times) or not np.all(np.diff(times) > 0):
        raise ValueError('video has no strictly increasing frame timestamps')
    return times


def resolve_episodes(input_path):
    """Return a source session and the ordinary episodes to align."""
    path = Path(input_path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f'alignment input is not a directory: {path}')
    if (path / 'video.mp4').is_file() and (path / 'pose').is_dir():
        session = (
            path.parent.parent
            if (path.parent.parent / 'session.yaml').is_file() else None
        )
        return session, [path]
    if not (path / 'session.yaml').is_file():
        raise ValueError('input must be an online session or one episode')
    episodes_path = path / 'episodes'
    episodes = sorted([
        child for child in episodes_path.iterdir()
        if child.is_dir() and child.name.startswith('episode_')
    ], key=natural_key) if episodes_path.is_dir() else []
    if not episodes:
        raise ValueError(f'session contains no ordinary episodes: {path}')
    return path, episodes


def load_offset(session, override=None):
    """Load an accepted session offset or use an explicit diagnostic value."""
    if override is not None:
        if not np.isfinite(override):
            raise ValueError('offset override must be finite')
        return float(override), 'command_line_override'
    if session is None:
        raise ValueError(
            'standalone episode requires --offset-seconds because it has no '
            'containing session')
    metadata = read_session(session)
    calibration = metadata.get('temporal_calibration', {})
    if calibration.get('status') != 'accepted':
        raise ValueError('session has no accepted temporal calibration')
    result_value = calibration.get('result')
    if not result_value:
        raise ValueError('accepted calibration has no result path')
    result_path = session / result_value
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if not result.get('accepted'):
        raise ValueError('referenced temporal calibration is not accepted')
    offset = float(result['video_to_pose_offset_seconds'])
    if not np.isfinite(offset):
        raise ValueError('temporal calibration offset is not finite')
    return offset, str(result_path)


def _output_directory(output_root, session, episode):
    if session is not None:
        relative = episode.relative_to(session)
        return output_root / relative
    return output_root / episode.name


def align_episode(
        episode, output_directory, offset_seconds, offset_source,
        maximum_pose_gap, minimum_valid_ratio, overwrite=False):
    """Align one episode and write normalized arrays, CSV, and report."""
    video_path = episode / 'video.mp4'
    timing_path = episode / 'video.timing.json'
    pose_path = episode / 'pose'
    for required in (video_path, timing_path, pose_path / 'metadata.yaml'):
        if not required.exists():
            raise ValueError(f'episode is missing required input: {required}')
    if output_directory.exists() and not overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {output_directory}')

    frame_pts = video_frame_times(video_path)
    timing = json.loads(timing_path.read_text(encoding='utf-8'))
    video_anchor = int(timing['first_receive_unix_ns']) / 1_000_000_000
    video_times = video_anchor + frame_pts
    query_times = video_times + offset_seconds
    pose_times, positions, orientations = read_vive_poses(pose_path)
    result = interpolate_poses(
        query_times, pose_times, positions, orientations,
        maximum_gap_seconds=maximum_pose_gap)
    output_directory.mkdir(parents=True, exist_ok=True)
    frame_indices = np.arange(len(frame_pts), dtype=np.int64)
    np.savez_compressed(
        output_directory / 'aligned_frames.npz',
        frame_index=frame_indices,
        video_pts_seconds=frame_pts,
        video_time_seconds=video_times,
        pose_query_time_seconds=query_times,
        valid=result.valid,
        position_xyz=result.positions,
        orientation_xyzw=result.orientations,
        pose_left_index=result.left_indices,
        pose_right_index=result.right_indices,
        interpolation_alpha=result.alphas,
        pose_gap_seconds=result.gaps,
    )
    _write_csv(
        output_directory / 'aligned_frames.csv', frame_indices, frame_pts,
        video_times, query_times, result)
    valid_count = int(np.count_nonzero(result.valid))
    valid_ratio = valid_count / len(frame_pts)
    report = {
        'schema_version': 1,
        'status': (
            'accepted' if valid_ratio >= minimum_valid_ratio else 'rejected'),
        'source_episode': str(episode),
        'source_video': str(video_path),
        'source_pose': str(pose_path),
        'offset_convention': OFFSET_CONVENTION,
        'video_to_pose_offset_seconds': offset_seconds,
        'offset_source': offset_source,
        'frame_count': len(frame_pts),
        'valid_frame_count': valid_count,
        'invalid_frame_count': len(frame_pts) - valid_count,
        'valid_frame_ratio': valid_ratio,
        'minimum_valid_frame_ratio': minimum_valid_ratio,
        'maximum_pose_gap_seconds': maximum_pose_gap,
        'largest_used_pose_gap_seconds': (
            float(np.max(result.gaps[result.valid]))
            if valid_count else None),
        'raw_data_modified': False,
    }
    (output_directory / 'alignment.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def _write_csv(path, indices, pts, video_times, query_times, result):
    fields = [
        'frame_index', 'video_pts_seconds', 'video_time_seconds',
        'pose_query_time_seconds', 'valid', 'pose_left_index',
        'pose_right_index', 'interpolation_alpha', 'pose_gap_seconds',
        'position_x', 'position_y', 'position_z',
        'orientation_x', 'orientation_y', 'orientation_z', 'orientation_w',
    ]
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(fields)
        for index in range(len(indices)):
            writer.writerow([
                indices[index], pts[index], video_times[index],
                query_times[index], bool(result.valid[index]),
                result.left_indices[index], result.right_indices[index],
                result.alphas[index], result.gaps[index],
                *result.positions[index], *result.orientations[index],
            ])


def align(args):
    """Align all selected episodes and return an aggregate exit status."""
    if not 0.0 <= args.minimum_valid_ratio <= 1.0:
        raise ValueError('minimum valid ratio must be between zero and one')
    session, episodes = resolve_episodes(args.input_path)
    offset, offset_source = load_offset(session, args.offset_seconds)
    if args.output:
        output_root = Path(args.output).expanduser().resolve()
    else:
        name = session.name if session is not None else episodes[0].name
        output_root = (Path.cwd() / 'processed' / name).resolve()
    summary_path = output_root / 'alignment_summary.json'
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {output_root}')
    reports = []
    for episode in episodes:
        destination = _output_directory(output_root, session, episode)
        try:
            report = align_episode(
                episode, destination, offset, offset_source,
                args.maximum_pose_gap, args.minimum_valid_ratio,
                args.overwrite)
        except (OSError, ValueError, KeyError, json.JSONDecodeError,
                subprocess.SubprocessError) as error:
            report = {
                'schema_version': 1,
                'status': 'failed',
                'source_episode': str(episode),
                'error': str(error),
                'raw_data_modified': False,
            }
            if not destination.exists() or args.overwrite:
                destination.mkdir(parents=True, exist_ok=True)
                (destination / 'alignment.json').write_text(
                    json.dumps(report, indent=2) + '\n', encoding='utf-8')
        reports.append(report)
        if report['status'] == 'failed':
            print(f'{episode.name}: failed: {report["error"]}')
        else:
            print(
                f'{episode.name}: {report["valid_frame_count"]}/'
                f'{report["frame_count"]} valid frames -> {destination}')
    summary = {
        'schema_version': 1,
        'source_input': str(Path(args.input_path).expanduser().resolve()),
        'offset_convention': OFFSET_CONVENTION,
        'video_to_pose_offset_seconds': offset,
        'offset_source': offset_source,
        'episode_count': len(reports),
        'accepted_episode_count': sum(
            report['status'] == 'accepted' for report in reports),
        'episodes': reports,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    if any(report['status'] == 'failed' for report in reports):
        return 1
    return 0 if all(
        report['status'] == 'accepted' for report in reports) else 2


def argument_parser():
    """Build the alignment command-line interface."""
    parser = argparse.ArgumentParser(
        description='Align UMI video frames with interpolated Vive poses')
    parser.add_argument(
        'input_path', help='Online session or episode directory')
    parser.add_argument('--output', help='Separate processed-data output root')
    parser.add_argument(
        '--offset-seconds', type=float,
        help='Diagnostic override when no accepted calibration is available')
    parser.add_argument('--maximum-pose-gap', type=float, default=0.1)
    parser.add_argument('--minimum-valid-ratio', type=float, default=0.95)
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run alignment without starting a ROS graph."""
    try:
        return align(argument_parser().parse_args(argv))
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        print(f'alignment failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
