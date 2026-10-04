"""Camera interface shared by online acquisition backends, without ROS."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageFrame:
    """One preview image with its source and host timing identities."""

    camera_id: str
    image_field: str
    width: int
    height: int
    encoding: str
    data: bytes
    source_pts_ns: int | None
    receive_unix_ns: int


class CameraSource(ABC):
    """Keep a camera warm and control its preview and recording lifecycle."""

    camera_id: str
    image_field: str

    @abstractmethod
    def start(self) -> None:
        """Start continuous image acquisition and preview."""

    @abstractmethod
    def latest_preview(self) -> ImageFrame | None:
        """Take the newest preview frame, dropping older preview frames."""

    @abstractmethod
    def wait_for_state(self, expected: str, timeout: float) -> bool:
        """Wait for worker readiness or a recording state transition."""

    @abstractmethod
    def start_recording(
            self, output_path: str | Path, timing_path: str | Path) -> None:
        """Start writing one recording without restarting acquisition."""

    @abstractmethod
    def stop_recording(self) -> None:
        """Finalize the current recording while acquisition continues."""

    @abstractmethod
    def poll(self) -> int | None:
        """Return the worker exit code, or None while it is running."""

    @abstractmethod
    def close(self) -> None:
        """Stop acquisition and release the worker."""
