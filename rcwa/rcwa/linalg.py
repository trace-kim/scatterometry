"""
Linear algebra helper functions for RCWA.
"""
from __future__ import annotations

from .backend import get_array_module


def _solve(A, B):
    """Solve A X = B (prefer solve over explicit inverse)."""
    xp = get_array_module()
    return xp.linalg.solve(A, B)


def _diag(v):
    """Diagonal matrix from vector."""
    xp = get_array_module()
    return xp.diag(v)


def _as_diag_vec(D):
    """Extract diagonal as vector (assumes D is diagonal-ish)."""
    xp = get_array_module()
    return xp.diag(D)


def _outgoing_sqrt(z):
    """
    Select the outgoing/decaying square-root branch elementwise.

    Fields propagate as ``exp(-1j * kz * z)`` in this implementation, so a
    forward passive or evanescent wave must have ``Im(kz) <= 0``. For a real
    propagating root, choose ``Re(kz) >= 0``.
    """
    xp = get_array_module()
    root = xp.sqrt(xp.asarray(z, dtype=xp.complex128))
    flip = (xp.imag(root) > 0) | (
        (xp.imag(root) == 0) & (xp.real(root) < 0)
    )
    return xp.where(flip, -root, root)
