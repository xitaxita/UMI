"""Export transformed UMI episodes as a self-contained HDF5 dataset."""

import argparse
import json
from pathlib import Path

import numpy as np

from .dataset_plan import (
    read_transformed_item,
    session_summary,
    sources_for_root,
    task_table,
)


# Version 2 (D-021): per-episode task/source attributes and a root task table.
FORMAT_VERSION = 2


def _h5py():
    try:
        import h5py
    except ImportError as error:
        raise RuntimeError(
            'HDF5 export requires h5py; install python3-h5py or pip install '
            'h5py in ~/umi_ros_venv') from error
    return h5py


def _cv2():
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError(
            'HDF5 image export requires OpenCV; install python3-opencv and '
            'create the venv with --system-site-packages') from error
    return cv2


def _video_shape(video_path):
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(video_path))
    try:
        available, frame = capture.read()
    finally:
        capture.release()
    if not available:
        raise ValueError(f'cannot decode first video frame: {video_path}')
    return frame.shape[0], frame.shape[1]


def _write_video_frames(group, video_path, frame_count, selected_indices,
                        jpeg_quality):
    cv2 = _cv2()
    h5py = _h5py()
    height, width = _video_shape(video_path)
    images = group.create_dataset(
        'images', shape=(len(selected_indices),),
        dtype=h5py.vlen_dtype(np.dtype('uint8')))
    lookup = {int(source): output for output, source in enumerate(
        selected_indices.tolist())}
    capture = cv2.VideoCapture(str(video_path))
    decoded = 0
    written = 0
    try:
        while True:
            available, frame = capture.read()
            if not available:
                break
            output_index = lookup.get(decoded)
            if output_index is not None:
                encoded, payload = cv2.imencode(
                    '.jpg', frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                if not encoded:
                    raise ValueError(
                        f'JPEG encoding failed for frame {decoded}')
                images[output_index] = np.asarray(payload, dtype=np.uint8)
                written += 1
            decoded += 1
    finally:
        capture.release()
    if decoded != frame_count:
        raise ValueError(
            f'video decoded {decoded} frames but contract has {frame_count}: '
            f'{video_path}')
    if written != len(selected_indices):
        raise ValueError(
            f'wrote {written}/{len(selected_indices)} selected video frames')
    images.attrs['encoding'] = 'jpeg'
    images.attrs['decoded_color_order'] = 'BGR_with_opencv'
    images.attrs['height'] = height
    images.attrs['width'] = width
    images.attrs['channels'] = 3
    images.attrs['jpeg_quality'] = jpeg_quality
    images.attrs['source_video'] = str(video_path)


def export_item(parent, source, episode_index, task_index, jpeg_quality=95):
    """Write one transformed episode group and return its sample count."""
    item = Path(source.item)
    report, arrays = read_transformed_item(item)
    valid = np.asarray(arrays['valid'], dtype=bool)
    selected = np.flatnonzero(valid)
    if not len(selected):
        raise ValueError(f'episode contains no valid samples: {item}')
    source_video = report.get('source_video')
    if not source_video:
        raise ValueError(f'transform report has no source_video: {item}')
    video_path = Path(source_video)
    if not video_path.is_file():
        raise ValueError(f'source video does not exist: {video_path}')

    group = parent.create_group(f'episode_{episode_index:04d}')
    group.attrs['task'] = source.task
    group.attrs['task_index'] = task_index
    group.attrs['source_session'] = source.source_session
    group.attrs['source_episode'] = source.source_episode
    group.attrs['video_to_pose_offset_seconds'] = (
        np.nan if source.video_to_pose_offset_seconds is None
        else float(source.video_to_pose_offset_seconds))
    group.attrs['source_video'] = str(video_path)
    group.attrs['reference_definition'] = report['reference_definition']
    group.attrs['source_frame_count'] = len(valid)
    group.attrs['sample_count'] = len(selected)
    group.attrs['dropped_invalid_frame_count'] = int(
        len(valid) - len(selected))
    observations = group.create_group('observations')
    _write_video_frames(
        observations, video_path, len(valid), selected, jpeg_quality)
    pose = np.concatenate([
        arrays['position_xyz'][selected],
        arrays['orientation_xyzw'][selected],
    ], axis=1)
    observations.create_dataset('pose', data=pose.astype(np.float32))
    observations['pose'].attrs['layout'] = 'x y z qx qy qz qw'
    group.create_dataset(
        'frame_index', data=arrays['frame_index'][selected].astype(np.int64))
    relative_time = (
        arrays['video_pts_seconds'][selected]
        - arrays['video_pts_seconds'][selected[0]])
    group.create_dataset('timestamp', data=relative_time.astype(np.float64))
    group['timestamp'].attrs['unit'] = 'seconds_from_first_exported_frame'
    group.create_dataset(
        'video_pts_seconds',
        data=arrays['video_pts_seconds'][selected].astype(np.float64))
    group.create_dataset(
        'pose_query_time_seconds',
        data=arrays['pose_query_time_seconds'][selected].astype(np.float64))
    return len(selected)


def write_hdf5(output, sources, jpeg_quality=95, overwrite=False,
               source_description=''):
    """Export planned episodes from one or more sessions into one file."""
    h5py = _h5py()
    if not sources:
        raise ValueError('no episodes to export')
    output = Path(output).expanduser().resolve()
    if output.exists() and not overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.partial')
    if temporary.exists():
        temporary.unlink()
    tasks = task_table(sources)
    sessions = session_summary(sources)
    try:
        with h5py.File(temporary, 'w') as dataset:
            dataset.attrs['format'] = 'umi_hdf5'
            dataset.attrs['format_version'] = FORMAT_VERSION
            dataset.attrs['coordinate_frame'] = 'episode_start_pose'
            dataset.attrs['pose_layout'] = 'x y z qx qy qz qw'
            dataset.attrs['source'] = source_description
            dataset.attrs['source_sessions'] = json.dumps(
                sessions, ensure_ascii=False)
            dataset.attrs['session_count'] = len(sessions)
            table = dataset.create_dataset(
                'tasks', data=np.array(tasks, dtype=object),
                dtype=h5py.string_dtype(encoding='utf-8'))
            table.attrs['description'] = (
                'task string indexed by the episode task_index attribute')
            episodes = dataset.create_group('episodes')
            counts = []
            for index, source in enumerate(sources):
                count = export_item(
                    episodes, source, index, tasks.index(source.task),
                    jpeg_quality)
                counts.append(count)
                print(f'episode_{index:04d} <- {source.source_session}/'
                      f'{Path(source.item).name}: exported {count} samples')
            dataset.attrs['episode_count'] = len(counts)
            dataset.attrs['sample_count'] = sum(counts)
        temporary.replace(output)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise
    print(f'HDF5 dataset -> {output}')
    return 0


def export_hdf5(args):
    """Export all episodes of one transformed root with one task."""
    root = Path(args.input_path).expanduser().resolve()
    return write_hdf5(
        args.output, sources_for_root(root, args.task),
        args.jpeg_quality, args.overwrite, str(root))


def argument_parser():
    """Build the HDF5 export command-line interface."""
    parser = argparse.ArgumentParser(
        description='Export transformed UMI episodes to HDF5')
    parser.add_argument('input_path', help='Transformed session or episode')
    parser.add_argument('--output', required=True, help='Output .hdf5 file')
    parser.add_argument(
        '--task', default='',
        help='Task for every episode of this one transformed root; use '
             'build_dataset to merge sessions with their own tasks')
    parser.add_argument('--jpeg-quality', type=int, default=95)
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run HDF5 export."""
    try:
        args = argument_parser().parse_args(argv)
        if not 1 <= args.jpeg_quality <= 100:
            raise ValueError('JPEG quality must be between 1 and 100')
        return export_hdf5(args)
    except (OSError, RuntimeError, ValueError, KeyError,
            json.JSONDecodeError) as error:
        print(f'HDF5 export failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
