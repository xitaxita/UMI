"""Small terminal client for toggling online episode services."""

import rclpy
from rclpy.node import Node

from std_srvs.srv import Trigger


class EpisodeKeyboard(Node):
    """Toggle start/stop on Enter while the launch keeps running."""

    def __init__(self):
        """Create service clients and start in the idle state."""
        super().__init__('online_episode_keyboard')
        self._recording = False
        self._recording_kind = None
        self._start = self.create_client(
            Trigger, '/action4_h264_capture_node/start_episode')
        self._calibration = self.create_client(
            Trigger, '/action4_h264_capture_node/start_calibration')
        self._stop = self.create_client(
            Trigger, '/action4_h264_capture_node/stop_episode')

    def run(self):
        """Wait for services and accept line-oriented terminal controls."""
        print(
            'Idle: Enter starts episode, c + Enter starts calibration | '
            'Recording: Enter stops | q + Enter leaves keyboard control')
        while rclpy.ok():
            key = input().strip().lower()
            if key == 'q':
                return
            if self._recording:
                client = self._stop
                requested_kind = None
            elif key == 'c':
                client = self._calibration
                requested_kind = 'calibration'
            else:
                client = self._start
                requested_kind = 'episode'
            if not client.wait_for_service(timeout_sec=5):
                print('Episode service is unavailable')
                continue
            future = client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future)
            result = future.result()
            print(result.message)
            if result.success:
                self._recording = not self._recording
                self._recording_kind = (
                    requested_kind if self._recording else None)


def main(args=None):
    """Run the interactive episode controller."""
    rclpy.init(args=args)
    node = EpisodeKeyboard()
    try:
        node.run()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
