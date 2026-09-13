"""Startup admission must reject bursts without hiding later frame gaps."""

import pytest

from umi_ros2.camera.capture_pipeline import WarmupGate


def test_burst_and_corruption_reset_stability():
    """Startup filtering must latch open and preserve later bad buffers."""
    gate = WarmupGate(seconds=0.1, fps=30, stable_intervals=3)
    assert not gate.accept(0, 0, valid=False)
    for i in range(1, 30):
        assert not gate.accept(i * 5_000_000, i * 5_000_000)
    assert not gate.accept(180_000_000, 180_000_000)
    assert not gate.accept(213_333_333, 213_333_333)
    assert gate.accept(246_666_666, 246_666_666)
    assert gate.excluded == 32
    # After readiness even an invalid PTS/gap remains visible in the recording.
    assert gate.accept(None, 900_000_000, valid=False)


def test_waits_for_elapsed_streaming_time_not_process_start():
    """Stable intervals alone cannot bypass the receive-time warmup."""
    gate = WarmupGate(seconds=5, fps=30, stable_intervals=3)
    for i in range(151):
        accepted = gate.accept(
            i * 33_333_334, 100_000_000_000 + i * 33_333_334)
        assert accepted == (i == 150)


def test_missing_or_backward_pts_does_not_open_gate():
    """Unusable source timestamps must reset readiness."""
    gate = WarmupGate(seconds=0, fps=30, stable_intervals=2)
    for i, pts in enumerate((None, 50_000_000, 40_000_000, None)):
        assert not gate.accept(pts, i * 100_000_000)
    assert not gate.started


@pytest.mark.parametrize('seconds', [-1, float('nan'), float('inf')])
def test_invalid_warmup_rejected(seconds):
    """Reject nonsensical or nonfinite warmup durations."""
    with pytest.raises(ValueError):
        WarmupGate(seconds=seconds)
