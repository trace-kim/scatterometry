"""
Convolution matrix construction for RCWA (Steps 2-3).
"""
from __future__ import annotations

import math
from typing import Tuple

from .backend import get_array_module
from .models import Layer, Lattice, RCWASettings


def _harmonic_indices(Nx: int, Ny: int, shift_x: int = 0, shift_y: int = 0) -> Tuple:
    """Return arrays mx, my listing harmonic orders in a consistent flattened order.

    Orders run shift_x-Nx..shift_x+Nx (mx fastest) and shift_y-Ny..shift_y+Ny.
    """
    if abs(shift_x) > Nx or abs(shift_y) > Ny:
        raise ValueError("harmonic window must contain the specular order: need |shift| <= N")
    xp = get_array_module()
    mx = xp.arange(shift_x - Nx, shift_x + Nx + 1)
    my = xp.arange(shift_y - Ny, shift_y + Ny + 1)
    MX, MY = xp.meshgrid(mx, my, indexing="xy")  # shape (2Ny+1, 2Nx+1)
    return MX.ravel(), MY.ravel()


def pupil_centre_shift(k_inc: float, g: float, N: int) -> int:
    """Window centre that puts kx = k_inc - m g = 0 mid-window, kept within |shift| <= N.

    k_inc and g are normalized by k0 (k_inc = n sin(theta) cos(phi), g = lambda / L).
    """
    if N == 0 or g == 0:
        return 0
    # Round half up (not Python's half-to-even) so the web UI can mirror it exactly.
    return int(max(-N, min(N, math.floor(k_inc / g + 0.5))))


def _fft_coeffs_2d(f_xy):
    """
    Fourier coefficients from a sampled real-space unit cell.
    Returns coefficients arranged with zero-frequency centered (fftshifted).
    Normalization matches the lecture-style convolution construction:
    coefficient = (1/NP) * FFT
    """
    xp = get_array_module()
    F = xp.fft.fft2(f_xy) / (f_xy.shape[0] * f_xy.shape[1])
    return xp.fft.fftshift(F)


def _convmat_from_coeffs(coeffs_shifted, mx, my):
    """
    Build the convolution matrix:
      C[p,q] = f_{(m_p - m_q, n_p - n_q)}
    where (m_p,n_p) are harmonic orders for flattened index p.

    coeffs_shifted is 2D array with zero-frequency at center (fftshifted).
    """
    xp = get_array_module()
    Nyc, Nxc = coeffs_shifted.shape
    cx0 = Nxc // 2
    cy0 = Nyc // 2

    dm = (mx[:, None] - mx[None, :]).astype(int)
    dn = (my[:, None] - my[None, :]).astype(int)

    ix = cx0 + dm
    iy = cy0 + dn

    # bounds safety (should not happen if grid supports requested harmonics)
    if xp.any(ix < 0) or xp.any(ix >= Nxc) or xp.any(iy < 0) or xp.any(iy >= Nyc):
        raise ValueError("Real-space grid too small for requested harmonics; increase grid_Nx/grid_Ny.")

    return coeffs_shifted[iy, ix].astype(xp.complex128)


def _build_convolution_matrices_for_layer(
    layer: Layer,
    lattice: Lattice,
    settings: RCWASettings,
    mx,
    my,
) -> Tuple:
    """
    Step 2 + Step 3:
    - sample eps_r(x,y) on high-res grid
    - FFT to get coefficients
    - build convolution matrix for eps_r and mu_r
    """
    xp = get_array_module()

    x = xp.linspace(0.0, lattice.Lx, settings.grid_Nx, endpoint=False)
    y = xp.linspace(0.0, lattice.Ly, settings.grid_Ny, endpoint=False)
    X, Y = xp.meshgrid(x, y, indexing="xy")

    eps_xy = layer.pattern.eps_r(X, Y)
    eps_inv_xy = 1.0 / eps_xy
    eps_inv_coeff = _fft_coeffs_2d(eps_inv_xy)
    E_inv_conv = _convmat_from_coeffs(eps_inv_coeff, mx, my)

    eps_xy = layer.pattern.eps_r(X, Y)
    eps_coeff = _fft_coeffs_2d(eps_xy)
    E_conv = _convmat_from_coeffs(eps_coeff, mx, my)


    # mu is usually homogeneous; we still support patterned mu by allowing future extension.
    mu_xy = xp.full(eps_xy.shape, layer.mu_r, dtype=xp.complex128)
    mu_coeff = _fft_coeffs_2d(mu_xy)
    U_conv = _convmat_from_coeffs(mu_coeff, mx, my)

    return E_conv, U_conv, E_inv_conv
