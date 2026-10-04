"""Action 4 adapter's image framing and recording-control contract."""

import io
from types import SimpleNamespace

from umi_ros2.camera.action4_source import Action4Source
from umi_ros2.camera.capture_worker import CaptureWorker
from umi_ros2.camera.stream_protocol import NO_SOURCE_PTS, PREVIEW_HEADER


class FakeProcess:
    """Provide binary preview output and capture worker commands."""

    def __init__(self, output):
        """Initialize the two process pipes."""
        self.stdout = io.BytesIO(output)
        self.stdin = io.BytesIO()

    def poll(self):
        """Keep the fake process alive for command tests."""
        return None


def test_action4_source_preserves_identity_and_source_pts(tmp_path):
    """The newest frame carries dataset field and source timing."""
    source = Action4Source({
        'camera_id': 'wrist', 'image_field': 'wrist_image',
        'preview_width': 2, 'preview_height': 1,
        'status_path': str(tmp_path / 'status.json'),
    })
    source.process = FakeProcess(
        PREVIEW_HEADER.pack(123, 456) + b'abcdef'
        + PREVIEW_HEADER.pack(NO_SOURCE_PTS, 789) + b'ghijkl')
    source._read_previews()

    frame = source.latest_preview()
    assert (frame.camera_id, frame.image_field) == ('wrist', 'wrist_image')
    assert (frame.width, frame.height, frame.encoding) == (2, 1, 'bgr8')
    assert (frame.source_pts_ns, frame.receive_unix_ns) == (None, 789)
    assert frame.data == b'ghijkl'
    assert source.latest_preview() is None

    source.start_recording('/tmp/video.mp4', '/tmp/video.timing.json')
    source.stop_recording()
    assert (b'"output_path": "/tmp/video.mp4"'
            in source.process.stdin.getvalue())
    assert b'"command": "stop"' in source.process.stdin.getvalue()


def test_worker_preview_protocol_carries_source_pts(monkeypatch):
    """The Action 4 worker emits timestamped BGR frames for the adapter."""
    from umi_ros2.camera import capture_worker

    output = io.BytesIO()
    monkeypatch.setattr(
        capture_worker.sys, 'stdout', SimpleNamespace(buffer=output))
    buffer = SimpleNamespace(
        pts=123,
        map=lambda flags: (True, SimpleNamespace(data=b'abcdef')),
        unmap=lambda info: None,
    )
    sink = SimpleNamespace(emit=lambda name: SimpleNamespace(
        get_buffer=lambda: buffer))
    worker = CaptureWorker.__new__(CaptureWorker)
    worker.config = {'preview_width': 2, 'preview_height': 1}
    worker.Gst = SimpleNamespace(
        MapFlags=SimpleNamespace(READ=1),
        CLOCK_TIME_NONE=NO_SOURCE_PTS,
        FlowReturn=SimpleNamespace(OK=0, ERROR=1),
    )

    assert worker._on_preview(sink) == 0
    pts, received = PREVIEW_HEADER.unpack(
        output.getvalue()[:PREVIEW_HEADER.size])
    assert pts == 123
    assert received > 0
    assert output.getvalue()[PREVIEW_HEADER.size:] == b'abcdef'
