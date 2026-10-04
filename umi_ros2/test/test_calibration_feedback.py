"""Operator feedback for calibration processing failures."""

from types import SimpleNamespace

from umi_ros2.camera.h264_capture_node import H264CaptureNode
from umi_ros2.session.layout import create_online_session, read_session
from umi_ros2.synchronization import calibrate_time


def test_missing_ffprobe_rejects_selected_camera(
        tmp_path, monkeypatch):
    """Processing failures reject without borrowing another camera's result."""
    session = create_online_session(tmp_path)
    recording = session / 'calibration' / 'calibration_001'
    recording.mkdir()

    def missing_ffprobe(_args):
        raise FileNotFoundError(2, 'No such file or directory', 'ffprobe')

    monkeypatch.setattr(calibrate_time, 'calibrate', missing_ffprobe)
    node = SimpleNamespace(_session_dir=session)
    accepted, message = H264CaptureNode._calibrate_recording(node, recording)

    assert accepted is False
    assert 'ffprobe' in message
    assert read_session(session)['temporal_calibration']['status'] == (
        'rejected')
