"""Launch and record the shared pose side of an offline UMI session."""

import os
from datetime import datetime

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
    TimerAction,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from umi_ros2.launch_support import asset_paths, rviz_node, vive_node
from umi_ros2.session.layout import create_offline_session


RECORDED_TOPICS = ('/vive/pose', '/tf', '/tf_static')


def initialize_session(context, session_output):
    """Create metadata and reserved directories before rosbag starts."""
    create_offline_session(session_output.perform(context))
    return []


def generate_launch_description():
    """Start Vive/RViz and record pose only; never start the USB camera."""
    paths = asset_paths()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_output = os.path.join(
        os.getcwd(), 'recordings', f'offline_session_{timestamp}'
    )
    session_output = LaunchConfiguration('session_output')
    warmup_seconds = LaunchConfiguration('warmup_seconds')
    vive = vive_node(paths['vive_config'])
    recorder = ExecuteProcess(
        cmd=[
            'ros2', 'bag', 'record',
            '--storage', 'mcap',
            '--output', PathJoinSubstitution([session_output, 'pose']),
            '--disable-keyboard-controls',
            '--topics', *RECORDED_TOPICS,
        ],
        name='umi_offline_pose_recorder',
        output='screen',
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            'session_output',
            default_value=default_output,
            description='New offline_session_<time> directory',
        ),
        DeclareLaunchArgument(
            'warmup_seconds',
            default_value='3.0',
            description='Delay recording while Vive and RViz stabilize',
        ),
        RegisterEventHandler(OnProcessExit(
            target_action=vive,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Vive pose node exited during recording'
            ))],
        )),
        RegisterEventHandler(OnProcessExit(
            target_action=recorder,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Offline pose recorder exited'
            ))],
        )),
        OpaqueFunction(
            function=initialize_session,
            args=[session_output],
        ),
        vive,
        rviz_node(paths['offline_rviz'], 'umi_offline_rviz'),
        TimerAction(period=warmup_seconds, actions=[recorder]),
    ])
