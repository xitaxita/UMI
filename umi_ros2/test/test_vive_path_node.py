"""Live path sampling must stay independent of high-frequency pose work."""

import importlib.util
from copy import deepcopy
from pathlib import Path

from geometry_msgs.msg import PoseStamped

from launch_ros.actions import Node as LaunchNode

import pytest

import rclpy

from umi_ros2.vive.path_node import VivePathNode
from umi_ros2.vive.pose_node import VivePoseNode


PACKAGE_ROOT = Path(__file__).parents[1]
CONFIG = PACKAGE_ROOT / 'config' / 'vive.yaml'


class CapturedPublisher:
    """Save publication snapshots without a display or DDS subscriber."""

    def __init__(self):
        """Start an empty observation list."""
        self.messages = []

    def publish(self, message):
        """Snapshot a message that the node may reuse later."""
        self.messages.append(deepcopy(message))


class FakeBackend:
    """Supply a deterministic Tracker without accessing hardware."""

    def __init__(self, **unused):
        """Accept the production backend selector parameters."""
        pass

    def start(self):
        """Describe the synthetic source."""
        return 'synthetic tracker'

    def read_pose(self):
        """Return a valid identity Tracker pose."""
        return (1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)

    def stop(self):
        """Finish without hardware work."""
        pass


def pose(index, frame='vive_world'):
    """Make distinguishable source samples with intact header metadata."""
    message = PoseStamped()
    message.header.frame_id = frame
    message.header.stamp.sec = index
    message.pose.position.x = float(index)
    message.pose.orientation.w = 1.0
    return message


@pytest.fixture
def ros(tmp_path, monkeypatch):
    """Load the real two-node configuration in a fresh ROS context."""
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path / 'ros_logs'))
    rclpy.init(args=['--ros-args', '--params-file', str(CONFIG)])
    yield
    rclpy.shutdown()


@pytest.fixture
def path_node(ros):
    """Observe timer publications directly for deterministic sampling tests."""
    node = VivePathNode()
    node._timer.cancel()
    node._publisher = CapturedPublisher()
    yield node
    node.destroy_node()


def test_path_samples_only_latest_pose_at_display_tick(path_node):
    """Several incoming poses contribute one latest sample, with its header."""
    assert path_node._timer.timer_period_ns == pytest.approx(1e9 / 30, abs=1)
    for index in (1, 2, 3):
        path_node._on_pose(pose(index))
    assert path_node._publisher.messages == []
    path_node._publish_path()
    message = path_node._publisher.messages[-1]
    assert message.header == pose(3).header
    assert message.poses == [pose(3)]


def test_path_does_not_duplicate_samples_when_pose_pauses(path_node):
    """An empty tick or a source pause neither adds nor republishes points."""
    path_node._publish_path()
    assert path_node._publisher.messages == []
    path_node._on_pose(pose(1))
    path_node._publish_path()
    for _ in range(5):
        path_node._publish_path()
    assert len(path_node._publisher.messages) == 1
    assert path_node._path.poses == [pose(1)]


def test_path_keeps_only_bounded_history(path_node):
    """Old visualization samples leave the buffer while newest ones remain."""
    path_node._max_path_points = 2
    for index in (1, 2, 3, 4):
        path_node._on_pose(pose(index))
        path_node._publish_path()
    assert path_node._publisher.messages[-1].poses == [pose(3), pose(4)]
    assert path_node._publisher.messages[-1].header == pose(4).header


def test_path_starts_new_history_on_coordinate_frame_change(path_node):
    """Never connect points from different coordinate frames."""
    path_node._on_pose(pose(1))
    path_node._publish_path()
    changed = pose(2, 'new_world')
    path_node._on_pose(changed)
    path_node._publish_path()
    message = path_node._publisher.messages[-1]
    assert message.header.frame_id == 'new_world'
    assert message.poses == [changed]


def test_pose_source_keeps_tf_and_has_no_path_publisher(ros):
    """The acquisition node produces both TFs without history processing."""
    node = VivePoseNode(backend_factory=FakeBackend)
    try:
        node._timer.cancel()
        node._publisher = CapturedPublisher()
        transforms = []
        node._tf_broadcaster.sendTransform = transforms.extend
        node._publish_pose()
        message = node._publisher.messages[-1]
        assert len(transforms) == 2
        assert {item.child_frame_id for item in transforms} == {
            'vive_tracker', 'gripper_tcp'}
        assert all(item.header == message.header for item in transforms)
        assert node._timer.timer_period_ns == pytest.approx(1e9 / 90, abs=1)
        assert not hasattr(node, '_path')
        assert not hasattr(node, '_path_publisher')
        assert all(topic != '/vive/path' for topic, _ in
                   node.get_publisher_names_and_types_by_node(
                       node.get_name(), node.get_namespace()))
    finally:
        node.destroy_node()


@pytest.mark.parametrize('name', ['vive', 'online_view', 'online_record'])
def test_live_launch_starts_pose_and_path_processes(name, monkeypatch):
    """All live entry points retain RViz-compatible path publication."""
    spec = importlib.util.spec_from_file_location(
        f'umi_test_{name}_launch',
        PACKAGE_ROOT / 'launch' / f'{name}.launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'asset_paths', lambda: {
        'vive_config': str(CONFIG),
        'camera_config': str(CONFIG.parent / 'action4.yaml'),
        'realsense_left_config': str(CONFIG.parent / 'realsense_left.yaml'),
        'online_rviz': str(PACKAGE_ROOT / 'rviz' / 'online.rviz'),
    })
    actions = module.generate_launch_description().entities
    executables = [action.node_executable for action in actions
                   if isinstance(action, LaunchNode)]
    assert executables.count('vive_pose_node') == 1
    assert executables.count('vive_path_node') == 1
