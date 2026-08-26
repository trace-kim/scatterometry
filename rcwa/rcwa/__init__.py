"""
RCWA (Rigorous Coupled-Wave Analysis) electromagnetic simulation package.

Based on Lecture-7b RCWA Implementation methodology for EUV photomask modeling.

GPU Acceleration:
- Automatically detects CUDA-capable GPU with CuPy at import time
- Falls back to NumPy (CPU) if GPU is unavailable
- Use is_gpu_available() to check GPU status programmatically
"""
import warnings

from .backend import is_gpu_available
from .models import (
    Lattice,
    IncidentWave,
    ExternalRegion,
    Layer,
    RCWASettings,
    RCWAProblem,
)
from .patterns import (
    Pattern2D,
    HomogeneousPattern,
    BinaryLinespace1D,
)
from .smatrix import SMatrix
from .solver import RCWASolver
from .utils import nk_to_eps
from .fresnel import (
    FresnelLayer,
    FresnelProblem,
    FresnelSolver,
    nk_to_n,
    eps_to_n,
)

# Print GPU status at import time
if is_gpu_available():
    print("[RCWA] GPU acceleration enabled (CuPy)")
else:
    warnings.warn("[RCWA] GPU not available, using CPU (NumPy)", stacklevel=2)

__all__ = [
    # Backend
    "is_gpu_available",
    # Models
    "Lattice",
    "IncidentWave",
    "ExternalRegion",
    "Layer",
    "RCWASettings",
    "RCWAProblem",
    # Patterns
    "Pattern2D",
    "HomogeneousPattern",
    "BinaryLinespace1D",
    # S-Matrix
    "SMatrix",
    # Solver
    "RCWASolver",
    # Utilities
    "nk_to_eps",
    # Fresnel/TMM
    "FresnelLayer",
    "FresnelProblem",
    "FresnelSolver",
    "nk_to_n",
    "eps_to_n",
]
