"""
S-matrix data structure and operations (Steps 6, 8, 9, 10).
"""
from __future__ import annotations

from dataclasses import dataclass

from .backend import get_array_module
from .blockdiag import DiagBlocks, dense, identity_like
from .linalg import _solve


@dataclass
class SMatrix:
    S11: object  # Can be numpy or cupy array
    S12: object
    S21: object
    S22: object


def _redheffer_star(SA: SMatrix, SB: SMatrix) -> SMatrix:
    """
    Redheffer star product: S = SA * SB
    SA, SB are 2-port scattering matrices with blocks (11,12,21,22).

    Formulas (standard):
      S11 = SA11 + SA12 (I - SB11 SA22)^-1 SB11 SA21
      S12 = SA12 (I - SB11 SA22)^-1 SB12
      S21 = SB21 (I - SA22 SB11)^-1 SA21
      S22 = SB22 + SB21 (I - SA22 SB11)^-1 SA22 SB12

    Two all-DiagBlocks S-matrices (homogeneous layers) combine in O(Nh); any other
    combination is computed densely.
    """
    blocks = (SA.S11, SA.S12, SA.S21, SA.S22, SB.S11, SB.S12, SB.S21, SB.S22)
    if not all(isinstance(b, DiagBlocks) for b in blocks):
        SA = SMatrix(*(dense(b) for b in blocks[:4]))
        SB = SMatrix(*(dense(b) for b in blocks[4:]))
    I = identity_like(SA.S11)

    D = I - SB.S11 @ SA.S22
    F = I - SA.S22 @ SB.S11

    D_inv_SB11_SA21 = _solve(D, SB.S11 @ SA.S21)
    D_inv_SB12      = _solve(D, SB.S12)

    F_inv_SA21      = _solve(F, SA.S21)
    F_inv_SA22_SB12 = _solve(F, SA.S22 @ SB.S12)

    S11 = SA.S11 + SA.S12 @ D_inv_SB11_SA21
    S12 = SA.S12 @ D_inv_SB12
    S21 = SB.S21 @ F_inv_SA21
    S22 = SB.S22 + SB.S21 @ F_inv_SA22_SB12

    return SMatrix(S11=S11, S12=S12, S21=S21, S22=S22)


def _init_device_smatrix(Nh: int) -> SMatrix:
    """
    Step 6: Initialize device scattering matrix:
      S11=0, S12=I, S21=I, S22=0
    """
    xp = get_array_module()
    Z = xp.zeros((2*Nh, 2*Nh), dtype=xp.complex128)
    I = xp.eye(2*Nh, dtype=xp.complex128)
    return SMatrix(S11=Z.copy(), S12=I.copy(), S21=I.copy(), S22=Z.copy())


def _connection_smatrix_reflection(W0, V0, Wref, Vref) -> SMatrix:
    """
    Step 8:
      A = W0^{-1} Wref + V0^{-1} Vref
      B = W0^{-1} Wref - V0^{-1} Vref
      SR11 = -A^{-1} B
      SR12 =  2 A^{-1}
      SR21 =  0.5 (A - B A^{-1} B)
      SR22 =  B A^{-1}
    """
    I = identity_like(W0, V0, Wref, Vref)

    A = _solve(W0, Wref) + _solve(V0, Vref)
    B = _solve(W0, Wref) - _solve(V0, Vref)

    A_inv = _solve(A, I)

    S11 = -A_inv @ B
    S12 = 2.0 * A_inv
    S21 = 0.5 * (A - B @ A_inv @ B)
    S22 = B @ A_inv
    return SMatrix(S11=S11, S12=S12, S21=S21, S22=S22)


def _connection_smatrix_transmission(W0, V0, Wtrn, Vtrn) -> SMatrix:
    """
    Step 9 (per slide code block):
      A = W0^{-1} Wtrn + V0^{-1} Vtrn
      B = W0^{-1} Wtrn - V0^{-1} Vtrn
      ST11 =  B/A
      ST12 =  0.5*(A - B/A*B)
      ST21 =  2*inv(A)
      ST22 = -A\\B
    """
    I = identity_like(W0, V0, Wtrn, Vtrn)

    A = _solve(W0, Wtrn) + _solve(V0, Vtrn)
    B = _solve(W0, Wtrn) - _solve(V0, Vtrn)

    A_inv = _solve(A, I)

    S11 = B @ A_inv
    S12 = 0.5 * (A - B @ A_inv @ B)
    S21 = 2.0 * A_inv
    S22 = -A_inv @ B
    return SMatrix(S11=S11, S12=S12, S21=S21, S22=S22)
