"""D-021 multi-session dataset build."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import pytest

from umi_ros2.postprocess import build_dataset, export_hdf5, export_lerobot
from umi_ros2.postprocess.dataset_plan import (
    read_plan,
    sources_for_root,
    write_plan,
)
from umi_ros2.session.layout import (
    create_online_session,
    read_session,
    update_session,
)


FRAME_SHAPES = {}
PTS_STEPS = {}


class _Capture:
    def __init__(self, path):
        self.path = str(path)
        self.index = 0

    def read(self):
        if self.index >= 3:
            return False, None
        self.index += 1
        shape = FRAME_SHAPES.get(self.path, (4, 6, 3))
        return True, np.zeros(shape, dtype=np.uint8)

    def release(self):
        pass


class _FakeCv2:
    VideoCapture = _Capture
    IMWRITE_JPEG_QUALITY = 1
    COLOR_BGR2RGB = 4

    @staticmethod
    def imencode(extension, frame, options):
        return True, np.array([255, 216, 255, 217], dtype=np.uint8)

    @staticmethod
    def cvtColor(frame, code):
        return frame


def _fake_align(args):
    """Write the aligned contract the real transform stage consumes."""
    session = Path(args.input_path)
    output = Path(args.output)
    metadata = read_session(session)
    offset = metadata['temporal_calibration'].get(
        'video_to_pose_offset_seconds', -0.095)
    reports = []
    for episode in sorted((session / 'episodes').iterdir()):
        destination = output / 'episodes' / episode.name
        destination.mkdir(parents=True)
        step = PTS_STEPS.get(str(episode), 1 / 30)
        np.savez_compressed(
            destination / 'aligned_frames.npz',
            frame_index=np.arange(3),
            video_pts_seconds=np.array([0.0, step, 2 * step]),
            video_time_seconds=np.array([10.0, 10 + 1 / 30, 10 + 2 / 30]),
            pose_query_time_seconds=np.array([9.9, 9.9 + 1 / 30, 10.0]),
            valid=np.array([True, True, False]),
            position_xyz=np.array([[1.0, 0, 0], [2.0, 0, 0], [np.nan] * 3]),
            orientation_xyzw=np.array([[0, 0, 0, 1.0]] * 2 + [[np.nan] * 4]),
        )
        report = {
            'status': 'accepted',
            'source_episode': str(episode),
            'source_video': str(episode / 'video.mp4'),
            'video_to_pose_offset_seconds': offset,
            'offset_source': 'test',
        }
        (destination / 'alignment.json').write_text(json.dumps(report))
        reports.append(report)
    (output / 'alignment_summary.json').write_text(
        json.dumps({'episodes': reports}))
    return 0


@pytest.fixture
def fake_media(monkeypatch):
    """Replace OpenCV and ROS-backed alignment with deterministic fakes."""
    FRAME_SHAPES.clear()
    PTS_STEPS.clear()
    monkeypatch.setattr(export_hdf5, '_cv2', lambda: _FakeCv2)
    monkeypatch.setattr(build_dataset, '_cv2', lambda: _FakeCv2)
    monkeypatch.setattr(export_lerobot, '_cv2', lambda: _FakeCv2)
    monkeypatch.setattr(build_dataset, 'align', _fake_align)


def _session(root, task, episodes=1, accepted=True, offset=-0.095):
    session = create_online_session(root, task)
    for number in range(1, episodes + 1):
        episode = session / 'episodes' / f'episode_{number:04d}'
        episode.mkdir()
        (episode / 'video.mp4').write_bytes(b'mp4')
    update_session(session, status='complete', temporal_calibration={
        'status': 'accepted' if accepted else 'not_calibrated',
        'result': None,
        'video_to_pose_offset_seconds': offset,
    })
    return session


def _args(inputs, output, **overrides):
    values = {
        'inputs': [str(value) for value in inputs], 'output': str(output),
        'format': 'hdf5', 'repo_id': None, 'run_calibration': False,
        'overwrite': False, 'maximum_pose_gap': 0.1,
        'minimum_valid_ratio': 0.95, 'jpeg_quality': 90,
        'lerobot_python': '/missing/python', 'video_codec': 'h264'}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_multi_session_hdf5_merge(tmp_path, fake_media):
    """Number episodes globally and keep each session's task and origin."""
    h5py = pytest.importorskip('h5py')
    raw = tmp_path / 'recordings'
    first = _session(raw, 'pick cube', episodes=2, offset=-0.095)
    second = _session(raw, 'fold towel', offset=-0.090)
    third = _session(raw, 'pick cube', offset=-0.1)
    output = tmp_path / 'dataset'
    assert build_dataset.build(_args([raw], output)) == 0
    assert not output.with_name('dataset.partial').exists()

    with h5py.File(output / 'dataset.hdf5', 'r') as dataset:
        assert dataset.attrs['format_version'] == 2
        assert 'task' not in dataset.attrs
        assert dataset.attrs['session_count'] == 3
        assert [value.decode() for value in dataset['tasks'][()]] == [
            'pick cube', 'fold towel']
        episodes = dataset['episodes']
        assert list(episodes) == [
            'episode_0000', 'episode_0001', 'episode_0002', 'episode_0003']
        expected = [
            (first, 'episode_0001', 'pick cube', 0, -0.095),
            (first, 'episode_0002', 'pick cube', 0, -0.095),
            (second, 'episode_0001', 'fold towel', 1, -0.090),
            (third, 'episode_0001', 'pick cube', 0, -0.1),
        ]
        for name, (session, episode, task, index, offset) in zip(
                episodes, expected):
            attrs = episodes[name].attrs
            assert attrs['task'] == task
            assert attrs['task_index'] == index
            assert attrs['source_session'] == session.name
            assert attrs['source_episode'] == str(
                session / 'episodes' / episode)
            assert attrs['video_to_pose_offset_seconds'] == pytest.approx(
                offset)
            assert episodes[name]['observations/pose'].shape == (2, 7)

    manifest = json.loads((output / 'build_manifest.json').read_text())
    assert manifest['tasks'] == ['pick cube', 'fold towel']
    assert [entry['session'] for entry in manifest['sessions']] == [
        first.name, second.name, third.name]
    assert manifest['sessions'][0]['episode_count'] == 2
    assert manifest['fps'] == 30
    assert (output / 'processed' / first.name / 'transformed' /
            'episodes' / 'episode_0002' / 'transform.json').is_file()


def test_prechecks_fail_whole_build_with_reasons(tmp_path, fake_media):
    """Report every failing session and why, before any processing."""
    good = _session(tmp_path, 'task')
    no_task = _session(tmp_path, '')
    uncalibrated = _session(tmp_path, 'task', accepted=False)
    empty = _session(tmp_path, 'task', episodes=0)
    output = tmp_path / 'out'
    with pytest.raises(build_dataset.BuildError) as error:
        build_dataset.build(_args(
            [good, no_task, uncalibrated, empty], output))
    message = str(error.value)
    assert f'{no_task.name}: task is empty' in message
    assert f'{uncalibrated.name}: temporal calibration is ' in message
    assert f'{empty.name}: contains no ordinary episodes' in message
    assert good.name not in message
    assert not output.exists()
    assert not output.with_name('out.partial').exists()


def test_run_calibration_uses_newest_only_when_needed(
        tmp_path, fake_media, monkeypatch):
    """Accepted sessions keep their result; others run the newest one."""
    accepted = _session(tmp_path, 'task')
    pending = _session(tmp_path, 'task', accepted=False)
    for number in (1, 2):
        (pending / 'calibration' / f'calibration_{number:03d}').mkdir()
    no_calibration = _session(tmp_path, 'task', accepted=False)
    with pytest.raises(build_dataset.BuildError, match='no calibration'):
        build_dataset.build(_args(
            [accepted, pending, no_calibration], tmp_path / 'x',
            run_calibration=True))
    calls = []
    monkeypatch.setattr(
        build_dataset, '_run_calibration',
        lambda session, calibration: calls.append(
            (session.name, calibration.name)))
    assert build_dataset.build(_args(
        [accepted, pending], tmp_path / 'y', run_calibration=True)) == 0
    assert calls == [(pending.name, 'calibration_002')]


def test_inconsistent_video_properties_fail(tmp_path, fake_media):
    """Image size and frame rate must match across sessions."""
    first = _session(tmp_path, 'a')
    second = _session(tmp_path, 'b')
    video = str(second / 'episodes' / 'episode_0001' / 'video.mp4')
    FRAME_SHAPES[video] = (8, 6, 3)
    with pytest.raises(build_dataset.BuildError, match=second.name):
        build_dataset.build(_args([first, second], tmp_path / 'out'))
    assert not (tmp_path / 'out').exists()
    FRAME_SHAPES.clear()
    PTS_STEPS[str(second / 'episodes' / 'episode_0001')] = 1 / 60
    with pytest.raises(build_dataset.BuildError, match='@ 60.0'):
        build_dataset.build(_args([first, second], tmp_path / 'out'))


def test_frame_rate_uses_real_frame_spacing():
    """A single long gap or container average must not skew the rate."""
    pts = np.arange(100) / 30
    pts[50:] += 0.5
    assert build_dataset.frame_rate(pts) == pytest.approx(30.0)
    with pytest.raises(build_dataset.BuildError):
        build_dataset.frame_rate([0.0])


def test_contract_version_mismatch_fails(tmp_path, fake_media, monkeypatch):
    """Refuse transformed intermediates from another contract version."""
    session = _session(tmp_path, 'a')
    original = build_dataset.transform

    def old_contract(args):
        result = original(args)
        report = next(Path(args.output).glob('episodes/*/transform.json'))
        data = json.loads(report.read_text())
        data['schema_version'] = 0
        report.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(build_dataset, 'transform', old_contract)
    with pytest.raises(build_dataset.BuildError, match='contract version'):
        build_dataset.build(_args([session], tmp_path / 'out'))


def test_rejected_alignment_names_session_and_episode(
        tmp_path, fake_media, monkeypatch):
    """A rejected episode fails the build with its valid-frame ratio."""
    session = _session(tmp_path, 'a')

    def rejecting_align(args):
        _fake_align(args)
        summary = Path(args.output) / 'alignment_summary.json'
        data = json.loads(summary.read_text())
        data['episodes'][0].update(
            status='rejected', valid_frame_ratio=0.5,
            minimum_valid_frame_ratio=0.95)
        summary.write_text(json.dumps(data))
        return 2

    monkeypatch.setattr(build_dataset, 'align', rejecting_align)
    with pytest.raises(
            build_dataset.BuildError,
            match=f'{session.name}: alignment not accepted: episode_0001 '
                  'rejected: valid frame ratio 0.500'):
        build_dataset.build(_args([session], tmp_path / 'out'))


def test_overwrite_only_replaces_previous_builds(tmp_path, fake_media):
    """Never delete a directory build_dataset did not create."""
    session = _session(tmp_path / 'raw', 'a')
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    (foreign / 'keep.txt').write_text('user data')
    with pytest.raises(build_dataset.BuildError, match='already exists'):
        build_dataset.build(_args([session], foreign))
    with pytest.raises(build_dataset.BuildError, match='refusing'):
        build_dataset.build(_args([session], foreign, overwrite=True))
    assert (foreign / 'keep.txt').read_text() == 'user data'

    output = tmp_path / 'dataset'
    assert build_dataset.build(_args([session], output)) == 0
    (output / 'stale.txt').write_text('old')
    assert build_dataset.build(_args([session], output, overwrite=True)) == 0
    assert not (output / 'stale.txt').exists()
    with pytest.raises(build_dataset.BuildError, match='raw session'):
        build_dataset.build(_args(
            [session], session / 'dataset', overwrite=True))
    with pytest.raises(build_dataset.BuildError, match='raw session'):
        build_dataset.build(_args([session], tmp_path, overwrite=True))


def test_resolve_sessions_accepts_parents_and_deduplicates(tmp_path):
    """Directories expand to their sessions in name order."""
    first = create_online_session(tmp_path / 'a')
    second = create_online_session(tmp_path / 'a')
    other = create_online_session(tmp_path / 'b')
    resolved = build_dataset.resolve_sessions(
        [tmp_path / 'a', first, other])
    assert resolved == [first, second, other]
    with pytest.raises(build_dataset.BuildError, match='no session.yaml'):
        build_dataset.resolve_sessions([tmp_path])
    (tmp_path / 'c').mkdir()
    create_online_session(tmp_path / 'c')
    copy = tmp_path / 'c' / first.name
    copy.mkdir()
    (copy / 'session.yaml').write_text('schema_version: 2\n')
    with pytest.raises(build_dataset.BuildError, match='unique'):
        build_dataset.resolve_sessions([first, copy])


def test_process_session_defaults_to_session_task(tmp_path, monkeypatch):
    """The single-session command reads the task from session.yaml."""
    from umi_ros2.postprocess import process_session

    session = _session(tmp_path, 'wipe table')
    seen = []
    monkeypatch.setattr(process_session, 'align', lambda args: 0)
    monkeypatch.setattr(process_session, 'transform', lambda args: 0)
    monkeypatch.setattr(
        process_session, 'export_hdf5',
        lambda args: seen.append(args.task) or 0)
    args = process_session.argument_parser().parse_args(
        [str(session), '--output', str(tmp_path / 'p')])
    assert process_session.process(args) == 0
    args = process_session.argument_parser().parse_args(
        [str(session), '--output', str(tmp_path / 'q'), '--task', 'x'])
    assert process_session.process(args) == 0
    assert seen == ['wipe table', 'x']


def test_lerobot_plan_carries_per_session_task_and_source(
        tmp_path, fake_media, monkeypatch):
    """Each LeRobot frame gets its session's task and source name."""
    first = _session(tmp_path / 'raw', 'pick cube')
    second = _session(tmp_path / 'raw', 'fold towel')
    output = tmp_path / 'dataset'
    captured = {}

    def fake_export(plan_path, lerobot_output, fps, args):
        captured['sources'] = read_plan(plan_path)
        captured['fps'] = fps
        lerobot_output.mkdir()

    monkeypatch.setattr(build_dataset, '_export_lerobot', fake_export)
    assert build_dataset.build(_args(
        [tmp_path / 'raw'], output, format='lerobot',
        repo_id='local/test')) == 0
    assert [(s.source_session, s.task) for s in captured['sources']] == [
        (first.name, 'pick cube'), (second.name, 'fold towel')]
    # The plan saved with the finished build still resolves after the move.
    sources = read_plan(output / 'processed' / 'dataset_plan.json')
    assert all(Path(source.item).is_dir() for source in sources)
    assert [(s.source_session, s.task) for s in sources] == [
        (first.name, 'pick cube'), (second.name, 'fold towel')]
    assert captured['fps'] == 30
    assert json.loads((output / 'build_manifest.json').read_text())[
        'formats'] == {'lerobot': 'lerobot'}

    frames = []

    class FakeDataset:
        def add_frame(self, frame):
            frames.append(frame)

        def save_episode(self, parallel_encoding):
            frames.append('saved')

        def finalize(self):
            pass

    class FakeDatasetClass:
        @staticmethod
        def create(**kwargs):
            captured['features'] = kwargs['features']
            kwargs['root'].mkdir()
            return FakeDataset()

    monkeypatch.setattr(
        export_lerobot, '_lerobot_dataset_class', lambda: FakeDatasetClass)
    plan = tmp_path / 'plan.json'
    write_plan(plan, sources)
    target = tmp_path / 'lerobot'
    export_lerobot.write_lerobot(target, read_plan(plan), 'local/test', 30)
    assert captured['features']['umi.source_session']['dtype'] == 'string'
    tasks = [f['task'] for f in frames if f != 'saved']
    origins = [f['umi.source_session'] for f in frames if f != 'saved']
    assert tasks == ['pick cube'] * 2 + ['fold towel'] * 2
    assert origins == [first.name] * 2 + [second.name] * 2
    manifest = json.loads((target / 'umi_export.json').read_text())
    assert manifest['tasks'] == ['pick cube', 'fold towel']
    assert [entry['session'] for entry in manifest['source_sessions']] == [
        first.name, second.name]
    assert manifest['action_field'] is None


def test_single_root_sources_keep_old_behaviour(tmp_path, fake_media):
    """The standalone exporters still describe one root with one task."""
    session = _session(tmp_path, 'unused')
    aligned = tmp_path / 'aligned'
    _fake_align(SimpleNamespace(input_path=session, output=aligned))
    build_dataset.transform(SimpleNamespace(
        input_path=str(aligned), output=str(tmp_path / 't'),
        overwrite=False))
    [source] = sources_for_root(tmp_path / 't', 'cli task')
    assert source.task == 'cli task'
    assert source.source_session == session.name
    assert source.video_to_pose_offset_seconds == pytest.approx(-0.095)


def test_lerobot_interpreter_symlink_is_not_resolved(tmp_path, monkeypatch):
    """A venv python symlink must be run as-is to stay inside the venv."""
    real = tmp_path / 'base' / 'python3'
    real.parent.mkdir()
    real.write_text('')
    venv_python = tmp_path / 'venv' / 'bin' / 'python'
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(real)
    commands = []
    monkeypatch.setattr(
        build_dataset.subprocess, 'run',
        lambda command, **kwargs: commands.append(command)
        or SimpleNamespace(returncode=0))
    build_dataset._export_lerobot(
        tmp_path / 'plan.json', tmp_path / 'lerobot', 30,
        SimpleNamespace(repo_id='local/x', lerobot_python=str(venv_python),
                        video_codec='h264'))
    assert commands[0][0] == str(venv_python)
