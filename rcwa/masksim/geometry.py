"""Anti-aliased periodic mask patterns (Pattern2D implementations).

Each sample is the area average of the ideal binary pattern over its pixel, so CD
changes smaller than the grid spacing (e.g. sidewall staircase steps) still change
the Fourier coefficients smoothly. All patterns are frozen dataclasses, so equal
layers hash equal and NearFieldSolver can share their eigenmodes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from rcwa.backend import get_array_module
from rcwa.patterns import Pattern2D


def _module_for(a):
    """Array module of `a`: the solver backend for device arrays, NumPy otherwise."""
    xp = get_array_module()
    return xp if isinstance(a, xp.ndarray) else np


def grid_pixel(X, Y, Lx: float, Ly: float) -> Tuple[float, float]:
    """Pixel size of a meshgrid (indexing="xy"); a single sample spans the whole period."""
    dx = abs(float(X[0, 1] - X[0, 0])) if X.shape[1] > 1 else Lx
    dy = abs(float(Y[1, 0] - Y[0, 0])) if Y.shape[0] > 1 else Ly
    return dx, dy


def interval_cover(x, d: float, center: float, width: float, period: float):
    """Fraction of [x - d/2, x + d/2] inside the periodic interval |x - center| <= width/2.

    d <= 0 gives point sampling.
    """
    xp = _module_for(x)
    width = min(max(float(width), 0.0), float(period))
    if d <= 0.0:
        u = (x - center + 0.5 * period) % period - 0.5 * period
        return (xp.abs(u) <= 0.5 * width).astype(float)
    start = center - 0.5 * width

    def covered(s):  # pattern length inside [start, s]; continuous and monotonic in s
        u = s - start
        n = xp.floor(u / period)
        return n * width + xp.minimum(u - n * period, width)

    return (covered(x + 0.5 * d) - covered(x - 0.5 * d)) / d


def ellipse_cover(x, y, dx, dy, cx, cy, wx, wy, Lx, Ly, oversample: int = 4):
    """Fraction of each pixel inside a periodic ellipse of diameters (wx, wy)."""
    xp = _module_for(x)
    if wx <= 0.0 or wy <= 0.0:
        return xp.zeros(x.shape)
    ax, ay = 0.5 * min(wx, Lx), 0.5 * min(wy, Ly)
    offsets = (np.arange(oversample) + 0.5) / oversample - 0.5
    acc = xp.zeros(x.shape)
    for ox in offsets:
        u = (x + ox * dx - cx + 0.5 * Lx) % Lx - 0.5 * Lx
        for oy in offsets:
            v = (y + oy * dy - cy + 0.5 * Ly) % Ly - 0.5 * Ly
            acc += (u / ax) ** 2 + (v / ay) ** 2 <= 1.0
    return acc / oversample**2


class MaskPattern(Pattern2D):
    """Two-material pattern: eps = eps_fill + f_host * (eps_host - eps_fill).

    Subclasses provide `cell` (unit-cell size) and `host_fraction`, the area
    fraction occupied by the layer's own (host) material.
    """
    eps_host: complex
    eps_fill: complex

    @property
    def cell(self) -> Tuple[float, float]:
        raise NotImplementedError

    def host_fraction(self, X, Y, dx: float = 0.0, dy: float = 0.0):
        raise NotImplementedError

    def uniform_eps(self):
        return complex(self.eps_host) if self.eps_host == self.eps_fill else None

    def eps_r(self, X, Y):
        f = self.host_fraction(X, Y, *grid_pixel(X, Y, *self.cell))
        xp = _module_for(X)
        return (self.eps_fill + f * (self.eps_host - self.eps_fill)).astype(xp.complex128)


@dataclass(frozen=True)
class UniformPattern(MaskPattern):
    """Homogeneous layer."""
    eps_host: complex
    eps_fill: complex = None

    def __post_init__(self):
        if self.eps_fill is None:
            object.__setattr__(self, "eps_fill", self.eps_host)

    @property
    def cell(self) -> Tuple[float, float]:
        return 1.0, 1.0

    def host_fraction(self, X, Y, dx: float = 0.0, dy: float = 0.0):
        return _module_for(X).ones(X.shape)


@dataclass(frozen=True)
class LineSpacePattern(MaskPattern):
    """Host lines of width `cd`, centred at pitch/2; axis="x" repeats along x (lines parallel to y)."""
    pitch: float
    cd: float
    eps_host: complex
    eps_fill: complex
    axis: str = "x"

    @property
    def cell(self) -> Tuple[float, float]:
        return self.pitch, self.pitch

    def host_fraction(self, X, Y, dx: float = 0.0, dy: float = 0.0):
        coord, d = (X, dx) if self.axis == "x" else (Y, dy)
        return interval_cover(coord, d, 0.5 * self.pitch, self.cd, self.pitch)


@dataclass(frozen=True)
class HoleArrayPattern(MaskPattern):
    """Rectangular or elliptical features on a square or staggered lattice.

    tone="holes": openings (eps_fill) in the host layer; tone="pillars": host islands
    in eps_fill. For staggered arrays pitch_y is the row spacing and alternate rows
    shift by pitch_x/2, giving a pitch_x x 2*pitch_y unit cell with two features.
    """
    pitch_x: float
    pitch_y: float
    cd_x: float
    cd_y: float
    eps_host: complex
    eps_fill: complex
    staggered: bool = False
    shape: str = "rect"
    tone: str = "holes"

    @property
    def cell(self) -> Tuple[float, float]:
        return self.pitch_x, self.pitch_y * (2.0 if self.staggered else 1.0)

    def centers(self):
        px, py = self.pitch_x, self.pitch_y
        if self.staggered:
            return [(0.5 * px, 0.5 * py), (0.0, 1.5 * py)]
        return [(0.5 * px, 0.5 * py)]

    def feature_fraction(self, X, Y, dx: float = 0.0, dy: float = 0.0):
        """Area fraction of the features (openings or pillars); overlaps are clipped."""
        xp = _module_for(X)
        Lx, Ly = self.cell
        total = xp.zeros(X.shape)
        for cx, cy in self.centers():
            if self.shape == "ellipse":
                total = total + ellipse_cover(X, Y, dx, dy, cx, cy, self.cd_x, self.cd_y, Lx, Ly)
            else:
                total = total + (interval_cover(X, dx, cx, self.cd_x, Lx)
                                 * interval_cover(Y, dy, cy, self.cd_y, Ly))
        return xp.minimum(total, 1.0)

    def host_fraction(self, X, Y, dx: float = 0.0, dy: float = 0.0):
        f = self.feature_fraction(X, Y, dx, dy)
        return 1.0 - f if self.tone == "holes" else f
