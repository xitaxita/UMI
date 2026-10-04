"""Launch the online-only DJI Action 4 camera path."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

from launch_ros.parameter_descriptions import ParameterValue

from umi_ros2.launch_support import asset_paths, camera_node


def generate_launch_description():
    """Start native H.264 capture with a decoded ROS preview."""
    paths = asset_paths()
    return LaunchDescription([
        DeclareLaunchArgument(
            'video_device', default_value='',
            description='Override the Action 4 device in action4.yaml'),
        camera_node(paths['camera_config'], {
            'device_override': ParameterValue(
                LaunchConfiguration('video_device'), value_type=str),
        }),
    ])
