"""
Data model classes for RCWA problem definition (Step 0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .patterns import Pattern2D


@dataclass(frozen=True)
class Lattice:
    """Unit cell periods."""
    Lx: float
    Ly: float = 1.0  # for 1D gratings, you may set Ly arbitrary (not used if Ny=0)


@dataclass(frozen=True)
class IncidentWave:
    """
    Source parameters.
    - wavelength: meters (or consistent length unit)
    - theta, phi: radians
    - pTE, pTM: weights along TE/TM basis (will be normalized)
    """
    wavelength: float
    theta: float = 0.0
    phi: float = 0.0
    pTE: float = 1.0
    pTM: float = 0.0


@dataclass(frozen=True)
class ExternalRegion:
    """
    Homogeneous external region (reflection or transmission side).
    Provide relative epsilon and mu (can be complex).
    """
    eps_r: complex = 1.0 + 0j
    mu_r: complex = 1.0 + 0j


@dataclass(frozen=True)
class Layer:
    """
    A single RCWA layer.
    - thickness: layer thickness
    - pattern: provides eps_r(x,y) on the unit cell
    - mu_r: usually 1.0
    """
    thickness: float
    pattern: Pattern2D
    mu_r: complex = 1.0 + 0j


@dataclass(frozen=True)
class RCWASettings:
    """
    RCWA numerical settings.
    Nx, Ny: number of harmonics on each side of the window centre
    shift_x, shift_y: window centre; orders are shift_x-Nx..shift_x+Nx (likewise y).
        |shift| <= N keeps the specular order (0, 0) in the window. A shift towards
        kx = 0 (pupil_centre_shift) covers the propagating orders at oblique incidence.
    grid_Nx, grid_Ny: real-space sampling for building convolution matrices (Step 2/3)
    """
    Nx: int
    Ny: int
    grid_Nx: int
    grid_Ny: int
    debug: bool = False
    shift_x: int = 0
    shift_y: int = 0


@dataclass(frozen=True)
class RCWAProblem:
    lattice: Lattice
    inc: IncidentWave
    region_ref: ExternalRegion
    region_trn: ExternalRegion
    layers: List[Layer]
    settings: RCWASettings
