"""ROS 2 node publishing a selected Vive pose from pysurvive."""

import math

from geometry_msgs.msg import PoseStamped, TransformStamped

from rcl_interfaces.msg import SetParametersResult

import rclpy
from rclpy.exceptions import ParameterUninitializedException
from rclpy.node import Node
from rclpy.parameter import Parameter

from tf2_ros import TransformBroadcaster

from .backend import PySurviveBackend


# D-022: the only copy of these values is config/vive.yaml.
TRANSLATION_PARAMETER = 'tracker_to_tcp_translation_m'
ROTATION_PARAMETER = 'tracker_to_tcp_rotation_xyzw'
UNIT_QUATERNION_TOLERANCE = 1e-3


def validated_extrinsic(translation, rotation):
    """Return a finite translation and normalized XYZW rotation.

    Raises ``ValueError`` for a missing value, wrong length, non-finite
    number, or a quaternion that is not (almost) unit length.
    """
    if translation is None or rotation is None:
        raise ValueError(
            f'{TRANSLATION_PARAMETER} and {ROTATION_PARAMETER} must be set '
            '(config/vive.yaml)')
    translation = tuple(float(value) for value in translation)
    rotation = tuple(float(value) for value in rotation)
    if len(translation) != 3 or len(rotation) != 4:
        raise ValueError(
            f'{TRANSLATION_PARAMETER} needs 3 values and '
            f'{ROTATION_PARAMETER} needs 4 (x, y, z, w)')
    if not all(math.isfinite(value) for value in translation + rotation):
        raise ValueError('Tracker-to-TCP extrinsic values must be finite')
    norm = math.sqrt(sum(value * value for value in rotation))
    if abs(norm - 1.0) > UNIT_QUATERNION_TOLERANCE:
        raise ValueError(
            f'{ROTATION_PARAMETER} must be a unit quaternion '
            f'(norm {norm:.6f})')
    return translation, tuple(value / norm for value in rotation)


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


def gripper_pose(tracker_position, tracker_orientation, extrinsic):
    """Compose world->tracker with the measured tracker->gripper pose."""
    translation, rotation = extrinsic
    offset = _rotate_vector(tracker_orientation, translation)
    return (
        tuple(value + delta for value, delta in zip(
            tracker_position, offset)),
        _quaternion_multiply(tracker_orientation, rotation),
    )


class VivePoseNode(Node):
    """Publish gripper pose and optional Tracker/TCP TF."""

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
        self.declare_parameter('publish_hz', 90.0)
        self.declare_parameter('publish_tf', True)
        # No defaults: the measured values live only in config/vive.yaml.
        self.declare_parameter(
            TRANSLATION_PARAMETER, Parameter.Type.DOUBLE_ARRAY)
        self.declare_parameter(ROTATION_PARAMETER, Parameter.Type.DOUBLE_ARRAY)

        publish_hz = float(self.get_parameter('publish_hz').value)
        if publish_hz <= 0.0:
            raise ValueError('publish_hz must be greater than zero')
        self._world_frame = self.get_parameter('world_frame').value
        self._tracker_frame = self.get_parameter('tracker_frame').value
        self._child_frame = self.get_parameter('child_frame').value
        self._extrinsic = validated_extrinsic(
            self._optional_parameter(TRANSLATION_PARAMETER),
            self._optional_parameter(ROTATION_PARAMETER))
        self._log_extrinsic('Loaded')
        self.add_on_set_parameters_callback(self._on_set_parameters)
        self._publisher = self.create_publisher(
            PoseStamped, self.get_parameter('pose_topic').value, 10
        )
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

    def _optional_parameter(self, name):
        try:
            return self.get_parameter(name).value
        except ParameterUninitializedException:
            return None

    def _log_extrinsic(self, verb):
        translation, rotation = self._extrinsic
        self.get_logger().info(
            f'{verb} {self._tracker_frame}->{self._child_frame} extrinsic: '
            f'translation_m={list(translation)}, '
            f'rotation_xyzw={[round(value, 9) for value in rotation]}')

    def _on_set_parameters(self, parameters):
        """Validate and apply live extrinsic updates (ros2 param set)."""
        changes = {
            parameter.name: parameter.value for parameter in parameters
            if parameter.name in (TRANSLATION_PARAMETER, ROTATION_PARAMETER)
        }
        if not changes:
            return SetParametersResult(successful=True)
        current_translation, current_rotation = self._extrinsic
        try:
            extrinsic = validated_extrinsic(
                changes.get(TRANSLATION_PARAMETER, current_translation),
                changes.get(ROTATION_PARAMETER, current_rotation))
        except (TypeError, ValueError) as error:
            return SetParametersResult(successful=False, reason=str(error))
        self._extrinsic = extrinsic
        self._log_extrinsic('Updated')
        return SetParametersResult(successful=True)

    def _publish_pose(self):
        pose = self._backend.read_pose()
        if pose is None:
            return
        tracker_position, tracker_orientation = pose
        position, orientation = gripper_pose(
            tracker_position, tracker_orientation, self._extrinsic)
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
