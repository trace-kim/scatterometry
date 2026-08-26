"""
Diffraction efficiency calculations for RCWA (Steps 13-14).
"""
from __future__ import annotations

from typing import Dict, Tuple

from .backend import get_array_module, to_numpy
from .models import ExternalRegion


def _diffraction_efficiencies(
    fields: Dict,
    Kz_ref,
    Kz_trn,
    kinc,
    region_ref: ExternalRegion,
    region_trn: ExternalRegion,
    mx,
    my,
) -> Dict:
    """
    Step 13 (per slide):
      |r|^2 = |rx|^2 + |ry|^2 + |rz|^2
      R = Re[ -Kz_ref / mu_ref ] / Re[ kinc_z / mu_inc ] * |r|^2

      |t|^2 = |tx|^2 + |ty|^2 + |tz|^2
      T = Re[  Kz_trn / mu_trn ] / Re[ kinc_z / mu_inc ] * |t|^2
    """
    xp = get_array_module()
    rx, ry, rz = fields["rx"], fields["ry"], fields["rz"]
    tx, ty, tz = fields["tx"], fields["ty"], fields["tz"]

    r2 = xp.abs(rx)**2 + xp.abs(ry)**2 + xp.abs(rz)**2
    t2 = xp.abs(tx)**2 + xp.abs(ty)**2 + xp.abs(tz)**2

    mu_inc = region_ref.mu_r
    mu_ref = region_ref.mu_r
    mu_trn = region_trn.mu_r

    denom = xp.real(kinc[2] / mu_inc)

    R = xp.real((-Kz_ref / mu_ref)) / denom * r2
    T = xp.real(( Kz_trn / mu_trn)) / denom * t2

    # Convert mx, my to numpy for dict keys (need to be hashable Python ints)
    mx_np = to_numpy(mx)
    my_np = to_numpy(my)
    R_np = to_numpy(R)
    T_np = to_numpy(T)

    # package per-order results keyed by (m,n)
    per_order_R: Dict[Tuple[int,int], float] = {}
    per_order_T: Dict[Tuple[int,int], float] = {}
    for i in range(mx_np.size):
        per_order_R[(int(mx_np[i]), int(my_np[i]))] = float(R_np[i].real)
        per_order_T[(int(mx_np[i]), int(my_np[i]))] = float(T_np[i].real)

    REF = float(xp.real(xp.sum(R)))
    TRN = float(xp.real(xp.sum(T)))

    return dict(R=R, T=T, per_order_R=per_order_R, per_order_T=per_order_T, REF=REF, TRN=TRN)


def _power_conservation(REF: float, TRN: float) -> Dict[str, float]:
    """
    Step 14: Check R_total + T_total (and optionally A_total = 1 - R - T).
    """
    total = REF + TRN
    A = 1.0 - total
    return dict(R_total=REF, T_total=TRN, RT_total=total, A_total=A)
