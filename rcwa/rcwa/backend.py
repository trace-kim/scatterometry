"""
Array backend abstraction for CPU/GPU support.

Provides a unified interface that uses CuPy when available, NumPy otherwise.
GPU detection happens at import time.
"""
from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)

# Global state for backend
_GPU_AVAILABLE = False
_xp = None  # Array module (numpy or cupy)

# Attempt to import CuPy and verify CUDA availability
try:
    import cupy as cp
    # Verify CUDA is actually available by checking device count
    if cp.cuda.runtime.getDeviceCount() > 0:
        _GPU_AVAILABLE = True
        _xp = cp
        _logger.info("GPU acceleration enabled (CuPy with CUDA)")
    else:
        raise RuntimeError("No CUDA devices found")
except Exception as e:
    import numpy as np
    _xp = np
    _GPU_AVAILABLE = False
    # Check if GPU was explicitly required
    if os.environ.get('RCWA_GPU_REQUIRED'):
        raise RuntimeError(f"GPU required but CuPy/CUDA not available: {e}")


def get_array_module():
    """
    Return the active array module (cupy or numpy).

    Use this to get the appropriate array library for computations.
    Example:
        xp = get_array_module()
        arr = xp.zeros((10, 10), dtype=xp.complex128)
    """
    return _xp


def is_gpu_available() -> bool:
    """Check if GPU acceleration is available."""
    return _GPU_AVAILABLE


def to_numpy(arr):
    """
    Convert array to NumPy (for output/compatibility).

    If arr is a CuPy array, transfers it to CPU.
    If arr is already NumPy, returns it unchanged.
    """
    if _GPU_AVAILABLE and hasattr(arr, 'get'):
        return arr.get()
    return arr


def to_device(arr):
    """
    Move NumPy array to device (GPU if available).

    If GPU is available, converts to CuPy array.
    If GPU is not available, returns the array unchanged.
    """
    if _GPU_AVAILABLE:
        import cupy as cp
        return cp.asarray(arr)
    return arr


def synchronize():
    """
    Synchronize GPU operations.

    Waits for all GPU operations to complete.
    No-op if running on CPU.
    """
    if _GPU_AVAILABLE:
        import cupy as cp
        cp.cuda.Stream.null.synchronize()
