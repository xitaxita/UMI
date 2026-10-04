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


def test_replay_uses_wrist_camera_directory(tmp_path):
    """New recording layout resolves the wrist video and timing together."""
    recording = tmp_path / 'episode_0008'
    make_recording(recording)
    wrist = recording / 'cameras' / 'wrist'
    wrist.mkdir(parents=True)
    (recording / 'video.mp4').rename(wrist / 'video.mp4')
    (recording / 'video.timing.json').rename(wrist / 'video.timing.json')

    [item] = resolve_replay_items(recording)
    assert item.video_path == wrist / 'video.mp4'
    assert item.video_start_ns == 2_000_000_000


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


def test_left_calibration_and_deleted_reject_folder_replay(tmp_path):
    """Replay reads left-only input and skips retained rejected folders."""
    session = tmp_path / 'online_session'
    left = session / 'calibration' / 'calibration_001'
    make_recording(left)
    color = left / 'cameras' / 'left'
    color.mkdir(parents=True)
    for suffix in ('.mp4', '.timing.json'):
        (left / f'video{suffix}').rename(color / f'video{suffix}')
    [item] = resolve_replay_items(left)
    assert item.video_path == color / 'video.mp4'
    rejected = session / 'calibration' / 'calibration_002'
    rejected.mkdir()
    (session / 'session.yaml').write_text(yaml.safe_dump({
        'schema_version': 2, 'recordings': [
            {'kind': 'calibration', 'path': 'calibration/calibration_002',
             'status': 'rejected'}]}))
    assert [item.path for item in resolve_replay_items(session)] == [left]


def test_aligned_episode_resolves_both_accepted_camera_offsets(tmp_path):
    """Keep two source anchors and independent offsets for one pose bag."""
    session = tmp_path / 'online_session'
    episode = session / 'episodes' / 'episode_0001'
    make_recording(episode)
    for camera_id, anchor in [('wrist', 2_000_000_000),
                              ('left', 2_060_000_000)]:
        folder = episode / 'cameras' / camera_id
        folder.mkdir(parents=True)
        (folder / 'video.mp4').touch()
        (folder / 'video.timing.json').write_text(json.dumps({
            'camera_id': camera_id,
            'first_receive_unix_ns': anchor,
        }), encoding='utf-8')
    calibrations = {}
    for camera_id, offset in [('wrist', -0.093), ('left', -0.010)]:
        result = session / 'calibration' / camera_id / 'time_offset.json'
        result.parent.mkdir(parents=True)
        result.write_text(json.dumps({
            'accepted': True,
            'video_to_pose_offset_seconds': offset,
        }), encoding='utf-8')
        calibrations[camera_id] = {
            'status': 'accepted',
            'result': str(result.relative_to(session)),
        }
    (session / 'session.yaml').write_text(yaml.safe_dump({
        'schema_version': 2,
        'temporal_calibrations': calibrations,
        'image_streams': [
            {'camera_id': 'wrist',
             'preview_topic': '/action4/image_preview'},
            {'camera_id': 'left',
             'preview_topic': '/realsense/left/image_preview'},
        ],
    }), encoding='utf-8')

    [item] = resolve_replay_items(episode, use_calibration=True)
    videos = {video.camera_id: video for video in item.videos}
    assert set(videos) == {'wrist', 'left'}
    assert videos['wrist'].start_ns == 2_000_000_000
    assert videos['left'].start_ns == 2_060_000_000
    assert videos['wrist'].offset_seconds == -0.093
    assert videos['left'].offset_seconds == -0.010
    assert videos['left'].preview_topic == '/realsense/left/image_preview'

    calibrations['left']['status'] = 'rejected'
    (session / 'session.yaml').write_text(yaml.safe_dump({
        'schema_version': 2,
        'temporal_calibrations': calibrations,
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='no accepted left calibration'):
        resolve_replay_items(episode, use_calibration=True)
