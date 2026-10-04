"""Verify tripled camera images, real clock pairing and 90 Hz pose queries."""

import json

import numpy as np

import pytest

from umi_ros2.postprocess import expand_session
from umi_ros2.postprocess.frame_expansion import expand_frames

import yaml


def _poses(start=0.0, stop=0.25):
    times = np.arange(start, stop, 1 / 90)
    positions = np.column_stack([times, 2 * times, -times])
    angles = times * np.pi
    orientations = np.column_stack([
        np.zeros(len(times)), np.zeros(len(times)),
        np.sin(angles / 2), np.cos(angles / 2),
    ])
    return times, positions, orientations


def test_three_copies_have_different_poses_on_a_fixed_clock():
    """One 30 Hz image group accompanies three distinct 90 Hz queries."""
    images = np.arange(3) / 30
    result = expand_frames({'wrist': images, 'left': images}, *_poses())
    assert result.valid.tolist() == [True] * 9
    for indices in result.frame_indices.values():
        assert indices.tolist() == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    np.testing.assert_allclose(result.timestamp, np.arange(9) / 90)
    np.testing.assert_allclose(result.poses.positions[:, 0], result.timestamp)
    np.testing.assert_allclose(
        result.poses.orientations[:, 2], np.sin(result.timestamp * np.pi / 2))
    assert result.repeat_index.tolist() == [0, 1, 2] * 3


def test_independent_camera_phase_uses_corrected_times():
    """Nonidentical camera clocks pair by time with a reported signed error."""
    images = np.arange(3) / 30
    result = expand_frames(
        {'wrist': images, 'left': images + 0.008}, *_poses())
    assert result.valid.all()
    np.testing.assert_allclose(result.pairing_deltas['left'], 0.008)
    np.testing.assert_allclose(result.image_times['left'],
                               np.repeat(images + 0.008, 3))


def test_missing_image_invalidates_three_samples_without_compressing_time():
    """An absent 30 Hz image leaves a visible three-tick hole."""
    result = expand_frames({
        'wrist': np.arange(4) / 30,
        'left': np.array([0.0, 1 / 30, 3 / 30]),
    }, *_poses())
    assert result.valid.tolist() == [True] * 6 + [False] * 3 + [True] * 3
    np.testing.assert_allclose(np.diff(result.timestamp), 1 / 90)
    assert result.group_index[9] == 3


def test_source_image_cannot_be_accepted_in_two_groups():
    """A broad diagnostic tolerance still never makes six valid copies."""
    result = expand_frames({
        'wrist': np.arange(4) / 30,
        'left': np.array([0.0, 0.09]),
    }, *_poses(), maximum_image_delta_seconds=0.05)
    indices, counts = np.unique(
        result.frame_indices['left'][result.valid], return_counts=True)
    assert indices.tolist() == [0, 1]
    assert counts.tolist() == [3, 3]


def test_equidistant_images_choose_the_earlier_frame():
    """An exactly tied pairing is deterministic on the corrected clock."""
    result = expand_frames({
        'wrist': np.arange(3) / 30,
        'left': np.array([-0.01, 0.01, 1 / 30 + 0.01, 2 / 30 + 0.01]),
    }, *_poses())
    assert result.valid.all()
    assert result.frame_indices['left'][:3].tolist() == [0, 0, 0]


def test_disjoint_cameras_have_no_expandable_groups():
    """A camera starting after the other ends cannot be clamped to an edge."""
    with pytest.raises(ValueError, match='no complete'):
        expand_frames({
            'wrist': np.arange(3) / 30,
            'left': 1.0 + np.arange(3) / 30,
        }, *_poses())


def test_pose_gap_invalidates_whole_groups_and_keeps_nan_queries():
    """Large pose holes are not interpolated over or hidden by image reuse."""
    times = np.array([0.0, 1 / 90, 2 / 90, 0.2, 0.21, 0.23])
    result = expand_frames(
        {'wrist': np.arange(7) / 30, 'left': np.arange(7) / 30},
        times, np.column_stack([times] * 3),
        np.tile([0.0, 0.0, 0.0, 1.0], (len(times), 1)))
    assert not result.valid[3:18].any()
    assert np.isnan(result.poses.positions[3:18]).all()
    assert np.all(result.valid.reshape(-1, 3) == result.valid[::3, None])


def test_pose_tail_crops_complete_groups_without_extrapolation():
    """A short pose tail cannot supply the next image's full three queries."""
    result = expand_frames(
        {'wrist': np.arange(3) / 30, 'left': np.arange(3) / 30},
        *_poses(stop=0.045))
    assert len(result.timestamp) == 3
    assert result.valid.all()


def test_epoch_times_and_opposite_quaternion_signs_remain_stable():
    """Unix-scale stamps retain a 90 Hz relative clock and continuous signs."""
    epoch = 1_790_811_000.0
    times, positions, orientations = _poses()
    orientations[1::2] *= -1
    images = epoch + np.arange(4) / 30
    result = expand_frames(
        {'wrist': images, 'left': images},
        epoch + times, positions, orientations)
    assert result.valid.all()
    np.testing.assert_allclose(np.diff(result.timestamp), 1 / 90, atol=1e-14)
    np.testing.assert_allclose(
        result.poses.positions[:, 0], result.timestamp, atol=4e-7)
    np.testing.assert_allclose(
        np.linalg.norm(result.poses.orientations, axis=1), 1.0)
    assert np.all(np.sum(result.poses.orientations[1:]
                         * result.poses.orientations[:-1], axis=1) >= 0)


@pytest.mark.parametrize('bad_times', [[], [0, 0], [0, np.nan], [1, 0]])
def test_bad_camera_timestamps_are_rejected(bad_times):
    """A missing or corrupt image clock cannot become nominal 90 Hz data."""
    with pytest.raises(ValueError, match='left needs'):
        expand_frames({'wrist': [0, 1 / 30], 'left': bad_times}, *_poses())


@pytest.mark.parametrize('parameter', [
    {'maximum_image_delta_seconds': float('nan')},
    {'maximum_image_delta_seconds': 0.0},
    {'maximum_pose_gap_seconds': float('inf')},
])
def test_nonfinite_or_zero_limits_fail(parameter):
    """Pairing and interpolation limits must remain finite and positive."""
    with pytest.raises(ValueError, match='finite and greater'):
        expand_frames({'wrist': [0], 'left': [0]}, *_poses(), **parameter)


@pytest.fixture
def calibrated_episode(tmp_path, monkeypatch):
    """Represent a raw episode with independent camera clocks and offsets."""
    session = tmp_path / 'online_session_test'
    episode = session / 'episodes' / 'episode_0001'
    pose = episode / 'pose'
    pose.mkdir(parents=True)
    (pose / 'metadata.yaml').write_text('{}', encoding='utf-8')
    calibration = {}
    for camera_id, anchor, offset in (
        ('wrist', 1_100_000_000, -0.1), ('left', 900_000_000, 0.1),
    ):
        camera = episode / 'cameras' / camera_id
        camera.mkdir(parents=True)
        (camera / 'video.mp4').write_bytes(b'unchanged raw image bytes')
        (camera / 'video.timing.json').write_text(json.dumps({
            'camera_id': camera_id, 'image_field': f'{camera_id}_image',
            'first_receive_unix_ns': anchor,
        }), encoding='utf-8')
        result = session / 'calibration' / camera_id / 'time_offset.json'
        result.parent.mkdir(parents=True)
        result.write_text(json.dumps({
            'accepted': True, 'camera_id': camera_id,
            'video_to_pose_offset_seconds': offset,
        }), encoding='utf-8')
        calibration[camera_id] = {
            'status': 'accepted', 'result': str(result.relative_to(session)),
        }
    (session / 'session.yaml').write_text(yaml.safe_dump({
        'schema_version': 2, 'mode': 'online', 'task': 'test task',
        'status': 'complete', 'temporal_calibrations': calibration,
        'temporal_calibration': calibration['wrist'],
    }), encoding='utf-8')
    monkeypatch.setattr(expand_session, 'video_frame_times',
                        lambda path: np.arange(3) / 30)
    monkeypatch.setattr(expand_session, 'read_vive_poses',
                        lambda path: _poses(start=0.5, stop=1.2))
    return episode


def test_episode_contract_preserves_offsets_raw_bytes_and_reference(
        calibrated_episode, tmp_path):
    """Keep raw bytes while writing tripled frames and world poses."""
    session = calibrated_episode.parent.parent
    before = {path: path.read_bytes() for path in session.rglob('*')
              if path.is_file()}
    output = tmp_path / 'expanded'
    report = expand_session.expand_episode(calibrated_episode, output)
    assert report['status'] == 'accepted'
    assert report['sample_count'] == 9
    assert report['reference_pose_time_seconds'] == 0.5
    assert report['pose_coordinate_frame'] == 'raw_world'
    assert report['images_materialized'] is False
    assert report['cameras']['wrist']['video_to_pose_offset_seconds'] == -0.1
    assert report['cameras']['left']['video_to_pose_offset_seconds'] == 0.1
    with np.load(output / 'expanded_frames.npz', allow_pickle=False) as values:
        assert int(values['fps']) == 90
        assert int(values['contract_version']) == 1
        assert values['wrist_frame_index'].tolist() == [
            0, 0, 0, 1, 1, 1, 2, 2, 2]
        np.testing.assert_allclose(values['left_pairing_delta_seconds'], 0.0)
        np.testing.assert_allclose(values['position_xyz'][0], [1.0, 2.0, -1.0])
        np.testing.assert_allclose(values['reference_position_xyz'],
                                   [0.5, 1.0, -0.5])
        assert 'state' not in values and 'action' not in values
    assert len((output / 'expanded_frames.csv').read_text().splitlines()) == 10
    assert {path: path.read_bytes() for path in before} == before


def test_left_calibration_cannot_inherit_wrist(calibrated_episode):
    """Dual-camera expansion requires an independent accepted left result."""
    session = calibrated_episode.parent.parent
    path = session / 'session.yaml'
    metadata = yaml.safe_load(path.read_text())
    del metadata['temporal_calibrations']['left']
    path.write_text(yaml.safe_dump(metadata))
    with pytest.raises(ValueError, match='no accepted left'):
        expand_session.load_camera_offset(session, 'left')


@pytest.mark.parametrize('change', [
    {'accepted': False}, {'camera_id': 'wrist'},
    {'video_to_pose_offset_seconds': float('nan')},
])
def test_bad_calibration_results_are_rejected(calibrated_episode, change):
    """Index acceptance alone cannot make a corrupt result authoritative."""
    session = calibrated_episode.parent.parent
    path = session / 'calibration' / 'left' / 'time_offset.json'
    result = json.loads(path.read_text())
    result.update(change)
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match='left calibration'):
        expand_session.load_camera_offset(session, 'left')


def test_overwrite_refuses_unrelated_output(calibrated_episode, tmp_path):
    """The explicit overwrite option cannot replace another stage's folder."""
    output = tmp_path / 'unrelated'
    output.mkdir()
    marker = output / 'keep.txt'
    marker.write_text('keep existing user output')
    with pytest.raises(ValueError, match='non-expansion'):
        expand_session.expand_episode(
            calibrated_episode, output, overwrite=True)
    assert marker.read_text() == 'keep existing user output'


def test_cli_runs_and_overwrites_only_its_own_intermediates(
        calibrated_episode, tmp_path):
    """The standalone entry point has a reusable, separate session root."""
    output = tmp_path / 'expanded'
    args = [str(calibrated_episode.parent.parent), '--output', str(output)]
    assert expand_session.main(args) == 0
    assert expand_session.main(args) == 1
    assert expand_session.main(args + ['--overwrite']) == 0
    report = json.loads((output / 'expansion_summary.json').read_text())
    assert report['fps'] == 90 and report['episode_count'] == 1
    assert report['episodes'][0]['status'] == 'accepted'
    with pytest.raises(ValueError, match='separate from raw'):
        expand_session.expand_episode(
            calibrated_episode, calibrated_episode / 'expanded')


def test_cli_records_failure_when_one_video_is_missing(
        calibrated_episode, tmp_path):
    """Missing image inputs produce a failed summary and no sample arrays."""
    (calibrated_episode / 'cameras' / 'left' / 'video.mp4').unlink()
    output = tmp_path / 'expanded'
    assert expand_session.main([
        str(calibrated_episode), '--output', str(output)]) == 1
    report = json.loads((output / 'expansion_summary.json').read_text())
    assert report['episodes'][0]['status'] == 'failed'
    assert 'left input is missing' in report['episodes'][0]['error']
    assert not list(output.rglob('expanded_frames.npz'))
