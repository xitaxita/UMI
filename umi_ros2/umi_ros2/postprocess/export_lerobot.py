"""Export transformed UMI episodes as a native LeRobot v3 dataset."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from .export_hdf5 import _cv2, resolve_transformed_items


FORMAT_VERSION = 1
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


def _read_item(item):
    report = json.loads(
        (item / 'transform.json').read_text(encoding='utf-8'))
    with np.load(item / 'episode_frames.npz') as values:
        arrays = {name: values[name].copy() for name in values.files}
    version = int(np.asarray(arrays['contract_version']).item())
    if version != FORMAT_VERSION:
        raise ValueError(
            f'unsupported episode contract version {version}: {item}')
    return report, arrays


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
    }


def _add_episode(dataset, item, task, fps):
    cv2 = _cv2()
    report, arrays = _read_item(item)
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
                    'task': task,
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


def export_lerobot(args):
    """Export all transformed episodes using the official LeRobot v3 API."""
    if args.fps <= 0:
        raise ValueError('fps must be greater than zero')
    items = resolve_transformed_items(args.input_path)
    first_report, _ = _read_item(items[0])
    first_video = Path(first_report['source_video'])
    height, width = _video_dimensions(first_video)
    for item in items[1:]:
        report, _ = _read_item(item)
        dimensions = _video_dimensions(Path(report['source_video']))
        if dimensions != (height, width):
            raise ValueError('all LeRobot episodes must use one image shape')

    output = Path(args.output).expanduser().resolve()
    if output.exists() and not args.overwrite:
        raise FileExistsError(
            f'output already exists; use --overwrite: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name + '.partial')
    _safe_remove_staging(staging)
    dataset_class = _lerobot_dataset_class()
    dataset = None
    try:
        dataset = dataset_class.create(
            repo_id=args.repo_id,
            fps=args.fps,
            features=_features(height, width),
            root=staging,
            robot_type='umi_vive_action4',
            use_videos=True,
            vcodec=args.video_codec,
            image_writer_threads=args.image_writer_threads,
            encoder_threads=args.encoder_threads,
        )
        counts = []
        for item in items:
            count = _add_episode(dataset, item, args.task, args.fps)
            counts.append(count)
            print(f'{item.name}: exported {count} LeRobot frames')
        dataset.finalize()
        dataset = None
        manifest = {
            'schema_version': FORMAT_VERSION,
            'format': 'lerobot_v3',
            'repo_id': args.repo_id,
            'fps': args.fps,
            'episode_count': len(counts),
            'frame_count': sum(counts),
            'source_transformed_root': str(
                Path(args.input_path).expanduser().resolve()),
            'state_layout': 'x y z qx qy qz qw',
            'coordinate_frame': 'episode_start_pose',
            'action_field': None,
        }
        (staging / 'umi_export.json').write_text(
            json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
    except Exception:
        if dataset is not None:
            try:
                dataset.finalize()
            except Exception:
                pass
        _safe_remove_staging(staging)
        raise
    print(f'LeRobot v3 dataset -> {output}')
    return 0


def argument_parser():
    """Build the LeRobot v3 export CLI."""
    parser = argparse.ArgumentParser(
        description='Export transformed UMI episodes to LeRobot v3')
    parser.add_argument('input_path', help='Transformed session or episode')
    parser.add_argument(
        '--output', required=True, help='Dataset root directory')
    parser.add_argument('--repo-id', required=True, help='owner/dataset name')
    parser.add_argument('--task', default='UMI demonstration')
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
