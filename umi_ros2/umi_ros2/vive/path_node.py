"""Sample live Vive poses into a separately published visualization path."""

import math

from geometry_msgs.msg import PoseStamped

from nav_msgs.msg import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy


class VivePathNode(Node):
    """Keep the latest pose and update a bounded path at the display rate."""

    def __init__(self):
        """Create the lightweight subscriber and sampling timer."""
        super().__init__('vive_path_node')
        self.declare_parameter('pose_topic', 'vive/pose')
        self.declare_parameter('path_topic', 'vive/path')
        self.declare_parameter('sample_hz', 30.0)
        self.declare_parameter('max_path_points', 10000)
        sample_hz = float(self.get_parameter('sample_hz').value)
        if not math.isfinite(sample_hz) or sample_hz <= 0.0:
            raise ValueError('sample_hz must be finite and greater than zero')
        self._max_path_points = int(
            self.get_parameter('max_path_points').value)
        if self._max_path_points <= 0:
            raise ValueError('max_path_points must be greater than zero')

        self._latest_pose = None
        self._path = Path()
        self._publisher = self.create_publisher(
            Path, str(self.get_parameter('path_topic').value), 1)
        self._subscription = self.create_subscription(
            PoseStamped, str(self.get_parameter('pose_topic').value),
            self._on_pose, QoSProfile(
                depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        self._timer = self.create_timer(1.0 / sample_hz, self._publish_path)
        self.get_logger().info(
            f'Sampling latest Vive pose and publishing path at '
            f'{sample_hz:g} Hz (maximum {self._max_path_points} points)')

    def _on_pose(self, pose):
        """Replace the display candidate without publishing or accumulating."""
        self._latest_pose = pose

    def _publish_path(self):
        """Append one fresh sample per tick without repeating paused input."""
        pose = self._latest_pose
        if pose is None:
            return
        self._latest_pose = None
        if self._path.header.frame_id != pose.header.frame_id:
            self._path = Path()
        self._path.header = pose.header
        self._path.poses.append(pose)
        if len(self._path.poses) > self._max_path_points:
            del self._path.poses[:-self._max_path_points]
        self._publisher.publish(self._path)


def main(args=None):
    """Run live path visualization in its own ROS process."""
    rclpy.init(args=args)
    node = None
    try:
        node = VivePathNode()
        rclpy.spin(node)
    except (RuntimeError, ValueError) as error:
        print(f'vive_path_node: {error}')
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
