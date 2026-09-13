"""Tests for session and recording replay input detection."""

import json

import pytest

from umi_ros2.visualization.replay_source import (
    relative_start_seconds,
    resolve_replay_items,
)

import yaml


def make_recording(path, video_start=2_000_000_000,
                   pose_start=1_500_000_000):
    """Create only the metadata needed by the replay resolver."""
    path.mkdir(parents=True)
    (path / 'video.mp4').touch()
    (path / 'video.timing.json').write_text(json.dumps({
        'first_receive_unix_ns': video_start,
    }), encoding='utf-8')
    pose = path / 'pose'
    pose.mkdir()
    (pose / 'metadata.yaml').write_text(yaml.safe_dump({
        'rosbag2_bagfile_information': {
            'starting_time': {
                'nanoseconds_since_epoch': pose_start,
            },
        },
    }), encoding='utf-8')


def test_recording_path_replays_directly(tmp_path):
    """Treat a concrete episode as one direct replay item."""
    recording = tmp_path / 'episode_0007'
    make_recording(recording)
    items = resolve_replay_items(recording)
    assert [item.path for item in items] == [recording]
    assert relative_start_seconds(items[0]) == (0.5, 0.0)


def test_session_orders_calibrations_before_natural_sorted_episodes(tmp_path):
    """Play every calibration before naturally sorted ordinary episodes."""
    session = tmp_path / 'online_session_example'
    session.mkdir()
    (session / 'session.yaml').write_text('mode: online\n', encoding='utf-8')
    make_recording(session / 'episodes' / 'episode_0010')
    make_recording(session / 'calibration' / 'calibration_002')
    make_recording(session / 'episodes' / 'episode_0002')
    make_recording(session / 'calibration' / 'calibration_001')
    items = resolve_replay_items(session)
    assert [item.path.name for item in items] == [
        'calibration_001', 'calibration_002',
        'episode_0002', 'episode_0010',
    ]


def test_incomplete_recording_fails_clearly(tmp_path):
    """Reject directories that cannot provide both video and pose metadata."""
    recording = tmp_path / 'episode_0001'
    recording.mkdir()
    (recording / 'video.mp4').touch()
    with pytest.raises(ValueError, match='incomplete replay recording'):
        resolve_replay_items(recording)
