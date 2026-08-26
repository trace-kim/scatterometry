"""
Main RCWA solver (Steps 0-14).
"""
from __future__ import annotations

from typing import Dict

from .backend import get_array_module, to_numpy
from .linalg import _solve, _diag
from .models import RCWAProblem
from .convolution import _harmonic_indices, _build_convolution_matrices_for_layer
from .wavevector import _wavevector_expansion
from .eigenmodes import (
    _gap_eigenmodes,
    _layer_scattering_matrix_with_lam,
    _external_region_modes,
)
from .smatrix import (
    _init_device_smatrix,
    _redheffer_star,
    _connection_smatrix_reflection,
    _connection_smatrix_transmission,
)
from .fields import _source_vector, _compute_fields
from .efficiencies import _diffraction_efficiencies, _power_conservation


class RCWASolver:
    def solve(self, problem: RCWAProblem) -> Dict[str, object]:
        """
        Executes Steps 0-14 as in lecture.

        Returns a dict with:
          - fields (rx,ry,rz, tx,ty,tz)
          - efficiencies per order + totals
          - power conservation
          - optional debug snapshots
        """
        xp = get_array_module()
        st = problem.settings

        # ---- Step 0/1: problem already defined via RCWAProblem ----

        # ---- Build harmonic indexing (used throughout) ----
        mx, my = _harmonic_indices(st.Nx, st.Ny)
        Nh = mx.size

        # ---- Step 4: wave vector expansion ----
        kdat = _wavevector_expansion(problem, mx, my)
        k0 = kdat["k0"]
        kinc = kdat["kinc"]
        Kx, Ky = kdat["Kx"], kdat["Ky"]
        Kz_ref, Kz_trn = kdat["Kz_ref"], kdat["Kz_trn"]

        # ---- Step 5: gap eigenmodes ----
        W0, V0, Kz_gap = _gap_eigenmodes(Kx, Ky)

        # ---- Step 6: initialize device S-matrix ----
        Sdev = _init_device_smatrix(Nh)

        debug_layers = []

        # ---- Step 7: loop through layers ----
        for li, layer in enumerate(problem.layers):
            # Step 2/3: build layer grid + convolution matrices
            E_conv, U_conv, E_inv_conv = _build_convolution_matrices_for_layer(layer, problem.lattice, st, mx, my)

            # Step 7a/b: eigenmodes
            Nh2 = 2*Nh

            KxD = _diag(Kx)
            KyD = _diag(Ky)

            Einv = _solve(E_conv, xp.eye(Nh, dtype=xp.complex128))
            Uinv = _solve(U_conv, xp.eye(Nh, dtype=xp.complex128))


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

            lam = xp.sqrt(lam2.astype(xp.complex128))

            flip = xp.real(lam) < 0
            lam[flip] = -lam[flip]
            Lam = _diag(lam)

            V = Q @ W @ _solve(Lam, xp.eye(Nh2, dtype=xp.complex128))

            # Step 7c: layer S-matrix
            Slayer = _layer_scattering_matrix_with_lam(
                W_i=W, V_i=V, lam=lam,
                W0=W0, V0=V0,
                k0=k0, thickness=layer.thickness
            )

            # Step 7d: update device scattering matrix
            Sdev = _redheffer_star(Sdev, Slayer)

            if st.debug:
                debug_layers.append(dict(
                    layer_index=li,
                    thickness=layer.thickness,
                    cond_E=float(xp.linalg.cond(E_conv)),
                    cond_U=float(xp.linalg.cond(U_conv)),
                ))

        # ---- Step 8: reflection-side connection S-matrix ----
        Wref, Vref = _external_region_modes(
            eps_r=problem.region_ref.eps_r,
            mu_r=problem.region_ref.mu_r,
            Kx=Kx, Ky=Ky,
            Kz_ext=Kz_ref,
            sign_lambda=-1,  # reflection: lambda_ref = -j Kz_ref
        )
        Sref = _connection_smatrix_reflection(W0, V0, Wref, Vref)

        # ---- Step 9: transmission-side connection S-matrix ----
        Wtrn, Vtrn = _external_region_modes(
            eps_r=problem.region_trn.eps_r,
            mu_r=problem.region_trn.mu_r,
            Kx=Kx, Ky=Ky,
            Kz_ext=Kz_trn,
            sign_lambda=+1,  # transmission: lambda_trn = +j Kz_trn
        )
        Strn = _connection_smatrix_transmission(W0, V0, Wtrn, Vtrn)

        # ---- Step 10: global S-matrix ----
        Sg = _redheffer_star(_redheffer_star(Sref, Sdev), Strn)

        # ---- Step 11: source parameters ----
        e_src = _source_vector(problem, mx, my, kdata=kdat)

        # ---- Step 12: reflected / transmitted fields ----
        fields = _compute_fields(
            Sg=Sg,
            Wref=Wref, Wtrn=Wtrn,
            Kx=Kx, Ky=Ky,
            Kz_ref=Kz_ref, Kz_trn=Kz_trn,
            e_src=e_src,
        )

        # ---- Step 13: diffraction efficiencies ----
        eff = _diffraction_efficiencies(
            fields=fields,
            Kz_ref=Kz_ref, Kz_trn=Kz_trn,
            kinc=kinc,
            region_ref=problem.region_ref,
            region_trn=problem.region_trn,
            mx=mx, my=my,
        )

        # ---- Step 14: conservation of power ----
        pwr = _power_conservation(eff["REF"], eff["TRN"])

        # ---- Convert all arrays to NumPy for output compatibility ----
        out = dict(
            harmonics=dict(mx=to_numpy(mx), my=to_numpy(my)),
            fields={k: to_numpy(v) for k, v in fields.items()},
            efficiencies=dict(
                R=to_numpy(eff["R"]),
                T=to_numpy(eff["T"]),
                per_order_R=eff["per_order_R"],
                per_order_T=eff["per_order_T"],
                REF=eff["REF"],
                TRN=eff["TRN"],
            ),
            power=pwr,
        )
        if st.debug:
            out["debug"] = dict(layers=debug_layers)
        return out
