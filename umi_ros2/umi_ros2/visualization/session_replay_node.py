"""Replay separated MP4 and pose recordings in RViz, sequentially."""

import signal
import subprocess
import threading
import time

import cv2

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from rosgraph_msgs.msg import Clock

from sensor_msgs.msg import Image

from std_srvs.srv import Trigger

from umi_ros2.visualization.replay_source import (
    relative_start_seconds,
    resolve_replay_items,
)


class SessionReplayNode(Node):
    """Publish MP4 previews while sequentially playing matching pose bags."""

    def __init__(self):
        """Resolve replay input and start the background coordinator."""
        super().__init__('umi_session_replay_node')
        self.declare_parameter('input_path', '')
        self.declare_parameter('playback_rate', 1.0)
        self.declare_parameter('preview_topic', '/action4/image_preview')
        self.declare_parameter('frame_id', 'action4_camera')
        self.declare_parameter('preview_width', 640)
        self.declare_parameter('preview_height', 360)
        self.declare_parameter('between_items_seconds', 1.0)
        input_path = str(self.get_parameter('input_path').value)
        self._rate = float(self.get_parameter('playback_rate').value)
        if not input_path:
            raise ValueError('input_path must not be empty')
        if self._rate <= 0:
            raise ValueError('playback_rate must be greater than zero')
        self._items = resolve_replay_items(input_path)
        self._frame_id = str(self.get_parameter('frame_id').value)
        self._width = int(self.get_parameter('preview_width').value)
        self._height = int(self.get_parameter('preview_height').value)
        self._between_items = float(
            self.get_parameter('between_items_seconds').value)
        self._publisher = self.create_publisher(
            Image,
            str(self.get_parameter('preview_topic').value),
            qos_profile_sensor_data,
        )
        self._reset_client = self.create_client(
            Trigger, '/vive_replay_path_node/reset')
        self._clock_condition = threading.Condition()
        self._clock_ns = None
        self._clock_subscription = self.create_subscription(
            Clock, '/clock', self._on_clock, qos_profile_sensor_data)
        self._stop = threading.Event()
        self._error = None
        self._bag_process = None
        self._worker = threading.Thread(
            target=self._run, name='umi_session_replay', daemon=True)
        self._worker.start()
        self.get_logger().info(
            f'Resolved {len(self._items)} replay item(s) from {input_path}')

    @property
    def finished(self):
        """Return whether all selected recordings have finished."""
        return not self._worker.is_alive()

    @property
    def error(self):
        """Return the background replay error, if one occurred."""
        return self._error

    def _reset_path(self):
        if not self._reset_client.wait_for_service(timeout_sec=5):
            self.get_logger().warning('Path reset service is unavailable')
            return
        future = self._reset_client.call_async(Trigger.Request())
        deadline = time.monotonic() + 2
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.01)

    def _on_clock(self, message):
        """Wake video playback when rosbag simulated time advances."""
        with self._clock_condition:
            self._clock_ns = (
                message.clock.sec * 1_000_000_000 + message.clock.nanosec)
            self._clock_condition.notify_all()

    def _run(self):
        try:
            for index, item in enumerate(self._items, start=1):
                if self._stop.is_set():
                    break
                self._reset_path()
                self.get_logger().info(
                    f'Replaying {index}/{len(self._items)}: {item.path}')
                self._play_item(item)
                if index < len(self._items):
                    self._stop.wait(self._between_items)
        except Exception as error:
            self._error = error
            self.get_logger().error(f'Replay failed: {error}')

    def _play_item(self, item):
        video_delay, pose_delay = relative_start_seconds(item)
        command = [
            'ros2', 'bag', 'play', str(item.pose_path),
            '--clock', '30', '--rate', str(self._rate),
        ]
        # rosbag's /clock is the scheduling authority. These values remain in
        # the log to make the recorded pre-roll relationship visible.
        self.get_logger().info(
            f'Recorded starts: video +{video_delay:.3f}s, '
            f'pose +{pose_delay:.3f}s from common start')
        self._bag_process = subprocess.Popen(command)
        capture = cv2.VideoCapture(str(item.video_path))
        if not capture.isOpened():
            self._stop_bag()
            raise RuntimeError(f'cannot open video: {item.video_path}')
        published_frames = 0
        skipped_frames = 0
        try:
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    break
                pts = max(0.0, capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
                stamp_ns = item.video_start_ns + int(pts * 1e9)
                if not self._wait_until_clock(stamp_ns):
                    break
                with self._clock_condition:
                    clock_ns = self._clock_ns
                frame_period_ns = int(1_000_000_000 / 30)
                if clock_ns - stamp_ns > frame_period_ns:
                    skipped_frames += 1
                    continue
                self._publish(frame, stamp_ns)
                published_frames += 1
        finally:
            capture.release()
        return_code = self._wait_bag()
        self.get_logger().info(
            f'Replay item complete: published {published_frames} preview '
            f'frames, skipped {skipped_frames} pre-roll/late frames')
        if not self._stop.is_set() and return_code != 0:
            raise RuntimeError(
                f'pose bag playback exited with code {return_code}')

    def _wait_until_clock(self, target_ns):
        """Wait until bag time reaches a video frame's absolute timestamp."""
        with self._clock_condition:
            while not self._stop.is_set():
                if self._clock_ns is not None and self._clock_ns >= target_ns:
                    return True
                if (self._bag_process is not None
                        and self._bag_process.poll() is not None):
                    return False
                self._clock_condition.wait(timeout=0.1)
        return False

    def _publish(self, frame, stamp_ns):
        frame = cv2.resize(frame, (self._width, self._height))
        message = Image()
        message.header.frame_id = self._frame_id
        message.header.stamp.sec = stamp_ns // 1_000_000_000
        message.header.stamp.nanosec = stamp_ns % 1_000_000_000
        message.height = self._height
        message.width = self._width
        message.encoding = 'bgr8'
        message.is_bigendian = False
        message.step = self._width * 3
        message.data = frame.tobytes()
        self._publisher.publish(message)

    def _wait_bag(self):
        while self._bag_process.poll() is None and not self._stop.wait(0.1):
            pass
        if self._stop.is_set() and self._bag_process.poll() is None:
            self._stop_bag()
        return self._bag_process.returncode

    def _stop_bag(self):
        if self._bag_process is None or self._bag_process.poll() is not None:
            return
        self._bag_process.send_signal(signal.SIGINT)
        try:
            self._bag_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._bag_process.terminate()
            self._bag_process.wait(timeout=5)

    def close(self):
        """Stop the active bag player and join the replay worker."""
        self._stop.set()
        with self._clock_condition:
            self._clock_condition.notify_all()
        self._stop_bag()
        self._worker.join(timeout=10)


def main(args=None):
    """Run the session-aware replay coordinator."""
    rclpy.init(args=args)
    node = SessionReplayNode()
    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        error = node.error
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 1 if error else 0


if __name__ == '__main__':
    raise SystemExit(main())
