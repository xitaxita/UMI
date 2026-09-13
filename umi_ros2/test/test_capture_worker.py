"""Contracts for the persistent camera and per-episode encoder."""

from umi_ros2.camera.capture_worker import CaptureWorker


def test_camera_and_episode_encoder_are_separate_pipelines():
    """Camera stays live while each episode owns a fresh MP4 encoder."""
    worker = CaptureWorker.__new__(CaptureWorker)
    worker.config = {
        'device': '/dev/video0', 'width': 1920, 'height': 1080, 'fps': 30,
        'preview_width': 640, 'preview_height': 360, 'io_mode': 'mmap',
        'bitrate_kbps': 12000,
    }
    camera = worker._camera_description()
    first = worker._encoder_description('/tmp/episode_1/video.mp4')
    second = worker._encoder_description('/tmp/episode_2/video.mp4')

    assert camera.count('v4l2src') == 1
    assert 'capture_sink' in camera
    assert 'fdsink' in camera
    assert 'x264enc' not in camera
    assert 'v4l2src' not in first
    assert 'appsrc' in first and 'x264enc' in first
    assert 'location="/tmp/episode_1/video.mp4"' in first
    assert 'location="/tmp/episode_2/video.mp4"' in second
