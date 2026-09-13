"""Decode recorded Action 4 JPEG messages for RViz playback."""

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage, Image

from umi_ros2.common.images import decode_jpeg, make_preview


class CompressedPreviewNode(Node):
    """Convert recorded compressed images into an RViz-compatible preview."""

    def __init__(self):
        """Create the compressed subscriber and raw preview publisher."""
        super().__init__('action4_compressed_preview_node')
        self.declare_parameter(
            'input_topic', 'action4/image_raw/compressed'
        )
        self.declare_parameter('output_topic', 'action4/image_preview')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 360)
        self._width = int(self.get_parameter('width').value)
        self._height = int(self.get_parameter('height').value)
        if self._width <= 0 or self._height <= 0:
            raise ValueError('preview width and height must be positive')
        self._publisher = self.create_publisher(
            Image,
            str(self.get_parameter('output_topic').value),
            qos_profile_sensor_data,
        )
        self._subscription = self.create_subscription(
            CompressedImage,
            str(self.get_parameter('input_topic').value),
            self._on_image,
            qos_profile_sensor_data,
        )

    def _on_image(self, message):
        try:
            frame = decode_jpeg(message.data)
        except ValueError as error:
            self.get_logger().error(str(error))
            return
        self._publisher.publish(make_preview(
            frame, message.header, self._width, self._height
        ))


def main(args=None):
    """Run the recorded-image preview decoder."""
    rclpy.init(args=args)
    node = CompressedPreviewNode()
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
