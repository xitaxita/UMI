"""Contracts for the recording-first Action 4 GStreamer pipeline."""

from umi_ros2.camera.capture_pipeline import gstreamer_command


def test_recording_command_encodes_mjpeg_and_outputs_raw_preview():
    """Only the independently decodable JPEG preview queue drops frames."""
    command = gstreamer_command(
        '/dev/video0', 1920, 1080, 30, 640, 360, '/tmp/video.mp4'
    )

    assert 'image/jpeg,width=1920,height=1080,framerate=30/1' in command
    assert 'x264enc' in command
    assert command.index('mp4mux') < command.index('leaky=downstream')
    assert 'videorate' not in command
    assert 'leaky=no' in command
    assert 'mp4mux' in command
    assert 'location=/tmp/video.mp4' in command
    assert 'leaky=downstream' in command
    assert 'video/x-raw,format=BGR,width=640,height=360' in command
    assert command[-3:] == ['fd=1', 'sync=false', 'async=false']


def test_preview_command_does_not_write_a_file():
    """Observation mode owns the camera but does not start recording."""
    command = gstreamer_command(
        '/dev/video0', 1920, 1080, 30, 640, 360
    )

    assert 'mp4mux' not in command
    assert 'x264enc' not in command
    assert not any(item.startswith('location=') for item in command)
    assert 'video/x-raw,format=BGR,width=640,height=360' in command
