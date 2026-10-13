"""
Eigenmode computations for RCWA (Steps 5, 7).
"""
from __future__ import annotations

from typing import Tuple

from .backend import get_array_module
from .linalg import _solve, _diag, _outgoing_sqrt
from .smatrix import SMatrix


def _gap_eigenmodes(Kx, Ky) -> Tuple:
    """
    Implements lecture Step 5 (gap medium assumed homogeneous, normalized):
      Kz uses the outgoing/decaying square-root branch.
      Q  = [[Kx Ky, I - Kx^2],
            [Ky^2 - I, -Ky Kx]]
      W0 = [[I,0],[0,I]]
      lambda  = [[j Kz, 0],
            [0,  j Kz]]
      V0 = Q lambda^{-1}
    Here Kx,Ky,Kz are diagonal => treat as vectors.
    """
    xp = get_array_module()
    Nh = Kx.size
    I = xp.eye(Nh, dtype=xp.complex128)
    Z = xp.zeros((Nh, Nh), dtype=xp.complex128)

    Kz = _outgoing_sqrt(1.0 - Kx**2 - Ky**2)  # gap assumed eps=mu=1

    KxD = _diag(Kx)
    KyD = _diag(Ky)
    KzD = _diag(Kz)

    Q11 = KxD @ KyD
    Q12 = I - KxD @ KxD
    Q21 = KyD @ KyD - I
    Q22 = -KyD @ KxD

    Q = xp.block([[Q11, Q12],
                  [Q21, Q22]])

    W0 = xp.block([[I, Z],
                   [Z, I]])

    lam = xp.block([[1j*KzD, Z],
                    [Z, 1j*KzD]])

    V0 = Q @ _solve(lam, xp.eye(2*Nh, dtype=xp.complex128))
    return W0, V0, Kz


def _layer_eigenmodes(
    E_conv,
    U_conv,
    Kx,
    Ky,
) -> Tuple:
    """
    Implements Step 7(a,b):
      Build P_i, Q_i:
        P = [[Kx E^{-1} Ky,   U - Kx E^{-1} Kx],
             [Ky E^{-1} Ky - U,   -Ky E^{-1} Kx]]

        Q = [[Kx U^{-1} Ky,   E - Kx U^{-1} Kx],
             [Ky U^{-1} Ky - E,   -Ky U^{-1} Kx]]

      Omega^2 = P Q
      eig(Omega^2) -> W, lam2
      lam = sqrt(lam2) (diagonal)
      V = Q W lam^{-1}

    Returns (W, V, lam), where lam is the 1D vector of eigenvalues (diagonal of LAM).
    RCWASolver inlines the same computation; NearFieldSolver calls this function.
    """
    xp = get_array_module()
    Nh = Kx.size
    I = xp.eye(Nh, dtype=xp.complex128)

    KxD = _diag(Kx)
    KyD = _diag(Ky)

    Einv = _solve(E_conv, I)
    Uinv = _solve(U_conv, I)

    P11 = KxD @ Einv @ KyD
    P12 = U_conv - KxD @ Einv @ KxD
    P21 = KyD @ Einv @ KyD - U_conv
    P22 = -KyD @ Einv @ KxD
    P = xp.block([[P11, P12],
                  [P21, P22]])

    Q11 = KxD @ Uinv @ KyD
    Q12 = E_conv - KxD @ Uinv @ KxD
    Q21 = KyD @ Uinv @ KyD - E_conv
    Q22 = -KyD @ Uinv @ KxD
    Q = xp.block([[Q11, Q12],
                  [Q21, Q22]])

    Omega2 = P @ Q

    lam2, W = xp.linalg.eig(Omega2)

    # MATLAB sqrt() returns principal sqrt with Re >= 0
    lam = xp.sqrt(lam2.astype(xp.complex128))
    # enforce positive real part when possible (stability for evanescent)
    flip = xp.real(lam) < 0
    lam[flip] = -lam[flip]

    Lam = _diag(lam)
    VinvLam = _solve(Lam, xp.eye(2*Nh, dtype=xp.complex128))
    V = Q @ W @ VinvLam

    return W, V, lam


def _layer_scattering_matrix(
    W_i,
    V_i,
    W0,
    V0,
    k0: float,
    thickness: float,
) -> SMatrix:
    """
    Implements Step 7(c) exactly as slide:
      A0 = W_i^{-1} W0 + V_i^{-1} V0
      B0 = W_i^{-1} W0 - V_i^{-1} V0
      Xi = exp(-LAM * k0 * Li)  (LAM is diagonal eigenvalue matrix)
    and
      S11 = (A0 - Xi B0 A0^{-1} Xi B0)^{-1} (Xi B0 A0^{-1} Xi A0 - B0)
      S12 = (A0 - Xi B0 A0^{-1} Xi B0)^{-1} Xi (A0 - B0 A0^{-1} B0)
      S21 = S12
      S22 = S11
    """

    # We need LAM from eigenvalues embedded in W_i/V_i? We do not store it separately.
    # Practical approach: recover LAM by diagonalizing via relation V = Q W LAM^{-1} is not available here.
    # Therefore, we modify the interface:
    # - Caller should pass lam (eigenvalues) explicitly, or store it in V_i/W_i wrapper.
    #
    # To keep this file simple and debuggable, we reconstruct lam by assuming
    # W_i diagonalizes Omega2 => lam are eigenvalues used in constructing V_i.
    # We can recover them via generalized eigenvalue relation:
    #   V_i = Q W Lam^{-1}  => Lam^{-1} ~ (W^{-1} Q^{-1} V)
    #
    # Instead of fragile reconstruction, we require the caller to pass lam explicitly.
    raise RuntimeError("Internal: call _layer_scattering_matrix_with_lam (see below).")


def _layer_scattering_matrix_with_lam(
    W_i,
    V_i,
    lam,         # 1D vector of eigenvalues (diagonal entries of LAM)
    W0,
    V0,
    k0: float,
    thickness: float,
) -> SMatrix:
    xp = get_array_module()
    Nh2 = W_i.shape[0]
    I2 = xp.eye(Nh2, dtype=xp.complex128)

    A0 = _solve(W_i, W0) + _solve(V_i, V0)
    B0 = _solve(W_i, W0) - _solve(V_i, V0)

    Xi = xp.diag(xp.exp(-lam * k0 * thickness))

    # Common subexpressions using solves (avoid inv)
    A0_inv = _solve(A0, I2)

    M = A0 - Xi @ B0 @ A0_inv @ Xi @ B0
    M_inv = _solve(M, I2)

    S11 = M_inv @ (Xi @ B0 @ A0_inv @ Xi @ A0 - B0)
    S12 = M_inv @ (Xi @ (A0 - B0 @ A0_inv @ B0))
    S21 = S12.copy()
    S22 = S11.copy()

    return SMatrix(S11=S11, S12=S12, S21=S21, S22=S22)


def _external_region_modes(
    eps_r: complex,
    mu_r: complex,
    Kx,
    Ky,
    Kz_ext,
    sign_lambda: int,
) -> Tuple:
    """
    Build Q, W, lambda, V for external region (Step 8/9).
    sign_lambda:
      reflection side uses lambda = -j Kz_ref
      transmission side uses lambda = +j Kz_trn
    """
    xp = get_array_module()
    Nh = Kx.size
    I = xp.eye(Nh, dtype=xp.complex128)
    Z = xp.zeros((Nh, Nh), dtype=xp.complex128)

    KxD = _diag(Kx)
    KyD = _diag(Ky)
    KzD = _diag(Kz_ext)

    Q11 = KxD @ KyD
    Q12 = (mu_r*eps_r)*I - KxD @ KxD
    Q21 = KyD @ KyD - (mu_r*eps_r)*I
    Q22 = -KyD @ KxD

    Q = (1.0/mu_r) * xp.block([[Q11, Q12],
                               [Q21, Q22]])

    W = xp.block([[I, Z],
                  [Z, I]])

    lam = xp.block([[sign_lambda*1j*KzD, Z],
                    [Z, sign_lambda*1j*KzD]])

    V = Q @ _solve(lam, xp.eye(2*Nh, dtype=xp.complex128))
    return W, V
