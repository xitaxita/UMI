"""Small terminal client for toggling online episode services."""

from rcl_interfaces.srv import SetParameters

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

from std_srvs.srv import Trigger


CAMERA_NODE = '/action4_h264_capture_node'


class EpisodeKeyboard(Node):
    """Toggle start/stop on Enter while the launch keeps running."""

    def __init__(self):
        """Create service clients and start in the idle state."""
        super().__init__('online_episode_keyboard')
        self._recording = False
        self._recording_kind = None
        self._start = self.create_client(
            Trigger, f'{CAMERA_NODE}/start_episode')
        self._calibration = self.create_client(
            Trigger, f'{CAMERA_NODE}/start_calibration')
        self._stop = self.create_client(
            Trigger, f'{CAMERA_NODE}/stop_episode')
        self._new_session = self.create_client(
            Trigger, f'{CAMERA_NODE}/new_session')
        self._set_parameters = self.create_client(
            SetParameters, f'{CAMERA_NODE}/set_parameters')

    def _call(self, client, request):
        """Call one service and return its result, or None if unavailable."""
        if not client.wait_for_service(timeout_sec=5):
            print(f'Service {client.srv_name} is unavailable')
            return None
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        return future.result()

    def _switch_session(self):
        """Ask for the next task and switch the camera node's session."""
        task = input(
            'Task for the new session (Enter leaves it empty): ').strip()
        request = SetParameters.Request()
        request.parameters = [
            Parameter('next_task', Parameter.Type.STRING, task)
            .to_parameter_msg()]
        result = self._call(self._set_parameters, request)
        if result is None:
            return
        if not all(item.successful for item in result.results):
            reasons = '; '.join(item.reason for item in result.results)
            print(f'Could not set the next task: {reasons}')
            return
        result = self._call(self._new_session, Trigger.Request())
        if result is not None:
            print(result.message)
            if result.success and not task:
                print('Warning: the new session has an empty task; fill it '
                      'in later with set_session_task')

    def run(self):
        """Wait for services and accept line-oriented terminal controls."""
        print(
            'Idle: Enter starts episode, c + Enter starts calibration, '
            'n + Enter switches to a new session/task | '
            'Recording: Enter stops | q + Enter leaves keyboard control')
        while rclpy.ok():
            key = input().strip().lower()
            if key == 'q':
                return
            if key == 'n':
                if self._recording:
                    print('Recording continues: stop it with Enter before '
                          'switching session')
                else:
                    self._switch_session()
                continue
            if self._recording:
                client = self._stop
                requested_kind = None
            elif key == 'c':
                client = self._calibration
                requested_kind = 'calibration'
            else:
                client = self._start
                requested_kind = 'episode'
            result = self._call(client, Trigger.Request())
            if result is None:
                continue
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
