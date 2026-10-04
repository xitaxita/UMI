"""Small terminal client for toggling online episode services."""

import json

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
        self._camera_list = self.create_client(
            Trigger, f'{CAMERA_NODE}/list_cameras')
        self._calibration = None
        self._calibration_retry = False
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
            if result.success:
                self._calibration_retry = False

    def _select_calibration(self):
        """Choose a live registered camera before starting its calibration."""
        result = self._call(self._camera_list, Trigger.Request())
        if result is None or not result.success:
            return False
        try:
            cameras = json.loads(result.message)
            choices = {str(camera['number']): camera for camera in cameras}
        except (ValueError, KeyError, TypeError):
            print('无法读取相机列表')
            return False
        if not choices:
            print('没有可标定的相机')
            return False
        print('选择时序标定相机：')
        for number, camera in choices.items():
            print(f"  {number}: {camera['camera_id']} / "
                  f"{camera['image_field']}")
        print('只做左右、前后、上下平移，保持姿态固定，标记全程可见。\n'
              'wrist：固定 ArUco 标记，移动相机与 Tracker 组件。\n'
              'left：固定相机，将标记与 Tracker/夹爪固定在一起并平移。')
        while True:
            number = input('相机编号 + Enter 开始录制（q 返回）：').strip()
            if number == 'q':
                return False
            if number in choices:
                break
            print('编号无效，请重新选择')
        previous = self._calibration
        self._calibration = self.create_client(
            Trigger, choices[number]['start_service'])
        if previous is not None:
            self.destroy_client(previous)
        self._calibration_retry = True
        return True

    def run(self):
        """Wait for services and accept line-oriented terminal controls."""
        print(
            'Idle: Enter starts episode, c + Enter selects a camera, '
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
                if not self._select_calibration():
                    continue
                client = self._calibration
                requested_kind = 'calibration'
            elif key == '' and getattr(self, '_calibration_retry', False):
                client = self._calibration
                requested_kind = 'calibration'
            else:
                if key:
                    print('请输入 Enter、c、n 或 q')
                    continue
                client = self._start
                requested_kind = 'episode'
            result = self._call(client, Trigger.Request())
            if result is None:
                continue
            print(result.message)
            stopped_kind = self._recording_kind
            if result.success or client is self._stop:
                self._recording = not self._recording
                self._recording_kind = (
                    requested_kind if self._recording else None)
            if client is self._stop and stopped_kind == 'calibration':
                self._calibration_retry = not result.success
                if self._calibration_retry:
                    print('Enter 重录当前相机；c 选择相机；n 换 session；q 退出')
            elif requested_kind == 'calibration':
                self._calibration_retry = not result.success


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
