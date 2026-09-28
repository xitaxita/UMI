"""Ordering helpers shared by acquisition, replay and post-processing.

Kept free of ROS and YAML so the separate LeRobot environment can import it.
"""

import re
from pathlib import Path


def natural_key(path):
    """Sort names containing numbers numerically (episode_2 < episode_10)."""
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r'(\d+)', Path(path).name)
    ]
