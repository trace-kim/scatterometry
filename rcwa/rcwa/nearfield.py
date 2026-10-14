"""
Layer-resolved RCWA solve with internal-field reconstruction.

NearFieldSolver reuses RCWASolver's building blocks (Steps 2-14) and returns the
same result dict. It also keeps every layer's eigenmodes and mode amplitudes, so
fields can be evaluated anywhere in the stack.

Differences from RCWASolver.solve():
- Layers that compare equal (pattern, mu_r, thickness) share one eigen-decomposition
  and one layer S-matrix, which makes periodic multilayers cheap. Patterns that are
  not value-hashable are cached by identity.
- Homogeneous layers (pattern.uniform_eps() is not None), the gap and the external
  regions get analytic modes stored as DiagBlocks (blockdiag.py). Their S-matrices and
  star products cost O(Nh), so only patterned layers pay for dense algebra.
- The cascade runs bottom-up and keeps the reflection matrix seen looking down from
  every interface. A top-down pass then gives the gap-medium amplitudes there.

Inside a layer (local depth z' in [0, L]) the transverse fields are
    s(z') = W ( X(z') c+ + X(L - z') d-)
    u(z') = V (-X(z') c+ + X(L - z') d-),     X(zeta) = diag(exp(-lam k0 zeta)),
where u = -j eta0 H is the normalized magnetic field. The backward amplitude d- is
referenced at the bottom of the layer, so every exponential stays bounded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np

from .backend import get_array_module, to_numpy
from .blockdiag import DiagBlocks, eye_minus, homogeneous_modes
from .convolution import _build_convolution_matrices_for_layer, _harmonic_indices
from .efficiencies import _diffraction_efficiencies, _power_conservation
from .eigenmodes import _layer_eigenmodes, _layer_scattering_matrix_with_lam
from .fields import _compute_fields, _source_vector, _te_tm_basis
from .linalg import _outgoing_sqrt, _solve
from .models import Layer, RCWAProblem
from .smatrix import (
    SMatrix,
    _connection_smatrix_reflection,
    _connection_smatrix_transmission,
    _redheffer_star,
)
from .wavevector import _wavevector_expansion


@dataclass
class LayerModes:
    """Eigen-solution of one distinct layer; identical layers share an instance.

    For a homogeneous layer W, V, A, B are DiagBlocks and E_conv, Einv, Uinv are the
    diagonals (length Nh) of the corresponding Nh x Nh matrices.
    """
    E_conv: object
    Einv: object
    Uinv: object
    W: object
    V: object
    lam: object
    A: object  # W^-1 W0 + V^-1 V0 (gap-to-layer mode coupling, Step 7c)
    B: object  # W^-1 W0 - V^-1 V0


@dataclass
class LayerField:
    """A layer of the solved stack with its mode amplitudes."""
    modes: LayerModes
    z_top: float
    thickness: float
    c_plus: object = None   # forward amplitudes at the top of the layer
    d_minus: object = None  # backward amplitudes at the bottom of the layer


def _uniform_eps(layer: Layer):
    uniform = getattr(layer.pattern, "uniform_eps", None)
    return None if uniform is None else uniform()


def _modes_key(layer: Layer):
    eps = _uniform_eps(layer)
    if eps is not None:
        return ("uniform", complex(eps), complex(layer.mu_r))
    try:
        hash(layer.pattern)
        return (layer.pattern, complex(layer.mu_r))
    except TypeError:
        return (id(layer.pattern), complex(layer.mu_r))


def _plane_wave_u(sx, sy, sz, Kx, Ky, Kz, mu):
    """Normalized H of plane waves from E: u = -j (K x s) / mu."""
    return (
        -1j * (Ky * sz - Kz * sy) / mu,
        -1j * (Kz * sx - Kx * sz) / mu,
        -1j * (Kx * sy - Ky * sx) / mu,
    )


def _times_transpose(X, M):
    """X @ M.T for a dense matrix, DiagBlocks, or diagonal vector M."""
    if isinstance(M, DiagBlocks):
        return (M @ X.T).T
    if M.ndim == 1:
        return X * M[None, :]
    return X @ M.T


class NearFieldSolver:
    """RCWA solver that keeps per-layer modes for field reconstruction."""

    def solve(self, problem: RCWAProblem, keep_fields: bool = True,
              progress: Optional[Callable[[float, str], None]] = None) -> "NearFieldSolution":
        """Solve `problem`.

        `progress(fraction, message)` is called as the solve advances (eigen-solves
        dominate the run time). It may raise to abort the solve, which is how callers
        implement cancellation.
        """
        report = progress or (lambda fraction, message: None)
        xp = get_array_module()
        st = problem.settings
        mx, my = _harmonic_indices(st.Nx, st.Ny, st.shift_x, st.shift_y)
        Nh = mx.size

        kdat = _wavevector_expansion(problem, mx, my)
        k0 = kdat["k0"]
        Kx, Ky = kdat["Kx"], kdat["Ky"]
        Kz_ref, Kz_trn = kdat["Kz_ref"], kdat["Kz_trn"]
        # Gap medium (vacuum): structured for homogeneous layers, dense for patterned ones.
        W0s, V0s, _ = homogeneous_modes(Kx, Ky, 1.0, 1.0, _outgoing_sqrt(1.0 - Kx**2 - Ky**2))
        W0, V0 = W0s.to_dense(), V0s.to_dense()

        mode_cache: Dict = {}
        smatrix_cache: Dict = {}
        layers: List[LayerField] = []
        smatrices: List[SMatrix] = []
        keys = [_modes_key(layer) for layer in problem.layers]
        n_unique = max(len(set(keys)), 1)
        report(0.0, "Layer modes")
        z = 0.0
        for layer, key in zip(problem.layers, keys):
            modes = mode_cache.get(key)
            uniform = key[0] == "uniform"
            if modes is None and uniform:
                eps, mu = key[1], key[2]
                W, V, lam = homogeneous_modes(Kx, Ky, eps, mu, _outgoing_sqrt(mu * eps - Kx**2 - Ky**2))
                W_W0 = _solve(W, W0s)
                V_V0 = _solve(V, V0s)
                ones = xp.ones(Nh, dtype=xp.complex128)
                modes = LayerModes(
                    E_conv=eps * ones, Einv=ones / eps, Uinv=ones / mu,
                    W=W, V=V, lam=lam, A=W_W0 + V_V0, B=W_W0 - V_V0,
                )
                mode_cache[key] = modes
            elif modes is None:
                I1 = xp.eye(Nh, dtype=xp.complex128)
                E_conv, U_conv, _ = _build_convolution_matrices_for_layer(layer, problem.lattice, st, mx, my)
                W, V, lam = _layer_eigenmodes(E_conv, U_conv, Kx, Ky)
                W_W0 = _solve(W, W0)
                V_V0 = _solve(V, V0)
                modes = LayerModes(
                    E_conv=E_conv, Einv=_solve(E_conv, I1), Uinv=_solve(U_conv, I1),
                    W=W, V=V, lam=lam, A=W_W0 + V_V0, B=W_W0 - V_V0,
                )
                mode_cache[key] = modes
                report(0.85 * len(mode_cache) / n_unique, f"Layer modes {len(mode_cache)}/{n_unique}")
            skey = (key, float(layer.thickness))
            S = smatrix_cache.get(skey)
            if S is None:
                S = _layer_scattering_matrix_with_lam(
                    W_i=modes.W, V_i=modes.V, lam=modes.lam,
                    W0=W0s if uniform else W0, V0=V0s if uniform else V0,
                    k0=k0, thickness=layer.thickness,
                )
                smatrix_cache[skey] = S
            layers.append(LayerField(modes=modes, z_top=z, thickness=float(layer.thickness)))
            smatrices.append(S)
            z += float(layer.thickness)

        # External regions: lam = -j Kz_ref above the stack and +j Kz_trn below it.
        ref, trn = problem.region_ref, problem.region_trn
        Wref, Vref, _ = homogeneous_modes(Kx, Ky, complex(ref.eps_r), complex(ref.mu_r), -Kz_ref)
        Sref = _connection_smatrix_reflection(W0s, V0s, Wref, Vref)
        Wtrn, Vtrn, _ = homogeneous_modes(Kx, Ky, complex(trn.eps_r), complex(trn.mu_r), Kz_trn)
        Strn = _connection_smatrix_transmission(W0s, V0s, Wtrn, Vtrn)

        # Bottom-up cascade. R_down[k] is the reflection seen looking down from
        # interface k (the top of layer k; interface N is the bottom of the stack).
        n = len(smatrices)
        R_down = [None] * (n + 1)
        S_below = Strn
        R_down[n] = S_below.S11
        for k in range(n - 1, -1, -1):
            S_below = _redheffer_star(smatrices[k], S_below)
            if keep_fields:
                R_down[k] = S_below.S11
        Sg = _redheffer_star(Sref, S_below)
        report(0.9, "Diffraction efficiencies")

        e_src = _source_vector(problem, mx, my, kdata=kdat)
        fields = _compute_fields(
            Sg=Sg, Wref=Wref, Wtrn=Wtrn, Kx=Kx, Ky=Ky,
            Kz_ref=Kz_ref, Kz_trn=Kz_trn, e_src=e_src,
        )
        eff = _diffraction_efficiencies(
            fields=fields, Kz_ref=Kz_ref, Kz_trn=Kz_trn, kinc=kdat["kinc"],
            region_ref=problem.region_ref, region_trn=problem.region_trn, mx=mx, my=my,
        )
        result = dict(
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
            power=_power_conservation(eff["REF"], eff["TRN"]),
        )

        if keep_fields:
            report(0.95, "Internal fields")
            # Top-down pass: gap amplitudes at each interface (a: down-going, b: up-going).
            a = _solve(eye_minus(Sref.S22 @ R_down[0]), Sref.S21 @ fields["c_src"])
            b = R_down[0] @ a
            for k, layer in enumerate(layers):
                S = smatrices[k]
                a_next = _solve(eye_minus(S.S22 @ R_down[k + 1]), S.S21 @ a)
                b_next = R_down[k + 1] @ a_next
                m = layer.modes
                layer.c_plus = 0.5 * (m.A @ a + m.B @ b)
                layer.d_minus = 0.5 * (m.B @ a_next + m.A @ b_next)
                a, b = a_next, b_next

        a_te, a_tm = _te_tm_basis(kdat["kinc"])
        p_inc = problem.inc.pTE * a_te + problem.inc.pTM * a_tm
        p_inc = p_inc / xp.linalg.norm(p_inc)

        return NearFieldSolution(
            result=result, problem=problem, k0=k0,
            Kx=Kx, Ky=Ky, Kz_ref=Kz_ref, Kz_trn=Kz_trn,
            kinc=kdat["kinc"], p_inc=p_inc, fields=fields,
            layers=layers, has_fields=keep_fields,
        )


@dataclass
class NearFieldSolution:
    """Solved stack: RCWASolver-style `result` plus field evaluation helpers.

    Depth z is in meters with 0 at the top surface of the first layer and +z
    pointing into the stack (toward the transmission region).
    """
    result: Dict[str, object]
    problem: RCWAProblem
    k0: float
    Kx: object
    Ky: object
    Kz_ref: object
    Kz_trn: object
    kinc: object
    p_inc: object
    fields: Dict[str, object]
    layers: List[LayerField]
    has_fields: bool

    @property
    def total_thickness(self) -> float:
        return self.layers[-1].z_top + self.layers[-1].thickness if self.layers else 0.0

    @property
    def z_interfaces(self) -> np.ndarray:
        return np.array([layer.z_top for layer in self.layers] + [self.total_thickness])

    @property
    def zero_order_index(self) -> int:
        h = self.result["harmonics"]
        return int(np.flatnonzero((h["mx"] == 0) & (h["my"] == 0))[0])

    def amplitudes(self, z) -> Dict[str, np.ndarray]:
        """Plane-wave amplitudes of E (sx, sy, sz) and u = -j*eta0*H (ux, uy, uz).

        Each array has shape (len(z), Nh) in harmonic order. Above the stack the
        incident wave is included in the zero-order harmonic.
        """
        if not self.has_fields:
            raise RuntimeError("solve with keep_fields=True to evaluate fields")
        xp = get_array_module()
        z = np.atleast_1d(np.asarray(z, dtype=float))
        Nh = int(self.Kx.size)
        out = {c: np.zeros((z.size, Nh), dtype=complex) for c in ("sx", "sy", "sz", "ux", "uy", "uz")}
        z_end = self.total_thickness
        above = z < 0.0
        below = z >= z_end if not self.layers else z > z_end
        if above.any():
            self._fill(out, above, self._reflection_region(xp.asarray(z[above])))
        if below.any():
            self._fill(out, below, self._transmission_region(xp.asarray(z[below] - z_end)))
        inside = ~(above | below)
        if inside.any():
            index = np.clip(np.searchsorted(self.z_interfaces, z, side="right") - 1, 0, len(self.layers) - 1)
            for k in np.unique(index[inside]):
                sel = inside & (index == k)
                layer = self.layers[k]
                self._fill(out, sel, self._layer_amplitudes(layer, xp.asarray(z[sel] - layer.z_top)))
        return out

    def efield_xz(self, x, z, y: float = 0.0) -> Dict[str, np.ndarray]:
        """E components on an x-z grid at fixed y; arrays of shape (len(z), len(x))."""
        amp = self.amplitudes(z)
        Kx, Ky = to_numpy(self.Kx), to_numpy(self.Ky)
        phase_x = np.exp(-1j * self.k0 * np.outer(Kx, np.asarray(x, dtype=float)))
        phase_y = np.exp(-1j * self.k0 * Ky * y)
        return {c: (amp["s" + c] * phase_y) @ phase_x for c in "xyz"}

    def efield_yz(self, y, z, x: float = 0.0) -> Dict[str, np.ndarray]:
        """E components on a y-z grid at fixed x; arrays of shape (len(z), len(y))."""
        amp = self.amplitudes(z)
        Kx, Ky = to_numpy(self.Kx), to_numpy(self.Ky)
        phase_y = np.exp(-1j * self.k0 * np.outer(Ky, np.asarray(y, dtype=float)))
        phase_x = np.exp(-1j * self.k0 * Kx * x)
        return {c: (amp["s" + c] * phase_x) @ phase_y for c in "xyz"}

    def efield_xy(self, x, y, z: float) -> Dict[str, np.ndarray]:
        """E components on an x-y grid at depth z; arrays of shape (len(y), len(x))."""
        amp = self.amplitudes([z])
        Kx, Ky = to_numpy(self.Kx), to_numpy(self.Ky)
        phase_x = np.exp(-1j * self.k0 * np.outer(Kx, np.asarray(x, dtype=float)))
        phase_y = np.exp(-1j * self.k0 * np.outer(Ky, np.asarray(y, dtype=float)))
        return {c: (phase_y.T * amp["s" + c][0]) @ phase_x for c in "xyz"}

    def power_flux(self, z) -> np.ndarray:
        """Downward time-averaged power through a unit cell, normalized to the incident flux."""
        amp = self.amplitudes(z)
        flux = np.sum(np.imag(amp["sx"] * np.conj(amp["uy"]) - amp["sy"] * np.conj(amp["ux"])), axis=1)
        kz_inc = complex(to_numpy(self.kinc)[2])
        return flux / np.real(kz_inc / complex(self.problem.region_ref.mu_r))

    def layer_absorption(self) -> np.ndarray:
        """Fraction of the incident power absorbed in each layer, top to bottom."""
        return -np.diff(self.power_flux(self.z_interfaces)) if self.layers else np.zeros(0)

    def order_table(self) -> Dict[str, np.ndarray]:
        """Per-order directions and complex amplitudes in each order's own TE/TM basis.

        Uses the incident-wave convention: a_TE = z x k / |z x k| (y-hat at normal
        incidence) and a_TM = k x a_TE. Evanescent orders get NaN amplitudes and angles.
        """
        Kx, Ky = to_numpy(self.Kx), to_numpy(self.Ky)
        f = {k: to_numpy(v) for k, v in self.fields.items()}
        out: Dict[str, np.ndarray] = {}
        for side, Kz, comps in (
            ("r", to_numpy(self.Kz_ref), (f["rx"], f["ry"], f["rz"])),
            ("t", to_numpy(self.Kz_trn), (f["tx"], f["ty"], f["tz"])),
        ):
            k = np.stack([Kx.real, Ky.real, Kz.real], axis=1)
            k_norm = np.linalg.norm(k, axis=1, keepdims=True)
            propagating = (np.abs(Kz.imag) < 1e-9) & (np.abs(Kz.real) > 1e-12)
            k = k / np.maximum(k_norm, 1e-300)
            a_te = np.cross([0.0, 0.0, 1.0], k)
            te_norm = np.linalg.norm(a_te, axis=1, keepdims=True)
            a_te = np.where(te_norm > 1e-12, a_te / np.maximum(te_norm, 1e-300), [0.0, 1.0, 0.0])
            a_tm = np.cross(k, a_te)
            a_tm /= np.maximum(np.linalg.norm(a_tm, axis=1, keepdims=True), 1e-300)
            amp = np.stack(comps, axis=1)
            nan = np.full(Kx.size, np.nan)
            out[f"{side}_te"] = np.where(propagating, np.sum(a_te * amp, axis=1), nan)
            out[f"{side}_tm"] = np.where(propagating, np.sum(a_tm * amp, axis=1), nan)
            out[f"{side}_theta_deg"] = np.where(propagating, np.degrees(np.arccos(np.clip(np.abs(k[:, 2]), 0.0, 1.0))), nan)
            out[f"{side}_phi_deg"] = np.where(propagating, np.degrees(np.arctan2(k[:, 1], k[:, 0])), nan)
            out[f"{side}_propagating"] = propagating
        return out

    # ---- internals -------------------------------------------------------

    @staticmethod
    def _fill(out, mask, values):
        for c, v in values.items():
            out[c][mask] = to_numpy(v)

    def _reflection_region(self, zz):
        xp = get_array_module()
        mu = complex(self.problem.region_ref.mu_r)
        phase = xp.exp(-1j * self.k0 * zz[:, None] * self.Kz_ref[None, :])
        f = self.fields
        sx, sy, sz = f["rx"][None, :] * phase, f["ry"][None, :] * phase, f["rz"][None, :] * phase
        ux, uy, uz = _plane_wave_u(sx, sy, sz, self.Kx, self.Ky, self.Kz_ref, mu)
        i0 = self.zero_order_index
        inc_phase = xp.exp(-1j * self.k0 * zz * self.kinc[2])
        u_inc = -1j * xp.cross(self.kinc, self.p_inc) / mu
        for s, value in zip((sx, sy, sz), self.p_inc):
            s[:, i0] += value * inc_phase
        for u, value in zip((ux, uy, uz), u_inc):
            u[:, i0] += value * inc_phase
        return dict(sx=sx, sy=sy, sz=sz, ux=ux, uy=uy, uz=uz)

    def _transmission_region(self, dz):
        xp = get_array_module()
        mu = complex(self.problem.region_trn.mu_r)
        phase = xp.exp(-1j * self.k0 * dz[:, None] * self.Kz_trn[None, :])
        f = self.fields
        sx, sy, sz = f["tx"][None, :] * phase, f["ty"][None, :] * phase, f["tz"][None, :] * phase
        ux, uy, uz = _plane_wave_u(sx, sy, sz, self.Kx, self.Ky, self.Kz_trn, mu)
        return dict(sx=sx, sy=sy, sz=sz, ux=ux, uy=uy, uz=uz)

    def _layer_amplitudes(self, layer: LayerField, zl):
        xp = get_array_module()
        m = layer.modes
        Nh = int(self.Kx.size)
        lam = m.lam[None, :]
        fwd = xp.exp(-lam * self.k0 * zl[:, None]) * layer.c_plus[None, :]
        bwd = xp.exp(-lam * self.k0 * (layer.thickness - zl)[:, None]) * layer.d_minus[None, :]
        s = _times_transpose(fwd + bwd, m.W)
        u = _times_transpose(bwd - fwd, m.V)
        sx, sy = s[:, :Nh], s[:, Nh:]
        ux, uy = u[:, :Nh], u[:, Nh:]
        sz = _times_transpose(-1j * (self.Kx[None, :] * uy - self.Ky[None, :] * ux), m.Einv)
        uz = _times_transpose(-1j * (self.Kx[None, :] * sy - self.Ky[None, :] * sx), m.Uinv)
        return dict(sx=sx, sy=sy, sz=sz, ux=ux, uy=uy, uz=uz)
