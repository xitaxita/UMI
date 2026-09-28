"""Overlay the live Vive TCP path with a separately supplied URDF model."""

import xml.etree.ElementTree as ET
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _root_link(urdf_text):
    """Infer the unique root link from a URDF document."""
    root = ET.fromstring(urdf_text)
    links = {link.attrib['name'] for link in root.findall('link')}
    children = {
        joint.find('child').attrib['link']
        for joint in root.findall('joint')
        if joint.find('child') is not None
    }
    roots = links - children
    if len(roots) != 1:
        raise ValueError(
            f'URDF must have exactly one root link; found {sorted(roots)}')
    return roots.pop()


def _create_nodes(context):
    """Load a user URDF and assemble the diagnostic-only ROS graph."""
    urdf_path = Path(
        LaunchConfiguration('urdf_file').perform(context)
    ).expanduser()
    if not urdf_path.is_file():
        raise ValueError(f'urdf_file does not exist: {urdf_path}')
    robot_description = urdf_path.read_text(encoding='utf-8')
    root_link = LaunchConfiguration('root_link').perform(context).strip()
    if not root_link:
        root_link = _root_link(robot_description)

    package_share = Path(get_package_share_directory('umi_ros2'))
    rviz_config = package_share / 'rviz' / 'urdf_path_diagnostic.rviz'
    world_frame = LaunchConfiguration('world_frame')
    transform_arguments = [
        '--x', LaunchConfiguration('base_x'),
        '--y', LaunchConfiguration('base_y'),
        '--z', LaunchConfiguration('base_z'),
        '--roll', LaunchConfiguration('base_roll'),
        '--pitch', LaunchConfiguration('base_pitch'),
        '--yaw', LaunchConfiguration('base_yaw'),
        '--frame-id', world_frame,
        '--child-frame-id', root_link,
    ]

    return [
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='urdf_diagnostic_state_publisher',
            parameters=[{'robot_description': robot_description}],
            output='screen',
        ),
        Node(
            package='joint_state_publisher',
            executable='joint_state_publisher',
            name='urdf_diagnostic_joint_state_publisher',
            output='screen',
        ),
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='urdf_diagnostic_world_alignment',
            arguments=transform_arguments,
            output='screen',
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='umi_urdf_path_diagnostic_rviz',
            arguments=['-d', str(rviz_config)],
            output='screen',
        ),
    ]


def generate_launch_description():
    """Expose an optional URDF plus Vive path visualization."""
    return LaunchDescription([
        DeclareLaunchArgument(
            'urdf_file',
            default_value='',
            description='Path to the robot URDF file',
        ),
        DeclareLaunchArgument(
            'world_frame',
            default_value='vive_world',
            description='Vive world frame used by /vive/path',
        ),
        DeclareLaunchArgument(
            'root_link',
            default_value='',
            description='URDF root link; inferred when empty',
        ),
        DeclareLaunchArgument('base_x', default_value='0.0'),
        DeclareLaunchArgument('base_y', default_value='0.0'),
        DeclareLaunchArgument('base_z', default_value='0.0'),
        DeclareLaunchArgument('base_roll', default_value='0.0'),
        DeclareLaunchArgument('base_pitch', default_value='0.0'),
        DeclareLaunchArgument('base_yaw', default_value='0.0'),
        OpaqueFunction(function=_create_nodes),
    ])
