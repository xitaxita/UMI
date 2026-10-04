"""Launch online UMI sensors and RViz without recording."""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration

from launch_ros.parameter_descriptions import ParameterValue

from umi_ros2.launch_support import (
    asset_paths,
    camera_node,
    rviz_node,
    vive_node,
    vive_path_node,
)


def generate_launch_description():
    """Start Vive, both color cameras, and the online RViz view."""
    paths = asset_paths()
    camera = camera_node(paths['camera_config'], {
        'device_override': ParameterValue(
            LaunchConfiguration('video_device'), value_type=str),
        'realsense_enabled': True,
        'realsense_config_path': paths['realsense_left_config'],
        'realsense_device_override': ParameterValue(
            LaunchConfiguration('left_video_device'), value_type=str),
        'preview_width': 320,
        'preview_height': 180,
        'preview_fps': 10.0,
    })
    return LaunchDescription([
        DeclareLaunchArgument(
            'video_device', default_value='',
            description='Override the Action 4 device in action4.yaml'),
        DeclareLaunchArgument(
            'left_video_device', default_value='',
            description='Override the RealSense left color device'),
        RegisterEventHandler(OnProcessExit(
            target_action=camera,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Online camera coordinator exited'
            ))],
        )),
        vive_node(paths['vive_config']),
        vive_path_node(paths['vive_config']),
        camera,
        rviz_node(paths['online_rviz'], 'umi_online_rviz'),
    ])
