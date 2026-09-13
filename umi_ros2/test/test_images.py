"""Tests for shared JPEG processing."""

import cv2
import numpy as np
import pytest

from umi_ros2.common.images import decode_jpeg, extract_jpeg


def test_extract_jpeg_removes_padding():
    jpeg = b'\xff\xd8payload\xff\xd9'
    assert extract_jpeg(b'prefix' + jpeg + bytes(20)) == jpeg


def test_extract_jpeg_rejects_incomplete_frame():
    with pytest.raises(ValueError, match='complete JPEG'):
        extract_jpeg(b'not a jpeg')


def test_decode_jpeg_returns_bgr_frame():
    source = np.zeros((3, 4, 3), dtype=np.uint8)
    source[:, :, 1] = 255
    encoded, jpeg = cv2.imencode('.jpg', source)
    assert encoded
    assert decode_jpeg(jpeg.tobytes()).shape == (3, 4, 3)


def test_decode_jpeg_rejects_invalid_data():
    with pytest.raises(ValueError, match='decode'):
        decode_jpeg(b'not a jpeg')
