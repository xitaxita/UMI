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
    assert 'name=preview_sink' in camera
    assert 'appsink' in camera
    assert 'x264enc' not in camera
    assert 'v4l2src' not in first
    assert 'appsrc' in first and 'x264enc' in first
    assert 'location="/tmp/episode_1/video.mp4"' in first
    assert 'location="/tmp/episode_2/video.mp4"' in second


def test_yuyv_camera_uses_raw_color_without_jpeg_decoder():
    """Capture raw RealSense color without JPEG negotiation."""
    worker = CaptureWorker.__new__(CaptureWorker)
    worker.config = {
        'device': '/dev/video14', 'input_format': 'YUYV',
        'width': 640, 'height': 480, 'fps': 30,
        'preview_width': 320, 'preview_height': 240,
        'io_mode': 'mmap', 'bitrate_kbps': 8000,
    }
    camera = worker._camera_description()
    encoder = worker._encoder_description('/tmp/color.mp4')

    assert 'video/x-raw,format=YUY2,width=640,height=480' in camera
    assert 'jpegdec' not in camera
    assert 'name=preview_sink' in camera
    assert 'name=capture_sink' in camera
    assert 'caps=video/x-raw,format=YUY2' in encoder
    assert 'jpegdec' not in encoder
    assert 'x264enc' in encoder
