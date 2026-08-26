"""
Source parameters and field computation for RCWA (Steps 11-12).
"""
from __future__ import annotations

from typing import Dict, Tuple

from .backend import get_array_module
from .linalg import _solve
from .models import RCWAProblem
from .smatrix import SMatrix


def _te_tm_basis(kinc) -> Tuple:
    """
    Step 11: TE/TM basis from k_inc direction.
    n-hat is z-hat in lecture.
      a_TE = (n x k) / |n x k|
      a_TM = (k x a_TE) / |k x a_TE|
    """
    xp = get_array_module()
    n = xp.array([0.0, 0.0, 1.0], dtype=xp.complex128)
    k = kinc / xp.linalg.norm(kinc)

    v = xp.cross(n, k)
    if xp.linalg.norm(v) < 1e-12:
        # normal incidence: TE can be any xy direction; choose y-hat
        a_te = xp.array([0.0, 1.0, 0.0], dtype=xp.complex128)
    else:
        a_te = v / xp.linalg.norm(v)

    u = xp.cross(k, a_te)
    a_tm = u / xp.linalg.norm(u)

    return a_te, a_tm


def _source_vector(problem: RCWAProblem, mx, my, kdata: Dict = {}) -> object:
    """
    Step 11:
      delta vector delta_{0,pq} has 1 at (m=0,n=0)
      polarization vector P = pTE a_TE + pTM a_TM (normalized)
      source field e_T^src = [p_x delta; p_y delta]
    """
    from .wavevector import _wavevector_expansion

    xp = get_array_module()
    inc = problem.inc
    if not kdata:
        kdata = _wavevector_expansion(problem, mx, my)
    kinc = kdata["kinc"]

    a_te, a_tm = _te_tm_basis(kinc)

    p = inc.pTE * a_te + inc.pTM * a_tm
    p = p / xp.linalg.norm(p)

    # delta at (m=0,n=0)
    idx0 = xp.where((mx == 0) & (my == 0))[0]
    if idx0.size != 1:
        raise RuntimeError("Could not locate unique zero-order harmonic index.")
    idx0 = int(idx0[0])

    Nh = mx.size
    delta = xp.zeros((Nh,), dtype=xp.complex128)
    delta[idx0] = 1.0 + 0j

    # only transverse (x,y) components are used in the lecture for e_T
    px, py = p[0], p[1]
    e_src = xp.concatenate([px * delta, py * delta])  # length 2Nh
    return e_src


def _compute_fields(
    Sg: SMatrix,
    Wref,
    Wtrn,
    Kx,
    Ky,
    Kz_ref,
    Kz_trn,
    e_src,
) -> Dict:
    """
    Step 12:
      c_src = W_ref^{-1} e_src
      c_ref = S11^global c_src
      c_trn = S21^global c_src
      [r_x;r_y] = W_ref c_ref
      [t_x;t_y] = W_trn c_trn
      r_z = -Kz_ref^{-1} (Kx r_x + Ky r_y)
      t_z = -Kz_trn^{-1} (Kx t_x + Ky t_y)
    """
    xp = get_array_module()
    Nh = Kx.size

    c_src = _solve(Wref, e_src.reshape(-1, 1))
    c_ref = Sg.S11 @ c_src
    c_trn = Sg.S21 @ c_src

    r_xy = (Wref @ c_ref).ravel()
    t_xy = (Wtrn @ c_trn).ravel()

    rx = r_xy[:Nh]
    ry = r_xy[Nh:]
    tx = t_xy[:Nh]
    ty = t_xy[Nh:]

    # longitudinal using diagonal K matrices (as vectors)
    rz = -(Kx*rx + Ky*ry) / Kz_ref
    tz = -(Kx*tx + Ky*ty) / Kz_trn

    return dict(rx=rx, ry=ry, rz=rz, tx=tx, ty=ty, tz=tz, c_src=c_src.ravel(), c_ref=c_ref.ravel(), c_trn=c_trn.ravel())
