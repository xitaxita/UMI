"""Read timestamped Vive poses from acquisition MCAP files."""

import numpy as np


def read_vive_poses(pose_directory, topic='/vive/pose'):
    """Return header times, XYZ positions, and XYZW orientations."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(
            uri=str(pose_directory), storage_id='mcap'),
        rosbag2_py.ConverterOptions('', ''),
    )
    type_map = {
        item.name: item.type for item in reader.get_all_topics_and_types()
    }
    if topic not in type_map:
        raise ValueError(f'{topic} is not present in {pose_directory}')
    message_type = get_message(type_map[topic])
    times = []
    positions = []
    orientations = []
    while reader.has_next():
        name, data, _ = reader.read_next()
        if name != topic:
            continue
        message = deserialize_message(data, message_type)
        stamp = message.header.stamp
        times.append(stamp.sec + stamp.nanosec / 1_000_000_000)
        position = message.pose.position
        orientation = message.pose.orientation
        positions.append((position.x, position.y, position.z))
        orientations.append((
            orientation.x, orientation.y, orientation.z, orientation.w))
    if len(times) < 2:
        raise ValueError(f'{topic} contains fewer than two poses')
    return (
        np.asarray(times, dtype=np.float64),
        np.asarray(positions, dtype=np.float64),
        np.asarray(orientations, dtype=np.float64),
    )
