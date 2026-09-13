"""ROS 2 node publishing a selected Vive pose from pysurvive."""

import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Path
from rclpy.node import Node
from tf2_ros import TransformBroadcaster

from .backend import PySurviveBackend


class VivePoseNode(Node):
    """Publish current Vive pose, bounded path, and optional TF."""

    def __init__(self, backend_factory=PySurviveBackend):
        super().__init__('vive_pose_node')
        self.declare_parameter('device_name', '')
        self.declare_parameter('device_serial', '')
        self.declare_parameter('device_index', -1)
        self.declare_parameter('libsurvive_args', '')
        self.declare_parameter('world_frame', 'vive_world')
        self.declare_parameter('child_frame', 'vive_tracker')
        self.declare_parameter('pose_topic', 'vive/pose')
        self.declare_parameter('path_topic', 'vive/path')
        self.declare_parameter('max_path_points', 10000)
        self.declare_parameter('publish_hz', 90.0)
        self.declare_parameter('publish_tf', True)

        publish_hz = float(self.get_parameter('publish_hz').value)
        if publish_hz <= 0.0:
            raise ValueError('publish_hz must be greater than zero')
        self._max_path_points = int(
            self.get_parameter('max_path_points').value
        )
        if self._max_path_points <= 0:
            raise ValueError('max_path_points must be greater than zero')
        self._world_frame = self.get_parameter('world_frame').value
        self._child_frame = self.get_parameter('child_frame').value
        self._publisher = self.create_publisher(
            PoseStamped, self.get_parameter('pose_topic').value, 10
        )
        self._path_publisher = self.create_publisher(
            Path, self.get_parameter('path_topic').value, 10
        )
        self._path = Path()
        self._path.header.frame_id = self._world_frame
        self._tf_broadcaster = (
            TransformBroadcaster(self)
            if self.get_parameter('publish_tf').value else None
        )
        self._backend = backend_factory(
            device_name=self.get_parameter('device_name').value,
            device_serial=self.get_parameter('device_serial').value,
            device_index=self.get_parameter('device_index').value,
            libsurvive_args=self.get_parameter('libsurvive_args').value,
        )
        selector = self._backend.start()
        self.get_logger().info(
            f'Publishing pysurvive updates for {selector} at {publish_hz:g} Hz'
        )
        self._timer = self.create_timer(1.0 / publish_hz, self._publish_pose)

    def _publish_pose(self):
        pose = self._backend.read_pose()
        if pose is None:
            return
        position, orientation = pose
        message = PoseStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self._world_frame
        (
            message.pose.position.x,
            message.pose.position.y,
            message.pose.position.z,
        ) = position
        (message.pose.orientation.x, message.pose.orientation.y,
         message.pose.orientation.z, message.pose.orientation.w) = orientation
        self._publisher.publish(message)

        self._path.header.stamp = message.header.stamp
        self._path.poses.append(message)
        if len(self._path.poses) > self._max_path_points:
            del self._path.poses[:-self._max_path_points]
        self._path_publisher.publish(self._path)

        if self._tf_broadcaster is not None:
            transform = TransformStamped()
            transform.header = message.header
            transform.child_frame_id = self._child_frame
            transform.transform.translation.x = message.pose.position.x
            transform.transform.translation.y = message.pose.position.y
            transform.transform.translation.z = message.pose.position.z
            transform.transform.rotation = message.pose.orientation
            self._tf_broadcaster.sendTransform(transform)

    def destroy_node(self):
        """Close the backend before destroying the ROS node."""
        self._backend.stop()
        return super().destroy_node()


def main(args=None):
    """Run the Vive pose node."""
    rclpy.init(args=args)
    node = None
    try:
        node = VivePoseNode()
        rclpy.spin(node)
    except (RuntimeError, ValueError) as error:
        if node is not None:
            node.get_logger().fatal(str(error))
        else:
            print(f'vive_pose_node: {error}')
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
