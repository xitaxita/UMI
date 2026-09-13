"""Generate the ArUco marker used by temporal calibration."""

import argparse
from pathlib import Path

import cv2

import numpy as np


def main(argv=None):
    """Write a printable marker PNG without depending on exUMI assets."""
    parser = argparse.ArgumentParser(
        description='Generate an ArUco marker PNG')
    parser.add_argument('--output', default='aruco_id4.png')
    parser.add_argument('--dictionary', default='DICT_4X4_50')
    parser.add_argument('--marker-id', type=int, default=4)
    parser.add_argument('--pixels', type=int, default=1200)
    args = parser.parse_args(argv)
    aruco = cv2.aruco
    if not hasattr(aruco, args.dictionary):
        parser.error(f'unknown ArUco dictionary {args.dictionary}')
    if args.pixels < 100:
        parser.error('--pixels must be at least 100')
    dictionary = aruco.getPredefinedDictionary(
        getattr(aruco, args.dictionary))
    marker = aruco.drawMarker(dictionary, args.marker_id, args.pixels)
    border = max(20, args.pixels // 8)
    printable = np.full(
        (args.pixels + 2 * border, args.pixels + 2 * border), 255,
        dtype=np.uint8)
    printable[border:-border, border:-border] = marker
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), printable):
        parser.error(f'could not write {output}')
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
