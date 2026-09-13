"""Reconstruct a Vive path from recorded pose messages during playback."""

from geometry_msgs.msg import PoseStamped

from nav_msgs.msg import Path

import rclpy
from rclpy.node import Node

from std_srvs.srv import Trigger


class ReplayPathNode(Node):
    """Accumulate replayed Vive poses into a bounded visualization path."""

    def __init__(self):
        """Create the pose subscriber and path publisher."""
        super().__init__('vive_replay_path_node')
        self.declare_parameter('pose_topic', 'vive/pose')
        self.declare_parameter('path_topic', 'vive/path')
        self.declare_parameter('max_path_points', 10000)
        self._max_path_points = int(
            self.get_parameter('max_path_points').value
        )
        if self._max_path_points <= 0:
            raise ValueError('max_path_points must be greater than zero')
        self._path = Path()
        self._publisher = self.create_publisher(
            Path, str(self.get_parameter('path_topic').value), 10
        )
        self._subscription = self.create_subscription(
            PoseStamped,
            str(self.get_parameter('pose_topic').value),
            self._on_pose,
            10,
        )
        self._reset_service = self.create_service(
            Trigger, '~/reset', self._reset)

    def _reset(self, request, response):
        """Clear the path before the next session recording is replayed."""
        self._path = Path()
        self._publisher.publish(self._path)
        response.success = True
        response.message = 'replay path reset'
        return response

    def _on_pose(self, pose):
        self._path.header = pose.header
        self._path.poses.append(pose)
        if len(self._path.poses) > self._max_path_points:
            del self._path.poses[:-self._max_path_points]
        self._publisher.publish(self._path)


def main(args=None):
    """Run the replay path reconstruction node."""
    rclpy.init(args=args)
    node = ReplayPathNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
