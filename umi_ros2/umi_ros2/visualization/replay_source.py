"""Resolve and time separated UMI session replay inputs."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from umi_ros2.common.ordering import natural_key
from umi_ros2.session.layout import (
    read_session, resolve_calibration_camera, resolve_video_path)

import yaml


@dataclass(frozen=True)
class ReplayVideo:
    """One camera's video, clock anchor and preview destination."""

    camera_id: str
    video_path: Path
    start_ns: int
    offset_seconds: float
    preview_topic: str


@dataclass(frozen=True)
class ReplayItem:
    """One video plus pose recording selected for replay."""

    path: Path
    video_path: Path
    pose_path: Path
    video_start_ns: int
    pose_start_ns: int
    videos: tuple = ()


def _session_metadata(path):
    session = path.parent.parent
    if (session / 'session.yaml').is_file():
        return session, read_session(session)
    return None, {}


def _accepted_offset(session, metadata, camera_id):
    calibration = metadata.get('temporal_calibrations', {}).get(camera_id)
    if calibration is None and camera_id == 'wrist':
        calibration = metadata.get('temporal_calibration')
    if (not session or not calibration
            or calibration.get('status') != 'accepted'):
        raise ValueError(
            f'no accepted {camera_id} calibration for aligned replay')
    result_path = session / calibration['result']
    result = json.loads(result_path.read_text(encoding='utf-8'))
    offset = float(result['video_to_pose_offset_seconds'])
    if not result.get('accepted') or not math.isfinite(offset):
        raise ValueError(f'invalid {camera_id} calibration for aligned replay')
    return offset


def _recording(path, use_calibration=False):
    camera_root = path / 'cameras'
    camera_videos = (sorted(camera_root.glob('*/video.mp4'))
                     if camera_root.is_dir() else [])
    if not camera_videos:
        camera_videos = [resolve_video_path(
            path, resolve_calibration_camera(path))]
    pose = path / 'pose'
    pose_metadata = pose / 'metadata.yaml'
    missing = [str(item) for item in (pose_metadata, *camera_videos)
               if not item.is_file()]
    for video in camera_videos:
        timing_path = video.with_suffix('.timing.json')
        if not timing_path.is_file():
            missing.append(str(timing_path))
    if missing:
        raise ValueError(
            f'incomplete replay recording {path}: missing {", ".join(missing)}'
        )
    session, session_data = _session_metadata(path)
    topics = {item['camera_id']: item['preview_topic']
              for item in session_data.get('image_streams', [])
              if 'camera_id' in item and 'preview_topic' in item}
    videos = []
    for video in camera_videos:
        timing = json.loads(video.with_suffix('.timing.json').read_text(
            encoding='utf-8'))
        camera_id = timing.get('camera_id', video.parent.name)
        if camera_id == path.name:
            camera_id = 'wrist'  # historical root-level video
        offset = (_accepted_offset(session, session_data, camera_id)
                  if use_calibration else 0.0)
        topic = topics.get(camera_id, {
            'wrist': '/action4/image_preview',
            'left': '/realsense/left/image_preview',
        }.get(camera_id, f'/camera/{camera_id}/image_preview'))
        videos.append(ReplayVideo(
            camera_id, video, int(timing['first_receive_unix_ns']),
            offset, topic))
    primary = next((item for item in videos if item.camera_id == 'wrist'),
                   videos[0])
    metadata = yaml.safe_load(pose_metadata.read_text(encoding='utf-8'))
    pose_start_ns = int(
        metadata['rosbag2_bagfile_information']['starting_time'][
            'nanoseconds_since_epoch'
        ]
    )
    return ReplayItem(
        path=path,
        video_path=primary.video_path,
        pose_path=pose,
        video_start_ns=primary.start_ns,
        pose_start_ns=pose_start_ns,
        videos=tuple(videos),
    )


def resolve_replay_items(input_path, use_calibration=False):
    """Resolve one recording or an ordered online session."""
    path = Path(input_path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f'replay input is not a directory: {path}')
    if ((path / 'pose').is_dir() or (path / 'video.mp4').is_file()
            or (path / 'cameras').is_dir()):
        return [_recording(path, use_calibration)]
    if not (path / 'session.yaml').is_file():
        raise ValueError(
            'replay input must be a session root or calibration/episode '
            f'directory: {path}'
        )
    candidates = []
    metadata = read_session(path)
    rejected = {item.get('path') for item in metadata.get('recordings', [])
                if item.get('kind') == 'calibration'
                and item.get('status') == 'rejected'}
    for group, prefix in (
        ('calibration', 'calibration_'),
        ('episodes', 'episode_'),
    ):
        group_path = path / group
        if not group_path.is_dir():
            continue
        children = [
            child for child in group_path.iterdir()
            if child.is_dir() and child.name.startswith(prefix)
            and str(child.relative_to(path)) not in rejected
        ]
        candidates.extend(sorted(children, key=natural_key))
    if not candidates:
        raise ValueError(f'session contains no replay recordings: {path}')
    return [_recording(candidate, use_calibration) for candidate in candidates]


def relative_start_seconds(item):
    """Return video and pose offsets from their common recorded start."""
    common_start = min(item.video_start_ns, item.pose_start_ns)
    return (
        (item.video_start_ns - common_start) / 1_000_000_000,
        (item.pose_start_ns - common_start) / 1_000_000_000,
    )
