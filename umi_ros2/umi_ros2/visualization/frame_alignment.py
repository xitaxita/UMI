"""Read recordings and pair individual images with corrected poses."""

from dataclasses import dataclass

import cv2

import numpy as np

from umi_ros2.postprocess.align_session import video_frame_times
from umi_ros2.postprocess.alignment import (
    interpolate_poses, prepare_pose_samples)
from umi_ros2.postprocess.episode_transform import poses_in_reference_frame
from umi_ros2.postprocess.pose_io import read_vive_poses


def nearest_frame(times, target):
    """Choose the closest actual frame; return None outside camera coverage."""
    if target < times[0] or target > times[-1]:
        return None
    right = int(np.searchsorted(times, target))
    if right == 0:
        return 0
    return right if times[right] - target < target - times[right - 1] else (
        right - 1)


class VideoFrames:
    """Decode selected MP4 frames without opening a live camera."""

    def __init__(self, path):
        """Open one file and keep only the last decoded frame in memory."""
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            raise ValueError(f'cannot open video: {path}')
        self.index = -1
        self.frame = None

    def read(self, index):
        """Read a zero-based frame, seeking only for non-sequential use."""
        if index == self.index:
            return self.frame
        if index != self.index + 1:
            if not self.capture.set(cv2.CAP_PROP_POS_FRAMES, index):
                raise ValueError(f'cannot seek to video frame {index}')
        ok, frame = self.capture.read()
        if not ok:
            raise ValueError(f'cannot decode video frame {index}')
        self.index = index
        self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self.frame

    def close(self):
        """Release this video file."""
        self.capture.release()


@dataclass
class CameraTimeline:
    """Actual frame times and both raw/corrected interpolated local poses."""

    video: object
    pts: np.ndarray
    query_times: dict
    poses: dict
    reader: VideoFrames


class AlignedRecording:
    """Cache one pose bag and each camera's timeline for manual inspection."""

    def __init__(self, item):
        """Use the first saved pose as the fixed recording-start reference."""
        self.item = item
        times, positions, orientations = read_vive_poses(item.pose_path)
        self.reference_time = float(times[0])
        local_positions, local_orientations = poses_in_reference_frame(
            positions, orientations, positions[0], orientations[0])
        self.pose_times, self.positions, self.orientations = (
            prepare_pose_samples(times, local_positions, local_orientations))
        self.cameras = {}
        try:
            for video in item.videos:
                pts = video_frame_times(video.video_path)
                base_times = video.start_ns / 1_000_000_000 + pts
                queries = {
                    False: base_times,
                    True: base_times + video.offset_seconds,
                }
                poses = {
                    mode: interpolate_poses(
                        values, self.pose_times, self.positions,
                        self.orientations)
                    for mode, values in queries.items()
                }
                self.cameras[video.camera_id] = CameraTimeline(
                    video, pts, queries, poses, VideoFrames(video.video_path))
        except Exception:
            self.close()
            raise

    def selection(self, primary, index, calibrated=True):
        """Pair by corrected times, retaining the exact primary frame."""
        target = self.cameras[primary].query_times[calibrated][index]
        return target, {
            camera_id: (index if camera_id == primary else
                        nearest_frame(camera.query_times[calibrated], target))
            for camera_id, camera in self.cameras.items()
        }

    def close(self):
        """Release all video files without changing any recording data."""
        for camera in self.cameras.values():
            camera.reader.close()
