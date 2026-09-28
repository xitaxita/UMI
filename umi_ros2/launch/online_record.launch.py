"""Record separate online MP4 and pose artifacts in one UMI session."""

import os

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
)


RECORDED_TOPICS = (
    '/vive/pose',
    '/tf',
    '/tf_static',
)


def generate_launch_description():
    """Start sensors, RViz, MP4 recording, and pose-only MCAP recording."""
    paths = asset_paths()
    default_output = os.path.join(
        os.getcwd(), 'recordings'
    )
    session_output = LaunchConfiguration('session_output')
    warmup_seconds = LaunchConfiguration('warmup_seconds')
    task = LaunchConfiguration('task')
    vive = vive_node(paths['vive_config'])
    camera = camera_node(
        paths['camera_config'],
        {
            'warmup_seconds': ParameterValue(warmup_seconds, value_type=float),
            'episode_mode': True,
            'recordings_root': session_output,
            'task': ParameterValue(task, value_type=str),
        },
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            'session_output',
            default_value=default_output,
            description='Parent directory for a new online session',
        ),
        DeclareLaunchArgument(
            'task',
            default_value='',
            description='Natural-language task of this session (may be empty '
                        'and filled in later with set_session_task)',
        ),
        DeclareLaunchArgument(
            'warmup_seconds',
            default_value='5.0',
            description='Minimum camera and pose warmup before recording',
        ),
        RegisterEventHandler(OnProcessExit(
            target_action=vive,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Vive pose node exited during recording'
            ))],
        )),
        RegisterEventHandler(OnProcessExit(
            target_action=camera,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Action 4 camera node exited during recording'
            ))],
        )),
        vive,
        rviz_node(paths['online_rviz'], 'umi_online_rviz'),
        camera,
    ])
