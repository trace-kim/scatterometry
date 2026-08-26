"""
Utility functions for RCWA.
"""
from __future__ import annotations


def nk_to_eps(n: float, k: float) -> complex:
    """
    Convert optical constants to relative permittivity.

    This implementation represents passive media as ``n - 1j*kappa``.
    Optical-constant tables use both positive and negative signs for the
    extinction coefficient, so ``k`` is treated as a magnitude here. Pass a
    complex permittivity directly when modeling an active (gain) medium.
    """
    n_complex = complex(n, -abs(k))
    return n_complex**2
