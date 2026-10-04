"""D-021 in-launch session switching and raw calibration copying."""

import inspect
import shutil
from types import SimpleNamespace

import pytest

from umi_ros2.camera import episode_keyboard
from umi_ros2.camera.h264_capture_node import H264CaptureNode
from umi_ros2.session import layout
from umi_ros2.session.layout import (
    calibration_directories,
    copy_calibration_raw,
    create_online_session,
    latest_calibration,
    read_session,
    register_recording,
    switch_session,
    update_session,
)


RAW = {'video.mp4', 'video.timing.json', 'video.validation.json', 'pose'}
DERIVED = ('time_offset.json', 'alignment_report.png', 'trajectory_xy.png')


def _calibration(session, number, status='complete', derived=True):
    path = session / 'calibration' / f'calibration_{number:03d}'
    (path / 'pose').mkdir(parents=True)
    (path / 'video.mp4').write_bytes(b'mp4-%d' % number)
    (path / 'video.timing.json').write_text('{"status": "complete"}')
    (path / 'video.validation.json').write_text('{}')
    (path / 'pose' / 'metadata.yaml').write_text('bag: 1\n')
    (path / 'pose' / 'pose_0.mcap').write_bytes(b'mcap')
    if derived:
        for name in DERIVED:
            (path / name).write_text('derived')
    register_recording(session, path, 'calibration', status=status)
    return path


def test_switch_copies_only_raw_calibration(tmp_path):
    """Copy raw inputs with their number; leave derived results behind."""
    old = create_online_session(tmp_path, 'task A')
    _calibration(old, 1)
    update_session(old, temporal_calibration={
        'status': 'accepted', 'result': 'x'})
    new, copied = switch_session(old, tmp_path, 'task B')

    assert [path.name for path in copied] == ['calibration_001']
    target = new / 'calibration' / 'calibration_001'
    assert {child.name for child in target.iterdir()} == RAW
    assert (target / 'video.mp4').read_bytes() == b'mp4-1'
    assert (target / 'pose' / 'pose_0.mcap').read_bytes() == b'mcap'
    assert not list((new / 'calibration').glob('.*'))

    metadata = read_session(new)
    assert metadata['task'] == 'task B'
    assert metadata['status'] == 'active'
    assert metadata['temporal_calibration']['status'] == 'not_calibrated'
    [item] = metadata['recordings']
    assert item['kind'] == 'calibration'
    assert item['path'] == 'calibration/calibration_001'
    assert item['copied_from'] == f'{old.name}/calibration/calibration_001'
    assert item['task'] == 'task B'

    previous = read_session(old)
    assert previous['status'] == 'complete'
    assert previous['ended_at']
    assert previous['task'] == 'task A'
    assert new.name.startswith('online_session_')
    assert 'task' not in new.name


def test_switch_copies_second_camera_raw_calibration(tmp_path):
    """Carry both raw streams and their field mapping into the new session."""
    old = create_online_session(tmp_path, image_streams=[
        {'camera_id': 'wrist', 'image_field': 'wrist_image'},
        {'camera_id': 'left', 'image_field': 'left_image'},
    ])
    source = _calibration(old, 1)
    wrist = source / 'cameras' / 'wrist'
    wrist.mkdir(parents=True)
    for name in ('video.mp4', 'video.timing.json',
                 'video.validation.json'):
        (source / name).rename(wrist / name)
    left = source / 'cameras' / 'left'
    left.mkdir(parents=True)
    (left / 'video.mp4').write_bytes(b'left video')
    (left / 'video.timing.json').write_text('{"status": "complete"}')
    (left / 'video.validation.json').write_text('{}')
    metadata = read_session(old)
    metadata['recordings'][0]['image_streams'] = [
        {'camera_id': 'wrist', 'image_field': 'wrist_image',
         'video_path': 'cameras/wrist/video.mp4'},
        {'camera_id': 'left', 'image_field': 'left_image',
         'video_path': 'cameras/left/video.mp4'},
    ]
    update_session(old, recordings=metadata['recordings'])

    new, _ = switch_session(
        old, tmp_path, image_streams=metadata['image_streams'])
    copied = new / 'calibration' / 'calibration_001'
    assert (copied / 'cameras/wrist/video.mp4').read_bytes() == b'mp4-1'
    assert (copied / 'cameras/left/video.mp4').read_bytes() == b'left video'
    assert not (copied / 'video.mp4').exists()
    assert read_session(new)['image_streams'] == metadata['image_streams']
    assert read_session(new)['recordings'][0]['image_streams'] == (
        metadata['recordings'][0]['image_streams'])


def test_switch_skips_failed_calibration_and_handles_none(tmp_path):
    """Only complete calibrations are copied; none at all is allowed."""
    old = create_online_session(tmp_path)
    _calibration(old, 1, status='failed')
    new, copied = switch_session(old, tmp_path, '')
    assert copied == []
    assert calibration_directories(new) == []
    assert read_session(new)['recordings'] == []


def test_copy_failure_leaves_no_partial_session(tmp_path, monkeypatch):
    """A failed copy removes the new session and keeps the old one active."""
    old = create_online_session(tmp_path, 'task A')
    _calibration(old, 1)

    def broken_copytree(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(layout.shutil, 'copytree', broken_copytree)
    with pytest.raises(OSError, match='disk full'):
        switch_session(old, tmp_path, 'task B')
    assert sorted(path.name for path in tmp_path.iterdir()) == [old.name]
    assert read_session(old)['status'] == 'active'


def test_partial_copy_is_hidden_and_removed(tmp_path, monkeypatch):
    """The staging directory never matches calibration_* and is cleaned."""
    old = create_online_session(tmp_path)
    _calibration(old, 1)
    new = create_online_session(tmp_path)
    seen = []
    original = shutil.copytree

    def observing_copytree(source, target, *args, **kwargs):
        seen.append(target.parent.name)
        assert calibration_directories(new) == []
        original(source, target, *args, **kwargs)
        raise OSError('interrupted')

    monkeypatch.setattr(layout.shutil, 'copytree', observing_copytree)
    with pytest.raises(OSError):
        copy_calibration_raw(old, new)
    assert seen == ['.calibration_001.partial']
    assert list((new / 'calibration').iterdir()) == []
    assert read_session(new)['recordings'] == []


def test_copied_calibration_propagates_and_numbering_continues(tmp_path):
    """A copied calibration is copied again, so one launch needs one."""
    first = create_online_session(tmp_path)
    _calibration(first, 1)
    second, _ = switch_session(first, tmp_path, 'B')
    (second / 'calibration' / 'calibration_001' / 'time_offset.json'
     ).write_text('derived in second')
    third, copied = switch_session(second, tmp_path, 'C')
    target = third / 'calibration' / 'calibration_001'
    assert [path.name for path in copied] == ['calibration_001']
    assert not (target / 'time_offset.json').exists()
    [item] = read_session(third)['recordings']
    assert item['copied_from'] == f'{second.name}/calibration/calibration_001'

    _calibration(third, 2, derived=False)
    fourth, copied = switch_session(third, tmp_path, 'D')
    assert [path.name for path in copied] == [
        'calibration_001', 'calibration_002']
    assert latest_calibration(fourth).name == 'calibration_002'


def test_calibration_order_is_numeric(tmp_path):
    """Pick the highest number, not the lexically last name."""
    session = create_online_session(tmp_path)
    for name in ('calibration_999', 'calibration_1000', 'calibration_x'):
        (session / 'calibration' / name).mkdir()
    (session / 'calibration' / '.calibration_1001.partial').mkdir()
    assert latest_calibration(session).name == 'calibration_1000'
    assert [path.name for path in calibration_directories(session)] == [
        'calibration_999', 'calibration_1000']


def test_copy_left_only_and_select_latest_per_camera(tmp_path):
    """Left calibrations copy correctly and never replace wrist defaults."""
    old = create_online_session(tmp_path)
    wrist = _calibration(old, 1)
    left = old / 'calibration' / 'calibration_002'
    color = left / 'cameras' / 'left'
    color.mkdir(parents=True)
    (left / 'pose').mkdir()
    (color / 'video.mp4').write_bytes(b'left')
    (color / 'video.timing.json').write_text('{"camera_id": "left"}')
    register_recording(old, left, 'calibration', image_streams=[{
        'camera_id': 'left', 'image_field': 'left_image'}])
    rejected = old / 'calibration' / 'calibration_003'
    rejected.mkdir()
    register_recording(old, rejected, 'calibration', status='rejected')
    assert latest_calibration(old) == wrist
    assert latest_calibration(old, 'left') == left
    new, copied = switch_session(old, tmp_path, 'next')
    assert [path.name for path in copied] == [wrist.name, left.name]
    assert (new / 'calibration' / left.name / 'cameras/left/video.mp4'
            ).read_bytes() == b'left'
    assert read_session(new)['recordings'][1]['image_streams'][0][
        'camera_id'] == 'left'
    assert read_session(new)['temporal_calibrations'] == {}


def test_latest_calibration_is_the_default_choice(tmp_path):
    """build_dataset --run-calibration uses the newest calibration."""
    session = create_online_session(tmp_path)
    _calibration(session, 1)
    second = _calibration(session, 2)
    assert latest_calibration(session) == second
    empty = create_online_session(tmp_path)
    with pytest.raises(ValueError, match='no calibration'):
        latest_calibration(empty)


class _FakeNode(SimpleNamespace):
    """Just enough of H264CaptureNode to exercise its service handler."""

    def __init__(self, **kwargs):
        super().__init__(logged=[], parameters={}, **kwargs)

    def get_parameter(self, name):
        return SimpleNamespace(value=self.parameters.get(name, ''))

    def set_parameters(self, parameters):
        for parameter in parameters:
            self.parameters[parameter.name] = parameter.value

    def get_logger(self):
        logged = self.logged
        return SimpleNamespace(
            info=lambda text: logged.append(('info', text)),
            warning=lambda text: logged.append(('warning', text)),
            error=lambda text: logged.append(('error', text)))

    def _log_session_task(self):
        H264CaptureNode._log_session_task(self)


def test_new_session_service_refuses_while_recording(tmp_path):
    """Never switch sessions under an open recording."""
    session = create_online_session(tmp_path)
    node = _FakeNode(
        _episode_dir=session / 'episodes' / 'episode_0001',
        _session_dir=session, _recordings_root=tmp_path)
    response = H264CaptureNode._new_session(
        node, None, SimpleNamespace(success=None, message=''))
    assert response.success is False
    assert 'while recording' in response.message
    assert [path.name for path in tmp_path.iterdir()] == [session.name]


def test_new_session_service_switches_and_resets_numbers(tmp_path):
    """Episode numbers restart; calibration numbers follow the copies."""
    old = create_online_session(tmp_path, 'A')
    _calibration(old, 1)
    _calibration(old, 2)
    node = _FakeNode(
        _episode_dir=None, _session_dir=old, _recordings_root=tmp_path,
        _episode_number=7, _calibration_number=2)
    node.parameters['next_task'] = '  task B '
    response = H264CaptureNode._new_session(
        node, None, SimpleNamespace(success=None, message=''))
    assert response.success is True, response.message
    assert node._session_dir != old
    assert read_session(node._session_dir)['task'] == 'task B'
    assert node._episode_number == 0
    assert node._calibration_number == 2
    assert node.parameters['next_task'] == ''
    assert 'calibrate_time' in response.message

    empty = _FakeNode(
        _episode_dir=None, _session_dir=node._session_dir,
        _recordings_root=tmp_path, _episode_number=0,
        _calibration_number=0)
    for path in calibration_directories(node._session_dir):
        shutil.rmtree(path)
    update_session(node._session_dir, recordings=[])
    response = H264CaptureNode._new_session(
        empty, None, SimpleNamespace(success=None, message=''))
    assert response.success is True
    assert 'no calibration data' in response.message
    assert empty._calibration_number == 0
    assert ('warning' in [level for level, _ in empty.logged])


def test_keyboard_n_does_not_stop_a_recording(monkeypatch, capsys):
    """While recording, n is refused instead of acting as stop."""
    keyboard = object.__new__(episode_keyboard.EpisodeKeyboard)
    keyboard._recording = True
    keyboard._recording_kind = 'episode'
    calls = []
    keyboard._call = lambda client, request: calls.append(client)
    keyboard._stop = 'stop-client'
    lines = iter(['n', 'q'])
    monkeypatch.setattr('builtins.input', lambda *args: next(lines))
    monkeypatch.setattr(episode_keyboard.rclpy, 'ok', lambda: True)
    keyboard.run()
    assert calls == []
    assert keyboard._recording is True
    assert 'Recording continues' in capsys.readouterr().out


def test_status_files_live_outside_sessions():
    """Worker status must survive a session switch without a restart."""
    text = inspect.getsource(H264CaptureNode.__init__)
    assert "self._session_dir / '.online_pose_status.json'" not in text
    assert "mkdtemp(prefix='umi_online_runtime_')" in text
    assert "self._runtime_dir / '.online_pose_status.json'" in text
