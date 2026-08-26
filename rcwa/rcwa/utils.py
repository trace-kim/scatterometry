"""
Utility functions for RCWA.
"""
from __future__ import annotations


def nk_to_eps(n: float, k: float) -> complex:
    """
    Convert (n,k) to relative permittivity eps_r = (n_complex)^2
    IMPORTANT: this RCWA implementation uses the convention that LOSS => Im(eps) < 0
    so we use n_complex = n - 1j*k.
    """
    n_complex = n - 1j * k
    return n_complex**2
