"""Required two-camera episode coordination and raw stream indexing."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from umi_ros2.camera.h264_capture_node import H264CaptureNode
from umi_ros2.session.layout import create_online_session, read_session
from umi_ros2.session.layout import update_temporal_calibration


class FakeCamera:
    """Model worker states while persisting camera-specific timing."""

    def __init__(self, camera_id, image_field, fail_start=False):
        """Set identity and optional start failure."""
        self.camera_id = camera_id
        self.image_field = image_field
        self._state = 'waiting'
        self.fail_start = fail_start

    def start_recording(self, output, timing):
        """Represent the worker entering recording state."""
        if self.fail_start:
            raise RuntimeError(f'{self.camera_id} cannot record')
        self.output = Path(output)
        self.timing = Path(timing)
        self._state = 'recording'
        self.timing.write_text(json.dumps({
            'status': 'recording', 'accepted_frames': 0,
            'camera_id': self.camera_id, 'image_field': self.image_field,
        }))

    def stop_recording(self):
        """Represent MP4 and timing finalization."""
        if self._state != 'recording':
            return
        self.output.write_bytes(b'fake video')
        self.timing.write_text(json.dumps({
            'status': 'complete', 'accepted_frames': 3,
            'camera_id': self.camera_id, 'image_field': self.image_field,
        }))
        self._state = 'waiting'

    def state(self):
        """Return the fake worker state."""
        return self._state

    def wait_for_state(self, expected, timeout):
        """Answer state waits without a polling delay."""
        return self._state == expected

    def poll(self):
        """Keep the worker alive."""
        return None


class FakeCoordinator:
    """Exercise H264CaptureNode service logic without a ROS graph."""

    _new_recording_dir = H264CaptureNode._new_recording_dir
    _start_recording = H264CaptureNode._start_recording
    _start_calibration = H264CaptureNode._start_calibration
    _list_cameras = H264CaptureNode._list_cameras
    _discard_calibration = H264CaptureNode._discard_calibration
    _reject_calibration = H264CaptureNode._reject_calibration
    _calibrate_recording = H264CaptureNode._calibrate_recording
    _stop_episode = H264CaptureNode._stop_episode
    _video_path = H264CaptureNode._video_path
    _recording_streams = H264CaptureNode._recording_streams
    _clear_recording = H264CaptureNode._clear_recording
    _finalize_recording = H264CaptureNode._finalize_recording
    _prepare_output = H264CaptureNode._prepare_output
    _wait_timing_complete = staticmethod(
        H264CaptureNode._wait_timing_complete)
    _worker_state = H264CaptureNode._worker_state
    _wait_worker_state = H264CaptureNode._wait_worker_state

    def __init__(self, root, fail_left=False):
        """Prepare a shared session and two required color cameras."""
        self._session_dir = create_online_session(root)
        self._camera = FakeCamera('wrist', 'wrist_image')
        self._cameras = {
            'wrist': self._camera,
            'left': FakeCamera('left', 'left_image', fail_left),
        }
        self._episode_dir = None
        self._recording_kind = None
        self._recording_camera_ids = None
        self._calibration_camera_id = 'wrist'
        self._calibration_retries = {}
        self._episode_number = 0
        self._calibration_number = 0
        self._output_path = ''
        self._output_paths = {}
        self.pose_commands = []

    def _wait_pose_state(self, state, timeout):
        return True

    def _send_pose_worker(self, command):
        self.pose_commands.append(command)
        if command['command'] == 'start':
            directory = Path(command['output_path'])
            directory.mkdir()
            (directory / 'pose_0.mcap').write_bytes(b'fake closed bag')

    def _stop_pose_recording(self):
        self.pose_commands.append({'command': 'stop'})

    def _write_validation(self, output, return_code):
        report = {'decode_ok': True, 'frame_count_matches': True}
        Path(output).with_suffix('.validation.json').write_text(
            json.dumps(report))
        return report

    def get_logger(self):
        """Discard log messages in the coordinator test."""
        return SimpleNamespace(info=lambda message: None,
                               error=lambda message: None)

    def get_fully_qualified_name(self):
        """Name the test coordinator's ROS service namespace."""
        return '/test_capture'


def test_two_streams_record_one_episode_with_distinct_fields(tmp_path):
    """Both cameras start after pose and finalize before session indexing."""
    node = FakeCoordinator(tmp_path)
    response = node._start_recording(
        'episode', SimpleNamespace(success=None, message=''))
    assert response.success is True
    assert node.pose_commands[0]['command'] == 'start'
    assert all(camera.state() == 'recording'
               for camera in node._cameras.values())

    response = node._stop_episode(
        None, SimpleNamespace(success=None, message=''))
    assert response.success is True
    assert node.pose_commands[-1]['command'] == 'stop'
    episode = node._session_dir / 'episodes' / 'episode_0001'
    streams = (
        read_session(node._session_dir)['recordings'][0]['image_streams'])
    identities = [(entry['camera_id'], entry['image_field'])
                  for entry in streams]
    assert identities == [
        ('wrist', 'wrist_image'), ('left', 'left_image')]
    assert [entry['video_path'] for entry in streams] == [
        'cameras/wrist/video.mp4', 'cameras/left/video.mp4']
    assert not (episode / 'video.mp4').exists()
    for entry in streams:
        assert (episode / entry['video_path']).is_file()
        assert (episode / entry['timing_path']).is_file()
        assert (episode / entry['validation_path']).is_file()
    assert read_session(node._session_dir)['recordings'][0]['status'] == (
        'complete')


def test_second_camera_start_failure_marks_partial_episode_failed(tmp_path):
    """Never index a one-camera recording as a complete two-camera one."""
    node = FakeCoordinator(tmp_path, fail_left=True)
    response = node._start_recording(
        'episode', SimpleNamespace(success=None, message=''))
    assert response.success is False
    assert node._episode_dir is None
    assert node._camera.state() == 'waiting'
    assert node.pose_commands[-1]['command'] == 'stop'
    [entry] = read_session(node._session_dir)['recordings']
    assert entry['status'] == 'failed'
    assert len(entry['image_streams']) == 2


@pytest.mark.parametrize('kind', ['episode', 'calibration'])
def test_images_start_after_first_pose_and_500ms_delay(
        tmp_path, monkeypatch, kind):
    """Neither camera writes during the pose lead, for either record kind."""
    node = FakeCoordinator(tmp_path)
    events = []

    def send_pose(command):
        events.append(('pose', command['command']))

    def wait_pose(expected, timeout):
        if expected == 'recording_ready':
            events.append(('pose', 'recording_ready'))
        return True

    def delay(seconds):
        assert all(camera.state() == 'waiting'
                   for camera in node._cameras.values())
        events.append(('delay', seconds))

    node._send_pose_worker = send_pose
    node._wait_pose_state = wait_pose
    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.time.sleep', delay)
    for camera_id, camera in node._cameras.items():
        original = camera.start_recording

        def start(output, timing, original=original, camera_id=camera_id):
            events.append(('camera', camera_id))
            original(output, timing)

        camera.start_recording = start

    response = node._start_recording(
        kind, SimpleNamespace(success=None, message=''))
    assert response.success is True
    expected = [
        ('pose', 'start'), ('pose', 'recording_ready'), ('delay', 0.5),
        ('camera', 'wrist'),
    ]
    if kind == 'episode':
        expected.append(('camera', 'left'))
    assert events == expected


def test_missing_first_pose_prevents_delay_and_image_start(
        tmp_path, monkeypatch):
    """A missing first pose must fail without starting either image stream."""
    node = FakeCoordinator(tmp_path)
    node._wait_pose_state = (
        lambda expected, timeout: expected != 'recording_ready')
    delays = []
    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.time.sleep', delays.append)

    response = node._start_recording(
        'episode', SimpleNamespace(success=None, message=''))
    assert response.success is False
    assert 'first pose' in response.message
    assert delays == []
    assert all(camera.state() == 'waiting'
               for camera in node._cameras.values())
    assert node.pose_commands[-1]['command'] == 'stop'
    assert read_session(node._session_dir)['recordings'][0]['status'] == (
        'failed')


def test_quality_runs_after_pose_close_and_reject_allows_next_episode(
        tmp_path, monkeypatch):
    """Each episode gets one verdict after all writers close."""
    node = FakeCoordinator(tmp_path)
    checked = []

    def diagnose(episode, streams, errors):
        assert node.pose_commands[-1]['command'] == 'stop'
        assert all(camera.state() == 'waiting'
                   for camera in node._cameras.values())
        assert len(streams) == 2
        checked.append(episode)
        return {'accepted': False, 'verdict': 'reject',
                'exclude_from_dataset': True, 'reasons': ['left: image 掉帧']}

    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.diagnose_episode', diagnose)
    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.time.sleep', lambda seconds: None)
    for number in (1, 2):
        assert node._start_recording(
            'episode', SimpleNamespace(success=None, message='')).success
        response = node._stop_episode(
            None, SimpleNamespace(success=None, message=''))
        assert response.success
        assert f'\033[31mepisode_{number:04d}: reject' in response.message
        assert node._episode_dir is None
        assert json.loads((checked[-1] / 'quality.json').read_text())[
            'exclude_from_dataset']
    assert len(checked) == 2


def test_left_calibration_does_not_record_or_wait_for_wrist(
        tmp_path, monkeypatch):
    """Only the selected camera participates; the other preview continues."""
    node = FakeCoordinator(tmp_path)
    node._camera._state = 'warming_up'
    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.time.sleep', lambda seconds: None)
    response = node._start_calibration(
        None, SimpleNamespace(success=None, message=''), 'left')
    assert response.success
    assert node._cameras['left'].state() == 'recording'
    assert node._camera.state() == 'warming_up'
    directory = node._episode_dir
    assert list(node._output_paths) == ['left']

    def accepted(episode, camera_id):
        assert camera_id == 'left'
        assert node.pose_commands[-1]['command'] == 'stop'
        return True, 'offset: 12 ms'

    node._calibrate_recording = accepted
    response = node._stop_episode(
        None, SimpleNamespace(success=None, message=''))
    assert response.success
    assert '\033[32mleft: accept' in response.message
    assert not (directory / 'cameras' / 'wrist').exists()
    assert node._camera.state() == 'warming_up'
    [entry] = read_session(node._session_dir)['recordings']
    assert [stream['camera_id']
            for stream in entry['image_streams']] == ['left']


def test_reject_removes_attempt_and_retries_same_directory(
        tmp_path, monkeypatch):
    """Retry replaces inputs/index and preserves another camera's result."""
    from umi_ros2.synchronization import calibrate_time

    node = FakeCoordinator(tmp_path)
    wrist_result = {'status': 'accepted', 'result': 'accepted_wrist.json'}
    update_temporal_calibration(node._session_dir, 'wrist', wrist_result)
    protected = node._session_dir / 'calibration' / 'calibration_099'
    protected.mkdir()
    (protected / 'video.mp4').write_bytes(b'accepted wrist')
    attempts = []

    def calibrate(args):
        directory = Path(args.calibration_episode)
        assert args.camera_id == 'left'
        assert node.pose_commands[-1]['command'] == 'stop'
        assert (directory / 'cameras' / 'left' / 'video.mp4').is_file()
        assert (directory / 'pose' / 'pose_0.mcap').is_file()
        attempts.append(directory)
        accepted = len(attempts) > 1
        (directory / 'time_offset.json').write_text(json.dumps({
            'accepted': accepted,
            'video_to_pose_offset_milliseconds': 12.0}))
        (directory / 'alignment_report.png').write_bytes(b'plot')
        update_temporal_calibration(node._session_dir, 'left', {
            'status': 'accepted' if accepted else 'rejected',
            'result': str((directory / 'time_offset.json').relative_to(
                node._session_dir)),
            'video_to_pose_offset_seconds': 0.012})
        return 0 if accepted else 2

    monkeypatch.setattr(calibrate_time, 'calibrate', calibrate)
    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.time.sleep', lambda seconds: None)
    assert node._start_calibration(
        None, SimpleNamespace(success=None, message=''), 'left').success
    directory = node._episode_dir
    rejected = node._stop_episode(
        None, SimpleNamespace(success=None, message=''))
    assert not rejected.success
    assert '\033[31mleft: reject' in rejected.message
    assert directory.is_dir()
    for name in ('pose', 'time_offset.json', 'alignment_report.png',
                 'cameras/left'):
        assert not (directory / name).exists()
    metadata = read_session(node._session_dir)
    assert metadata['temporal_calibration'] == wrist_result
    assert metadata['temporal_calibrations']['left']['result'] is None
    assert metadata['recordings'][0]['status'] == 'rejected'

    assert node._start_calibration(
        None, SimpleNamespace(success=None, message=''), 'left').success
    assert node._episode_dir == directory
    accepted = node._stop_episode(
        None, SimpleNamespace(success=None, message=''))
    assert accepted.success
    assert '\033[32mleft: accept' in accepted.message
    assert attempts == [directory, directory]
    assert node._calibration_retries == {}
    assert (directory / 'cameras/left/video.mp4').is_file()
    metadata = read_session(node._session_dir)
    assert len(metadata['recordings']) == 1
    assert metadata['recordings'][0]['status'] == 'complete'
    assert metadata['temporal_calibration'] == wrist_result
    assert metadata['temporal_calibrations']['left']['status'] == 'accepted'
    assert (protected / 'video.mp4').read_bytes() == b'accepted wrist'


def test_camera_menu_and_unknown_camera(tmp_path):
    """Number registered cameras and reject unknown camera IDs."""
    node = FakeCoordinator(tmp_path)
    response = node._list_cameras(
        None, SimpleNamespace(success=None, message=''))
    assert [(item['number'], item['camera_id'], item['image_field'])
            for item in json.loads(response.message)] == [
                (1, 'wrist', 'wrist_image'), (2, 'left', 'left_image')]
    response = node._start_calibration(
        None, SimpleNamespace(success=None, message=''), 'unknown')
    assert not response.success
    assert node.pose_commands == []
