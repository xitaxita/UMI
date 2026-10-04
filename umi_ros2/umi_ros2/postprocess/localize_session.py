"""Write episode-start-relative poses from standalone 90 Hz expansions."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from umi_ros2.common.ordering import natural_key

from .local_pose import localize_poses


CONTRACT_NAME = 'umi_local_pose'
CONTRACT_VERSION = 1
EXPANSION_CONTRACT = 'umi_frame_expansion'
REFERENCE_DEFINITION = 'first_recorded_tcp_pose_after_start'
SAMPLE_FIELDS = (
    'sample_index', 'group_index', 'repeat_index', 'timestamp',
    'pose_query_time_seconds', 'episode_time_seconds', 'valid', 'pose_valid',
    'pose_left_index', 'pose_right_index', 'interpolation_alpha',
    'pose_gap_seconds',
) + tuple(
    f'{camera}_{field}' for camera in ('wrist', 'left') for field in (
        'frame_index', 'video_pts_seconds', 'image_time_seconds',
        'pairing_delta_seconds', 'image_age_seconds', 'valid'))


def _read_report(path, contract):
    report = json.loads(path.read_text(encoding='utf-8'))
    if (report.get('contract') != contract
            or report.get('schema_version') != CONTRACT_VERSION):
        raise ValueError(f'unsupported input contract: {path}')
    if not report.get('source_session'):
        raise ValueError(f'input has no source raw session: {path}')
    return report


def resolve_expanded_items(input_path):
    """Resolve one expanded episode or every indexed session episode."""
    path = Path(input_path).expanduser().resolve()
    if (path / 'expansion.json').is_file():
        return None, [path], _read_report(
            path / 'expansion.json', EXPANSION_CONTRACT)
    summary = _read_report(
        path / 'expansion_summary.json', EXPANSION_CONTRACT)
    entries = summary.get('episodes', [])
    if not entries:
        raise ValueError(f'expanded session contains no episodes: {path}')
    names = [Path(entry['source_episode']).name for entry in entries]
    if (len(set(names)) != len(names)
            or any(not name.startswith('episode_') for name in names)):
        raise ValueError('expansion summary has invalid episode paths')
    return path, [path / 'episodes' / name for name in sorted(
        names, key=natural_key)], summary


def _check_output(destination, input_path, report, overwrite, marker):
    raw_session = Path(report['source_session']).expanduser().resolve()
    for protected in (input_path, raw_session):
        if (destination == protected or protected in destination.parents
                or destination in protected.parents):
            raise ValueError(
                'local output must be separate from raw and input')
    if destination.exists():
        if not overwrite:
            raise FileExistsError(
                f'output exists; use --overwrite: {destination}')
        markers = [marker]
        if marker == 'local_pose.json':
            # A failed single-episode CLI run may have only its own summary.
            markers.append('local_pose_summary.json')
        own_output = any(
            (destination / name).is_file() and json.loads(
                (destination / name).read_text(encoding='utf-8')).get(
                    'contract') == CONTRACT_NAME for name in markers)
        if not own_output:
            raise ValueError(f'refusing to overwrite non-local-pose output: '
                             f'{destination}')


def _load_expansion(item, report):
    if (report.get('pose_coordinate_frame') != 'raw_world'
            or report.get('pose_reference_definition') != REFERENCE_DEFINITION
            or report.get('status') not in ('accepted', 'rejected')):
        raise ValueError(
            'input needs world poses and the first raw TCP reference')
    with np.load(item / 'expanded_frames.npz', allow_pickle=False) as source:
        arrays = {name: source[name].copy() for name in source.files}
    for name, expected in (
        ('contract_version', 1), ('fps', 90), ('image_repeats', 3),
    ):
        if arrays[name].shape != () or arrays[name].item() != expected:
            raise ValueError(f'unsupported expansion {name}')
    if arrays['sample_index'].ndim != 1:
        raise ValueError('expanded sample index must be one-dimensional')
    count = len(arrays['sample_index'])
    if (not count or count % 3 or count != report['sample_count']
            or any(arrays[name].shape != (count,) for name in SAMPLE_FIELDS)):
        raise ValueError('expanded sample arrays have incompatible shapes')
    for name in ('valid', 'pose_valid', 'wrist_valid', 'left_valid'):
        if arrays[name].dtype != np.dtype(bool):
            raise ValueError(f'{name} must be a boolean mask')
    if np.any(arrays['valid'] & ~arrays['pose_valid']):
        raise ValueError('valid image group has an invalid pose query')
    reference_time = arrays['reference_pose_time_seconds']
    if reference_time.shape != () or not np.isfinite(reference_time):
        raise ValueError('first raw TCP reference time is invalid')
    if float(reference_time) != report['reference_pose_time_seconds']:
        raise ValueError('first raw TCP reference times disagree')
    if 'state' in arrays or 'action' in arrays:
        raise ValueError('expansion v1 must not contain state/action')
    return arrays


def _write_csv(path, arrays):
    fields = (
        'sample_index', 'group_index', 'repeat_index', 'timestamp',
        'episode_time_seconds', 'pose_query_time_seconds', 'valid',
        'pose_valid', 'wrist_frame_index', 'left_frame_index',
    )
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow([*fields, 'x', 'y', 'z', 'qx', 'qy', 'qz', 'qw'])
        for index in range(len(arrays['sample_index'])):
            writer.writerow([
                *(arrays[field][index] for field in fields),
                *arrays['position_xyz'][index],
                *arrays['orientation_xyzw'][index],
            ])


def localize_item(item, destination, overwrite=False):
    """Transform one expansion, without reading videos or raw pose files."""
    item = Path(item).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    expansion = _read_report(item / 'expansion.json', EXPANSION_CONTRACT)
    _check_output(destination, item, expansion, overwrite, 'local_pose.json')
    arrays = _load_expansion(item, expansion)
    positions, orientations = localize_poses(
        arrays['position_xyz'], arrays['orientation_xyzw'],
        arrays['pose_valid'], arrays['reference_position_xyz'],
        arrays['reference_orientation_xyzw'])
    arrays['world_position_xyz'] = arrays['position_xyz']
    arrays['world_orientation_xyzw'] = arrays['orientation_xyzw']
    arrays['position_xyz'] = positions
    arrays['orientation_xyzw'] = orientations
    arrays['contract'] = np.asarray(CONTRACT_NAME)
    arrays['pose_coordinate_frame'] = np.asarray('episode_start_tcp')
    count = len(positions)
    report = {
        'contract': CONTRACT_NAME, 'schema_version': CONTRACT_VERSION,
        'status': 'complete', 'source_expanded_directory': str(item),
        'source_expansion_status': expansion['status'],
        'source_episode': expansion['source_episode'],
        'source_session': expansion['source_session'],
        'source_pose': expansion['source_pose'],
        'cameras': expansion['cameras'],
        'fps': 90, 'image_repeats': 3, 'sample_count': count,
        'valid_sample_count': int(np.count_nonzero(arrays['valid'])),
        'invalid_sample_count': int(np.count_nonzero(~arrays['valid'])),
        'valid_pose_count': int(np.count_nonzero(arrays['pose_valid'])),
        'pose_coordinate_frame': 'episode_start_tcp',
        'pose_layout': 'x y z qx qy qz qw', 'position_unit': 'm',
        'reference_definition': REFERENCE_DEFINITION,
        'reference_pose_time_seconds': float(
            arrays['reference_pose_time_seconds']),
        'reference_position_xyz': arrays['reference_position_xyz'].tolist(),
        'reference_orientation_xyzw': (
            arrays['reference_orientation_xyzw'] / np.linalg.norm(
                arrays['reference_orientation_xyzw'])).tolist(),
        'reference_coordinate_frame': 'raw_world',
        'transform_convention': (
            'T_local_i = inverse(T_world_start) * T_world_i'),
        'quaternion_sign_convention': (
            'continuous_across_successive_valid_poses'),
        'state_action_generated': False, 'images_materialized': False,
        'raw_data_modified': False,
    }
    destination.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination / 'local_frames.npz', **arrays)
    _write_csv(destination / 'local_frames.csv', arrays)
    (destination / 'local_pose.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8')
    return report


def localize(args):
    """Localize selected episodes, using an independent reference for each."""
    root, items, source_report = resolve_expanded_items(args.input_path)
    input_path = root or items[0]
    output = (Path(args.output).expanduser().resolve() if args.output else
              input_path.with_name(f'{input_path.name}_local'))
    marker = 'local_pose_summary.json' if root else 'local_pose.json'
    _check_output(output, input_path, source_report, args.overwrite, marker)
    reports = []
    for item in items:
        destination = output / item.relative_to(root) if root else output
        try:
            report = localize_item(item, destination, args.overwrite)
        except (OSError, ValueError, KeyError) as error:
            report = {'status': 'failed',
                      'source_expanded_directory': str(item),
                      'error': str(error), 'raw_data_modified': False}
        reports.append(report)
        if report['status'] == 'failed':
            print(f'{item.name}: failed: {report["error"]}')
        else:
            print(f'{item.name}: {report["valid_pose_count"]}/'
                  f'{report["sample_count"]} poses localized -> {destination}')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'local_pose_summary.json').write_text(json.dumps({
        'contract': CONTRACT_NAME, 'schema_version': CONTRACT_VERSION,
        'source_expanded_root': str(input_path), 'episode_count': len(reports),
        'episodes': reports, 'raw_data_modified': False,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if any(report['status'] == 'failed' for report in reports):
        return 1
    return 2 if any(report['source_expansion_status'] == 'rejected'
                    for report in reports) else 0


def argument_parser():
    """Build the standalone fixed-reference pose CLI."""
    parser = argparse.ArgumentParser(
        description=(
            'Localize expanded poses to each episode first raw TCP pose'))
    parser.add_argument('input_path',
                        help='Expanded session or episode output')
    parser.add_argument('--output',
                        help='Separate local-pose output directory')
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run pose localization without ROS, video decoding or state/action."""
    try:
        return localize(argument_parser().parse_args(argv))
    except (OSError, ValueError, KeyError) as error:
        print(f'pose localization failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
