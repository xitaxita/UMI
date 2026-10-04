"""DJI Action 4 implementation of the common camera source interface."""

from umi_ros2.camera.worker_source import WorkerCameraSource


class Action4Source(WorkerCameraSource):
    """Capture Action 4 MJPEG through the persistent worker."""

    def __init__(self, config):
        """Require the Action 4's MJPEG input format."""
        config = dict(config)
        if config.get('input_format', 'MJPEG') != 'MJPEG':
            raise ValueError('Action 4 input_format must be MJPEG')
        config['input_format'] = 'MJPEG'
        super().__init__(config)
