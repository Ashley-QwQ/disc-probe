"""Level iPhone 17 Pro 1x, standard stabilisation, 3840px video calibration.

Change VIDEO_FOCAL_PX here, then run tools/focal_geometry.py, editor_pose_swatches.py,
focal_regression.py and make_rulers.py. Generated browser values are not a second calibration.
The placement grid is frozen; the table-to-lens height changes with focal length.
"""
from __future__ import annotations

import numpy as np

VIDEO_FOCAL_PX = 3355.0  # provisional: awaiting the user's two-height ruler measurement
VIDEO_WIDTH_PX = 3840
VIDEO_SHARE = .819
NATIVE_FRAME_PX = (8064, 6048)
LEGACY_DISC_HEIGHT_MM = 206.5
DISC_MM, SHEET_MM = 1.2, .1
DISC_AND_SHEET_MM = DISC_MM + SHEET_MM
LEGACY_TABLE_HEIGHT_MM = LEGACY_DISC_HEIGHT_MM + DISC_AND_SHEET_MM
# Frozen bbox from the original pose_1x.json, before the focal correction.
LEGACY_PHOTO_FOCAL_PX = 3124.067773216577 * LEGACY_DISC_HEIGHT_MM / 120
LEGACY_VIDEO_FOCAL_PX = LEGACY_PHOTO_FOCAL_PX * VIDEO_WIDTH_PX / (NATIVE_FRAME_PX[0] * VIDEO_SHARE)
TABLE_HEIGHT_MM = LEGACY_TABLE_HEIGHT_MM * VIDEO_FOCAL_PX / LEGACY_VIDEO_FOCAL_PX
DESIGN_Z_MM = TABLE_HEIGHT_MM - DISC_AND_SHEET_MM
DESIGN_RULER_CM = round(TABLE_HEIGHT_MM / 10, 2)
PHOTO_FOCAL_PX = VIDEO_FOCAL_PX * NATIVE_FRAME_PX[0] * VIDEO_SHARE / VIDEO_WIDTH_PX
LENS_Y_MM = 28.45
FLASH_Y_MM = 76.3857872575386  # exact original printed dot; do not move it to rounded 47.9mm
CAMERA = (0., LENS_Y_MM, DESIGN_Z_MM)
FLASH = (0., FLASH_Y_MM, DESIGN_Z_MM)
MAP_SIZE, MAP_WIDTH_MM = 4096, 160.


def along_track(x, y, camera=CAMERA, flash=FLASH):
    """Absolute (to camera + to flash) dot unit track tangent; x right, y up, mm."""
    r = np.maximum(np.hypot(x, y), 1e-30)
    result = np.zeros(np.broadcast_shapes(np.shape(x), np.shape(y)))
    for cx, cy, cz in (camera, flash):
        length = np.sqrt((cx - x) ** 2 + (cy - y) ** 2 + cz ** 2)
        result += (-(cx - x) * y + (cy - y) * x) / (length * r)
    return np.abs(result)


def map_rows(start, stop, size=MAP_SIZE, camera=CAMERA, flash=FLASH):
    c = (np.arange(size) + .5) * MAP_WIDTH_MM / size - MAP_WIDTH_MM / 2
    x, y = np.meshgrid(c, -c[start:stop])
    value = along_track(x, y, camera, flash).astype(np.float32)
    r = np.hypot(x, y)
    value[(r < 24) | (r > 58)] = np.nan
    return value
