"""
Pattern classes for RCWA layer permittivity definitions.
"""
from __future__ import annotations

from .backend import get_array_module


class Pattern2D:
    """
    Minimal pattern interface.
    Return epsilon_r(x,y) on a meshgrid (X,Y).
    """
    def eps_r(self, X, Y):
        raise NotImplementedError

    def uniform_eps(self):
        """The permittivity if the pattern is homogeneous, else None.

        NearFieldSolver gives homogeneous layers analytic modes and O(Nh) S-matrices.
        """
        return None


class HomogeneousPattern(Pattern2D):
    def __init__(self, eps_r: complex):
        self._eps = complex(eps_r)

    def uniform_eps(self):
        return self._eps

    def eps_r(self, X, Y):
        xp = get_array_module()
        return xp.full(X.shape, self._eps, dtype=xp.complex128)


class BinaryLinespace1D(Pattern2D):
    """
    1D binary grating in x (lines along y):
      - pitch: Lx
      - CD: critical dimension (line width)
      - eps_line, eps_space: relative permittivities (complex OK)
      - center: if True, line centered in unit cell
    """
    def __init__(self, pitch: float, CD: float, eps_line: complex, eps_space: complex, center: bool = True):
        self.pitch = pitch
        self.CD = CD
        self.eps_line = complex(eps_line)
        self.eps_space = complex(eps_space)
        self.center = center

    def eps_r(self, X, Y):
        xp = get_array_module()
        # X is assumed to span [0, Lx)
        if self.center:
            x0 = 0.5 * self.pitch
        else:
            x0 = 0.0
        dx = (X - x0 + 0.5*self.pitch) % self.pitch - 0.5*self.pitch
        mask = xp.abs(dx) <= 0.5 * self.CD
        out = xp.full(X.shape, self.eps_space, dtype=xp.complex128)
        out[mask] = self.eps_line
        return out
