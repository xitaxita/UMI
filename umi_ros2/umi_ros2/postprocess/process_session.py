"""Orchestrate calibration, alignment, transform and dataset export."""

import argparse
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from umi_ros2.postprocess.align_session import align
from umi_ros2.postprocess.export_hdf5 import export_hdf5
from umi_ros2.postprocess.transform_session import transform
from umi_ros2.session.layout import (
    calibration_number,
    latest_calibration,
    read_session,
)


def select_calibration(session, requested=None):
    """Return the requested calibration, or the newest one by default."""
    if requested is None:
        return latest_calibration(session)
    candidate = Path(requested).expanduser()
    if not candidate.is_absolute() and len(candidate.parts) == 1:
        candidate = session / 'calibration' / candidate
    candidate = candidate.resolve()
    if (candidate.parent != session / 'calibration'
            or calibration_number(candidate) is None
            or not candidate.is_dir()):
        raise ValueError(
            f'{requested} is not a calibration_<n> directory of {session}')
    return candidate


def _ensure_calibration(
        session, run_calibration, offset_seconds, requested=None):
    if requested is not None:
        if not run_calibration:
            raise ValueError('--calibration requires --run-calibration')
        if offset_seconds is not None:
            raise ValueError(
                '--calibration cannot be combined with --offset-seconds')
    metadata = read_session(session)
    accepted = (
        metadata.get('temporal_calibration', {}).get('status') == 'accepted')
    # An explicitly chosen calibration is always re-run.
    if accepted and requested is None:
        return
    if offset_seconds is not None:
        return
    if not run_calibration:
        raise ValueError(
            'session has no accepted calibration; run calibrate_time first or '
            'use --run-calibration')
    from umi_ros2.synchronization.calibrate_time import (
        argument_parser as calibration_argument_parser,
        calibrate,
    )
    calibration = select_calibration(session, requested)
    print(f'running temporal calibration on {calibration}')
    calibration_args = calibration_argument_parser().parse_args([
        str(calibration),
    ])
    result = calibrate(calibration_args)
    if result != 0:
        raise ValueError('temporal calibration was not accepted')


def process(args):
    """Run the independently testable processing stages in order."""
    session = Path(args.session).expanduser().resolve()
    if not (session / 'session.yaml').is_file():
        raise ValueError(f'input is not a session: {session}')
    _ensure_calibration(
        session, args.run_calibration, args.offset_seconds,
        getattr(args, 'calibration', None))
    output_root = (
        Path(args.output).expanduser().resolve()
        if args.output else
        (Path.cwd() / 'processed' / session.name).resolve()
    )
    aligned_root = output_root / 'aligned'
    transformed_root = output_root / 'transformed'
    dataset_path = output_root / 'dataset.hdf5'
    lerobot_path = output_root / 'lerobot'

    align_result = align(SimpleNamespace(
        input_path=str(session), output=str(aligned_root),
        offset_seconds=args.offset_seconds,
        maximum_pose_gap=args.maximum_pose_gap,
        minimum_valid_ratio=args.minimum_valid_ratio,
        overwrite=args.overwrite,
    ))
    if align_result != 0:
        raise ValueError(f'alignment returned status {align_result}')
    transform_result = transform(SimpleNamespace(
        input_path=str(aligned_root), output=str(transformed_root),
        overwrite=args.overwrite,
    ))
    if transform_result != 0:
        raise ValueError(f'coordinate transform returned {transform_result}')
    if args.format in ('hdf5', 'both'):
        export_result = export_hdf5(SimpleNamespace(
            input_path=str(transformed_root), output=str(dataset_path),
            task=args.task, jpeg_quality=args.jpeg_quality,
            overwrite=args.overwrite,
        ))
        if export_result != 0:
            raise ValueError(f'HDF5 export returned {export_result}')
    if args.format in ('lerobot', 'both'):
        if not args.repo_id:
            raise ValueError('--repo-id is required for LeRobot export')
        lerobot_python = Path(
            args.lerobot_python).expanduser().resolve()
        if not lerobot_python.is_file():
            raise ValueError(
                f'LeRobot Python interpreter not found: {lerobot_python}')
        command = [
            str(lerobot_python), '-m',
            'umi_ros2.postprocess.export_lerobot',
            str(transformed_root), '--output', str(lerobot_path),
            '--repo-id', args.repo_id, '--task', args.task,
            '--fps', str(args.fps), '--video-codec', args.video_codec,
        ]
        if args.overwrite:
            command.append('--overwrite')
        child_environment = os.environ.copy()
        package_root = Path(__file__).resolve().parents[2]
        child_environment['PYTHONPATH'] = str(package_root)
        result = subprocess.run(
            command, check=False, env=child_environment)
        if result.returncode != 0:
            raise ValueError(
                f'LeRobot export returned {result.returncode}')
    return 0


def argument_parser():
    """Build the complete processing pipeline CLI."""
    parser = argparse.ArgumentParser(
        description='Process one raw UMI session into a dataset')
    parser.add_argument('session', help='Raw online session directory')
    parser.add_argument('--output', help='Processing output root')
    parser.add_argument(
        '--run-calibration', action='store_true',
        help='Run calibrate_time when no offset is accepted (on the newest '
             'calibration unless --calibration is given)')
    parser.add_argument(
        '--calibration',
        help='calibration_<n> name or path to (re)run with '
             '--run-calibration, even if an offset is already accepted')
    parser.add_argument(
        '--offset-seconds', type=float,
        help='Diagnostic offset override; does not mark calibration accepted')
    parser.add_argument('--maximum-pose-gap', type=float, default=0.1)
    parser.add_argument('--minimum-valid-ratio', type=float, default=0.95)
    parser.add_argument('--task', default='')
    parser.add_argument(
        '--format', choices=('hdf5', 'lerobot', 'both'), default='hdf5')
    parser.add_argument('--repo-id', help='LeRobot owner/dataset identifier')
    parser.add_argument(
        '--lerobot-python',
        default='~/umi_lerobot_venv312/bin/python',
        help='Python interpreter containing lerobot>=0.4')
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument(
        '--video-codec', choices=('h264', 'hevc', 'libsvtav1', 'auto'),
        default='h264')
    parser.add_argument('--jpeg-quality', type=int, default=95)
    parser.add_argument('--overwrite', action='store_true')
    return parser


def main(argv=None):
    """Run the raw-session processing pipeline."""
    try:
        args = argument_parser().parse_args(argv)
        if not 1 <= args.jpeg_quality <= 100:
            raise ValueError('JPEG quality must be between 1 and 100')
        return process(args)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f'dataset processing failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
