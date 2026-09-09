from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
import os


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory("vive_ros2"), "config", "vive.yaml"
    )
    return LaunchDescription([
        Node(
            package="vive_ros2",
            executable="vive_pose_node",
            name="vive_pose_node",
            output="screen",
            parameters=[config],
        ),
    ])
