"""Tests for online session organization."""

import pytest

from umi_ros2.session.layout import (
    SCHEMA_VERSION,
    create_online_session,
    read_session,
    register_recording,
    session_task,
    set_task,
    update_session,
)
from umi_ros2.session.set_session_task import main as set_session_task_main

import yaml


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


def test_v2_session_records_task_and_recording_snapshot(tmp_path):
    """D-021: one task per session, snapshotted into each recording."""
    session = create_online_session(tmp_path, '  pick up the red cube  ')
    metadata = read_session(session)
    assert metadata['schema_version'] == SCHEMA_VERSION == 2
    assert metadata['task'] == 'pick up the red cube'
    assert list(metadata)[:3] == ['schema_version', 'session_id', 'task']
    episode = session / 'episodes' / 'episode_0001'
    episode.mkdir()
    register_recording(session, episode, 'episode')
    assert read_session(session)['recordings'][0]['task'] == (
        'pick up the red cube')


def test_session_task_may_start_empty(tmp_path):
    """Launching without task:= creates a v2 session with an empty task."""
    session = create_online_session(tmp_path)
    assert read_session(session)['task'] == ''
    assert session_task(read_session(session)) == ''


def _write_v1_session(path):
    path.mkdir()
    (path / 'session.yaml').write_text(yaml.safe_dump({
        'schema_version': 1,
        'session_id': path.name,
        'mode': 'online',
        'status': 'complete',
        'recordings': [{'kind': 'episode', 'path': 'episodes/episode_0001'}],
    }, sort_keys=False), encoding='utf-8')
    return path


def test_v1_session_is_readable_with_empty_task(tmp_path):
    """Version 1 metadata has no task and is treated as empty."""
    session = _write_v1_session(tmp_path / 'online_session_v1')
    metadata = read_session(session)
    assert metadata['schema_version'] == 1
    assert session_task(metadata) == ''


def test_unknown_schema_version_is_rejected(tmp_path):
    """Do not silently misread metadata from a future layout."""
    session = tmp_path / 'future'
    session.mkdir()
    (session / 'session.yaml').write_text(
        'schema_version: 99\n', encoding='utf-8')
    with pytest.raises(ValueError, match='schema_version'):
        read_session(session)


def test_set_task_upgrades_v1_and_keeps_snapshots(tmp_path):
    """Changing the task never rewrites recording snapshots."""
    session = _write_v1_session(tmp_path / 'online_session_v1')
    set_task(session, 'fold the towel')
    metadata = read_session(session)
    assert metadata['schema_version'] == 2
    assert metadata['task'] == 'fold the towel'
    assert list(metadata)[:3] == ['schema_version', 'session_id', 'task']
    assert 'task_updated_at' in metadata
    assert 'task' not in metadata['recordings'][0]

    v2 = create_online_session(tmp_path, 'old task')
    episode = v2 / 'episodes' / 'episode_0001'
    episode.mkdir()
    register_recording(v2, episode, 'episode')
    set_task(v2, 'new task')
    metadata = read_session(v2)
    assert metadata['task'] == 'new task'
    assert metadata['recordings'][0]['task'] == 'old task'


def test_set_session_task_cli(tmp_path, capsys):
    """The CLI refuses active sessions unless forced and only edits YAML."""
    session = create_online_session(tmp_path)
    marker = session / 'episodes' / 'video.mp4'
    marker.write_bytes(b'raw')
    assert set_session_task_main([str(session), 'wipe table']) == 1
    assert 'still active' in capsys.readouterr().err
    assert read_session(session)['task'] == ''

    assert set_session_task_main(
        [str(session), 'wipe table', '--force']) == 0
    assert read_session(session)['task'] == 'wipe table'
    assert marker.read_bytes() == b'raw'

    update_session(session, status='complete')
    assert set_session_task_main([str(session), '']) == 0
    assert 'task is empty' in capsys.readouterr().err
    assert read_session(session)['task'] == ''
    assert set_session_task_main([str(tmp_path / 'missing'), 'x']) == 1
