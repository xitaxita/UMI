"""Accept episodes with good images, complete coverage and 88 Hz pose."""

import json
from types import SimpleNamespace

import pytest

from umi_ros2.camera import episode_quality as quality
from umi_ros2.camera.episode_keyboard import EpisodeKeyboard
from umi_ros2.camera.h264_capture_node import validate_video


def image_inputs():
    """Return a covered one-second, 30 fps recording."""
    return ({'status': 'complete', 'first_receive_unix_ns': 1_500_000_000},
            {'decode_ok': True, 'clean_shutdown': True,
             'frame_count_matches': True, 'decoded_frames': 31,
             'timestamped_frames': 31, 'first_frame_pts_seconds': 0.0,
             'last_frame_pts_seconds': 1.0,
             'max_timestamp_gap_seconds': 1 / 30,
             'non_increasing_timestamps': 0, 'image_gap_count': 0})


def pose_inputs():
    """Return 90 Hz pose spanning before and after the images."""
    return quality.pose_statistics(
        [1_000_000_000 + round(i * 1e9 / 90) for i in range(181)])


def test_isolated_pose_gap_can_still_accept():
    """Allow one missed pose with sufficient rate and coverage."""
    stamps = [1_000_000_000 + round(i * 1e9 / 90) for i in range(181)]
    del stamps[100]
    pose = quality.pose_statistics(stamps)
    assert pose['gap_count'] == 1
    assert pose['average_hz'] == 89.5
    assert quality.check_image(*image_inputs(), pose)['accepted']


@pytest.mark.parametrize('change,reason', [
    ({'max_timestamp_gap_seconds': 2 / 30}, 'image 掉帧'),
    ({'frame_count_matches': False}, 'image 文件或帧数检查失败'),
    ({'decode_ok': False}, 'image 文件或帧数检查失败'),
    ({'timestamped_frames': 30}, 'image 时间戳检查失败'),
    ({'non_increasing_timestamps': 1}, 'image 时间戳检查失败'),
])
def test_bad_image_rejects(change, reason):
    """A missing saved frame or timestamp must not silently accept."""
    timing, video = image_inputs()
    video.update(change)
    result = quality.check_image(timing, video, pose_inputs())
    assert not result['accepted']
    assert reason in result['reasons']


@pytest.mark.parametrize('change', [
    {'first_timestamp_ns': 1_500_000_001},
    {'last_timestamp_ns': 2_499_999_999},
])
def test_even_one_ns_uncovered_rejects(change):
    """Both boundaries must be inside pose, without a coverage tolerance."""
    pose = pose_inputs()
    pose.update(change)
    assert not quality.check_image(*image_inputs(), pose)['accepted']


def write_stream(episode, camera_id):
    """Write saved ffprobe/timing facts, without needing another MP4 decode."""
    directory = episode / 'cameras' / camera_id
    directory.mkdir(parents=True)
    timing, video = image_inputs()
    (directory / 'video.timing.json').write_text(json.dumps(timing))
    (directory / 'video.validation.json').write_text(json.dumps(video))
    return {'camera_id': camera_id,
            'timing_path': f'cameras/{camera_id}/video.timing.json',
            'validation_path': f'cameras/{camera_id}/video.validation.json'}


@pytest.mark.parametrize('hz,accepted', [(88.0, True), (87.999, False)])
def test_both_streams_and_pose_rate_gate(tmp_path, monkeypatch, hz, accepted):
    """Require both images and the rate threshold, saving exclusion flags."""
    streams = [write_stream(tmp_path, name) for name in ('wrist', 'left')]
    pose = pose_inputs()
    pose['average_hz'] = hz
    monkeypatch.setattr(quality, 'read_pose_statistics', lambda path: pose)
    result = quality.diagnose_episode(tmp_path, streams)
    assert result['accepted'] is accepted
    assert result['exclude_from_dataset'] is not accepted
    text = quality.format_verdict(result, 'episode_0001')
    assert text.startswith('\033[32m' if accepted else '\033[31m')
    assert ('accept' if accepted else 'reject') in text
    if accepted:
        assert 'image 未发现掉帧' in text
        assert 'pose 未发现掉帧' in text


def test_failed_or_missing_diagnostics_reject(tmp_path, monkeypatch):
    """Incomplete finalization and missing streams cannot return accept."""
    monkeypatch.setattr(quality, 'read_pose_statistics', lambda path: {})
    result = quality.diagnose_episode(
        tmp_path, [{'camera_id': 'left', 'timing_path': 'missing',
                    'validation_path': 'missing'}], ['video stop failed'])
    assert result['verdict'] == 'reject'
    assert result['exclude_from_dataset']


def test_ffprobe_pass_reports_gaps_and_endpoints(monkeypatch):
    """Extract dropped-frame evidence in the existing single decode pass."""
    calls = []

    def probe(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
            'frames': [{'best_effort_timestamp_time': str(value)}
                       for value in (0, 1 / 30, 0.1)]}))

    monkeypatch.setattr(
        'umi_ros2.camera.h264_capture_node.subprocess.run', probe)
    result = validate_video('video.mp4')
    assert len(calls) == 1
    assert result['timestamped_frames'] == 3
    assert result['last_frame_pts_seconds'] == 0.1
    assert result['image_gap_count'] == 1


def test_keyboard_can_start_after_failed_finalization(monkeypatch):
    """A failed file check still ends recording; next Enter starts afresh."""
    start, stop = object(), object()
    calls = []

    def call(client, request):
        calls.append(client)
        return SimpleNamespace(success=client is start, message='reject')

    node = SimpleNamespace(
        _recording=True, _recording_kind='episode', _start=start, _stop=stop,
        _calibration=object(), _call=call)
    keys = iter(['', '', 'q'])
    monkeypatch.setattr('builtins.input', lambda: next(keys))
    monkeypatch.setattr(
        'umi_ros2.camera.episode_keyboard.rclpy.ok', lambda: True)
    EpisodeKeyboard.run(node)
    assert calls == [stop, start]
    assert node._recording
