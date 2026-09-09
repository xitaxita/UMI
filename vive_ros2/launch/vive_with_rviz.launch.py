import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory("vive_ros2")
    config = os.path.join(package_share, "config", "vive.yaml")
    rviz_config = os.path.join(package_share, "rviz", "vive_path.rviz")

    return LaunchDescription([
        Node(
            package="vive_ros2",
            executable="vive_pose_node",
            name="vive_pose_node",
            output="screen",
            parameters=[config],
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="vive_path_rviz",
            output="screen",
            arguments=["-d", rviz_config],
        ),
    ])
