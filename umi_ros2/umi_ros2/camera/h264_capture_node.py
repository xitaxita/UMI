"""Coordinate online color cameras, pose recording and ROS previews."""

import contextlib
import io
import json
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from functools import partial
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image

from std_srvs.srv import Trigger

from umi_ros2.camera.action4_source import Action4Source
from umi_ros2.camera.episode_quality import (
    IMAGE_GAP_LIMIT_SECONDS, diagnose_episode, format_verdict)
from umi_ros2.camera.realsense_source import RealSenseSource
from umi_ros2.session.layout import (
    calibration_number,
    camera_video_path,
    create_online_session,
    normalize_task,
    now_text,
    read_session,
    register_recording,
    session_task,
    switch_session,
    update_session,
    update_temporal_calibration,
)

import yaml


IMAGE_RECORDING_DELAY_SECONDS = 0.5


class H264CaptureNode(Node):
    """Coordinate required camera sources, pose and online sessions."""

    def __init__(self):
        """Start camera previews and optional shared session recording."""
        super().__init__('action4_h264_capture_node')
        self.declare_parameter('video_device', '/dev/video0')
        self.declare_parameter('device_override', '')
        self.declare_parameter('camera_id', 'wrist')
        self.declare_parameter('image_field', 'wrist_image')
        self.declare_parameter('image_width', 1920)
        self.declare_parameter('image_height', 1080)
        self.declare_parameter('framerate', 30)
        self.declare_parameter('io_mode', 'mmap')
        self.declare_parameter('frame_id', 'action4_camera')
        self.declare_parameter('preview_topic', '/action4/image_preview')
        self.declare_parameter('preview_width', 640)
        self.declare_parameter('preview_height', 360)
        self.declare_parameter('episode_mode', False)
        self.declare_parameter('recordings_root', 'recordings')
        self.declare_parameter('task', '')
        self.declare_parameter('next_task', '')
        self.declare_parameter('preview_fps', 15.0)
        self.declare_parameter('bitrate_kbps', 12000)
        self.declare_parameter('warmup_seconds', 5.0)
        self.declare_parameter('startup_timeout_seconds', 30.0)
        self.declare_parameter('realsense_enabled', False)
        self.declare_parameter('realsense_config_path', '')
        self.declare_parameter('realsense_device_override', '')

        self._frame_id = str(self.get_parameter('frame_id').value)
        self._preview_width = int(
            self.get_parameter('preview_width').value
        )
        self._preview_height = int(
            self.get_parameter('preview_height').value
        )
        self._closed = False

        self._episode_mode = bool(self.get_parameter('episode_mode').value)
        self._recordings_root = Path(
            str(self.get_parameter('recordings_root').value)
        ).expanduser().resolve()
        self._session_dir = None
        self._runtime_dir = None
        if self._episode_mode:
            self._session_dir = create_online_session(
                self._recordings_root,
                normalize_task(self.get_parameter('task').value))
            self._log_session_task()
            # Worker status outlives any one session, so it is kept per
            # launch rather than inside a session directory.
            self._runtime_dir = Path(
                tempfile.mkdtemp(prefix='umi_online_runtime_'))
        self._status_path = (
            (self._runtime_dir or self._recordings_root)
            / '.online_camera_status.json'
        )
        self._pose_status_path = (
            self._runtime_dir / '.online_pose_status.json'
            if self._runtime_dir is not None else None
        )
        self._base_config = {
            'device': (
                str(self.get_parameter('device_override').value).strip()
                or str(self.get_parameter('video_device').value)),
            'camera_id': str(self.get_parameter('camera_id').value),
            'image_field': str(self.get_parameter('image_field').value),
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
        self._output_paths = {}
        self._episode_dir = None
        self._recording_kind = None
        self._recording_camera_ids = None
        self._calibration_camera_id = self._base_config['camera_id']
        self._calibration_retries = {}
        self._episode_number = 0
        self._calibration_number = 0
        self._pose_process = None
        self._camera = Action4Source(self._base_config)
        self._cameras = {self._camera.camera_id: self._camera}
        self._frame_ids = {self._camera.camera_id: self._frame_id}
        self._preview_topics = {
            self._camera.camera_id:
            str(self.get_parameter('preview_topic').value)}
        if bool(self.get_parameter('realsense_enabled').value):
            config_path = Path(str(
                self.get_parameter('realsense_config_path').value))
            if not config_path.is_file():
                raise ValueError(
                    f'RealSense config file does not exist: {config_path}')
            left_config = yaml.safe_load(
                config_path.read_text(encoding='utf-8'))
            if not isinstance(left_config, dict):
                raise ValueError('RealSense config must be a mapping')
            left_config = dict(left_config)
            left_override = str(self.get_parameter(
                'realsense_device_override').value).strip()
            left_config['device'] = left_override or str(left_config['device'])
            left_config['auto_select_color'] = not bool(left_override)
            left_config['warmup_seconds'] = (
                self._base_config['warmup_seconds'])
            left_config['startup_timeout_seconds'] = (
                self._base_config['startup_timeout_seconds'])
            left_config['status_path'] = str(
                (self._runtime_dir or self._recordings_root)
                / '.online_realsense_status.json')
            left = RealSenseSource(left_config)
            if (left.camera_id in self._cameras
                    or left.image_field == self._camera.image_field):
                raise ValueError('camera_id and image_field must be unique')
            if not re.fullmatch(r'[A-Za-z0-9_]+', left.camera_id):
                raise ValueError('RealSense camera_id must be a path-safe ID')
            self._cameras[left.camera_id] = left
            self._frame_ids[left.camera_id] = str(
                left_config.get('frame_id', 'realsense_left_camera'))
            self._preview_topics[left.camera_id] = str(
                left_config.get(
                    'preview_topic', '/realsense/left/image_preview'))
        self._configured_streams = [
            {'camera_id': camera.camera_id,
             'image_field': camera.image_field,
             'preview_topic': self._preview_topics[camera_id]}
            for camera_id, camera in self._cameras.items()
        ]
        if self._session_dir is not None:
            update_session(
                self._session_dir, image_streams=self._configured_streams)
        self._publisher = self.create_publisher(
            Image,
            str(self.get_parameter('preview_topic').value),
            qos_profile_sensor_data,
        )
        self._preview_publishers = {self._camera.camera_id: self._publisher}
        for camera_id in self._cameras:
            if camera_id != self._camera.camera_id:
                self._preview_publishers[camera_id] = self.create_publisher(
                    Image, self._preview_topics[camera_id],
                    qos_profile_sensor_data)
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
            self._list_cameras_service = self.create_service(
                Trigger, '~/list_cameras', self._list_cameras)
            self._camera_calibration_services = [
                self.create_service(
                    Trigger, f'~/start_calibration/{camera_id}',
                    partial(self._start_calibration, camera_id=camera_id))
                for camera_id in self._cameras
            ]
            self._stop_service = self.create_service(
                Trigger, '~/stop_episode', self._stop_episode)
            self._new_session_service = self.create_service(
                Trigger, '~/new_session', self._new_session)
            self.get_logger().info(
                f'Online session ready at {self._session_dir}; use '
                'start_episode/start_calibration, stop_episode and '
                'new_session services')

    def _log_session_task(self):
        """Report the current session task, warning when it is empty."""
        task = session_task(read_session(self._session_dir))
        if task:
            self.get_logger().info(
                f'Session {self._session_dir.name} task: {task!r}')
            return
        self.get_logger().warning(
            f'Session {self._session_dir.name} has an empty task. Fill it in '
            'before dataset export with: ros2 run umi_ros2 set_session_task '
            f'{self._session_dir} "<task>"')

    def _new_session(self, request, response):
        """Close this session and open the next one without restarting."""
        if self._episode_dir is not None:
            response.success = False
            response.message = (
                f'cannot switch session while recording {self._episode_dir}; '
                'stop the recording first')
            return response
        task = normalize_task(self.get_parameter('next_task').value)
        previous = self._session_dir
        try:
            session, copied = switch_session(
                previous, self._recordings_root, task,
                image_streams=getattr(self, '_configured_streams', None))
        except Exception as error:  # noqa: B902 - report, keep old session
            response.success = False
            response.message = (
                f'session switch failed, still using {previous}: {error}')
            self.get_logger().error(response.message)
            return response
        finally:
            # A task is used for exactly one switch request.
            self.set_parameters([
                Parameter('next_task', Parameter.Type.STRING, '')])
        self._session_dir = session
        self._episode_number = 0
        self._calibration_number = max(
            (calibration_number(path) for path in copied), default=0)
        self._calibration_retries = {}
        self.get_logger().info(
            f'Session {previous.name} complete; now recording into '
            f'{session}')
        self._log_session_task()
        if copied:
            names = ', '.join(path.name for path in copied)
            calibration_note = (
                f'copied raw calibration {names}; run calibrate_time in this '
                'session separately for each camera')
            self.get_logger().info(f'Session switch: {calibration_note}')
        else:
            calibration_note = (
                'this session has no calibration data; record one '
                '(c + Enter)')
            self.get_logger().warning(f'Session switch: {calibration_note}')
        response.success = True
        response.message = (
            f'new session {session} (task {task!r}); {calibration_note}')
        return response

    def _start_worker(self, output_path):
        """Start each persistent camera worker once per launch."""
        started = []
        try:
            for camera in self._cameras.values():
                camera.start()
                started.append(camera)
                self.get_logger().info(
                    f'{camera.camera_id} camera process launched; '
                    'performing one-time warmup')
        except Exception:
            for camera in reversed(started):
                camera.close()
            raise

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
        """Stop both persistent workers when the ROS session exits."""
        for camera in reversed(list(self._cameras.values())):
            camera.close()

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
            retry = getattr(self, '_calibration_retries', {}).get(
                self._calibration_camera_id)
            if retry is not None:
                return retry
            self._calibration_number += 1
            name = f'calibration_{self._calibration_number:03d}'
            return self._session_dir / 'calibration' / name
        self._episode_number += 1
        name = f'episode_{self._episode_number:04d}'
        return self._session_dir / 'episodes' / name

    def _start_episode(self, request, response):
        """Create one new video and pose recording."""
        return self._start_recording('episode', response)

    def _list_cameras(self, request, response):
        """Return numbered camera identities and their start services."""
        response.success = True
        response.message = json.dumps([
            {'number': number, 'camera_id': camera_id,
             'image_field': camera.image_field,
             'start_service': (
                 f'{self.get_fully_qualified_name()}/start_calibration/'
                 f'{camera_id}')}
            for number, (camera_id, camera) in enumerate(
                self._cameras.items(), 1)
        ])
        return response

    def _start_calibration(self, request, response, camera_id=None):
        """Record only the selected camera and the shared pose."""
        return self._start_recording(
            'calibration', response, camera_id or self._camera.camera_id)

    def _start_recording(self, kind, response, camera_id=None):
        """Save a 500 ms pose lead before starting the requested cameras."""
        if self._episode_dir is not None:
            response.success = False
            response.message = (
                f'already recording {self._episode_dir}')
            return response
        camera_id = camera_id or self._camera.camera_id
        camera_ids = [camera_id] if kind == 'calibration' else list(
            self._cameras)
        if any(identity not in self._cameras for identity in camera_ids):
            response.success = False
            response.message = f'unknown camera: {camera_id}'
            return response
        if not self._wait_worker_state('waiting', 30, camera_ids):
            response.success = False
            response.message = (
                'selected cameras must complete warmup before recording; '
                f'current states: {self._worker_state()}')
            return response
        if not self._wait_pose_state('waiting', 30):
            response.success = False
            response.message = (
                'pose recorder has not completed its one-time warmup')
            return response
        self._calibration_camera_id = camera_id
        retries = getattr(self, '_calibration_retries', {})
        episode = self._new_recording_dir(kind)
        pose = episode / 'pose'
        if kind == 'calibration' and camera_id in retries:
            self._discard_calibration(episode, camera_id)
        episode.mkdir(
            parents=True,
            exist_ok=kind == 'calibration' and camera_id in retries)
        self._episode_dir = episode
        self._recording_kind = kind
        self._recording_camera_ids = camera_ids
        started = []
        try:
            self._output_paths = {
                camera_id: self._prepare_output(
                    self._video_path(episode, camera_id))
                for camera_id in camera_ids
            }
            self._output_path = next(iter(self._output_paths.values()))
            self._send_pose_worker({
                'command': 'start', 'output_path': str(pose)})
            if not self._wait_pose_state('recording_ready', 5):
                raise RuntimeError(
                    'pose recorder did not write its first pose in time')
            self.get_logger().info(
                'First pose saved; recording pose for 500 ms before '
                'starting selected image streams')
            time.sleep(IMAGE_RECORDING_DELAY_SECONDS)
            for identity in camera_ids:
                camera = self._cameras[identity]
                output = Path(self._output_paths[identity])
                camera.start_recording(
                    output, output.with_suffix('.timing.json'))
                started.append(camera)
            if not self._wait_worker_state('recording', 5, camera_ids):
                raise RuntimeError(
                    'not all cameras entered recording state: '
                    f'{self._worker_state()}')
        except Exception as error:
            for camera in started:
                try:
                    camera.stop_recording()
                except (OSError, RuntimeError):
                    pass
            try:
                self._stop_pose_recording()
            except (OSError, RuntimeError):
                pass
            register_recording(
                self._session_dir, episode, kind, status='failed',
                image_streams=self._recording_streams(episode))
            if kind == 'calibration':
                self._reject_calibration(episode, camera_id, str(error))
            self._clear_recording()
            response.success = False
            response.message = f'{kind} start failed: {error}'
            self.get_logger().error(response.message)
            return response
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
        """Finalize raw files and immediately calibrate a selected camera."""
        if self._episode_dir is None:
            response.success = False
            response.message = 'no episode is recording'
            return response
        episode = self._episode_dir
        kind = self._recording_kind
        camera_id = getattr(
            self, '_calibration_camera_id', self._camera.camera_id)
        errors = self._finalize_recording()
        response.success = not errors
        response.message = (
            f'{kind} complete: {episode}' if not errors
            else f'{kind} failed: {episode}; ' + '; '.join(errors))
        if kind == 'calibration':
            accepted, detail = (
                self._calibrate_recording(episode, camera_id) if not errors
                else (False, '; '.join(errors)))
            if accepted:
                self._calibration_retries.pop(camera_id, None)
            else:
                try:
                    self._reject_calibration(episode, camera_id, detail)
                    detail += '; 已清除本次记录，按 Enter 在原目录重录'
                except OSError as error:
                    detail += f'; 清理失败，重试前需清理: {error}'
            response.success = accepted
            color = '\033[32m' if accepted else '\033[31m'
            verdict = 'accept' if accepted else 'reject'
            response.message = (
                f'{color}{camera_id}: {verdict} — {detail}\033[0m\n'
                f'标定目录: {episode}')
        if errors:
            self.get_logger().error(response.message)
        else:
            self.get_logger().info(response.message)
        if kind == 'episode':
            response.message += '\n' + self._episode_quality_message
        return response

    def _video_path(self, episode, camera_id):
        """Place every stream under its camera identity."""
        return camera_video_path(episode, camera_id)

    def _recording_streams(self, episode, camera_ids=None):
        """List every camera's raw paths relative to this recording."""
        streams = []
        identities = camera_ids or getattr(
            self, '_recording_camera_ids', None) or self._cameras
        for camera_id in identities:
            camera = self._cameras[camera_id]
            video = self._video_path(episode, camera_id)
            streams.append({
                'camera_id': camera_id,
                'image_field': camera.image_field,
                'video_path': str(video.relative_to(episode)),
                'timing_path': str(video.with_suffix(
                    '.timing.json').relative_to(episode)),
                'validation_path': str(video.with_suffix(
                    '.validation.json').relative_to(episode)),
            })
        return streams

    def _clear_recording(self):
        self._episode_dir = None
        self._recording_kind = None
        self._recording_camera_ids = None
        self._output_path = ''
        self._output_paths = {}

    def _finalize_recording(self):
        """Stop both cameras, validate raw files and close the shared pose."""
        episode = self._episode_dir
        kind = self._recording_kind
        errors = []
        stopped = set()
        camera_ids = getattr(
            self, '_recording_camera_ids', None) or self._cameras
        for camera_id in camera_ids:
            camera = self._cameras[camera_id]
            try:
                camera.stop_recording()
                stopped.add(camera_id)
            except (OSError, RuntimeError) as error:
                errors.append(f'{camera_id} stop failed: {error}')
        for camera_id in camera_ids:
            camera = self._cameras[camera_id]
            output = self._output_paths.get(camera_id)
            if output is None or camera_id not in stopped:
                continue
            timing_path = Path(output).with_suffix('.timing.json')
            if not self._wait_timing_complete(timing_path, 20):
                errors.append(f'{camera_id} video finalization timed out')
                continue
            try:
                timing = json.loads(timing_path.read_text(encoding='utf-8'))
                if timing.get('status') != 'complete':
                    errors.append(f'{camera_id} timing status is failed')
                report = self._write_validation(output, camera.poll())
                if (not report.get('decode_ok')
                        or not report.get('frame_count_matches')):
                    errors.append(f'{camera_id} video validation failed')
            except (OSError, ValueError, KeyError) as error:
                errors.append(f'{camera_id} validation failed: {error}')
        try:
            self._stop_pose_recording()
        except (OSError, RuntimeError) as error:
            errors.append(f'pose finalization failed: {error}')
        register_recording(
            self._session_dir, episode, kind,
            status='failed' if errors else 'complete',
            image_streams=self._recording_streams(episode))
        if kind == 'episode':
            result = diagnose_episode(
                episode, self._recording_streams(episode), errors)
            try:
                (episode / 'quality.json').write_text(
                    json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
            except OSError as error:
                result['accepted'] = False
                result['verdict'] = 'reject'
                result['reasons'].append(f'诊断结果保存失败: {error}')
            self._episode_quality_message = format_verdict(
                result, episode.name)
            self.get_logger().info(self._episode_quality_message)
        self._clear_recording()
        return errors

    def _discard_calibration(self, episode, camera_id):
        """Delete rejected inputs/results, retaining the recording folder."""
        for directory in (episode / 'cameras' / camera_id, episode / 'pose'):
            if directory.exists():
                shutil.rmtree(directory)
        for name in ('time_offset.json', 'alignment_report.png'):
            (episode / name).unlink(missing_ok=True)

    def _reject_calibration(self, episode, camera_id, reason):
        """Invalidate one camera and reserve the same path for its retry."""
        if not hasattr(self, '_calibration_retries'):
            self._calibration_retries = {}
        self._calibration_retries[camera_id] = episode
        update_temporal_calibration(self._session_dir, camera_id, {
            'status': 'rejected', 'result': None, 'camera_id': camera_id,
            'image_field': self._cameras[camera_id].image_field,
            'calibrated_at': now_text(), 'error': reason,
        })
        register_recording(
            self._session_dir, episode, 'calibration', status='rejected',
            image_streams=self._recording_streams(episode, [camera_id]))
        self._discard_calibration(episode, camera_id)

    def _calibrate_recording(self, episode, camera_id='wrist'):
        """Estimate and report the offset as soon as raw files are closed."""
        try:
            from umi_ros2.synchronization.calibrate_time import (
                argument_parser, calibrate)

            args = argument_parser().parse_args([
                str(episode), '--camera-id', camera_id])
            # The CLI function normally prints its complete JSON report.
            # Capture it here and return the useful summary in the service.
            with contextlib.redirect_stdout(io.StringIO()):
                status = calibrate(args)
            result_path = episode / 'time_offset.json'
            result = json.loads(result_path.read_text(encoding='utf-8'))
            offset_ms = result['video_to_pose_offset_milliseconds']
            report_path = episode / 'alignment_report.png'
            if status == 0 and result.get('accepted'):
                return True, (
                    f'video-to-pose offset: {offset_ms:.2f} ms; '
                    f'report: {report_path}')
            return False, '平移轨迹拟合或分段一致性未通过原有标定阈值'
        except Exception as error:
            reason = f'{type(error).__name__}: {error}'
            try:
                update_temporal_calibration(self._session_dir, camera_id, {
                    'status': 'rejected',
                    'result': None,
                    'camera_id': camera_id,
                    'calibrated_at': now_text(),
                    'error': reason,
                })
            except Exception as metadata_error:
                reason += (
                    '; could not update session metadata: '
                    f'{metadata_error}')
            return False, f'标定执行失败: {reason}'

    @staticmethod
    def _state_from(path):
        try:
            return json.loads(
                path.read_text(encoding='utf-8'))['state']
        except (OSError, KeyError, json.JSONDecodeError):
            return None

    def _worker_state(self):
        return {camera_id: camera.state()
                for camera_id, camera in self._cameras.items()}

    def _wait_worker_state(self, expected, timeout, camera_ids=None):
        deadline = time.monotonic() + timeout
        for identity in camera_ids or self._cameras:
            camera = self._cameras[identity]
            remaining = deadline - time.monotonic()
            if (remaining <= 0
                    or not camera.wait_for_state(expected, remaining)):
                return False
        return True

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

    def _publish_latest_preview(self):
        for camera_id, camera in self._cameras.items():
            frame = camera.latest_preview()
            if frame is None:
                continue
            message = Image()
            message.header.frame_id = self._frame_ids[camera_id]
            message.header.stamp.sec = (
                frame.receive_unix_ns // 1_000_000_000)
            message.header.stamp.nanosec = (
                frame.receive_unix_ns % 1_000_000_000)
            message.height = frame.height
            message.width = frame.width
            message.encoding = frame.encoding
            message.is_bigendian = False
            message.step = frame.width * 3
            message.data = frame.data
            self._preview_publishers[camera_id].publish(message)

    def _check_process(self):
        for camera_id, camera in self._cameras.items():
            return_code = camera.poll()
            if not self._closed and return_code is not None:
                raise RuntimeError(
                    f'{camera_id} GStreamer process exited with code '
                    f'{return_code}')
        if (not self._closed and self._pose_process is not None
                and self._pose_process.poll() is not None):
            raise RuntimeError(
                'Persistent pose recorder exited unexpectedly with code '
                f'{self._pose_process.returncode}')

    def close(self):
        """Finalize active raw recordings, then stop all workers."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._episode_dir is not None:
                errors = self._finalize_recording()
                if errors:
                    self.get_logger().error(
                        'Recording finalized with errors: '
                        + '; '.join(errors))
        finally:
            try:
                self._stop_worker()
            finally:
                self._stop_pose_worker()
                if self._session_dir is not None:
                    update_session(
                        self._session_dir, status='complete',
                        ended_at=now_text())
                if self._runtime_dir is not None:
                    shutil.rmtree(self._runtime_dir, ignore_errors=True)

    def _write_validation(self, output_path, return_code):
        """Validate the finalized video and combine worker timing facts."""
        report = validate_video(output_path)
        report['capture_exit_code'] = return_code
        report['clean_shutdown'] = return_code in (None, 0)
        timing_path = Path(output_path).with_suffix('.timing.json')
        if timing_path.exists():
            timing = json.loads(timing_path.read_text(encoding='utf-8'))
            report['recording_started'] = 'first_source_pts_ns' in timing
            report['accepted_source_frames'] = timing['accepted_frames']
            report['frame_count_matches'] = (
                report.get('decoded_frames') == timing['accepted_frames']
                and timing['accepted_frames'] > 0
            )
        Path(output_path).with_suffix('.validation.json').write_text(
            json.dumps(report, indent=2) + '\n', encoding='utf-8'
        )
        return report


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
            'timestamped_frames': len(stamps),
            'max_timestamp_gap_seconds': max(gaps, default=None),
            'min_timestamp_gap_seconds': min(gaps, default=None),
            'first_frame_pts_seconds': stamps[0] if stamps else None,
            'last_frame_pts_seconds': stamps[-1] if stamps else None,
            'image_gap_count': sum(
                gap > IMAGE_GAP_LIMIT_SECONDS for gap in gaps),
            'first_20_frame_pts_seconds': stamps[:20],
            'non_increasing_timestamps': sum(gap <= 0 for gap in gaps),
            'errors': result.stderr[-4000:],
        })
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        report.update({'decode_ok': False, 'errors': str(error)})
    return report


def main(args=None):
    """Run color camera recording and ROS preview publication."""
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
