"""Shared JPEG and preview conversion helpers."""

import cv2
import numpy as np
from sensor_msgs.msg import Image


def extract_jpeg(data):
    """Extract one JPEG payload from a possibly padded byte sequence."""
    payload = bytes(data)
    start = payload.find(b'\xff\xd8')
    end = payload.find(b'\xff\xd9', start + 2)
    if start < 0 or end < 0:
        raise ValueError('source frame does not contain a complete JPEG')
    return payload[start:end + 2]


def decode_jpeg(data):
    """Decode JPEG bytes to a BGR array, raising on invalid input."""
    encoded = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError('Unable to decode compressed JPEG image')
    return frame


def make_preview(source, header, width, height):
    """Resize a BGR array and return a ROS Image message."""
    frame = cv2.resize(
        source, (width, height), interpolation=cv2.INTER_AREA
    )
    preview = Image()
    preview.header = header
    preview.height = height
    preview.width = width
    preview.encoding = 'bgr8'
    preview.is_bigendian = False
    preview.step = width * 3
    preview.data = frame.tobytes()
    return preview
