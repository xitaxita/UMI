"""Small adapter around pysurvive's high-level Simple API."""

from math import isfinite, sqrt
from shlex import split


def _text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def pose_components(pose):
    """Return finite ROS position and normalized (x, y, z, w) quaternion."""
    position = tuple(float(value) for value in pose.Pos)
    survive_quaternion = tuple(float(value) for value in pose.Rot)
    if len(position) != 3 or len(survive_quaternion) != 4:
        raise RuntimeError("pysurvive returned a malformed pose")
    if not all(isfinite(value) for value in position + survive_quaternion):
        raise RuntimeError("pysurvive returned a non-finite pose")
    norm = sqrt(sum(value * value for value in survive_quaternion))
    if norm <= 1e-12:
        raise RuntimeError("pysurvive returned an invalid zero quaternion")
    w, x, y, z = (value / norm for value in survive_quaternion)
    return position, (x, y, z, w)


class PySurviveBackend:
    def __init__(
        self,
        device_name="",
        device_serial="",
        device_index=-1,
        libsurvive_args="",
        pysurvive_module=None,
    ):
        if device_index < -1:
            raise ValueError("device_index must be -1 or greater")
        self.device_name = device_name
        self.device_serial = device_serial
        self.device_index = device_index
        self.libsurvive_args = libsurvive_args
        self._pysurvive = pysurvive_module
        self._context = None
        self._selected_identity = None

    def start(self):
        if self._pysurvive is None:
            try:
                import pysurvive
            except ImportError as error:
                raise RuntimeError(
                    "pysurvive is missing; install libsurvive and its "
                    "Python bindings"
                ) from error
            self._pysurvive = pysurvive

        arguments = ["vive_pose_node"] + split(self.libsurvive_args)
        self._context = self._pysurvive.SimpleContext(arguments)
        if not self._context.Running():
            self.stop()
            raise RuntimeError("libsurvive failed to start")
        return self.selector_description()

    def stop(self):
        if self._context is not None:
            self._pysurvive.simple_close(self._context.ptr)
        self._context = None
        self._selected_identity = None

    def selector_description(self):
        if self.device_name:
            return f"name '{self.device_name}'"
        if self.device_serial:
            return f"serial '{self.device_serial}'"
        if self.device_index >= 0:
            return f"device index {self.device_index}"
        return "the first tracked object"

    def _identity(self, tracked_object):
        name = _text(tracked_object.Name())
        serial_function = getattr(
            self._pysurvive, "simple_serial_number", None
        )
        serial = (
            _text(serial_function(tracked_object.ptr))
            if serial_function is not None else name
        )
        return name, serial

    @staticmethod
    def _is_lighthouse(name):
        return name.startswith("LH")

    def _matches(self, tracked_object):
        identity = self._identity(tracked_object)
        name, serial = identity
        if self._selected_identity is not None:
            return identity == self._selected_identity
        if self._is_lighthouse(name):
            return False
        if self.device_name:
            if name != self.device_name:
                return False
        elif self.device_serial:
            if serial != self.device_serial:
                return False
        elif self.device_index >= 0:
            candidates = [
                obj for obj in self._context.Objects()
                if not self._is_lighthouse(self._identity(obj)[0])
            ]
            if self.device_index >= len(candidates):
                return False
            if identity != self._identity(candidates[self.device_index]):
                return False
        self._selected_identity = identity
        return True

    def read_pose(self):
        if self._context is None:
            raise RuntimeError("pysurvive backend has not been started")
        if not self._context.Running():
            raise RuntimeError("libsurvive stopped running")

        latest_pose = None
        while True:
            tracked_object = self._context.NextUpdated()
            if tracked_object is None:
                break
            if not self._matches(tracked_object):
                continue
            pose, timecode = tracked_object.Pose()
            if float(timecode) <= 0.0:
                continue
            latest_pose = pose_components(pose)
        return latest_pose
