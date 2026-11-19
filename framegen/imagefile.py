"""Image files at any path. OpenCV's imread/imwrite open files by Windows' narrow (ANSI) names, so a folder whose name
has letters outside English (e.g. Chinese, or an accented Windows user name) can't be read or written through them.
Python opens the file here; OpenCV only encodes and decodes."""
from __future__ import annotations

import os

import numpy as np


def read_image(path, flags: int | None = None):
    """cv2.imread(path, flags) for any path; None when the file is missing or isn't a picture."""
    import cv2
    try:
        data = np.fromfile(os.fspath(path), np.uint8)
    except OSError:
        return None
    if not data.size:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR if flags is None else flags)


def write_image(path, img) -> bool:
    """cv2.imwrite(path, img) for any path, in the format its extension names (PNG without one)."""
    import cv2
    ok, buf = cv2.imencode(os.path.splitext(os.fspath(path))[1] or ".png", img)
    if not ok:
        return False
    try:
        buf.tofile(os.fspath(path))
    except OSError:
        return False
    return True
