"""Binary array responses: NumPy .npz archives (uncompressed zip of .npy files).

The browser unpacks them with fflate and reads each .npy header for dtype and shape,
so responses double as files that open directly with numpy.load.
"""
from __future__ import annotations

import io
from typing import Dict

import numpy as np
from fastapi import Response

NPZ_MEDIA_TYPE = "application/octet-stream"
NPZ_RESPONSES: Dict = {200: {"content": {NPZ_MEDIA_TYPE: {}}, "description": "NumPy .npz archive"}}


def npz_response(**arrays: np.ndarray) -> Response:
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    return Response(buffer.getvalue(), media_type=NPZ_MEDIA_TYPE, headers={"X-Array-Format": "npz"})


def as_complex64(value: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(value, dtype=np.complex64)


def as_index(value: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(value, dtype=np.uint8)


def nm(value_m: np.ndarray) -> np.ndarray:
    return np.asarray(value_m, dtype=np.float64) / 1e-9
