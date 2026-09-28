"""Build one HDF5 and/or LeRobot v3 dataset from several raw sessions.

Every session is calibrated, aligned and transformed on its own (D-021);
sessions meet only at export. Each run rebuilds the dataset from scratch into
``<output>.partial`` and replaces ``<output>`` only after everything passed.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from umi_ros2.postprocess.align_session import align
from umi_ros2.postprocess.dataset_plan import (
    read_transformed_item,
    session_summary,
    sources_for_root,
    task_table,
    write_plan,
)
from umi_ros2.postprocess.export_hdf5 import _cv2, write_hdf5
from umi_ros2.postprocess.transform_session import (
    CONTRACT_VERSION,
    transform,
)
from umi_ros2.session.layout import (
    latest_calibration,
    now_text,
    read_session,
    session_task,
)


MANIFEST_NAME = 'build_manifest.json'
MANIFEST_VERSION = 1


class BuildError(ValueError):
    """A dataset build check failed; the message names session and reason."""


def resolve_sessions(inputs):
    """Expand session directories and directories of sessions, in order."""
    sessions = []
    for value in inputs:
        path = Path(value).expanduser().resolve()
        if (path / 'session.yaml').is_file():
            found = [path]
        elif path.is_dir():
            found = sorted(
                child for child in path.iterdir()
                if child.is_dir() and (child / 'session.yaml').is_file())
            if not found:
                raise BuildError(f'{path} contains no session.yaml sessions')
        else:
            raise BuildError(f'{path} is not a session or a directory')
        for session in found:
            if session not in sessions:
                sessions.append(session)
    if not sessions:
        raise BuildError('no sessions given')
    names = [session.name for session in sessions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise BuildError(
            f'session names must be unique: {", ".join(duplicates)}')
    return sessions


def _has_episodes(session):
    episodes = session / 'episodes'
    return episodes.is_dir() and any(
        child.is_dir() and child.name.startswith('episode_')
        for child in episodes.iterdir())


def check_sessions(sessions, run_calibration):
    """Return (tasks, sessions to calibrate) or raise one combined error."""
    errors = []
    tasks = {}
    to_calibrate = []
    for session in sessions:
        try:
            metadata = read_session(session)
        except (OSError, ValueError) as error:
            errors.append(f'{session.name}: unreadable session.yaml: {error}')
            continue
        task = session_task(metadata)
        tasks[session] = task
        if not task:
            errors.append(
                f'{session.name}: task is empty; fill it in with '
                f'set_session_task {session} "<task>"')
        if metadata.get('status') == 'active':
            print(f'warning: {session.name} is still marked active')
        if not _has_episodes(session):
            errors.append(f'{session.name}: contains no ordinary episodes')
        status = metadata.get('temporal_calibration', {}).get('status')
        if status != 'accepted':
            if not run_calibration:
                errors.append(
                    f'{session.name}: temporal calibration is {status!r}, '
                    'not accepted; run calibrate_time or pass '
                    '--run-calibration')
            else:
                try:
                    to_calibrate.append((session, latest_calibration(session)))
                except ValueError:
                    errors.append(
                        f'{session.name}: not calibrated and has no '
                        'calibration recording to run')
    if errors:
        raise BuildError('\n'.join(errors))
    return tasks, to_calibrate


def _run_calibration(session, calibration):
    from umi_ros2.synchronization.calibrate_time import (
        argument_parser as calibration_argument_parser,
        calibrate,
    )
    print(f'{session.name}: running calibrate_time on {calibration.name}')
    result = calibrate(
        calibration_argument_parser().parse_args([str(calibration)]))
    if result != 0:
        raise BuildError(
            f'{session.name}: calibration {calibration.name} was not '
            'accepted')


def _alignment_failures(aligned_root):
    summary_path = aligned_root / 'alignment_summary.json'
    if not summary_path.is_file():
        return 'no alignment summary was written'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    problems = []
    for report in summary.get('episodes', []):
        if report.get('status') == 'accepted':
            continue
        name = Path(report.get('source_episode', '?')).name
        if report.get('status') == 'failed':
            problems.append(f'{name} failed: {report.get("error")}')
        else:
            problems.append(
                f'{name} rejected: valid frame ratio '
                f'{report.get("valid_frame_ratio", 0):.3f} < '
                f'{report.get("minimum_valid_frame_ratio")}')
    return '; '.join(problems) or 'alignment did not complete'


def process_one_session(session, task, processed_root, args):
    """Align and transform one session; return its planned episodes."""
    aligned_root = processed_root / session.name / 'aligned'
    transformed_root = processed_root / session.name / 'transformed'
    result = align(SimpleNamespace(
        input_path=str(session), output=str(aligned_root),
        offset_seconds=None, maximum_pose_gap=args.maximum_pose_gap,
        minimum_valid_ratio=args.minimum_valid_ratio, overwrite=False,
    ))
    if result != 0:
        raise BuildError(
            f'{session.name}: alignment not accepted: '
            f'{_alignment_failures(aligned_root)}')
    result = transform(SimpleNamespace(
        input_path=str(aligned_root), output=str(transformed_root),
        overwrite=False,
    ))
    if result != 0:
        raise BuildError(f'{session.name}: coordinate transform failed')
    return sources_for_root(transformed_root, task, session.name)


def video_size(path):
    """Return (height, width) of one MP4's first decoded frame."""
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        available, frame = capture.read()
    finally:
        capture.release()
    if not available:
        raise BuildError(f'cannot decode first video frame: {path}')
    return frame.shape[0], frame.shape[1]


def frame_rate(video_pts_seconds):
    """Return the frame rate from the median real PTS interval.

    Container averages (for example OpenCV ``CAP_PROP_FPS``) are skewed by
    the stream duration, so the actual frame spacing is used instead.
    """
    intervals = np.diff(np.asarray(video_pts_seconds, dtype=float))
    intervals = intervals[intervals > 0]
    if not len(intervals):
        raise BuildError('cannot determine frame rate from fewer than two '
                         'frames')
    return 1.0 / float(np.median(intervals))


def check_consistency(sources):
    """Require one contract version, image size and frame rate; return them."""
    errors = []
    properties = {}
    for source in sources:
        where = f'{source.source_session}/{Path(source.item).name}'
        try:
            report, arrays = read_transformed_item(Path(source.item))
        except (OSError, ValueError, KeyError) as error:
            errors.append(f'{where}: {error}')
            continue
        if report.get('schema_version') != CONTRACT_VERSION:
            errors.append(
                f'{where}: transform contract version '
                f'{report.get("schema_version")!r} != {CONTRACT_VERSION}')
            continue
        height, width = video_size(report['source_video'])
        fps = frame_rate(arrays['video_pts_seconds'])
        properties[where] = (height, width, round(fps, 2))
    if not errors and len(set(properties.values())) > 1:
        reference = next(iter(properties.values()))
        for where, value in properties.items():
            if value != reference:
                errors.append(
                    f'{where}: image/fps {value[1]}x{value[0]} @ {value[2]} '
                    f'differs from {reference[1]}x{reference[0]} @ '
                    f'{reference[2]}')
    if errors:
        raise BuildError('\n'.join(errors))
    height, width, fps = next(iter(properties.values()))
    if not fps or abs(fps - round(fps)) > 0.01:
        raise BuildError(f'video frame rate {fps} is not an integer rate')
    return height, width, int(round(fps))


def _export_lerobot(plan_path, output, fps, args):
    if not args.repo_id:
        raise BuildError('--repo-id is required for LeRobot export')
    # absolute(), not resolve(): a venv's bin/python is a symlink to the
    # base interpreter, and following it would leave the venv.
    interpreter = Path(args.lerobot_python).expanduser().absolute()
    if not interpreter.is_file():
        raise BuildError(
            f'LeRobot Python interpreter not found: {interpreter}')
    command = [
        str(interpreter), '-m', 'umi_ros2.postprocess.export_lerobot',
        '--plan', str(plan_path), '--output', str(output),
        '--repo-id', args.repo_id, '--fps', str(fps),
        '--video-codec', args.video_codec,
    ]
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run(command, check=False, env=environment)
    if result.returncode != 0:
        raise BuildError(f'LeRobot export returned {result.returncode}')


def _prepare_output(output, overwrite):
    if output.exists():
        if not overwrite:
            raise BuildError(
                f'output already exists; use --overwrite: {output}')
        if not (output / MANIFEST_NAME).is_file():
            raise BuildError(
                f'refusing to replace {output}: it has no {MANIFEST_NAME}, '
                'so it was not written by build_dataset')
    staging = output.with_name(output.name + '.partial')
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    return staging


def build(args):
    """Rebuild the requested dataset formats from the given sessions."""
    sessions = resolve_sessions(args.inputs)
    tasks, to_calibrate = check_sessions(sessions, args.run_calibration)
    output = Path(args.output).expanduser().resolve()
    for session in sessions:
        if (output == session or session in output.parents
                or output in session.parents):
            raise BuildError(
                f'output {output} must neither contain nor be inside the '
                f'raw session {session}')
    staging = _prepare_output(output, args.overwrite)
    processed_root = staging / 'processed'
    try:
        for session, calibration in to_calibrate:
            _run_calibration(session, calibration)
        sources = []
        for session in sessions:
            sources.extend(process_one_session(
                session, tasks[session], processed_root, args))
        height, width, fps = check_consistency(sources)
        outputs = {}
        if args.format in ('hdf5', 'both'):
            write_hdf5(
                staging / 'dataset.hdf5', sources, args.jpeg_quality,
                source_description=str(output))
            outputs['hdf5'] = 'dataset.hdf5'
        if args.format in ('lerobot', 'both'):
            plan_path = processed_root / 'dataset_plan.json'
            write_plan(plan_path, sources)
            _export_lerobot(plan_path, staging / 'lerobot', fps, args)
            outputs['lerobot'] = 'lerobot'
        paths = {session.name: str(session) for session in sessions}
        summary = session_summary(sources)
        for entry in summary:
            entry['path'] = paths[entry['session']]
        manifest = {
            'schema_version': MANIFEST_VERSION,
            'built_at': now_text(),
            'inputs': [str(Path(value).expanduser()) for value in args.inputs],
            'formats': outputs,
            'tasks': task_table(sources),
            'sessions': summary,
            'episode_count': len(sources),
            'image_height': height,
            'image_width': width,
            'fps': fps,
            'transform_contract_version': CONTRACT_VERSION,
            'processed': 'processed',
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
    except BaseException:
        print(f'build failed; intermediate results kept in {staging}')
        raise
    if output.exists():
        shutil.rmtree(output)
    staging.rename(output)
    print(f'dataset with {len(sources)} episodes from {len(sessions)} '
          f'sessions -> {output}')
    return 0


def argument_parser():
    """Build the multi-session dataset CLI."""
    parser = argparse.ArgumentParser(
        description=(
            'Build one dataset from several raw sessions. Each session is '
            'calibrated, aligned and transformed on its own and uses the '
            'task in its own session.yaml.'))
    parser.add_argument(
        'inputs', nargs='+',
        help='online_session_<time> directories and/or directories '
             'containing sessions')
    parser.add_argument(
        '--output', required=True,
        help='Dataset directory (rebuilt from scratch every run)')
    parser.add_argument(
        '--format', choices=('hdf5', 'lerobot', 'both'), default='hdf5')
    parser.add_argument('--repo-id', help='LeRobot owner/dataset identifier')
    parser.add_argument(
        '--run-calibration', action='store_true',
        help='Run calibrate_time on the newest calibration of sessions '
             'without an accepted result')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--maximum-pose-gap', type=float, default=0.1)
    parser.add_argument('--minimum-valid-ratio', type=float, default=0.95)
    parser.add_argument('--jpeg-quality', type=int, default=95)
    parser.add_argument(
        '--lerobot-python',
        default='~/umi_lerobot_venv312/bin/python',
        help='Python interpreter containing lerobot>=0.4')
    parser.add_argument(
        '--video-codec', choices=('h264', 'hevc', 'libsvtav1', 'auto'),
        default='h264')
    return parser


def main(argv=None):
    """Run the multi-session dataset build."""
    try:
        args = argument_parser().parse_args(argv)
        if not 1 <= args.jpeg_quality <= 100:
            raise BuildError('JPEG quality must be between 1 and 100')
        if not math.isfinite(args.maximum_pose_gap):
            raise BuildError('maximum pose gap must be finite')
        return build(args)
    except (OSError, RuntimeError, ValueError, KeyError,
            json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f'dataset build failed:\n{error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
