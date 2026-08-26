"""
Wave vector expansion for RCWA (Step 4).
"""
from __future__ import annotations

from typing import Dict

from .backend import get_array_module
from .linalg import _conj_sqrt
from .models import RCWAProblem


def _wavevector_expansion(problem: RCWAProblem, mx, my) -> Dict:
    """
    Implements lecture Step 4:
      k_inc_tilde = n_inc (sin(theta) cos(phi) xhat + sin(theta) sin(phi) yhat + cos(theta) zhat)
      kx(m,n) = kx_inc - m*T1x - n*T2x, where T1 = 2*pi/Lx, T2 = 2*pi/Ly
      In normalized form: kx_tilde = kx/k0 = kx_inc/k0 - m*(2*pi/(k0 Lx)) ...
    """
    xp = get_array_module()
    lat = problem.lattice
    inc = problem.inc

    k0 = 2*xp.pi / inc.wavelength

    # External media indices (normalized magnitude in k/k0 is sqrt(mu*eps))
    n_inc = xp.sqrt(problem.region_ref.mu_r * problem.region_ref.eps_r)

    kx_inc = n_inc * xp.sin(inc.theta) * xp.cos(inc.phi)
    ky_inc = n_inc * xp.sin(inc.theta) * xp.sin(inc.phi)
    kz_inc = n_inc * xp.cos(inc.theta)

    # normalized reciprocal lattice vectors
    gx = 2*xp.pi / (k0 * lat.Lx)
    gy = 2*xp.pi / (k0 * lat.Ly) if problem.settings.Ny != 0 else 0.0

    kx = kx_inc - mx * gx
    ky = ky_inc - my * gy

    # Kx, Ky are diagonal matrices (stored as vectors for efficiency)
    Kx = kx.astype(xp.complex128)
    Ky = ky.astype(xp.complex128)

    # longitudinal components in reflection/transmission regions:
    # kz_ref = - sqrt(mu_ref*eps_ref - kx^2 - ky^2)^*
    # kz_trn = + sqrt(mu_trn*eps_trn - kx^2 - ky^2)^*
    mu1, eps1 = problem.region_ref.mu_r, problem.region_ref.eps_r
    mu2, eps2 = problem.region_trn.mu_r, problem.region_trn.eps_r

    kz_ref = -_conj_sqrt(mu1*eps1 - Kx**2 - Ky**2)
    kz_trn = +_conj_sqrt(mu2*eps2 - Kx**2 - Ky**2)

    return dict(
        k0=float(k0),
        kinc=xp.array([kx_inc, ky_inc, kz_inc], dtype=xp.complex128),
        Kx=Kx,
        Ky=Ky,
        Kz_ref=kz_ref,
        Kz_trn=kz_trn,
    )
