"""Resolve and time separated UMI session replay inputs."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ReplayItem:
    """One video plus pose recording selected for replay."""

    path: Path
    video_path: Path
    pose_path: Path
    video_start_ns: int
    pose_start_ns: int


def _natural_key(path):
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r'(\d+)', path.name)
    ]


def _recording(path):
    video = path / 'video.mp4'
    timing_path = path / 'video.timing.json'
    pose = path / 'pose'
    pose_metadata = pose / 'metadata.yaml'
    missing = [
        item.name for item in (video, timing_path, pose_metadata)
        if not item.is_file()
    ]
    if missing:
        raise ValueError(
            f'incomplete replay recording {path}: missing {", ".join(missing)}'
        )
    timing = json.loads(timing_path.read_text(encoding='utf-8'))
    video_start_ns = int(timing['first_receive_unix_ns'])
    metadata = yaml.safe_load(pose_metadata.read_text(encoding='utf-8'))
    pose_start_ns = int(
        metadata['rosbag2_bagfile_information']['starting_time'][
            'nanoseconds_since_epoch'
        ]
    )
    return ReplayItem(
        path=path,
        video_path=video,
        pose_path=pose,
        video_start_ns=video_start_ns,
        pose_start_ns=pose_start_ns,
    )


def resolve_replay_items(input_path):
    """Resolve one recording or an ordered online session."""
    path = Path(input_path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f'replay input is not a directory: {path}')
    if (path / 'video.mp4').is_file() or (path / 'pose').is_dir():
        return [_recording(path)]
    if not (path / 'session.yaml').is_file():
        raise ValueError(
            'replay input must be a session root or calibration/episode '
            f'directory: {path}'
        )
    candidates = []
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
        ]
        candidates.extend(sorted(children, key=_natural_key))
    if not candidates:
        raise ValueError(f'session contains no replay recordings: {path}')
    return [_recording(candidate) for candidate in candidates]


def relative_start_seconds(item):
    """Return video and pose offsets from their common recorded start."""
    common_start = min(item.video_start_ns, item.pose_start_ns)
    return (
        (item.video_start_ns - common_start) / 1_000_000_000,
        (item.pose_start_ns - common_start) / 1_000_000_000,
    )
