"""Tests for post-processing orchestration boundaries."""

import json
from types import SimpleNamespace

import numpy as np

import pytest

from umi_ros2.postprocess.transform_session import transform_item


def test_transform_item_writes_versioned_export_contract(tmp_path):
    """Persist transformed arrays with an explicit contract version."""
    source = tmp_path / 'aligned' / 'episode_0001'
    source.mkdir(parents=True)
    np.savez_compressed(
        source / 'aligned_frames.npz',
        frame_index=np.array([0, 1]),
        video_pts_seconds=np.array([0.0, 1 / 30]),
        video_time_seconds=np.array([10.0, 10.0 + 1 / 30]),
        pose_query_time_seconds=np.array([10.1, 10.1 + 1 / 30]),
        valid=np.array([True, True]),
        position_xyz=np.array([[2.0, 0.0, 0.0], [3.0, 0.0, 0.0]]),
        orientation_xyzw=np.array([[0.0, 0.0, 0.0, 1.0]] * 2),
    )
    (source / 'alignment.json').write_text(json.dumps({
        'source_episode': '/raw/episodes/episode_0001',
        'source_video': '/raw/episodes/episode_0001/video.mp4',
    }), encoding='utf-8')
    destination = tmp_path / 'transformed' / 'episode_0001'
    report = transform_item(source, destination)
    assert report['reference_frame_index'] == 0
    with np.load(destination / 'episode_frames.npz') as result:
        assert int(result['contract_version']) == 1
        np.testing.assert_allclose(result['position_xyz'], [
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])


def test_hdf5_export_keeps_image_pose_counts_equal(tmp_path, monkeypatch):
    """Write one compressed image and one relative pose per valid frame."""
    h5py = pytest.importorskip('h5py')
    from umi_ros2.postprocess import export_hdf5

    item = tmp_path / 'transformed' / 'episodes' / 'episode_0001'
    item.mkdir(parents=True)
    video = tmp_path / 'video.mp4'
    video.touch()
    np.savez_compressed(
        item / 'episode_frames.npz',
        contract_version=np.asarray(1), frame_index=np.array([0, 1]),
        video_pts_seconds=np.array([0.0, 1 / 30]),
        video_time_seconds=np.array([10.0, 10.0 + 1 / 30]),
        pose_query_time_seconds=np.array([10.1, 10.1 + 1 / 30]),
        valid=np.array([True, False]),
        position_xyz=np.array([[0.0, 0.0, 0.0], [np.nan] * 3]),
        orientation_xyzw=np.array([
            [0.0, 0.0, 0.0, 1.0], [np.nan] * 4]),
        reference_frame_index=np.asarray(0),
        reference_position_xyz=np.zeros(3),
        reference_orientation_xyzw=np.array([0.0, 0.0, 0.0, 1.0]),
    )
    (item / 'transform.json').write_text(json.dumps({
        'source_episode': '/raw/episode_0001',
        'source_video': str(video),
        'reference_definition': 'first_valid_aligned_video_frame_pose',
    }), encoding='utf-8')
    (tmp_path / 'transformed' / 'transform_summary.json').write_text(
        '{}', encoding='utf-8')

    class Capture:
        def __init__(self, unused_path):
            self.index = 0

        def read(self):
            if self.index >= 2:
                return False, None
            self.index += 1
            return True, np.zeros((2, 3, 3), dtype=np.uint8)

        def release(self):
            pass

    class FakeCv2:
        VideoCapture = Capture
        IMWRITE_JPEG_QUALITY = 1

        @staticmethod
        def imencode(extension, frame, options):
            return True, np.array([255, 216, 255, 217], dtype=np.uint8)

    monkeypatch.setattr(export_hdf5, '_cv2', lambda: FakeCv2)
    output = tmp_path / 'dataset.hdf5'
    args = SimpleNamespace(
        input_path=str(tmp_path / 'transformed'), output=str(output),
        task='test', jpeg_quality=90, overwrite=False,
    )
    assert export_hdf5.export_hdf5(args) == 0
    with h5py.File(output, 'r') as dataset:
        episode = dataset['episodes/episode_0000']
        assert episode['observations/images'].shape == (1,)
        assert episode['observations/pose'].shape == (1, 7)
        assert episode.attrs['dropped_invalid_frame_count'] == 1


def test_lerobot_export_uses_native_writer_contract(tmp_path, monkeypatch):
    """Feed synchronized frames through create/add/save/finalize."""
    from umi_ros2.postprocess import export_lerobot

    root = tmp_path / 'transformed'
    item = root / 'episodes' / 'episode_0001'
    item.mkdir(parents=True)
    video = tmp_path / 'video.mp4'
    video.touch()
    np.savez_compressed(
        item / 'episode_frames.npz',
        contract_version=np.asarray(1), frame_index=np.array([4, 5]),
        video_pts_seconds=np.array([1.0, 1.04]),
        video_time_seconds=np.array([11.0, 11.04]),
        pose_query_time_seconds=np.array([11.1, 11.14]),
        valid=np.array([True, False]),
        position_xyz=np.array([[0.0, 0.0, 0.0], [np.nan] * 3]),
        orientation_xyzw=np.array([
            [0.0, 0.0, 0.0, 1.0], [np.nan] * 4]),
        reference_frame_index=np.asarray(0),
        reference_position_xyz=np.zeros(3),
        reference_orientation_xyzw=np.array([0.0, 0.0, 0.0, 1.0]),
    )
    (item / 'transform.json').write_text(json.dumps({
        'source_episode': '/raw/episode_0001',
        'source_video': str(video),
        'reference_definition': 'first_valid_aligned_video_frame_pose',
    }), encoding='utf-8')
    (root / 'transform_summary.json').write_text('{}', encoding='utf-8')

    class Capture:
        def __init__(self, unused_path):
            self.index = 0

        def read(self):
            if self.index >= 2:
                return False, None
            self.index += 1
            return True, np.zeros((2, 3, 3), dtype=np.uint8)

        def release(self):
            pass

    class FakeCv2:
        VideoCapture = Capture
        COLOR_BGR2RGB = 1

        @staticmethod
        def cvtColor(frame, unused_conversion):
            return frame

    class FakeDataset:
        created = None

        @classmethod
        def create(cls, **kwargs):
            kwargs['root'].mkdir(parents=True)
            cls.created = cls()
            cls.created.kwargs = kwargs
            cls.created.frames = []
            cls.created.saved = 0
            cls.created.finalized = False
            return cls.created

        def add_frame(self, frame):
            self.frames.append(frame)

        def save_episode(self, parallel_encoding):
            assert parallel_encoding is False
            self.saved += 1

        def finalize(self):
            self.finalized = True

    monkeypatch.setattr(export_lerobot, '_cv2', lambda: FakeCv2)
    monkeypatch.setattr(
        export_lerobot, '_lerobot_dataset_class', lambda: FakeDataset)
    output = tmp_path / 'lerobot'
    args = SimpleNamespace(
        input_path=str(root), output=str(output), repo_id='local/test',
        task='pick', fps=30, video_codec='h264', image_writer_threads=0,
        encoder_threads=None, overwrite=False,
    )
    assert export_lerobot.export_lerobot(args) == 0
    created = FakeDataset.created
    assert created.saved == 1
    assert created.finalized
    assert len(created.frames) == 1
    assert created.frames[0]['observation.state'].tolist() == [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    assert created.frames[0]['umi.source_frame_index'].tolist() == [4]
    assert json.loads((output / 'umi_export.json').read_text())[
        'format'] == 'lerobot_v3'
