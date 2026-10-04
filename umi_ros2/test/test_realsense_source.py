"""RealSense color adapter's identity, input and preview contract."""

import io

import pytest

from umi_ros2.camera.realsense_source import (
    RealSenseSource, resolve_color_device)
from umi_ros2.camera.stream_protocol import PREVIEW_HEADER


class FakeProcess:
    """Provide an in-memory preview pipe and command input."""

    def __init__(self, output):
        """Initialize the fake worker pipes."""
        self.stdout = io.BytesIO(output)
        self.stdin = io.BytesIO()

    def poll(self):
        """Represent a running worker."""
        return None


def test_realsense_color_source_preserves_dataset_field(tmp_path):
    """Preview and recording control use one stable color stream identity."""
    source = RealSenseSource({
        'camera_id': 'left', 'image_field': 'left_image',
        'device': '/dev/video14', 'preview_width': 2,
        'preview_height': 1,
        'status_path': str(tmp_path / 'color-status.json'),
    })
    assert source.config['input_format'] == 'YUYV'
    source.process = FakeProcess(PREVIEW_HEADER.pack(123, 456) + b'abcdef')
    source._read_previews()

    frame = source.latest_preview()
    assert (frame.camera_id, frame.image_field) == ('left', 'left_image')
    assert (frame.width, frame.height, frame.encoding) == (2, 1, 'bgr8')
    assert (frame.source_pts_ns, frame.receive_unix_ns) == (123, 456)
    assert frame.data == b'abcdef'
    source.start_recording('/tmp/color.mp4', '/tmp/color.timing.json')
    source.stop_recording()
    assert b'"command": "start"' in source.process.stdin.getvalue()
    assert b'"command": "stop"' in source.process.stdin.getvalue()


def test_realsense_requires_color_device_and_format(tmp_path):
    """Depth paths cannot silently enter the YUYV color adapter."""
    config = {
        'camera_id': 'left', 'image_field': 'left_image',
        'preview_width': 2, 'preview_height': 1,
        'status_path': str(tmp_path / 'status.json'),
    }
    with pytest.raises(ValueError, match='device'):
        RealSenseSource(config)
    with pytest.raises(ValueError, match='YUYV'):
        RealSenseSource({**config, 'device': '/dev/video10',
                         'input_format': 'Z16'})


def add_usb_endpoint(root, video, serial, interface_number, index=0):
    """Represent a V4L2 endpoint and its USB parent in a temporary sysfs."""
    usb = root / 'usb' / serial
    usb.mkdir(parents=True, exist_ok=True)
    (usb / 'serial').write_text(serial)
    interface = usb / ('interface' + interface_number)
    interface.mkdir(exist_ok=True)
    (interface / 'bInterfaceNumber').write_text(interface_number)
    endpoint = root / 'video4linux' / video
    endpoint.mkdir(parents=True)
    (endpoint / 'index').write_text(str(index))
    (endpoint / 'device').symlink_to(interface, target_is_directory=True)


def test_rgb_selection_ignores_depth_metadata_and_other_camera(tmp_path):
    """Serial and RGB interface remain correct when video nodes change."""
    add_usb_endpoint(tmp_path, 'video0', '435i', '00')
    add_usb_endpoint(tmp_path, 'video2', '435i', '02')
    add_usb_endpoint(tmp_path, 'video14', '435i', '03')
    add_usb_endpoint(tmp_path, 'video15', '435i', '03', index=1)
    add_usb_endpoint(tmp_path, 'video4', 'another', '03')
    assert resolve_color_device(
        '435i', sysfs_root=tmp_path / 'video4linux') == '/dev/video14'


def test_rgb_selection_rejects_missing_or_ambiguous_endpoint(tmp_path):
    """A missing RGB interface must never fall back to a depth endpoint."""
    add_usb_endpoint(tmp_path, 'video0', '435i', '00')
    with pytest.raises(ValueError, match='found 0'):
        resolve_color_device('435i', sysfs_root=tmp_path / 'video4linux')
    add_usb_endpoint(tmp_path, 'video4', '435i', '03')
    add_usb_endpoint(tmp_path, 'video8', '435i', '03')
    with pytest.raises(ValueError, match='found 2'):
        resolve_color_device('435i', sysfs_root=tmp_path / 'video4linux')


def test_source_uses_discovery_unless_overridden_or_synthetic(monkeypatch):
    """Explicit overrides and test inputs bypass default hardware discovery."""
    selected = []

    def resolve(serial, interface_number):
        selected.append((serial, interface_number))
        return '/dev/video14'

    monkeypatch.setattr(
        'umi_ros2.camera.realsense_source.resolve_color_device', resolve)
    config = {
        'camera_id': 'left', 'image_field': 'left_image', 'serial': '435i',
        'color_usb_interface': '03', 'device': '/dev/video0',
        'preview_width': 2, 'preview_height': 1,
        'status_path': '/tmp/unused-color-status.json',
    }
    assert RealSenseSource(config).config['device'] == '/dev/video14'
    assert RealSenseSource({
        **config, 'device': '/dev/video20', 'auto_select_color': False,
    }).config['device'] == '/dev/video20'
    assert RealSenseSource({
        **config, 'test_source': True,
    }).config['device'] == '/dev/video0'
    assert selected == [('435i', '03')]
