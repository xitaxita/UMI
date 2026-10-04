"""Per-camera results and signed latency with a real 500 ms pose lead MCAP."""

import json

import numpy as np

import pytest

from umi_ros2.postprocess.episode_transform import (
    quaternion_multiply, rotate_vector)
from umi_ros2.session.layout import (
    create_online_session, read_session, update_temporal_calibration)
from umi_ros2.synchronization import calibrate_time


def motion(times):
    """Independent XYZ translations supply informative alignment channels."""
    return 0.2 * np.column_stack((
        np.sin(times * 1.7) + 0.2 * np.sin(times * 4.1),
        np.cos(times * 1.1) + 0.15 * np.sin(times * 3.3),
        np.sin(times * 0.7 + 0.4),
    ))


def write_pose_bag(path, times, positions, reference_orientation=None):
    """Write real PoseStamped headers; bag receipt is intentionally later."""
    import rosbag2_py
    from geometry_msgs.msg import PoseStamped
    from rclpy.serialization import serialize_message

    writer = rosbag2_py.SequentialWriter()
    writer.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id='mcap'),
        rosbag2_py.ConverterOptions('', ''))
    writer.create_topic(rosbag2_py.TopicMetadata(
        id=0, name='/vive/pose', type='geometry_msgs/msg/PoseStamped',
        serialization_format='cdr'))
    if reference_orientation is None:
        reference_orientation = np.array([0.0, 0.0, 0.0, 1.0])
    for index, (time_value, position) in enumerate(zip(times, positions)):
        message = PoseStamped()
        stamp = round(time_value * 1e9)
        message.header.stamp.sec = stamp // 1_000_000_000
        message.header.stamp.nanosec = stamp % 1_000_000_000
        message.header.frame_id = 'vive_world'
        message.pose.position.x = float(position[0])
        message.pose.position.y = float(position[1])
        message.pose.position.z = float(position[2])
        # Only the initial orientation defines the fixed coordinate frame.
        orientation = quaternion_multiply(reference_orientation, [
            0.0, 0.0, np.sin(index * 0.01), np.cos(index * 0.01)])
        message.pose.orientation.x = float(orientation[0])
        message.pose.orientation.y = float(orientation[1])
        message.pose.orientation.z = float(orientation[2])
        message.pose.orientation.w = float(orientation[3])
        writer.write('/vive/pose', serialize_message(message),
                     stamp + 25_000_000)
    del writer


def calibration_inputs(tmp_path, monkeypatch, camera_id, offset,
                       stationary=False, reference_orientation=None):
    """Keep genuine MCAP input and replace only image feature extraction."""
    session = create_online_session(tmp_path)
    episode = session / 'calibration' / 'calibration_001'
    color = episode / 'cameras' / camera_id
    color.mkdir(parents=True)
    (color / 'video.mp4').write_bytes(b'feature extraction fixture')
    epoch = 1_790_000_000
    anchor = epoch * 1_000_000_000 + 500_000_000
    (color / 'video.timing.json').write_text(json.dumps({
        'camera_id': camera_id, 'image_field': f'{camera_id}_image',
        'first_receive_unix_ns': anchor}))
    pts = np.arange(0, 12, 1 / 30)
    image_motion = motion(0.5 + pts) @ np.diag([0.8, -0.7, 0.8])
    relative_pose = np.arange(0, 14, 1 / 90)
    positions = (np.zeros((len(relative_pose), 3)) if stationary
                 else motion(relative_pose - offset))
    if reference_orientation is not None:
        positions = np.asarray([
            rotate_vector(reference_orientation, position)
            for position in positions]) + [1.5, -2.0, 0.7]
    write_pose_bag(episode / 'pose', epoch + relative_pose, positions,
                   reference_orientation)
    monkeypatch.setattr(calibrate_time, 'video_frame_times', lambda path: pts)
    monkeypatch.setattr(
        calibrate_time, 'aruco_trajectory',
        lambda *args: (pts, image_motion, len(pts)))
    monkeypatch.setattr(
        calibrate_time, 'save_plot',
        lambda path, *args: path.write_bytes(b'plot'))
    args = calibrate_time.argument_parser().parse_args([
        str(episode), '--minimum-offset', '-0.3', '--maximum-offset', '0.3',
        '--search-step', '0.005'])
    return session, episode, args


@pytest.mark.parametrize('camera_id,expected,reference_orientation', [
    ('left', -0.1374, None), ('wrist', 0.1274, None),
    ('left', -0.1374, [0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)]),
    ('wrist', 0.1274, quaternion_multiply(
        [0.0, 0.0, np.sin(0.31), np.cos(0.31)],
        [0.0, np.sin(0.47), 0.0, np.cos(0.47)])),
])
def test_500ms_lead_is_not_calibration_latency(
        tmp_path, monkeypatch, camera_id, expected, reference_orientation):
    """Infer each camera and recover true latency with earlier pose headers."""
    session, episode, args = calibration_inputs(
        tmp_path, monkeypatch, camera_id, expected,
        reference_orientation=reference_orientation)
    other = 'wrist' if camera_id == 'left' else 'left'
    previous = {'status': 'accepted', 'result': 'other-camera.json',
                'video_to_pose_offset_seconds': 0.08}
    update_temporal_calibration(session, other, previous)
    assert calibrate_time.calibrate(args) == 0
    result = json.loads((episode / 'time_offset.json').read_text())
    assert result['camera_id'] == camera_id
    assert result['image_field'] == f'{camera_id}_image'
    assert result['pose_features'] == ['x', 'y', 'z']
    assert result['pose_frame'] == 'recording_start_tcp'
    assert result['pose_reference']['pose_time_seconds'] == 1_790_000_000
    assert result['pose_reference']['orientation_xyzw'] == pytest.approx(
        [0.0, 0.0, 0.0, 1.0] if reference_orientation is None
        else reference_orientation)
    assert result['recording_pose_lead_seconds'] == pytest.approx(0.5)
    assert result['video_to_pose_offset_seconds'] == pytest.approx(
        expected, abs=0.004)
    metadata = read_session(session)
    assert metadata['temporal_calibrations'][other] == previous
    assert metadata['temporal_calibrations'][camera_id]['status'] == 'accepted'
    if camera_id == 'left':
        assert metadata['temporal_calibration'] == previous
    else:
        assert metadata['temporal_calibration']['camera_id'] == 'wrist'


def test_rotation_without_xyz_translation_is_rejected(tmp_path, monkeypatch):
    """Changing orientations alone cannot satisfy translation checks."""
    _, _, args = calibration_inputs(
        tmp_path, monkeypatch, 'left', 0, stationary=True)
    with pytest.raises(ValueError, match='motion is too small'):
        calibrate_time.calibrate(args)


def test_explicit_unknown_camera_does_not_fall_back_to_wrist(
        tmp_path, monkeypatch):
    """Never calibrate the wrong stream when a selected camera has no video."""
    _, _, args = calibration_inputs(tmp_path, monkeypatch, 'wrist', 0)
    args.camera_id = 'left'
    with pytest.raises(FileNotFoundError):
        calibrate_time.calibrate(args)
