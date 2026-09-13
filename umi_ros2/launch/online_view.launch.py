"""Launch online UMI sensors and RViz without recording."""

from launch import LaunchDescription
from launch.actions import EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown

from umi_ros2.launch_support import (
    asset_paths,
    camera_node,
    rviz_node,
    vive_node,
)


def generate_launch_description():
    """Start Vive, Action 4, and the online RViz view."""
    paths = asset_paths()
    camera = camera_node(paths['camera_config'])
    return LaunchDescription([
        RegisterEventHandler(OnProcessExit(
            target_action=camera,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Action 4 camera node exited'
            ))],
        )),
        vive_node(paths['vive_config']),
        camera,
        rviz_node(paths['online_rviz'], 'umi_online_rviz'),
    ])
