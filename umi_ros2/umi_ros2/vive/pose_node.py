"""ROS 2 node publishing a selected Vive pose from pysurvive."""

from geometry_msgs.msg import PoseStamped, TransformStamped

from nav_msgs.msg import Path

import rclpy
from rclpy.node import Node

from tf2_ros import TransformBroadcaster

from .backend import PySurviveBackend


TRACKER_TO_GRIPPER_TRANSLATION = (
    0.0, -0.080371453, 0.194957425)
TRACKER_TO_GRIPPER_ROTATION = (
    0.628736470, -0.628736470, 0.323559039, 0.323559039)


def _quaternion_multiply(left, right):
    """Compose two ROS-order XYZW quaternions."""
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def _rotate_vector(quaternion, vector):
    """Rotate a vector by a normalized ROS-order XYZW quaternion."""
    x, y, z, w = quaternion
    vx, vy, vz = vector
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def _gripper_pose(tracker_position, tracker_orientation):
    """Compose world->tracker with the measured tracker->gripper pose."""
    offset = _rotate_vector(
        tracker_orientation, TRACKER_TO_GRIPPER_TRANSLATION)
    return (
        tuple(value + delta for value, delta in zip(
            tracker_position, offset)),
        _quaternion_multiply(
            tracker_orientation, TRACKER_TO_GRIPPER_ROTATION),
    )


class VivePoseNode(Node):
    """Publish gripper pose, path, and optional world-to-TCP TF."""

    def __init__(self, backend_factory=PySurviveBackend):
        """Initialize publishers and the selected Vive backend."""
        super().__init__('vive_pose_node')
        self.declare_parameter('device_name', '')
        self.declare_parameter('device_serial', '')
        self.declare_parameter('device_index', -1)
        self.declare_parameter('libsurvive_args', '')
        self.declare_parameter('world_frame', 'vive_world')
        self.declare_parameter('tracker_frame', 'vive_tracker')
        self.declare_parameter('child_frame', 'gripper_tcp')
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
        self._tracker_frame = self.get_parameter('tracker_frame').value
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
        tracker_position, tracker_orientation = pose
        position, orientation = _gripper_pose(
            tracker_position, tracker_orientation)
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
            tracker_transform = TransformStamped()
            tracker_transform.header = message.header
            tracker_transform.child_frame_id = self._tracker_frame
            (
                tracker_transform.transform.translation.x,
                tracker_transform.transform.translation.y,
                tracker_transform.transform.translation.z,
            ) = tracker_position
            (
                tracker_transform.transform.rotation.x,
                tracker_transform.transform.rotation.y,
                tracker_transform.transform.rotation.z,
                tracker_transform.transform.rotation.w,
            ) = tracker_orientation

            gripper_transform = TransformStamped()
            gripper_transform.header = message.header
            gripper_transform.child_frame_id = self._child_frame
            (
                gripper_transform.transform.translation.x,
                gripper_transform.transform.translation.y,
                gripper_transform.transform.translation.z,
            ) = position
            (
                gripper_transform.transform.rotation.x,
                gripper_transform.transform.rotation.y,
                gripper_transform.transform.rotation.z,
                gripper_transform.transform.rotation.w,
            ) = orientation
            self._tf_broadcaster.sendTransform(
                [tracker_transform, gripper_transform])

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
