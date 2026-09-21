"""Encode Action 4 MJPEG into H.264 MP4 with a disposable ROS preview."""

import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image

from std_srvs.srv import Trigger

from umi_ros2.session.layout import (
    create_online_session,
    now_text,
    register_recording,
    update_session,
)


class H264CaptureNode(Node):
    """Own one GStreamer process and publish only its latest preview."""

    def __init__(self):
        """Start MJPEG capture, H.264 encoding and the preview reader."""
        super().__init__('action4_h264_capture_node')
        self.declare_parameter('video_device', '/dev/video0')
        self.declare_parameter('image_width', 1920)
        self.declare_parameter('image_height', 1080)
        self.declare_parameter('framerate', 30)
        self.declare_parameter('io_mode', 'mmap')
        self.declare_parameter('frame_id', 'action4_camera')
        self.declare_parameter('preview_topic', '/action4/image_preview')
        self.declare_parameter('preview_width', 640)
        self.declare_parameter('preview_height', 360)
        self.declare_parameter('output_path', '')
        self.declare_parameter('episode_mode', False)
        self.declare_parameter('recordings_root', 'recordings')
        self.declare_parameter('preview_fps', 15.0)
        self.declare_parameter('bitrate_kbps', 12000)
        self.declare_parameter('warmup_seconds', 5.0)
        self.declare_parameter('startup_timeout_seconds', 30.0)

        self._frame_id = str(self.get_parameter('frame_id').value)
        self._preview_width = int(
            self.get_parameter('preview_width').value
        )
        self._preview_height = int(
            self.get_parameter('preview_height').value
        )
        self._frame_size = self._preview_width * self._preview_height * 3
        self._preview_lock = threading.Lock()
        self._pending_preview = None
        self._closed = False

        self._episode_mode = bool(self.get_parameter('episode_mode').value)
        self._recordings_root = Path(
            str(self.get_parameter('recordings_root').value)
        ).expanduser().resolve()
        self._session_dir = None
        if self._episode_mode:
            self._session_dir = create_online_session(self._recordings_root)
        self._status_path = (
            (self._session_dir or self._recordings_root)
            / '.online_camera_status.json'
        )
        self._pose_status_path = (
            self._session_dir / '.online_pose_status.json'
            if self._session_dir is not None else None
        )
        self._base_config = {
            'device': str(self.get_parameter('video_device').value),
            'width': int(self.get_parameter('image_width').value),
            'height': int(self.get_parameter('image_height').value),
            'fps': int(self.get_parameter('framerate').value),
            'preview_width': self._preview_width,
            'preview_height': self._preview_height,
            'output_path': '',
            'io_mode': str(self.get_parameter('io_mode').value),
            'bitrate_kbps': int(self.get_parameter('bitrate_kbps').value),
            'warmup_seconds': float(
                self.get_parameter('warmup_seconds').value),
            'startup_timeout_seconds': float(
                self.get_parameter('startup_timeout_seconds').value),
            'status_path': str(self._status_path),
        }
        self._output_path = ''
        self._episode_dir = None
        self._recording_kind = None
        self._episode_number = 0
        self._calibration_number = 0
        self._pose_process = None
        self._process = None
        self._publisher = self.create_publisher(
            Image,
            str(self.get_parameter('preview_topic').value),
            qos_profile_sensor_data,
        )
        self._preview_timer = self.create_timer(
            1.0 / max(1.0, float(self.get_parameter('preview_fps').value)),
            self._publish_latest_preview,
        )
        self._health_timer = self.create_timer(0.2, self._check_process)
        if self._episode_mode:
            self._start_pose_worker()
        self._start_worker('')
        if self._episode_mode:
            self._start_service = self.create_service(
                Trigger, '~/start_episode', self._start_episode)
            self._calibration_service = self.create_service(
                Trigger, '~/start_calibration', self._start_calibration)
            self._stop_service = self.create_service(
                Trigger, '~/stop_episode', self._stop_episode)
            self.get_logger().info(
                f'Online session ready at {self._session_dir}; use '
                'start_episode/start_calibration and stop_episode services')

    def _start_worker(self, output_path):
        """Start the one persistent preview and episode-recording worker."""
        self._status_path.unlink(missing_ok=True)
        config = dict(self._base_config)
        config['output_path'] = output_path
        command = [sys.executable, '-m', 'umi_ros2.camera.capture_worker',
                   json.dumps(config)]
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            start_new_session=True,
        )
        process = self._process
        self._reader = threading.Thread(
            target=self._read_previews,
            args=(process,),
            name='action4_preview_reader',
            daemon=True,
        )
        self._reader.start()
        self.get_logger().info(
            'Action 4 camera process launched; performing one-time warmup '
            'before entering waiting state'
        )

    def _start_pose_worker(self):
        """Start one pose subscriber retained for the complete session."""
        self._pose_status_path.unlink(missing_ok=True)
        config = {
            'warmup_seconds': self._base_config['warmup_seconds'],
            'startup_timeout_seconds': (
                self._base_config['startup_timeout_seconds']),
            'status_path': str(self._pose_status_path),
        }
        self._pose_process = subprocess.Popen(
            [sys.executable, '-m',
             'umi_ros2.vive.pose_recording_worker', json.dumps(config)],
            stdin=subprocess.PIPE,
            start_new_session=True,
        )
        self.get_logger().info(
            'Persistent pose recorder launched; warming subscriptions with '
            'the camera')

    def _stop_worker(self):
        """Stop the persistent worker when the complete ROS session exits."""
        if self._process is None:
            return
        process = self._process
        self._process = None
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        self._reader.join(timeout=2)
        process.stdout.close()

    def _stop_pose_worker(self):
        """Stop the persistent pose subscriber when the session exits."""
        if self._pose_process is None:
            return
        process = self._pose_process
        self._pose_process = None
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)

    def _new_recording_dir(self, kind):
        """Return the next sequential ordinary or calibration directory."""
        if kind == 'calibration':
            self._calibration_number += 1
            name = f'calibration_{self._calibration_number:03d}'
            return self._session_dir / 'calibration' / name
        self._episode_number += 1
        name = f'episode_{self._episode_number:04d}'
        return self._session_dir / 'episodes' / name

    def _start_episode(self, request, response):
        """Create one new video and pose recording."""
        return self._start_recording('episode', response)

    def _start_calibration(self, request, response):
        """Create one dedicated temporal-calibration recording."""
        return self._start_recording('calibration', response)

    def _start_recording(self, kind, response):
        """Start one recording without restarting the warmed camera."""
        if self._episode_dir is not None:
            response.success = False
            response.message = (
                f'already recording {self._episode_dir}')
            return response
        if not self._wait_worker_state('waiting', 30):
            response.success = False
            response.message = 'camera has not completed its one-time warmup'
            return response
        if not self._wait_pose_state('waiting', 30):
            response.success = False
            response.message = (
                'pose recorder has not completed its one-time warmup')
            return response
        episode = self._new_recording_dir(kind)
        pose = episode / 'pose'
        episode.mkdir(parents=True, exist_ok=False)
        self._episode_dir = episode
        self._recording_kind = kind
        self._output_path = self._prepare_output(episode / 'video.mp4')
        try:
            self._send_pose_worker({
                'command': 'start', 'output_path': str(pose)})
            if not self._wait_pose_state('recording_ready', 5):
                raise RuntimeError(
                    'pose recorder did not write its first pose in time')
            self._send_worker({
                'command': 'start', 'output_path': self._output_path,
                'timing_path': str(
                    Path(self._output_path).with_suffix('.timing.json')),
            })
            if not self._wait_worker_state('recording', 5):
                raise RuntimeError('camera did not enter recording state')
        except Exception:
            self._stop_pose_recording()
            register_recording(
                self._session_dir, episode, kind, status='failed')
            self._episode_dir = None
            self._recording_kind = None
            self._output_path = ''
            raise
        response.success = True
        response.message = f'{kind} started: {episode}'
        self.get_logger().info(response.message)
        return response

    def _send_pose_worker(self, command):
        """Send one recording command to the persistent pose worker."""
        self._pose_process.stdin.write(
            (json.dumps(command) + '\n').encode())
        self._pose_process.stdin.flush()

    def _stop_pose_recording(self):
        """Close the current per-recording MCAP without unsubscribing."""
        if self._pose_process is None or self._pose_process.poll() is not None:
            return
        self._send_pose_worker({'command': 'stop'})
        if not self._wait_pose_state('waiting', 15):
            raise RuntimeError('pose recording did not finalize in time')

    def _stop_episode(self, request, response):
        """Finalize the current episode and resume idle preview."""
        if self._episode_dir is None:
            response.success = False
            response.message = 'no episode is recording'
            return response
        episode = self._episode_dir
        kind = self._recording_kind
        self._send_worker({'command': 'stop'})
        timing_path = Path(self._output_path).with_suffix('.timing.json')
        if not self._wait_timing_complete(timing_path, 20):
            response.success = False
            response.message = (
                'video finalization timed out; system still running'
            )
            return response
        self._write_validation(self._process.poll())
        self._stop_pose_recording()
        register_recording(self._session_dir, episode, kind)
        self._episode_dir = None
        self._recording_kind = None
        self._output_path = ''
        response.success = True
        response.message = f'{kind} complete: {episode}'
        self.get_logger().info(response.message)
        return response

    def _send_worker(self, command):
        """Send one JSON command to the persistent camera worker."""
        self._process.stdin.write((json.dumps(command) + '\n').encode())
        self._process.stdin.flush()

    @staticmethod
    def _state_from(path):
        try:
            return json.loads(
                path.read_text(encoding='utf-8'))['state']
        except (OSError, KeyError, json.JSONDecodeError):
            return None

    def _worker_state(self):
        return self._state_from(self._status_path)

    def _wait_worker_state(self, expected, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._worker_state() == expected:
                return True
            if self._process.poll() is not None:
                return False
            time.sleep(0.05)
        return False

    def _wait_pose_state(self, expected, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._state_from(self._pose_status_path) == expected:
                return True
            if self._pose_process.poll() is not None:
                return False
            time.sleep(0.05)
        return False

    @staticmethod
    def _wait_timing_complete(path, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                state = json.loads(path.read_text(encoding='utf-8'))['status']
                if state in ('complete', 'failed'):
                    return True
            except (OSError, KeyError, json.JSONDecodeError):
                pass
            time.sleep(0.05)
        return False

    def _prepare_output(self, output):
        """Reserve a new MP4 path and reject stale metadata."""
        output.parent.mkdir(parents=True, exist_ok=True)
        if any(output.with_suffix(suffix).exists()
               for suffix in ('.validation.json', '.timing.json')):
            raise FileExistsError('online recording metadata already exists')
        # Reserve the name exclusively before the child opens its filesink.
        output.touch(exist_ok=False)
        return str(output)

    def _read_exactly(self, process, size):
        chunks = bytearray()
        while len(chunks) < size:
            chunk = process.stdout.read(size - len(chunks))
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_previews(self, process):
        while True:
            frame = self._read_exactly(process, self._frame_size)
            if frame is None:
                return
            receive_time_ns = time.time_ns()
            with self._preview_lock:
                self._pending_preview = (frame, receive_time_ns)

    def _publish_latest_preview(self):
        with self._preview_lock:
            preview = self._pending_preview
            self._pending_preview = None
        if preview is None:
            return
        data, stamp_ns = preview
        message = Image()
        message.header.frame_id = self._frame_id
        message.header.stamp.sec = stamp_ns // 1_000_000_000
        message.header.stamp.nanosec = stamp_ns % 1_000_000_000
        message.height = self._preview_height
        message.width = self._preview_width
        message.encoding = 'bgr8'
        message.is_bigendian = False
        message.step = self._preview_width * 3
        message.data = data
        self._publisher.publish(message)

    def _check_process(self):
        if self._process is None:
            return
        return_code = self._process.poll()
        if not self._closed and return_code is not None:
            raise RuntimeError(
                f'Action 4 GStreamer process exited with code {return_code}'
            )
        if (not self._closed and self._pose_process is not None
                and self._pose_process.poll() is not None):
            raise RuntimeError(
                'Persistent pose recorder exited unexpectedly with code '
                f'{self._pose_process.returncode}')

    def close(self):
        """Stop GStreamer cleanly so MP4 metadata is finalized."""
        if self._closed:
            return
        self._closed = True
        if self._episode_dir is not None:
            episode = self._episode_dir
            kind = self._recording_kind
            self._send_worker({'command': 'stop'})
            timing_path = Path(self._output_path).with_suffix('.timing.json')
            self._wait_timing_complete(timing_path, 20)
            self._write_validation(self._process.poll())
            self._stop_pose_recording()
            register_recording(self._session_dir, episode, kind)
            self._episode_dir = None
        self._stop_worker()
        self._stop_pose_worker()
        if self._session_dir is not None:
            update_session(
                self._session_dir, status='complete', ended_at=now_text())

    def _write_validation(self, return_code):
        """Validate the finalized video and combine worker timing facts."""
        report = validate_video(self._output_path)
        report['capture_exit_code'] = return_code
        report['clean_shutdown'] = return_code in (None, 0)
        timing_path = Path(self._output_path).with_suffix('.timing.json')
        if timing_path.exists():
            timing = json.loads(timing_path.read_text(encoding='utf-8'))
            report['recording_started'] = 'first_source_pts_ns' in timing
            report['accepted_source_frames'] = timing['accepted_frames']
            report['frame_count_matches'] = (
                report.get('decoded_frames') == timing['accepted_frames']
                and timing['accepted_frames'] > 0
            )
        Path(self._output_path).with_suffix('.validation.json').write_text(
            json.dumps(report, indent=2) + '\n', encoding='utf-8'
        )
        self.get_logger().info(f'Video validation: {report}')


def validate_video(path):
    """Inspect decoded MP4 frames; do not claim camera-side completeness."""
    report = {'source_completeness': 'not_verified'}
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_frames', '-show_entries',
            'frame=best_effort_timestamp_time', '-of', 'json', str(path),
        ], capture_output=True, text=True, timeout=120)
        frames = json.loads(result.stdout or '{}').get('frames', [])
        stamps = [float(f['best_effort_timestamp_time']) for f in frames
                  if 'best_effort_timestamp_time' in f]
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        report.update({
            'decode_ok': result.returncode == 0 and not result.stderr.strip()
            and bool(frames),
            'decoded_frames': len(frames),
            'max_timestamp_gap_seconds': max(gaps, default=None),
            'min_timestamp_gap_seconds': min(gaps, default=None),
            'first_frame_pts_seconds': stamps[0] if stamps else None,
            'first_20_frame_pts_seconds': stamps[:20],
            'non_increasing_timestamps': sum(gap <= 0 for gap in gaps),
            'errors': result.stderr[-4000:],
        })
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        report.update({'decode_ok': False, 'errors': str(error)})
    return report


def main(args=None):
    """Run MJPEG-to-H.264 recording and ROS preview publication."""
    rclpy.init(args=args)
    node = H264CaptureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
