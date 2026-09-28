"""Static contracts for consolidated launch entry points."""

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1]
LAUNCH_DIR = PACKAGE_ROOT / 'launch'
CONFIG_DIR = PACKAGE_ROOT / 'config'


def assigned_tuple(path, name):
    """Read a static topic tuple without starting ROS launch."""
    module = ast.parse(path.read_text(encoding='utf-8'))
    assignment = next(
        node for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )
    return ast.literal_eval(assignment.value)


def test_online_recorded_topic_contract():
    """Record pose separately from the camera-owned video artifact."""
    topics = assigned_tuple(
        LAUNCH_DIR / 'online_record.launch.py', 'RECORDED_TOPICS'
    )
    assert topics == (
        '/vive/pose',
        '/tf',
        '/tf_static',
    )
    source = (LAUNCH_DIR / 'online_record.launch.py').read_text()
    assert 'camera_node(' in source
    assert "'episode_mode': True" in source
    assert "'recordings_root': session_output" in source
    assert "'task',\n            default_value=''" in source
    assert "'task': ParameterValue(task, value_type=str)" in source
    assert 'online_session_' not in source
    assert 'video_timestamps.csv' not in source
    assert "ros2', 'bag', 'record'" not in source


def test_camera_uses_h264_output_capture_contract():
    """Use the project's worker-owning ROS preview node."""
    support = (
        PACKAGE_ROOT / 'umi_ros2' / 'launch_support.py'
    ).read_text(encoding='utf-8')
    config = (CONFIG_DIR / 'action4.yaml').read_text(encoding='utf-8')
    assert "executable='h264_capture_node'" in support
    assert "package='usb_cam'" not in support
    assert 'action4_h264_capture_node:' in config
    assert 'preview_topic: /action4/image_preview' in config


def test_recording_launch_keeps_warmup():
    """Online warms the stream inside the camera node."""
    online = (LAUNCH_DIR / 'online_record.launch.py').read_text()
    assert "default_value='5.0'" in online
    assert 'ParameterValue(warmup_seconds, value_type=float)' in online
    assert 'TimerAction' not in online


def test_offline_mode_is_removed():
    """D-021: online acquisition is the only recording mode."""
    assert not (LAUNCH_DIR / 'offline_record.launch.py').exists()
    assert not (PACKAGE_ROOT / 'rviz' / 'offline.rviz').exists()
    support = (
        PACKAGE_ROOT / 'umi_ros2' / 'launch_support.py'
    ).read_text(encoding='utf-8')
    layout = (
        PACKAGE_ROOT / 'umi_ros2' / 'session' / 'layout.py'
    ).read_text(encoding='utf-8')
    assert 'offline' not in support
    assert 'offline' not in layout


def test_replay_launch_uses_auto_detected_separated_artifacts():
    """Replay MP4 and pose through the session-aware coordinator."""
    source = (LAUNCH_DIR / 'replay.launch.py').read_text()
    assert "'input_path'" in source
    assert "executable='session_replay_node'" in source
    assert "executable='replay_path_node'" in source
    assert 'compressed_preview_node' not in source
    assert "ros2', 'bag', 'play'" not in source


def test_replay_preview_quality_defaults_are_playback_only():
    """Expose a clearer replay without changing live acquisition settings."""
    launch = (LAUNCH_DIR / 'replay.launch.py').read_text()
    replay = (
        PACKAGE_ROOT / 'umi_ros2' / 'visualization' /
        'session_replay_node.py'
    ).read_text()
    assert "'preview_width', default_value='1280'" in launch
    assert "'preview_height', default_value='720'" in launch
    assert "self.declare_parameter('preview_width', 1280)" in replay
    assert "self.declare_parameter('preview_height', 720)" in replay
    assert "'--clock', '120'" in replay
