"""ROS-independent pipeline construction and startup admission policy."""

import math


class WarmupGate:
    """Exclude startup buffers, then preserve every recording buffer."""

    def __init__(self, seconds=5.0, fps=30, stable_intervals=15):
        """Use elapsed receive time and consecutive source-PTS intervals."""
        if not math.isfinite(seconds) or seconds < 0 or fps <= 0:
            raise ValueError('warmup_seconds must be finite >= 0; fps > 0')
        if stable_intervals < 1:
            raise ValueError('stable_intervals must be positive')
        self.seconds = seconds
        self.period_ns = 1_000_000_000 / fps
        self.required = stable_intervals
        self.first_receive_ns = None
        self.previous_pts = None
        self.stable = 0
        self.started = False
        self.excluded = 0

    def accept(self, pts_ns, receive_ns, valid=True):
        """Latch open only after warmup; never filter later irregularities."""
        if self.started:
            return True
        if self.first_receive_ns is None:
            self.first_receive_ns = receive_ns
        delta = (pts_ns - self.previous_pts
                 if pts_ns is not None and self.previous_pts is not None
                 else None)
        good = (valid and delta is not None
                and 0.5 * self.period_ns <= delta <= 1.5 * self.period_ns)
        self.stable = self.stable + 1 if good else 0
        self.previous_pts = pts_ns if valid else None
        elapsed = (receive_ns - self.first_receive_ns) / 1_000_000_000
        if valid and elapsed >= self.seconds and self.stable >= self.required:
            self.started = True
            return True
        self.excluded += 1
        return False


def gstreamer_command(
        device, width, height, fps, preview_width, preview_height,
        output_path='', io_mode='mmap', bitrate_kbps=12000):
    """Build MJPEG recording and independently disposable preview branches."""
    command = [
        'gst-launch-1.0', '-q', '-e',
        'v4l2src', 'name=camera', f'device={device}', f'io-mode={io_mode}',
        'do-timestamp=true', '!',
        f'image/jpeg,width={width},height={height},framerate={fps}/1', '!',
        'tee', 'name=stream',
    ]
    if output_path:
        command.extend([
            'stream.', '!', 'identity', 'name=record_gate', '!',
            'queue', 'leaky=no', 'max-size-buffers=120',
            'max-size-bytes=0', 'max-size-time=0', '!',
            'jpegdec', '!', 'videoconvert', '!',
            'video/x-raw,format=I420', '!', 'x264enc',
            'speed-preset=ultrafast', 'tune=zerolatency',
            f'bitrate={bitrate_kbps}', f'key-int-max={fps}', '!',
            'h264parse', '!', 'mp4mux', 'faststart=true', '!',
            'filesink', f'location={output_path}', 'async=false',
        ])
    command.extend([
        'stream.', '!', 'queue', 'max-size-buffers=2',
        'max-size-bytes=0', 'max-size-time=0', 'leaky=downstream', '!',
        'jpegdec', '!', 'videoconvert', '!', 'videoscale', '!',
        f'video/x-raw,format=BGR,width={preview_width},'
        f'height={preview_height}',
        '!', 'fdsink', 'fd=1', 'sync=false', 'async=false',
    ])
    return command
