"""Tests for shared online and offline session organization."""

from pathlib import Path

from umi_ros2.session.layout import (
    create_offline_session,
    create_online_session,
    read_session,
    register_recording,
    update_session,
)


def test_online_session_groups_calibration_and_episodes(tmp_path):
    """Create one indexed session rather than timestamped flat episodes."""
    session = create_online_session(tmp_path)
    assert session.name.startswith('online_session_')
    assert (session / 'calibration').is_dir()
    assert (session / 'episodes').is_dir()
    metadata = read_session(session)
    assert metadata['mode'] == 'online'
    assert metadata['status'] == 'active'
    assert metadata['temporal_calibration']['status'] == 'not_calibrated'

    episode = session / 'episodes' / 'episode_0001'
    episode.mkdir()
    register_recording(session, episode, 'episode')
    update_session(session, status='complete')
    metadata = read_session(session)
    assert metadata['status'] == 'complete'
    assert metadata['recordings'][0]['path'] == 'episodes/episode_0001'


def test_offline_session_reserves_calibration_and_pose_path(tmp_path):
    """Leave pose creation to rosbag while reserving offline metadata."""
    session = tmp_path / 'offline_session_example'
    create_offline_session(session)
    assert (session / 'calibration').is_dir()
    assert not (session / 'pose').exists()
    metadata = read_session(session)
    assert metadata['mode'] == 'offline'
    assert metadata['layout']['pose'] == 'pose'
    assert Path(session / metadata['layout']['calibration']).is_dir()
