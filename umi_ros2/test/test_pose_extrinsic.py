"""D-022: the Tracker-to-TCP extrinsic comes only from config/vive.yaml."""

from pathlib import Path

import pytest

import rclpy
from rclpy.parameter import Parameter

from umi_ros2.vive import pose_node
from umi_ros2.vive.pose_node import (
    VivePoseNode,
    gripper_pose,
    validated_extrinsic,
)

import yaml


CONFIG = Path(__file__).parents[1] / 'config' / 'vive.yaml'
# Values accepted in D-020 (remeasured 2026-09-21).
D020_TRANSLATION = (0.0, -0.080371453, 0.194957425)
D020_ROTATION = (0.628736470, -0.628736470, 0.323559039, 0.323559039)


class _Backend:
    def __init__(self, **unused):
        pass

    def start(self):
        return 'fake tracker'

    def read_pose(self):
        return None

    def stop(self):
        pass


def _config_parameters():
    return yaml.safe_load(CONFIG.read_text())['vive_pose_node'][
        'ros__parameters']


def test_vive_yaml_holds_the_d020_extrinsic():
    """The only copy of the extrinsic is in vive.yaml."""
    parameters = _config_parameters()
    translation, rotation = validated_extrinsic(
        parameters['tracker_to_tcp_translation_m'],
        parameters['tracker_to_tcp_rotation_xyzw'])
    assert translation == pytest.approx(D020_TRANSLATION)
    assert rotation == pytest.approx(D020_ROTATION, abs=1e-8)
    assert all(isinstance(value, float) for value in (
        parameters['tracker_to_tcp_translation_m']
        + parameters['tracker_to_tcp_rotation_xyzw']))
    assert not hasattr(pose_node, 'TRACKER_TO_GRIPPER_TRANSLATION')
    assert not (CONFIG.parent / 'gripper_extrinsics.yaml').exists()


def test_gripper_pose_composes_the_given_extrinsic():
    """With an identity Tracker pose the TCP pose equals the extrinsic."""
    extrinsic = validated_extrinsic(D020_TRANSLATION, D020_ROTATION)
    position, orientation = gripper_pose(
        (1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0), extrinsic)
    assert position == pytest.approx((1.0, 1.919628547, 3.194957425))
    assert orientation == pytest.approx(extrinsic[1])


@pytest.mark.parametrize('translation, rotation, message', [
    (None, D020_ROTATION, 'must be set'),
    ((0.0, 0.0), D020_ROTATION, 'needs 3 values'),
    (D020_TRANSLATION, (0.0, 0.0, 0.0, 2.0), 'unit quaternion'),
    (D020_TRANSLATION, (0.0, 0.0, float('nan'), 1.0), 'finite'),
])
def test_invalid_extrinsic_is_rejected(translation, rotation, message):
    """Never compose with a malformed transform."""
    with pytest.raises(ValueError, match=message):
        validated_extrinsic(translation, rotation)


@pytest.fixture
def ros_with_config(tmp_path, monkeypatch):
    """Start rclpy with the real vive.yaml as the node's parameter file."""
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path / 'ros_logs'))
    rclpy.init(args=['--ros-args', '--params-file', str(CONFIG)])
    yield
    rclpy.shutdown()


def test_node_loads_yaml_and_applies_validated_live_updates(ros_with_config):
    """ros2 param set updates the transform; bad values are refused."""
    node = VivePoseNode(backend_factory=_Backend)
    try:
        assert node._extrinsic[0] == pytest.approx(D020_TRANSLATION)
        result = node.set_parameters([Parameter(
            'tracker_to_tcp_translation_m', Parameter.Type.DOUBLE_ARRAY,
            [0.0, 0.0, 0.1])])
        assert result[0].successful
        assert node._extrinsic[0] == pytest.approx((0.0, 0.0, 0.1))
        assert node._extrinsic[1] == pytest.approx(D020_ROTATION, abs=1e-8)

        result = node.set_parameters([Parameter(
            'tracker_to_tcp_rotation_xyzw', Parameter.Type.DOUBLE_ARRAY,
            [0.0, 0.0, 0.0, 3.0])])
        assert not result[0].successful
        assert 'unit quaternion' in result[0].reason
        assert node._extrinsic[1] == pytest.approx(D020_ROTATION, abs=1e-8)
        assert node.get_parameter(
            'tracker_to_tcp_rotation_xyzw').value == pytest.approx(
                D020_ROTATION)
    finally:
        node.destroy_node()


def test_node_refuses_to_start_without_extrinsic(tmp_path, monkeypatch):
    """A missing vive.yaml extrinsic is a startup error, not a default."""
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path / 'ros_logs'))
    rclpy.init()
    try:
        with pytest.raises(ValueError, match='must be set'):
            VivePoseNode(backend_factory=_Backend)
    finally:
        rclpy.shutdown()
