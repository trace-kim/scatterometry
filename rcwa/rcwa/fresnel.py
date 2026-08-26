"""
Fresnel coefficient based reflectance/transmittance using transfer matrix method (TMM).

Used to cross-check RCWA results for homogeneous multilayer stacks.
For homogeneous layers (no grating), RCWA and Fresnel/TMM should give identical results.

Convention: n_complex = n - i*k (loss gives negative imaginary part in epsilon).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict

import numpy as np


@dataclass
class FresnelLayer:
    """
    A layer for Fresnel/TMM calculation.
    - thickness: layer thickness in meters
    - n: complex refractive index (n - i*k convention)
    """
    thickness: float
    n: complex


@dataclass
class FresnelProblem:
    """
    Problem definition for Fresnel/TMM calculation.
    - wavelength: wavelength in meters
    - theta: angle of incidence in radians (from normal)
    - n_inc: refractive index of incident medium
    - n_sub: refractive index of substrate (exit medium)
    - layers: list of layers between incident medium and substrate
    - polarization: 's' (TE) or 'p' (TM)
    """
    wavelength: float
    theta: float
    n_inc: complex
    n_sub: complex
    layers: List[FresnelLayer]
    polarization: str = 's'


def _cos_theta(n0: complex, theta0: float, nj: complex) -> complex:
    """
    Compute cos(theta_j) using Snell's law: n0*sin(theta0) = nj*sin(theta_j).
    Branch choice: Re(cos) >= 0 for forward-propagating/decaying waves.
    """
    sin_j = (n0 * np.sin(theta0)) / nj
    cos_j = np.sqrt(1 - sin_j * sin_j)
    if np.real(cos_j) < 0:
        cos_j = -cos_j
    return cos_j


def _admittance(n: complex, cos_theta: complex, pol: str) -> complex:
    """
    Optical admittance for each polarization (non-magnetic mu=1).
    s (TE): q = n * cos(theta)
    p (TM): q = n / cos(theta)
    """
    if pol == 's':
        return n * cos_theta
    else:  # 'p'
        return n / cos_theta


class FresnelSolver:
    """
    Solver for multilayer reflectance/transmittance using characteristic matrix TMM.
    """

    def solve(self, problem: FresnelProblem) -> Dict[str, float]:
        """
        Calculate reflectance and transmittance for the multilayer stack.

        Returns dict with:
          - R: reflectance (power)
          - T: transmittance (power)
          - A: absorptance (1 - R - T)
          - r: complex amplitude reflection coefficient
          - t: complex amplitude transmission coefficient
        """
        k0 = 2.0 * np.pi / problem.wavelength
        pol = problem.polarization

        n0 = complex(problem.n_inc)
        ns = complex(problem.n_sub)
        theta0 = problem.theta

        # Angles and admittances in incident and substrate
        cos0 = _cos_theta(n0, theta0, n0)
        coss = _cos_theta(n0, theta0, ns)

        q0 = _admittance(n0, cos0, pol)
        qs = _admittance(ns, coss, pol)

        # Build characteristic matrix M
        M = np.eye(2, dtype=np.complex128)

        for layer in problem.layers:
            nj = complex(layer.n)
            dj = layer.thickness

            cosj = _cos_theta(n0, theta0, nj)
            qj = _admittance(nj, cosj, pol)

            delta = k0 * nj * cosj * dj  # phase thickness
            c = np.cos(delta)
            s = 1j * np.sin(delta)

            # Characteristic matrix for layer j
            Mj = np.array([
                [c, s / qj],
                [s * qj, c]
            ], dtype=np.complex128)

            M = M @ Mj

        # Extract r, t from characteristic matrix
        A, B = M[0, 0], M[0, 1]
        C, D = M[1, 0], M[1, 1]

        Y_in = (C + D * qs) / (A + B * qs)

        r = (q0 - Y_in) / (q0 + Y_in)
        t = 2 * q0 / ((q0 + Y_in) * (A + B * qs))

        # Power coefficients
        R = float(np.real(r * np.conj(r)))
        T = float(np.real(qs) / np.real(q0) * np.real(t * np.conj(t)))
        A_abs = 1.0 - R - T

        return dict(
            R=R,
            T=T,
            A=A_abs,
            r=complex(r),
            t=complex(t),
        )


def nk_to_n(n: float, k: float) -> complex:
    """
    Convert (n, k) optical constants to complex refractive index.

    Passive media use ``n - 1j*kappa``. Both positive and negative extinction
    values are accepted and normalized to that convention. Pass a complex
    refractive index directly when modeling gain.
    """
    return complex(n, -abs(k))


def eps_to_n(eps_r: complex) -> complex:
    """
    Convert relative permittivity to complex refractive index.
    Select the passive branch with ``Im(n) <= 0`` and, for real roots,
    ``Re(n) >= 0``.
    """
    n = np.sqrt(complex(eps_r))
    if np.imag(n) > 0 or (np.imag(n) == 0 and np.real(n) < 0):
        n = -n
    return complex(n)
