"""Launch the online-only DJI Action 4 camera path."""

from launch import LaunchDescription

from umi_ros2.launch_support import asset_paths, camera_node


def generate_launch_description():
    """Start native H.264 capture with a decoded ROS preview."""
    paths = asset_paths()
    return LaunchDescription([camera_node(paths['camera_config'])])
