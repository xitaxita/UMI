"""Export transformed UMI episodes as a native LeRobot v3 dataset."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from .dataset_plan import (
    read_plan,
    read_transformed_item,
    session_summary,
    sources_for_root,
    task_table,
)
from .export_hdf5 import _cv2


# Version 2 (D-021): per-session tasks and umi.source_session per frame.
FORMAT_VERSION = 2
IMAGE_KEY = 'observation.images.action4'
STATE_KEY = 'observation.state'


def _lerobot_dataset_class():
    try:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
    except ImportError as error:
        raise RuntimeError(
            'LeRobot export requires lerobot>=0.4 in a separate environment; '
            'do not install it into ~/umi_ros_venv because its NumPy and '
            'setuptools requirements conflict with ROS 2 Jazzy. Import error: '
            f'{error}') from error
    return LeRobotDataset


def _video_dimensions(path):
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        available, frame = capture.read()
    finally:
        capture.release()
    if not available:
        raise ValueError(f'cannot decode first video frame: {path}')
    return frame.shape[0], frame.shape[1]


def _features(height, width):
    return {
        IMAGE_KEY: {
            'dtype': 'video',
            'shape': (3, height, width),
            'names': ['channels', 'height', 'width'],
        },
        STATE_KEY: {
            'dtype': 'float32',
            'shape': (7,),
            'names': ['x', 'y', 'z', 'qx', 'qy', 'qz', 'qw'],
        },
        'umi.source_frame_index': {
            'dtype': 'int64', 'shape': (1,), 'names': ['frame_index'],
        },
        'umi.video_pts_seconds': {
            'dtype': 'float64', 'shape': (1,), 'names': ['seconds'],
        },
        'umi.pose_query_time_seconds': {
            'dtype': 'float64', 'shape': (1,), 'names': ['seconds'],
        },
        'umi.source_session': {
            'dtype': 'string', 'shape': (1,), 'names': None,
        },
    }


def _add_episode(dataset, source):
    cv2 = _cv2()
    item = Path(source.item)
    report, arrays = read_transformed_item(item)
    valid = np.asarray(arrays['valid'], dtype=bool)
    selected = np.flatnonzero(valid)
    if not len(selected):
        raise ValueError(f'episode contains no valid samples: {item}')
    source_video = report.get('source_video')
    if not source_video or not Path(source_video).is_file():
        raise ValueError(f'transform report has invalid source_video: {item}')
    selected_lookup = {
        int(value): index for index, value in enumerate(selected)
    }
    capture = cv2.VideoCapture(str(source_video))
    decoded = 0
    added = 0
    try:
        while True:
            available, frame = capture.read()
            if not available:
                break
            if decoded in selected_lookup:
                pose = np.concatenate([
                    arrays['position_xyz'][decoded],
                    arrays['orientation_xyzw'][decoded],
                ]).astype(np.float32)
                dataset.add_frame({
                    IMAGE_KEY: cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    STATE_KEY: pose,
                    'umi.source_frame_index': np.asarray(
                        [arrays['frame_index'][decoded]], dtype=np.int64),
                    'umi.video_pts_seconds': np.asarray(
                        [arrays['video_pts_seconds'][decoded]],
                        dtype=np.float64),
                    'umi.pose_query_time_seconds': np.asarray(
                        [arrays['pose_query_time_seconds'][decoded]],
                        dtype=np.float64),
                    'umi.source_session': source.source_session,
                    'task': source.task,
                })
                added += 1
            decoded += 1
    finally:
        capture.release()
    if decoded != len(valid):
        raise ValueError(
            f'video decoded {decoded} frames but contract has {len(valid)}: '
            f'{source_video}')
    if added != len(selected):
        raise ValueError(f'added {added}/{len(selected)} selected frames')
    dataset.save_episode(parallel_encoding=False)
    return added


def _safe_remove_staging(path):
    if path.exists():
        if not path.name.endswith('.partial') or path.parent == path:
            raise ValueError(f'refusing to remove unsafe staging path: {path}')
        shutil.rmtree(path)


def write_lerobot(output, sources, repo_id, fps, video_codec='h264',
                  image_writer_threads=4, encoder_threads=None,
                  overwrite=False, source_description=''):
    """Export planned episodes from one or more sessions via LeRobot v3."""
    if fps <= 0:
        raise ValueError('fps must be greater than zero')
    if not sources:
        raise ValueError('no episodes to export')
    dimensions = set()
    for source in sources:
        report, _ = read_transformed_item(Path(source.item))
        dimensions.add(_video_dimensions(Path(report['source_video'])))
    if len(dimensions) != 1:
        raise ValueError(
            f'all LeRobot episodes must use one image shape: {dimensions}')
    height, width = dimensions.pop()

    output = Path(output).expanduser().resolve()
    if output.exists() and not overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name + '.partial')
    _safe_remove_staging(staging)
    dataset_class = _lerobot_dataset_class()
    dataset = None
    try:
        dataset = dataset_class.create(
            repo_id=repo_id,
            fps=fps,
            features=_features(height, width),
            root=staging,
            robot_type='umi_vive_action4',
            use_videos=True,
            vcodec=video_codec,
            image_writer_threads=image_writer_threads,
            encoder_threads=encoder_threads,
        )
        counts = []
        for index, source in enumerate(sources):
            count = _add_episode(dataset, source)
            counts.append(count)
            print(f'episode {index} <- {source.source_session}/'
                  f'{Path(source.item).name}: exported {count} frames')
        dataset.finalize()
        dataset = None
        manifest = {
            'schema_version': FORMAT_VERSION,
            'format': 'lerobot_v3',
            'repo_id': repo_id,
            'fps': fps,
            'episode_count': len(counts),
            'frame_count': sum(counts),
            'source': source_description,
            'tasks': task_table(sources),
            'source_sessions': session_summary(sources),
            'episodes': [
                {
                    'episode_index': index,
                    'source_session': source.source_session,
                    'source_episode': source.source_episode,
                    'task': source.task,
                    'video_to_pose_offset_seconds': (
                        source.video_to_pose_offset_seconds),
                    'frame_count': count,
                }
                for index, (source, count) in enumerate(zip(sources, counts))
            ],
            'state_layout': 'x y z qx qy qz qw',
            'coordinate_frame': 'episode_start_pose',
            'action_field': None,
        }
        (staging / 'umi_export.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
    except BaseException:
        if dataset is not None:
            try:
                dataset.finalize()
            except Exception:
                pass
        _safe_remove_staging(staging)
        raise
    print(f'LeRobot v3 dataset -> {output}')
    return 0


def export_lerobot(args):
    """Export one transformed root, or a multi-session plan."""
    input_path = getattr(args, 'input_path', None)
    plan = getattr(args, 'plan', None)
    if bool(input_path) == bool(plan):
        raise ValueError('give either a transformed input_path or --plan')
    if plan:
        sources = read_plan(plan)
        description = str(Path(plan).expanduser().resolve())
    else:
        root = Path(input_path).expanduser().resolve()
        sources = sources_for_root(root, args.task)
        description = str(root)
    return write_lerobot(
        args.output, sources, args.repo_id, args.fps, args.video_codec,
        args.image_writer_threads, args.encoder_threads, args.overwrite,
        description)


def argument_parser():
    """Build the LeRobot v3 export CLI."""
    parser = argparse.ArgumentParser(
        description='Export transformed UMI episodes to LeRobot v3')
    parser.add_argument(
        'input_path', nargs='?', help='Transformed session or episode')
    parser.add_argument(
        '--plan', help='Multi-session dataset plan written by build_dataset')
    parser.add_argument(
        '--output', required=True, help='Dataset root directory')
    parser.add_argument('--repo-id', required=True, help='owner/dataset name')
    parser.add_argument(
        '--task', default='UMI demonstration',
        help='Task for input_path episodes (ignored with --plan)')
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument(
        '--video-codec', choices=('h264', 'hevc', 'libsvtav1', 'auto'),
        default='h264')
    parser.add_argument('--image-writer-threads', type=int, default=4)
    parser.add_argument('--encoder-threads', type=int)
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run native LeRobot v3 export."""
    try:
        return export_lerobot(argument_parser().parse_args(argv))
    except (OSError, RuntimeError, ValueError, KeyError,
            json.JSONDecodeError) as error:
        print(f'LeRobot export failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
