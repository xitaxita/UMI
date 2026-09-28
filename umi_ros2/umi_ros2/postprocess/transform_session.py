"""Create episode-relative pose intermediates from aligned frame data."""

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

from .episode_transform import transform_to_episode_frame


CONTRACT_VERSION = 1


def _natural_key(path):
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r'(\d+)', path.name)
    ]


def resolve_aligned_items(input_path):
    """Resolve one aligned episode directory or an aligned session root."""
    path = Path(input_path).expanduser().resolve()
    if (path / 'aligned_frames.npz').is_file():
        return None, [path]
    summary = path / 'alignment_summary.json'
    episodes = path / 'episodes'
    if not summary.is_file() or not episodes.is_dir():
        raise ValueError(
            'input must contain aligned_frames.npz or alignment_summary.json')
    items = sorted([
        child for child in episodes.iterdir()
        if child.is_dir() and (child / 'aligned_frames.npz').is_file()
    ], key=_natural_key)
    if not items:
        raise ValueError(f'aligned session contains no episodes: {path}')
    return path, items


def _destination(output_root, aligned_root, item):
    if aligned_root is None:
        return output_root / item.name
    return output_root / item.relative_to(aligned_root)


def transform_item(item, destination, overwrite=False):
    """Transform one aligned episode and write the exporter contract."""
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {destination}')
    with np.load(item / 'aligned_frames.npz') as source:
        transformed = transform_to_episode_frame(
            source['frame_index'], source['video_pts_seconds'],
            source['video_time_seconds'], source['pose_query_time_seconds'],
            source['valid'], source['position_xyz'],
            source['orientation_xyzw'])
    alignment = json.loads(
        (item / 'alignment.json').read_text(encoding='utf-8'))
    destination.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination / 'episode_frames.npz',
        contract_version=np.asarray(CONTRACT_VERSION, dtype=np.int64),
        frame_index=transformed.frame_index,
        video_pts_seconds=transformed.video_pts_seconds,
        video_time_seconds=transformed.video_time_seconds,
        pose_query_time_seconds=transformed.pose_query_time_seconds,
        valid=transformed.valid,
        position_xyz=transformed.position_xyz,
        orientation_xyzw=transformed.orientation_xyzw,
        reference_frame_index=np.asarray(
            transformed.reference_frame_index, dtype=np.int64),
        reference_position_xyz=transformed.reference_position_xyz,
        reference_orientation_xyzw=(
            transformed.reference_orientation_xyzw),
    )
    _write_csv(destination / 'episode_frames.csv', transformed)
    report = {
        'schema_version': CONTRACT_VERSION,
        'status': 'complete',
        'source_aligned_directory': str(item),
        'source_episode': alignment.get('source_episode'),
        'source_video': alignment.get('source_video'),
        'video_to_pose_offset_seconds': alignment.get(
            'video_to_pose_offset_seconds'),
        'offset_source': alignment.get('offset_source'),
        'frame_count': len(transformed.frame_index),
        'valid_frame_count': int(np.count_nonzero(transformed.valid)),
        'reference_definition': 'first_valid_aligned_video_frame_pose',
        'transform_convention': (
            'T_episode_i = inverse(T_world_reference) * T_world_i'),
        'reference_frame_index': transformed.reference_frame_index,
        'reference_position_xyz': (
            transformed.reference_position_xyz.tolist()),
        'reference_orientation_xyzw': (
            transformed.reference_orientation_xyzw.tolist()),
        'raw_data_modified': False,
    }
    (destination / 'transform.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def _write_csv(path, data):
    fields = [
        'frame_index', 'video_pts_seconds', 'video_time_seconds',
        'pose_query_time_seconds', 'valid', 'position_x', 'position_y',
        'position_z', 'orientation_x', 'orientation_y', 'orientation_z',
        'orientation_w',
    ]
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(fields)
        for index in range(len(data.frame_index)):
            writer.writerow([
                data.frame_index[index], data.video_pts_seconds[index],
                data.video_time_seconds[index],
                data.pose_query_time_seconds[index], bool(data.valid[index]),
                *data.position_xyz[index], *data.orientation_xyzw[index],
            ])


def transform(args):
    """Transform all selected aligned episodes."""
    aligned_root, items = resolve_aligned_items(args.input_path)
    if args.output:
        output_root = Path(args.output).expanduser().resolve()
    else:
        name = aligned_root.name if aligned_root is not None else items[0].name
        output_root = (
            Path.cwd() / 'processed' / f'{name}_transformed').resolve()
    summary_path = output_root / 'transform_summary.json'
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {output_root}')
    reports = []
    for item in items:
        destination = _destination(output_root, aligned_root, item)
        report = transform_item(item, destination, args.overwrite)
        reports.append(report)
        print(
            f'{item.name}: {report["valid_frame_count"]}/'
            f'{report["frame_count"]} transformed -> {destination}')
    summary = {
        'schema_version': CONTRACT_VERSION,
        'status': 'complete',
        'source_aligned_root': str(aligned_root or items[0]),
        'episode_count': len(reports),
        'episodes': reports,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return 0


def argument_parser():
    """Build the episode-coordinate transform CLI."""
    parser = argparse.ArgumentParser(
        description='Transform aligned Vive poses to episode coordinates')
    parser.add_argument('input_path', help='Aligned session or episode output')
    parser.add_argument('--output', help='Transformed-data output root')
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run episode-coordinate transformation."""
    try:
        return transform(argument_parser().parse_args(argv))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f'coordinate transform failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
