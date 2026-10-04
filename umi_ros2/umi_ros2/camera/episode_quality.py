"""Small raw-episode quality gate using saved video checks and pose headers."""

import json
import math
from pathlib import Path


IMAGE_GAP_LIMIT_SECONDS = 0.050
MIN_POSE_HZ = 88.0


def pose_statistics(stamps):
    """Count pose gaps without rejecting isolated missed 90 Hz updates."""
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    span = stamps[-1] - stamps[0] if len(stamps) > 1 else 0
    return {
        'frames': len(stamps),
        'first_timestamp_ns': stamps[0] if stamps else None,
        'last_timestamp_ns': stamps[-1] if stamps else None,
        'average_hz': (len(stamps) - 1) * 1e9 / span if span > 0 else 0,
        'max_gap_seconds': max(gaps, default=0) / 1e9,
        'gap_count': sum(gap > 1.5 * 1e9 / 90 for gap in gaps),
        'non_increasing_timestamps': sum(gap <= 0 for gap in gaps),
    }


def read_pose_statistics(directory):
    """Read only PoseStamped messages from the closed episode MCAP once."""
    import rosbag2_py
    from geometry_msgs.msg import PoseStamped
    from rclpy.serialization import deserialize_message

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(directory), storage_id='mcap'),
        rosbag2_py.ConverterOptions('', ''))
    reader.set_filter(rosbag2_py.StorageFilter(topics=['/vive/pose']))
    stamps = []
    while reader.has_next():
        _, data, _ = reader.read_next()
        stamp = deserialize_message(data, PoseStamped).header.stamp
        stamps.append(stamp.sec * 1_000_000_000 + stamp.nanosec)
    return pose_statistics(stamps)


def check_image(timing, validation, pose):
    """Judge saved frames and their raw host-time coverage by pose."""
    reasons = []
    if (timing.get('status') != 'complete'
            or not validation.get('decode_ok')
            or not validation.get('clean_shutdown')
            or not validation.get('frame_count_matches')):
        reasons.append('image 文件或帧数检查失败')
    first = validation.get('first_frame_pts_seconds')
    last = validation.get('last_frame_pts_seconds')
    gap = validation.get('max_timestamp_gap_seconds')
    if (not all(isinstance(value, (int, float)) and math.isfinite(value)
                for value in (first, last, gap))
            or last <= first
            or validation.get('timestamped_frames')
            != validation.get('decoded_frames')
            or validation.get('non_increasing_timestamps') != 0):
        reasons.append('image 时间戳检查失败')
    elif gap > IMAGE_GAP_LIMIT_SECONDS:
        reasons.append('image 掉帧')
    origin = timing.get('first_receive_unix_ns')
    covered = False
    if (isinstance(origin, int) and not isinstance(origin, bool)
            and all(isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (first, last))
            and pose.get('first_timestamp_ns') is not None
            and pose.get('last_timestamp_ns') is not None):
        covered = (
            pose['first_timestamp_ns'] <= origin + round(first * 1e9)
            and pose['last_timestamp_ns'] >= origin + round(last * 1e9))
    if not covered:
        reasons.append('pose 未完整覆盖 image')
    return {
        'accepted': not reasons, 'reasons': reasons,
        'pose_covers_image': covered,
        'decoded_frames': validation.get('decoded_frames'),
        'max_gap_seconds': gap,
        'gap_count': validation.get('image_gap_count'),
    }


def diagnose_episode(episode, streams, finalization_errors=()):
    """Reuse MP4 validation JSONs; never decode either video again here."""
    episode = Path(episode)
    reasons = list(finalization_errors)
    try:
        pose = read_pose_statistics(episode / 'pose')
        if pose['frames'] < 2 or pose['non_increasing_timestamps']:
            reasons.append('pose 时间戳检查失败')
        if pose['average_hz'] < MIN_POSE_HZ:
            reasons.append('pose 平均帧率低于 88 Hz')
    except Exception as error:
        pose = {'error': str(error)}
        reasons.append('pose 诊断失败')
    cameras = {}
    if not streams:
        reasons.append('缺少 image 流')
    for stream in streams:
        camera_id = stream['camera_id']
        try:
            timing = json.loads(
                (episode / stream['timing_path']).read_text())
            validation = json.loads(
                (episode / stream['validation_path']).read_text())
            result = check_image(timing, validation, pose)
        except Exception as error:
            result = {'accepted': False, 'reasons': ['image 诊断失败'],
                      'error': str(error)}
        cameras[camera_id] = result
        reasons.extend(f'{camera_id}: {reason}'
                       for reason in result['reasons'])
    return {
        'verdict': 'reject' if reasons else 'accept',
        'accepted': not reasons, 'exclude_from_dataset': bool(reasons),
        'reasons': reasons, 'pose': pose, 'cameras': cameras,
        'image_gap_limit_seconds': IMAGE_GAP_LIMIT_SECONDS,
        'minimum_pose_hz': MIN_POSE_HZ,
        'coverage_time_basis': 'first host receipt + video PTS; pose header',
    }


def format_verdict(result, episode_name):
    """Color only the compact verdict and optional rejection reasons."""
    color = '\033[32m' if result['accepted'] else '\033[31m'
    reason = '; '.join(result['reasons'])
    if result['accepted']:
        pose_gaps = result.get('pose', {}).get('gap_count', 0)
        pose_text = '有掉帧迹象' if pose_gaps else '未发现掉帧'
        reason = f'image 未发现掉帧；pose {pose_text}'
    suffix = f' — {reason}' if reason else ''
    return f"{color}{episode_name}: {result['verdict']}{suffix}\033[0m"
