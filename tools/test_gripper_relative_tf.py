#!/usr/bin/env python3
"""Publish gripper TCP motion relative to its first received TF."""

from math import sqrt

from geometry_msgs.msg import TransformStamped

import rclpy
from rclpy.node import Node

from tf2_msgs.msg import TFMessage

from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


def quaternion_conjugate(quaternion):
    """Return the inverse of a normalized XYZW quaternion."""
    x, y, z, w = quaternion
    return -x, -y, -z, w


def quaternion_multiply(left, right):
    """Compose two XYZW quaternions."""
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def normalize_quaternion(quaternion):
    """Normalize an XYZW quaternion."""
    norm = sqrt(sum(value * value for value in quaternion))
    if norm <= 1e-12:
        raise ValueError('received a zero quaternion')
    return tuple(value / norm for value in quaternion)


def rotate_vector(quaternion, vector):
    """Rotate a vector using a normalized XYZW quaternion."""
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


class TcpRelativeTfNode(Node):
    """Freeze the first TCP TF and publish later TFs relative to it."""

    def __init__(self):
        """Create the TF subscription and diagnostic TF broadcasters."""
        super().__init__('test_tcp_relative_tf')
        self.declare_parameter('tf_topic', '/tf')
        self.declare_parameter('world_frame', 'vive_world')
        self.declare_parameter('tcp_frame', 'gripper_tcp')
        self.declare_parameter('initial_frame', 'tcp_initial')
        self.declare_parameter('relative_frame', 'tcp_relative')

        self._world_frame = self.get_parameter('world_frame').value
        self._tcp_frame = self.get_parameter('tcp_frame').value
        self._initial_frame = self.get_parameter('initial_frame').value
        self._relative_frame = self.get_parameter('relative_frame').value
        self._initial_position = None
        self._initial_orientation = None
        self._dynamic_broadcaster = TransformBroadcaster(self)
        self._static_broadcaster = StaticTransformBroadcaster(self)
        self._subscription = self.create_subscription(
            TFMessage,
            self.get_parameter('tf_topic').value,
            self._tf_callback,
            100,
        )
        self.get_logger().info(
            f'Waiting for {self._world_frame} -> {self._tcp_frame} '
            f'on {self.get_parameter("tf_topic").value}')

    @staticmethod
    def _transform_values(message):
        position = (
            message.transform.translation.x,
            message.transform.translation.y,
            message.transform.translation.z,
        )
        orientation = normalize_quaternion((
            message.transform.rotation.x,
            message.transform.rotation.y,
            message.transform.rotation.z,
            message.transform.rotation.w,
        ))
        return position, orientation

    def _capture_initial_pose(self, message, position, orientation):
        self._initial_position = position
        self._initial_orientation = orientation
        initial = TransformStamped()
        initial.header.stamp = message.header.stamp
        initial.header.frame_id = self._world_frame
        initial.child_frame_id = self._initial_frame
        (
            initial.transform.translation.x,
            initial.transform.translation.y,
            initial.transform.translation.z,
        ) = position
        (
            initial.transform.rotation.x,
            initial.transform.rotation.y,
            initial.transform.rotation.z,
            initial.transform.rotation.w,
        ) = orientation
        self._static_broadcaster.sendTransform(initial)
        self.get_logger().info(
            f'Captured {self._world_frame} -> {self._initial_frame}; '
            f'publishing {self._initial_frame} -> {self._relative_frame}')

    def _tf_callback(self, tf_message):
        message = next((
            transform for transform in tf_message.transforms
            if transform.header.frame_id == self._world_frame
            and transform.child_frame_id == self._tcp_frame
        ), None)
        if message is None:
            return
        try:
            position, orientation = self._transform_values(message)
        except ValueError as error:
            self.get_logger().error(str(error))
            return

        if self._initial_position is None:
            self._capture_initial_pose(message, position, orientation)

        initial_inverse = quaternion_conjugate(
            self._initial_orientation)
        world_delta = tuple(
            current - initial for current, initial in zip(
                position, self._initial_position))
        relative_position = rotate_vector(initial_inverse, world_delta)
        relative_orientation = normalize_quaternion(
            quaternion_multiply(initial_inverse, orientation))

        relative = TransformStamped()
        relative.header.stamp = message.header.stamp
        relative.header.frame_id = self._initial_frame
        relative.child_frame_id = self._relative_frame
        (
            relative.transform.translation.x,
            relative.transform.translation.y,
            relative.transform.translation.z,
        ) = relative_position
        (
            relative.transform.rotation.x,
            relative.transform.rotation.y,
            relative.transform.rotation.z,
            relative.transform.rotation.w,
        ) = relative_orientation
        self._dynamic_broadcaster.sendTransform(relative)


def main():
    """Run the standalone relative-TF diagnostic node."""
    rclpy.init()
    node = TcpRelativeTfNode()
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
