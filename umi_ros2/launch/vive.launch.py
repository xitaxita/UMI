"""Launch the shared Vive pose source."""

from launch import LaunchDescription

from umi_ros2.launch_support import asset_paths, vive_node, vive_path_node


def generate_launch_description():
    """Start only Vive pose, path, and TF publication."""
    paths = asset_paths()
    return LaunchDescription([
        vive_node(paths['vive_config']),
        vive_path_node(paths['vive_config']),
    ])
