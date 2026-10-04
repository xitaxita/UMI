"""Tests for per-video-frame Vive pose interpolation."""

import json

import numpy as np

import pytest

from umi_ros2.postprocess.align_session import (
    align,
    align_episode,
    load_offset,
    resolve_episodes,
)
from umi_ros2.postprocess.alignment import (
    interpolate_poses,
    prepare_pose_samples,
    slerp,
)


def test_interpolates_position_and_orientation():
    """Use linear XYZ interpolation and shortest-path quaternion SLERP."""
    times = np.array([0.0, 1.0])
    positions = np.array([[0.0, 0.0, 0.0], [2.0, 4.0, 6.0]])
    orientations = np.array([
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
    ])
    result = interpolate_poses(
        np.array([0.5]), times, positions, orientations,
        maximum_gap_seconds=2.0)
    assert result.valid.tolist() == [True]
    assert result.positions[0] == pytest.approx([1.0, 2.0, 3.0])
    assert result.orientations[0] == pytest.approx(
        [0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)])


def test_rejects_extrapolation_and_large_pose_gaps():
    """Mark unavailable frame poses invalid instead of inventing values."""
    result = interpolate_poses(
        np.array([-0.1, 0.5, 1.1]),
        np.array([0.0, 1.0]),
        np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]),
        np.array([[0.0, 0.0, 0.0, 1.0]] * 2),
        maximum_gap_seconds=0.2)
    assert result.valid.tolist() == [False, False, False]
    assert np.isnan(result.positions).all()


def test_pose_preparation_keeps_last_duplicate_and_normalizes():
    """Make recorded duplicate timestamps deterministic."""
    times, positions, orientations = prepare_pose_samples(
        [1.0, 1.0, 2.0],
        [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
        [[0.0, 0.0, 0.0, 2.0]] * 3)
    assert times.tolist() == [1.0, 2.0]
    assert positions[:, 0].tolist() == [2.0, 3.0]
    assert orientations[:, 3].tolist() == [1.0, 1.0]


def test_slerp_handles_equivalent_opposite_quaternion_signs():
    """Avoid a long rotation when quaternion signs differ."""
    value = slerp(
        np.array([0.0, 0.0, 0.0, 1.0]),
        np.array([0.0, 0.0, 0.0, -1.0]), 0.5)
    assert value == pytest.approx([0.0, 0.0, 0.0, 1.0])


def test_resolves_only_ordinary_session_episodes(tmp_path):
    """Exclude calibration recordings from dataset episode alignment."""
    session = tmp_path / 'online_session_example'
    (session / 'episodes' / 'episode_0010').mkdir(parents=True)
    (session / 'episodes' / 'episode_0002').mkdir()
    (session / 'calibration' / 'calibration_001').mkdir(parents=True)
    (session / 'session.yaml').write_text('mode: online\n', encoding='utf-8')
    _, episodes = resolve_episodes(session)
    assert [episode.name for episode in episodes] == [
        'episode_0002', 'episode_0010']


def test_align_reads_wrist_camera_directory(tmp_path, monkeypatch):
    """Alignment resolves the new wrist MP4 and its own timing file."""
    episode = tmp_path / 'episode_0001'
    wrist = episode / 'cameras' / 'wrist'
    wrist.mkdir(parents=True)
    video = wrist / 'video.mp4'
    video.touch()
    (wrist / 'video.timing.json').write_text(json.dumps({
        'first_receive_unix_ns': 1_000_000_000,
    }))
    pose = episode / 'pose'
    pose.mkdir()
    (pose / 'metadata.yaml').touch()
    monkeypatch.setattr(
        'umi_ros2.postprocess.align_session.video_frame_times',
        lambda path: np.array([0.0, 0.05]))
    monkeypatch.setattr(
        'umi_ros2.postprocess.align_session.read_vive_poses',
        lambda path: (
            np.array([0.95, 1.0, 1.05, 1.1]),
            np.zeros((4, 3)),
            np.tile([0.0, 0.0, 0.0, 1.0], (4, 1)),
        ))

    report = align_episode(
        episode, tmp_path / 'output', 0.0, 'test', 0.1, 1.0)
    assert report['status'] == 'accepted'
    assert report['source_video'] == str(video)
    assert report['pose_reference_definition'] == (
        'first_recorded_tcp_pose_after_start')
    with np.load(tmp_path / 'output' / 'aligned_frames.npz') as arrays:
        assert float(arrays['reference_pose_time_seconds']) == 0.95
        assert float(arrays['pose_query_time_seconds'][0]) == 1.0
    assert resolve_episodes(episode)[1] == [episode]


def test_loads_only_accepted_calibration_result(tmp_path):
    """Require both session and referenced result acceptance."""
    session = tmp_path / 'online_session_example'
    result = session / 'calibration/calibration_001/time_offset.json'
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({
        'accepted': True,
        'video_to_pose_offset_seconds': 0.123,
    }), encoding='utf-8')
    (session / 'session.yaml').write_text(
        'temporal_calibration:\n'
        '  status: accepted\n'
        '  result: calibration/calibration_001/time_offset.json\n',
        encoding='utf-8')
    offset, source = load_offset(session)
    assert offset == pytest.approx(0.123)
    assert source == str(result)


def test_session_alignment_records_episode_failure_and_continues(
        tmp_path, monkeypatch):
    """Write a complete summary even when one episode cannot be aligned."""
    session = tmp_path / 'online_session_example'
    first = session / 'episodes' / 'episode_0001'
    second = session / 'episodes' / 'episode_0002'
    first.mkdir(parents=True)
    second.mkdir()
    (session / 'session.yaml').write_text('mode: online\n', encoding='utf-8')
    output = tmp_path / 'processed'
    calls = []

    def fake_align(episode, destination, *args, **kwargs):
        calls.append(episode.name)
        if episode == first:
            raise ValueError('bad pose bag')
        destination.mkdir(parents=True)
        return {
            'status': 'accepted', 'source_episode': str(episode),
            'valid_frame_count': 10, 'frame_count': 10,
        }

    monkeypatch.setattr(
        'umi_ros2.postprocess.align_session.align_episode', fake_align)
    arguments = type('Arguments', (), {
        'input_path': str(session),
        'output': str(output),
        'offset_seconds': 0.0,
        'maximum_pose_gap': 0.1,
        'minimum_valid_ratio': 0.95,
        'overwrite': False,
    })()
    assert align(arguments) == 1
    assert calls == ['episode_0001', 'episode_0002']
    summary = json.loads(
        (output / 'alignment_summary.json').read_text(encoding='utf-8'))
    assert [item['status'] for item in summary['episodes']] == [
        'failed', 'accepted']
