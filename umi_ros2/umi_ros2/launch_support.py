"""Shared launch actions and installed asset paths."""

import os

from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node


def asset_paths():
    """Return installed Vive config, camera config, and RViz paths."""
    share = get_package_share_directory('umi_ros2')
    return {
        'vive_config': os.path.join(share, 'config', 'vive.yaml'),
        'camera_config': os.path.join(share, 'config', 'action4.yaml'),
        'online_rviz': os.path.join(share, 'rviz', 'online.rviz'),
        'offline_rviz': os.path.join(share, 'rviz', 'offline.rviz'),
    }


def vive_node(config):
    """Build the shared Vive pose action."""
    return Node(
        package='umi_ros2',
        executable='vive_pose_node',
        name='vive_pose_node',
        output='screen',
        parameters=[config],
    )


def camera_node(config, parameters=None):
    """Build MJPEG-to-H.264 capture with an isolated GStreamer worker."""
    return Node(
        package='umi_ros2',
        executable='h264_capture_node',
        sigterm_timeout='150',
        sigkill_timeout='5',
        name='action4_h264_capture_node',
        output='screen',
        parameters=[config, parameters or {}],
    )


def rviz_node(config, name, use_sim_time=False):
    """Build an RViz action for live or replay use."""
    return Node(
        package='rviz2',
        executable='rviz2',
        name=name,
        output='screen',
        arguments=['-d', config],
        parameters=[{'use_sim_time': use_sim_time}],
    )
