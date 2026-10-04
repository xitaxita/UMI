"""Verify fixed raw-start references and expanded-pose conversion."""

import json
import shutil

import numpy as np

import pytest

from umi_ros2.postprocess import expand_session, localize_session
from umi_ros2.postprocess.episode_transform import quaternion_multiply
from umi_ros2.postprocess.local_pose import localize_poses


def test_start_pose_is_identity_and_initial_axes_remain_fixed():
    """A world Y displacement becomes local X under a 90-degree Z start."""
    half = np.sqrt(0.5)
    start = np.array([0.0, 0.0, half, half])
    turn = np.array([half, 0.0, 0.0, half])
    positions, orientations = localize_poses(
        [[1, 2, 3], [1, 3, 3], [1, 4, 3]],
        [start, quaternion_multiply(start, turn), start], [True] * 3,
        [1, 2, 3], start)
    np.testing.assert_allclose(positions, [[0, 0, 0], [1, 0, 0], [2, 0, 0]],
                               atol=1e-12)
    np.testing.assert_allclose(
        orientations, [[0, 0, 0, 1], turn, [0, 0, 0, 1]], atol=1e-12)


def test_quaternion_sign_is_continuous_through_180_degrees():
    """Keep equivalent quaternion signs when w crosses zero."""
    angles = np.deg2rad([170, 179, 181, 190, 350, 359, 361])
    # Include an unobserved large step; successive valid signs stay equivalent.
    world = np.column_stack([
        np.zeros((len(angles), 2)), np.sin(angles / 2), np.cos(angles / 2)])
    world[1::2] *= -3
    before = world.copy()
    _, orientations = localize_poses(
        np.zeros((len(world), 3)), world, np.ones(len(world), dtype=bool),
        [0, 0, 0], [0, 0, 0, 2])
    np.testing.assert_allclose(np.linalg.norm(orientations, axis=1), 1)
    assert np.all(np.sum(orientations[1:] * orientations[:-1], axis=1) >= 0)
    assert orientations[2, 3] < 0
    np.testing.assert_array_equal(world, before)


def test_pose_gaps_stay_nan_and_do_not_rebase_later_poses():
    """The fixed reference survives an invalid query between valid poses."""
    positions, orientations = localize_poses(
        [[6, 0, 0], [np.nan] * 3, [8, 0, 0]],
        [[0, 0, 0, 2], [np.nan] * 4, [0, 0, 0, -3]],
        [True, False, True], [5, 0, 0], [0, 0, 0, 1])
    np.testing.assert_allclose(positions[[0, 2]], [[1, 0, 0], [3, 0, 0]])
    assert np.isnan(positions[1]).all() and np.isnan(orientations[1]).all()
    np.testing.assert_allclose(orientations[[0, 2]], [[0, 0, 0, 1]] * 2)


@pytest.mark.parametrize('reference_position,reference_orientation', [
    ([np.nan, 0, 0], [0, 0, 0, 1]),
    ([0, 0, 0], [0, 0, 0, 0]),
    ([0, 0, 0], [0, 0, np.inf, 1]),
])
def test_invalid_reference_is_rejected_even_without_valid_queries(
        reference_position, reference_orientation):
    """Never invent a reference when the raw first TCP pose is unusable."""
    with pytest.raises(ValueError, match='reference'):
        localize_poses([[np.nan] * 3], [[np.nan] * 4], [False],
                       reference_position, reference_orientation)


def test_all_invalid_queries_can_be_retained_with_a_valid_reference():
    """Localization does not silently delete episodes with diagnostic gaps."""
    positions, orientations = localize_poses(
        [[np.nan] * 3], [[np.nan] * 4], [False], [1, 2, 3], [0, 0, 0, 1])
    assert np.isnan(positions).all() and np.isnan(orientations).all()


def test_invalid_finite_pose_is_not_repaired():
    """Zero-norm quaternions marked pose-valid are rejected."""
    with pytest.raises(ValueError, match='orientation is invalid'):
        localize_poses([[0, 0, 0]], [[0, 0, 0, 0]], [True],
                       [0, 0, 0], [0, 0, 0, 1])


@pytest.fixture
def expanded_episode(tmp_path, monkeypatch):
    """Run expansion with pre-image pose motion and one invalid image group."""
    session = tmp_path / 'raw_session'
    episode = session / 'episodes' / 'episode_0001'
    pose = episode / 'pose'
    pose.mkdir(parents=True)
    (session / 'session.yaml').write_text('{}')
    (pose / 'metadata.yaml').write_text('{}')
    for camera_id in ('wrist', 'left'):
        camera = episode / 'cameras' / camera_id
        camera.mkdir(parents=True)
        (camera / 'video.mp4').write_bytes(b'raw image bytes')

    def read_camera(item, source_session, camera_id):
        pts = np.array([0, 1, 2] if camera_id == 'wrist' else [0, 2]) / 30
        return pts, 1 + pts, {
            'source_video': str(item / 'cameras' / camera_id / 'video.mp4'),
            'image_field': f'{camera_id}_image',
            'source_frame_count': len(pts),
            'video_to_pose_offset_seconds': -0.01,
        }

    times = np.arange(110) / 90
    positions = np.column_stack([np.ones(len(times)), 2 + times,
                                 np.full(len(times), 3)])
    half = np.sqrt(0.5)
    orientations = np.tile([0, 0, half, half], (len(times), 1))
    monkeypatch.setattr(expand_session, '_read_camera', read_camera)
    monkeypatch.setattr(expand_session, 'read_vive_poses', lambda _: (
        times, positions, orientations))
    output = tmp_path / 'expanded' / 'episodes' / episode.name
    expand_session.expand_episode(episode, output, minimum_valid_ratio=0.6)
    return output


def _arrays(item):
    with np.load(item / 'expanded_frames.npz', allow_pickle=False) as source:
        return {name: source[name].copy() for name in source.files}


def test_file_stage_keeps_pre_image_motion_masks_and_source_bytes(
        expanded_episode, tmp_path):
    """Use raw t=0, and keep valid poses even when their images are invalid."""
    protected = {path: path.read_bytes() for path in tmp_path.rglob('*')
                 if path.is_file()}
    source = _arrays(expanded_episode)
    destination = tmp_path / 'local'
    report = localize_session.localize_item(expanded_episode, destination)
    assert report['reference_pose_time_seconds'] == 0
    assert report['state_action_generated'] is False
    assert report['pose_coordinate_frame'] == 'episode_start_tcp'
    with np.load(destination / 'local_frames.npz', allow_pickle=False) as data:
        assert 'state' not in data and 'action' not in data
        assert str(data['contract']) == 'umi_local_pose'
        assert not data['valid'][3:6].any() and data['pose_valid'].all()
        np.testing.assert_allclose(data['position_xyz'][:, 0],
                                   source['pose_query_time_seconds'])
        np.testing.assert_allclose(data['position_xyz'][:, 1:], 0, atol=1e-12)
        np.testing.assert_allclose(
            data['orientation_xyzw'], [[0, 0, 0, 1]] * 9)
        for name, values in source.items():
            if name not in ('position_xyz', 'orientation_xyzw'):
                np.testing.assert_array_equal(data[name], values)
        np.testing.assert_array_equal(data['world_position_xyz'],
                                      source['position_xyz'])
        np.testing.assert_array_equal(data['world_orientation_xyzw'],
                                      source['orientation_xyzw'])
    rows = (destination / 'local_frames.csv').read_text().splitlines()
    assert len(rows) == 10
    assert {path: path.read_bytes() for path in protected} == protected


def test_file_stage_keeps_invalid_pose_queries(expanded_episode, tmp_path):
    """Keep invalid pose queries at their original sample indices."""
    arrays = _arrays(expanded_episode)
    arrays['pose_valid'][4] = False
    arrays['position_xyz'][4] = np.nan
    arrays['orientation_xyzw'][4] = np.nan
    np.savez_compressed(expanded_episode / 'expanded_frames.npz', **arrays)
    output = tmp_path / 'local'
    localize_session.localize_item(expanded_episode, output)
    with np.load(output / 'local_frames.npz') as data:
        assert len(data['sample_index']) == 9
        assert np.isnan(data['position_xyz'][4]).all()
        assert np.isnan(data['orientation_xyzw'][4]).all()
        np.testing.assert_allclose(np.diff(data['timestamp']), 1 / 90)


@pytest.mark.parametrize('field', [
    'reference_position_xyz', 'reference_orientation_xyzw',
    'reference_pose_time_seconds',
])
def test_missing_reference_has_no_first_image_fallback(
        expanded_episode, tmp_path, field):
    """The new stage never falls back to the first expanded pose."""
    arrays = _arrays(expanded_episode)
    del arrays[field]
    np.savez_compressed(expanded_episode / 'expanded_frames.npz', **arrays)
    output = tmp_path / 'local'
    with pytest.raises(KeyError, match=field):
        localize_session.localize_item(expanded_episode, output)
    assert not output.exists()


@pytest.mark.parametrize('changes', [
    {'schema_version': 2}, {'pose_coordinate_frame': 'episode_start_tcp'},
    {'pose_reference_definition': 'first_image_pose'},
    {'reference_pose_time_seconds': 0.1},
])
def test_wrong_contract_or_reference_is_rejected(
        expanded_episode, tmp_path, changes):
    """Reject ambiguous coordinates, schemas and reference drift."""
    path = expanded_episode / 'expansion.json'
    report = json.loads(path.read_text())
    report.update(changes)
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        localize_session.localize_item(expanded_episode, tmp_path / 'local')


def test_output_paths_cannot_overlap_input_or_raw(expanded_episode, tmp_path):
    """Even overwrite cannot replace raw, input or an unrelated output."""
    outputs = [expanded_episode, expanded_episode / 'local',
               expanded_episode.parent, tmp_path / 'raw_session' / 'local']
    for output in outputs:
        with pytest.raises(ValueError, match='separate'):
            localize_session.localize_item(
                expanded_episode, output, overwrite=True)
    unrelated = tmp_path / 'unrelated'
    unrelated.mkdir()
    (unrelated / 'keep.txt').write_text('keep')
    with pytest.raises(ValueError, match='non-local-pose'):
        localize_session.localize_item(
            expanded_episode, unrelated, overwrite=True)
    assert (unrelated / 'keep.txt').read_text() == 'keep'


def test_cli_session_uses_each_episode_reference(expanded_episode, tmp_path):
    """Two recordings with different raw starts do not share an origin."""
    root = expanded_episode.parent.parent
    second = expanded_episode.with_name('episode_0002')
    shutil.copytree(expanded_episode, second)
    arrays = _arrays(second)
    shift = [10, 20, 30]
    arrays['reference_position_xyz'] += shift
    arrays['position_xyz'] += shift
    np.savez_compressed(second / 'expanded_frames.npz', **arrays)
    report = json.loads((second / 'expansion.json').read_text())
    report['source_episode'] = str(
        tmp_path / 'raw_session' / 'episodes' / second.name)
    (second / 'expansion.json').write_text(json.dumps(report))
    (root / 'expansion_summary.json').write_text(json.dumps({
        'contract': 'umi_frame_expansion', 'schema_version': 1,
        'source_session': report['source_session'], 'episodes': [
            json.loads((expanded_episode / 'expansion.json').read_text()),
            report],
    }))
    output = tmp_path / 'local'
    args = [str(root), '--output', str(output)]
    assert localize_session.main(args) == 0
    assert localize_session.main(args) == 1
    assert localize_session.main(args + ['--overwrite']) == 0
    first_path = (
        output / 'episodes' / expanded_episode.name / 'local_frames.npz')
    second_path = output / 'episodes' / second.name / 'local_frames.npz'
    with np.load(first_path) as first, np.load(second_path) as other:
        np.testing.assert_allclose(
            first['position_xyz'], other['position_xyz'])
        np.testing.assert_allclose(other['reference_position_xyz']
                                   - first['reference_position_xyz'], shift)


def test_cli_preserves_source_rejection(expanded_episode, tmp_path):
    """Coordinate conversion cannot upgrade rejected expansion QC."""
    path = expanded_episode / 'expansion.json'
    report = json.loads(path.read_text())
    report['status'] = 'rejected'
    path.write_text(json.dumps(report))
    output = tmp_path / 'local'
    assert localize_session.main([
        str(expanded_episode), '--output', str(output)]) == 2
    localized = json.loads((output / 'local_pose.json').read_text())
    assert localized['status'] == 'complete'
    assert localized['source_expansion_status'] == 'rejected'


def test_cli_reports_missing_reference_without_output_arrays(
        expanded_episode, tmp_path):
    """Return file errors without fabricating local poses."""
    arrays = _arrays(expanded_episode)
    original = dict(arrays)
    del arrays['reference_position_xyz']
    np.savez_compressed(expanded_episode / 'expanded_frames.npz', **arrays)
    output = tmp_path / 'local'
    assert localize_session.main([
        str(expanded_episode), '--output', str(output)]) == 1
    summary = json.loads((output / 'local_pose_summary.json').read_text())
    assert summary['episodes'][0]['status'] == 'failed'
    assert not (output / 'local_frames.npz').exists()
    np.savez_compressed(expanded_episode / 'expanded_frames.npz', **original)
    assert localize_session.main([
        str(expanded_episode), '--output', str(output), '--overwrite']) == 0


def test_shared_world_transform_does_not_change_relative_poses():
    """A common world-frame rotation and translation cancel out."""
    half = np.sqrt(0.5)
    start = np.array([0, 0, half, half])
    turn = np.array([0, half, 0, half])
    world_rotation = np.array([half, 0, 0, half])
    first_positions, first_orientations = localize_poses(
        [[1, 3, 3]], [quaternion_multiply(start, turn)], [True],
        [1, 2, 3], start)
    # Rx(90 degrees) maps (x,y,z) to (x,-z,y), then translate (10,20,30).
    other_positions, other_orientations = localize_poses(
        [[11, 17, 33]], [quaternion_multiply(
            world_rotation, quaternion_multiply(start, turn))], [True],
        [11, 17, 32], quaternion_multiply(world_rotation, start))
    np.testing.assert_allclose(
        other_positions, first_positions, atol=1e-12)
    np.testing.assert_allclose(
        other_orientations, first_orientations, atol=1e-12)


def test_incompatible_pose_shapes_fail():
    """Reject mismatched sample counts before indexing pose arrays."""
    with pytest.raises(ValueError, match='incompatible shapes'):
        localize_poses([[0, 0, 0]], [[0, 0, 0, 1]], [True, False],
                       [0, 0, 0], [0, 0, 0, 1])
