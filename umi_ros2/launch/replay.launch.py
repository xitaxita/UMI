"""Replay one UMI session or one recording in RViz."""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from umi_ros2.launch_support import asset_paths, rviz_node


def generate_launch_description():
    """Auto-detect a session/recording and replay MP4 plus pose in RViz."""
    paths = asset_paths()
    input_path = LaunchConfiguration('input_path')
    playback_rate = LaunchConfiguration('playback_rate')
    preview_width = LaunchConfiguration('preview_width')
    preview_height = LaunchConfiguration('preview_height')
    use_calibration = LaunchConfiguration('use_calibration')
    loop = LaunchConfiguration('loop')
    replay = Node(
        package='umi_ros2', executable='session_replay_node',
        name='umi_session_replay_node', output='screen',
        parameters=[{
            'input_path': input_path,
            'playback_rate': ParameterValue(
                playback_rate, value_type=float),
            'preview_width': ParameterValue(
                preview_width, value_type=int),
            'preview_height': ParameterValue(
                preview_height, value_type=int),
            'use_calibration': ParameterValue(
                use_calibration, value_type=bool),
            'loop': ParameterValue(loop, value_type=bool),
        }],
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            'input_path',
            description=(
                'Path to a UMI session or calibration/episode directory'),
        ),
        DeclareLaunchArgument(
            'playback_rate', default_value='1.0',
            description='Rosbag playback speed multiplier',
        ),
        DeclareLaunchArgument(
            'preview_width', default_value='1280',
            description='RViz replay preview width in pixels',
        ),
        DeclareLaunchArgument(
            'preview_height', default_value='720',
            description='RViz replay preview height in pixels',
        ),
        DeclareLaunchArgument(
            'use_calibration', default_value='false',
            description='Apply accepted per-camera time offsets to images',
        ),
        DeclareLaunchArgument(
            'loop', default_value='false',
            description='Repeat the selected replay for visual inspection',
        ),
        RegisterEventHandler(OnProcessExit(
            target_action=replay,
            on_exit=[EmitEvent(event=Shutdown(
                reason='Session/recording playback finished'
            ))],
        )),
        Node(
            package='umi_ros2', executable='replay_path_node',
            name='vive_replay_path_node', output='screen',
            parameters=[{'use_sim_time': True}],
        ),
        rviz_node(
            paths['online_rviz'], 'umi_replay_rviz', use_sim_time=True
        ),
        replay,
    ])
