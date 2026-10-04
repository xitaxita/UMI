"""Numbered camera selection and deliberate retries in the keyboard client."""

import json
from types import SimpleNamespace

from umi_ros2.camera import episode_keyboard


def test_selected_camera_retries_after_reject(monkeypatch, capsys):
    """Reject prompts for Enter and starts the same service again."""
    keyboard = object.__new__(episode_keyboard.EpisodeKeyboard)
    keyboard._recording = False
    keyboard._recording_kind = None
    keyboard._calibration_retry = False
    keyboard._calibration = None
    keyboard._camera_list = 'list'
    keyboard._stop = 'stop'
    keyboard._start = 'episode'
    keyboard.create_client = lambda service, name: name
    keyboard.destroy_client = lambda client: None
    camera = {'number': 2, 'camera_id': 'left', 'image_field': 'left_image',
              'start_service': '/test/start_calibration/left'}
    stops = iter([False, True])
    calls = []

    def call(client, request):
        calls.append(client)
        if client == 'list':
            return SimpleNamespace(success=True, message=json.dumps([camera]))
        if client == 'stop':
            accepted = next(stops)
            return SimpleNamespace(success=accepted,
                                   message='accept' if accepted else 'reject')
        assert client == camera['start_service']
        return SimpleNamespace(success=True, message='calibration started')

    keyboard._call = call
    lines = iter(['c', 'invalid', '2', '', '', '', 'q'])
    monkeypatch.setattr('builtins.input', lambda *args: next(lines))
    monkeypatch.setattr(episode_keyboard.rclpy, 'ok', lambda: True)
    keyboard.run()
    assert calls == ['list', camera['start_service'], 'stop',
                     camera['start_service'], 'stop']
    assert not keyboard._recording
    assert not keyboard._calibration_retry
    output = capsys.readouterr().out
    assert '2: left / left_image' in output
    assert 'Enter 重录当前相机' in output
    assert '编号无效' in output
