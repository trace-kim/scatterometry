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


def _conj_sqrt(z):
    """
    Lecture uses sqrt(.)^* for Kz choices.
    Implement as conj(sqrt(z)) elementwise.
    """
    xp = get_array_module()
    return xp.conj(xp.sqrt(z.astype(xp.complex128)))
