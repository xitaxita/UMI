from types import SimpleNamespace

import pytest

from umi_ros2.vive.backend import PySurviveBackend, pose_components


class FakeObject:
    def __init__(self, name, serial, pose, timecode=1.0):
        self.ptr = self
        self.name = name
        self.serial = serial
        self.pose = pose
        self.timecode = timecode

    def Name(self):
        return self.name.encode()

    def Pose(self):
        return self.pose, self.timecode


class FakeContext:
    def __init__(self, objects):
        self.ptr = self
        self.objects = objects
        self.updates = list(objects)
        self.running = True

    def Running(self):
        return self.running

    def Objects(self):
        return self.objects

    def NextUpdated(self):
        return self.updates.pop(0) if self.updates else None


class FakePySurvive:
    def __init__(self, objects):
        self.context = FakeContext(objects)
        self.arguments = None
        self.closed = False

    def SimpleContext(self, arguments):
        self.arguments = arguments
        return self.context

    @staticmethod
    def simple_serial_number(pointer):
        return pointer.serial.encode()

    def simple_close(self, pointer):
        self.closed = True
        pointer.running = False


def make_pose(position=(1.0, 2.0, 3.0), rotation=(1.0, 0.0, 0.0, 0.0)):
    return SimpleNamespace(Pos=position, Rot=rotation)


def test_pose_components_reorders_wxyz_for_ros():
    position, orientation = pose_components(
        make_pose(rotation=(0.5, 0.5, 0.5, 0.5))
    )
    assert position == (1.0, 2.0, 3.0)
    assert orientation == (0.5, 0.5, 0.5, 0.5)


def test_backend_selects_device_by_serial_and_skips_lighthouse():
    lighthouse = FakeObject('LH0', 'base', make_pose())
    tracker = FakeObject('T20', 'tracker-123', make_pose())
    module = FakePySurvive([lighthouse, tracker])
    backend = PySurviveBackend(
        device_serial='tracker-123', pysurvive_module=module
    )
    assert backend.start() == "serial 'tracker-123'"
    assert backend.read_pose() == (
        (1.0, 2.0, 3.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    backend.stop()
    assert module.closed


def test_backend_passes_libsurvive_arguments():
    module = FakePySurvive([])
    backend = PySurviveBackend(
        libsurvive_args='--force-calibrate --v 10',
        pysurvive_module=module,
    )
    backend.start()
    assert module.arguments == [
        'vive_pose_node', '--force-calibrate', '--v', '10'
    ]


def test_pose_components_rejects_zero_quaternion():
    with pytest.raises(RuntimeError, match='zero quaternion'):
        pose_components(make_pose(rotation=(0.0, 0.0, 0.0, 0.0)))
