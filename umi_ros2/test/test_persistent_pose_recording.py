"""Contracts for the persistent online pose recorder."""

import time
from pathlib import Path

from geometry_msgs.msg import PoseStamped

import rclpy
from rclpy.executors import SingleThreadedExecutor

from umi_ros2.vive.pose_recording_worker import PoseRecordingWorker


PACKAGE_ROOT = Path(__file__).parents[1]


def test_online_camera_uses_persistent_pose_worker():
    """Do not launch a new rosbag CLI process for every episode."""
    source = (
        PACKAGE_ROOT / 'umi_ros2/camera/h264_capture_node.py'
    ).read_text(encoding='utf-8')
    assert 'umi_ros2.vive.pose_recording_worker' in source
    assert "'ros2', 'bag', 'record'" not in source
    assert "_wait_pose_state('waiting', 30)" in source
    assert "_wait_pose_state('recording_ready', 5)" in source
    assert source.index('_start_pose_worker()') < source.index(
        "self._start_worker('')")


def test_pose_worker_subscribes_once_and_switches_mcap_writer():
    """Retain subscriptions while each recording gets a fresh writer URI."""
    source = (
        PACKAGE_ROOT / 'umi_ros2/vive/pose_recording_worker.py'
    ).read_text(encoding='utf-8')
    assert "PoseStamped, '/vive/pose'" in source
    assert "TFMessage, '/tf'" in source
    assert "TFMessage, '/tf_static'" in source
    assert 'rosbag2_py.SequentialWriter()' in source
    assert "uri=output_path, storage_id='mcap'" in source
    assert "'recording_ready', first_pose_unix_ns" in source
    assert "self._set_state('waiting'" in source


def test_persistent_worker_writes_two_independent_pose_bags(
        tmp_path, monkeypatch):
    """Reuse subscriptions while closing each recording into its own MCAP."""
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path / 'ros_logs'))
    rclpy.init()
    worker = PoseRecordingWorker({
        'warmup_seconds': 0.0,
        'startup_timeout_seconds': 2.0,
        'status_path': str(tmp_path / 'status.json'),
        'read_commands': False,
    })
    source = rclpy.create_node('synthetic_vive_pose_source')
    publisher = source.create_publisher(PoseStamped, '/vive/pose', 10)
    executor = SingleThreadedExecutor()
    executor.add_node(worker)
    executor.add_node(source)
    try:
        for number in (1, 2):
            output = tmp_path / f'pose_{number}'
            worker._start_recording(str(output))
            for sample in range(2):
                message = PoseStamped()
                message.header.stamp = source.get_clock().now().to_msg()
                message.pose.position.x = float(number * 10 + sample)
                message.pose.orientation.w = 1.0
                publisher.publish(message)
                deadline = time.monotonic() + 1.0
                while worker._pose_count <= sample:
                    executor.spin_once(timeout_sec=0.02)
                    assert time.monotonic() < deadline
            assert worker._status['state'] == 'recording_ready'
            worker._stop_recording()
            assert (output / 'metadata.yaml').is_file()
            assert list(output.glob('*.mcap'))
    finally:
        worker.close()
        executor.remove_node(source)
        executor.remove_node(worker)
        source.destroy_node()
        worker.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
