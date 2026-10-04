"""Shared subprocess transport for persistent GStreamer camera sources."""

import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from umi_ros2.camera.source import CameraSource, ImageFrame
from umi_ros2.camera.stream_protocol import NO_SOURCE_PTS, PREVIEW_HEADER


class WorkerCameraSource(CameraSource):
    """Own one persistent V4L2/GStreamer worker and its preview stream."""

    def __init__(self, config):
        """Keep camera identity and capture settings for the worker."""
        self.config = dict(config)
        self.camera_id = str(config['camera_id']).strip()
        self.image_field = str(config['image_field']).strip()
        if not self.camera_id or not self.image_field:
            raise ValueError('camera_id and image_field must be non-empty')
        self.config['camera_id'] = self.camera_id
        self.config['image_field'] = self.image_field
        self.width = int(config['preview_width'])
        self.height = int(config['preview_height'])
        if self.width <= 0 or self.height <= 0:
            raise ValueError('preview dimensions must be positive')
        self.frame_size = self.width * self.height * 3
        self.status_path = Path(config['status_path'])
        self.process = None
        self.reader = None
        self._preview_lock = threading.Lock()
        self._pending_preview = None

    def start(self):
        """Start one camera process and drain framed preview images."""
        if self.process is not None:
            raise RuntimeError('Camera source is already running')
        self.status_path.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'umi_ros2.camera.capture_worker',
             json.dumps(self.config)],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            start_new_session=True,
        )
        self.reader = threading.Thread(
            target=self._read_previews,
            name=f'{self.camera_id}_preview_reader',
            daemon=True,
        )
        self.reader.start()

    def _read_exactly(self, size):
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.process.stdout.read(size - len(chunks))
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_previews(self):
        while True:
            header = self._read_exactly(PREVIEW_HEADER.size)
            if header is None:
                return
            source_pts_ns, receive_unix_ns = PREVIEW_HEADER.unpack(header)
            data = self._read_exactly(self.frame_size)
            if data is None:
                return
            frame = ImageFrame(
                camera_id=self.camera_id,
                image_field=self.image_field,
                width=self.width,
                height=self.height,
                encoding='bgr8',
                data=data,
                source_pts_ns=(
                    None if source_pts_ns == NO_SOURCE_PTS
                    else source_pts_ns),
                receive_unix_ns=receive_unix_ns,
            )
            with self._preview_lock:
                self._pending_preview = frame

    def latest_preview(self):
        """Return only the newest preview image since the last request."""
        with self._preview_lock:
            frame = self._pending_preview
            self._pending_preview = None
        return frame

    def state(self):
        """Read the child worker's status file."""
        try:
            return json.loads(
                self.status_path.read_text(encoding='utf-8'))['state']
        except (OSError, KeyError, json.JSONDecodeError):
            return None

    def wait_for_state(self, expected, timeout):
        """Wait for state while checking if the worker exited."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.state() == expected:
                return True
            if self.poll() is not None:
                return False
            time.sleep(0.05)
        return False

    def _send(self, command):
        if self.process is None or self.poll() is not None:
            raise RuntimeError('Camera worker is not running')
        self.process.stdin.write((json.dumps(command) + '\n').encode())
        self.process.stdin.flush()

    def start_recording(self, output_path, timing_path):
        """Attach a new MP4 encoder to the live camera stream."""
        self._send({
            'command': 'start',
            'output_path': str(output_path),
            'timing_path': str(timing_path),
        })

    def stop_recording(self):
        """Detach the current MP4 encoder without closing the camera."""
        self._send({'command': 'stop'})

    def poll(self):
        """Return the worker exit status, if it has exited."""
        return None if self.process is None else self.process.poll()

    def close(self):
        """Stop the worker and close its preview pipe."""
        if self.process is None:
            return
        process = self.process
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        if self.reader is not None:
            self.reader.join(timeout=2)
        process.stdin.close()
        process.stdout.close()
        self.process = None
        self.reader = None
