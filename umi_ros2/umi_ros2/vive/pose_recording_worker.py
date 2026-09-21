"""Persistent online pose subscriber with per-recording MCAP writers."""

import json
import queue
import signal
import sys
import threading
import time
from pathlib import Path

from geometry_msgs.msg import PoseStamped

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.serialization import serialize_message

from tf2_msgs.msg import TFMessage


TOPICS = (
    ('/vive/pose', 'geometry_msgs/msg/PoseStamped'),
    ('/tf', 'tf2_msgs/msg/TFMessage'),
    ('/tf_static', 'tf2_msgs/msg/TFMessage'),
)


class PoseRecordingWorker(Node):
    """Keep pose/TF subscriptions alive and switch MCAP output on command."""

    def __init__(self, config):
        """Start subscriptions and the one-time pose warmup."""
        super().__init__('online_pose_recording_worker')
        self._warmup_seconds = float(config['warmup_seconds'])
        self._startup_timeout_seconds = float(
            config['startup_timeout_seconds'])
        self._status_path = Path(config['status_path'])
        self._started_at = time.monotonic()
        self._pose_seen = False
        self._writer = None
        self._pose_count = 0
        self._cached_tf_static = None
        self._commands = queue.Queue()
        self._stopping = False
        self._status = {'state': 'warming_up', 'error': ''}
        self._save_status()
        normal_qos = QoSProfile(
            depth=100, reliability=ReliabilityPolicy.RELIABLE)
        static_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(
            PoseStamped, '/vive/pose', self._on_pose, normal_qos)
        self.create_subscription(
            TFMessage, '/tf', self._on_tf, normal_qos)
        self.create_subscription(
            TFMessage, '/tf_static', self._on_tf_static, static_qos)
        self.create_timer(0.02, self._tick)
        if config.get('read_commands', True):
            threading.Thread(
                target=self._read_commands, name='pose_command_reader',
                daemon=True).start()

    def _save_status(self):
        temporary = self._status_path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(self._status, indent=2) + '\n', encoding='utf-8')
        temporary.replace(self._status_path)

    def _set_state(self, state, **details):
        self._status = {'state': state, 'error': '', **details}
        self._save_status()

    def _on_pose(self, message):
        self._pose_seen = True
        self._write('/vive/pose', message)
        if self._writer is not None:
            self._pose_count += 1
            if self._pose_count == 1:
                self._set_state(
                    'recording_ready', first_pose_unix_ns=time.time_ns())

    def _on_tf(self, message):
        self._write('/tf', message)

    def _on_tf_static(self, message):
        self._cached_tf_static = message
        self._write('/tf_static', message)

    def _write(self, topic, message):
        if self._writer is None:
            return
        self._writer.write(
            topic, serialize_message(message),
            self.get_clock().now().nanoseconds)

    def _start_recording(self, output_path):
        if self._writer is not None:
            raise RuntimeError('pose writer is already recording')
        import rosbag2_py
        writer = rosbag2_py.SequentialWriter()
        writer.open(
            rosbag2_py.StorageOptions(uri=output_path, storage_id='mcap'),
            rosbag2_py.ConverterOptions('', ''),
        )
        for topic, message_type in TOPICS:
            writer.create_topic(rosbag2_py.TopicMetadata(
                id=0, name=topic, type=message_type,
                serialization_format='cdr'))
        self._writer = writer
        self._pose_count = 0
        self._set_state('recording', output_path=output_path)
        if self._cached_tf_static is not None:
            self._write('/tf_static', self._cached_tf_static)

    def _stop_recording(self):
        if self._writer is None:
            return
        pose_count = self._pose_count
        self._writer.close()
        self._writer = None
        self._pose_count = 0
        self._set_state('waiting', last_recording_pose_count=pose_count)

    def _read_commands(self):
        for line in sys.stdin:
            try:
                self._commands.put(json.loads(line))
            except json.JSONDecodeError as error:
                self.get_logger().error(f'Invalid pose command: {error}')

    def _tick(self):
        elapsed = time.monotonic() - self._started_at
        if (self._status['state'] == 'warming_up'
                and self._pose_seen
                and elapsed >= self._warmup_seconds):
            self._set_state('waiting', warmup_complete=True)
        elif (self._status['state'] == 'warming_up'
              and elapsed > self._startup_timeout_seconds):
            raise RuntimeError(
                'pose recorder did not receive Vive pose during warmup')
        try:
            command = self._commands.get_nowait()
        except queue.Empty:
            return
        if command['command'] == 'start':
            self._start_recording(command['output_path'])
        elif command['command'] == 'stop':
            self._stop_recording()

    def close(self):
        """Finalize an active MCAP writer."""
        self._stop_recording()


def main():
    """Run the internal persistent pose recorder."""
    rclpy.init()
    node = PoseRecordingWorker(json.loads(sys.argv[1]))

    def stop(signum, frame):
        node._stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while rclpy.ok() and not node._stopping:
            rclpy.spin_once(node, timeout_sec=0.1)
    except Exception as error:
        node._status = {'state': 'failed', 'error': str(error)}
        node._save_status()
        node.get_logger().fatal(str(error))
        return 1
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
