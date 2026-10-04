"""RealSense color stream implementation of the common camera interface."""

from pathlib import Path

from umi_ros2.camera.worker_source import WorkerCameraSource


def resolve_color_device(serial, interface_number='03',
                         sysfs_root=Path('/sys/class/video4linux')):
    """Find the RGB capture node by USB serial and interface, not video ID."""
    matches = []
    for endpoint in Path(sysfs_root).glob('video*'):
        try:
            if (endpoint / 'index').read_text().strip() != '0':
                continue
            interface = (endpoint / 'device').resolve()
            if ((interface / 'bInterfaceNumber').read_text().strip()
                    != str(interface_number)):
                continue
            serial_path = next(
                (parent / 'serial' for parent in interface.parents
                 if (parent / 'serial').is_file()), None)
            if (serial_path is not None
                    and serial_path.read_text().strip() == str(serial)):
                matches.append('/dev/' + endpoint.name)
        except OSError:
            continue
    if len(matches) != 1:
        raise ValueError(
            f'RealSense RGB device selection requires one capture endpoint '
            f'for serial {serial}, USB interface {interface_number}; '
            f'found {len(matches)}: {matches}')
    return matches[0]


class RealSenseSource(WorkerCameraSource):
    """Capture a RealSense V4L2 color endpoint as YUYV video."""

    def __init__(self, config):
        """Select the RGB endpoint and require a YUYV stream format."""
        config = dict(config)
        if config.get('input_format', 'YUYV') != 'YUYV':
            raise ValueError('RealSense color input_format must be YUYV')
        if (config.get('serial') and config.get('auto_select_color', True)
                and not config.get('test_source')):
            config['device'] = resolve_color_device(
                config['serial'], config.get('color_usb_interface', '03'))
        if not str(config.get('device', '')).strip():
            raise ValueError('RealSense color device is required')
        config['input_format'] = 'YUYV'
        super().__init__(config)
