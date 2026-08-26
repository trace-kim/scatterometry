"""
Convolution matrix construction for RCWA (Steps 2-3).
"""
from __future__ import annotations

from typing import Tuple

from .backend import get_array_module
from .models import Layer, Lattice, RCWASettings


def _harmonic_indices(Nx: int, Ny: int) -> Tuple:
    """Return arrays mx, my listing harmonic orders in a consistent flattened order."""
    xp = get_array_module()
    mx = xp.arange(-Nx, Nx+1)
    my = xp.arange(-Ny, Ny+1)
    MX, MY = xp.meshgrid(mx, my, indexing="xy")  # shape (2Ny+1, 2Nx+1)
    return MX.ravel(), MY.ravel()


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
