"""Binary framing for preview images sent by a camera worker."""

import struct


PREVIEW_HEADER = struct.Struct('!QQ')
NO_SOURCE_PTS = (1 << 64) - 1
