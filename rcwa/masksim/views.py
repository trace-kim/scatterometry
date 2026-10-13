"""Numerical data behind the UI views: geometry maps, permittivity, fields, orders.

No plotting here. The web server (maskserver) and the Plotly helpers in
masksim.plots both build on these functions. Lengths are meters, like the rest of
masksim; depth z is 0 at the top surface and increases into the stack.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from rcwa.backend import to_numpy
from rcwa.convolution import _build_convolution_matrices_for_layer, _harmonic_indices
from rcwa.models import Layer

from .stack import NM, MaskSpec, Slice, solver_settings, unit_cell

# ---- materials and sampling grids -----------------------------------------------


def material_names(spec: MaskSpec) -> List[str]:
    return [m.name for m in spec.materials]


def is_clear(spec: MaskSpec, name: str) -> bool:
    """Vacuum-like material (n = 1, k = 0); drawn transparent in 3D views."""
    m = spec.material(name)
    return m.n == 1.0 and m.k == 0.0


def incident_index(spec: MaskSpec) -> float:
    """Real refractive index of the incident medium (normalizes pupil coordinates)."""
    return math.sqrt(max(spec.material(spec.superstrate).eps.real, 1e-12))


def section_axes(spec: MaskSpec, axis: str, periods: float, z_min: float, z_max: float,
                 n_lateral: int = 480, n_z: int = 420) -> Tuple[np.ndarray, np.ndarray]:
    """Lateral pixel centres across `periods` unit cells and a depth grid from z_min to z_max."""
    Lx, Ly = unit_cell(spec.pattern)
    span = periods * (Lx if axis == "x" else Ly)
    lateral = (np.arange(n_lateral) + 0.5) * span / n_lateral
    return lateral, np.linspace(z_min, z_max, n_z)


def plane_axes(spec: MaskSpec, periods: float, n: int) -> Tuple[np.ndarray, np.ndarray]:
    """Pixel centres of an n x n top-view grid covering `periods` unit cells per axis."""
    Lx, Ly = unit_cell(spec.pattern)
    return (np.arange(n) + 0.5) * periods * Lx / n, (np.arange(n) + 0.5) * periods * Ly / n


def _line_points(axis: str, coords: np.ndarray, offset: float) -> Tuple[np.ndarray, np.ndarray]:
    other = np.full(coords.shape, offset)
    return (coords, other) if axis == "x" else (other, coords)


def _slice_rows(slices: Sequence[Slice], z: np.ndarray) -> Iterator[Tuple[Slice, np.ndarray]]:
    for s in slices:
        rows = (z >= s.z_top) & (z < s.z_bottom)
        if rows.any():
            yield s, rows


def slice_at(slices: Sequence[Slice], depth: float) -> Optional[Slice]:
    for s in slices:
        if s.z_top <= depth < s.z_bottom:
            return s
    return None


# ---- geometry ----------------------------------------------------------------------


def section_index(spec: MaskSpec, slices: Sequence[Slice], axis: str, offset: float,
                  lateral: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Material index (into spec.materials) on a depth x lateral grid; shape (len(z), len(lateral))."""
    names = material_names(spec)
    index = np.empty((z.size, lateral.size), dtype=int)
    index[z < 0.0] = names.index(spec.superstrate)
    index[z >= slices[-1].z_bottom] = names.index(spec.substrate)
    X, Y = _line_points(axis, lateral, offset)
    for s, rows in _slice_rows(slices, z):
        host = s.pattern.host_fraction(X[None, :], Y[None, :])[0] >= 0.5
        index[rows] = np.where(host, names.index(s.material), names.index(s.fill))[None, :]
    return index


def plane_index(spec: MaskSpec, s: Slice, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Material index of one slice on an x-y grid; shape (len(ys), len(xs))."""
    names = material_names(spec)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    host = s.pattern.host_fraction(X, Y) >= 0.5
    return np.where(host, names.index(s.material), names.index(s.fill))


def edge_mask(index: np.ndarray) -> np.ndarray:
    """Pixels where the material changes from the left or upper neighbour."""
    edges = np.zeros(index.shape, dtype=bool)
    edges[:, 1:] |= index[:, 1:] != index[:, :-1]
    edges[1:, :] |= index[1:, :] != index[:-1, :]
    return edges


def mask_rects(mask: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Cover a boolean (ny, nx) mask with rectangles (x0, x1, y0, y1), merging identical row runs."""
    rects, open_runs = [], {}
    for j, row in enumerate(mask):
        padded = np.concatenate([[False], row, [False]])
        changes = np.flatnonzero(padded[1:] != padded[:-1])
        runs = set(zip(changes[::2].tolist(), changes[1::2].tolist(), strict=True))
        for run in list(open_runs):
            if run not in runs:
                rects.append((run[0], run[1], open_runs.pop(run), j))
        for run in runs:
            open_runs.setdefault(run, j)
    rects += [(run[0], run[1], j0, mask.shape[0]) for run, j0 in open_runs.items()]
    return rects


def stack_boxes(spec: MaskSpec, slices: Sequence[Slice], periods: float, z_max: float,
                n: int = 160) -> List[Tuple[str, float, float, float, float, float, float]]:
    """Boxes (material, x0, x1, y0, y1, z0, z1) tiling the stack down to z_max; clear materials are omitted.

    Homogeneous slices become one slab; patterned slices are extruded pixel runs on an
    n x n grid per `periods` unit cells.
    """
    xs, ys = plane_axes(spec, periods, n)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    Lx, Ly = unit_cell(spec.pattern)
    width, height = periods * Lx, periods * Ly
    boxes = []
    for s in slices:
        if s.z_top >= z_max:
            break
        z0, z1 = s.z_top, min(s.z_bottom, z_max)
        if not s.patterned:
            if not is_clear(spec, s.material):
                boxes.append((s.material, 0.0, width, 0.0, height, z0, z1))
            continue
        host = s.pattern.host_fraction(X, Y) >= 0.5
        for material, mask in ((s.material, host), (s.fill, ~host)):
            if is_clear(spec, material):
                continue
            for i0, i1, j0, j1 in mask_rects(mask):
                boxes.append((material, i0 * width / n, i1 * width / n, j0 * height / n, j1 * height / n, z0, z1))
    return boxes


# ---- permittivity --------------------------------------------------------------------


def exact_eps(s: Slice, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Point-sampled (binary) permittivity of a slice."""
    p = s.pattern
    return p.eps_fill + p.host_fraction(X, Y) * (p.eps_host - p.eps_fill)


def _fourier_terms(spec: MaskSpec, slices: Sequence[Slice], s: Slice):
    """Fourier coefficients of eps that the solver's convolution matrix uses (|m| <= 2Nx, |n| <= 2Ny).

    Returns (coefficients[n, m], m, n, Lx, Ly).
    """
    lattice, settings = solver_settings(spec, list(slices))
    Lx, Ly = lattice.Lx, lattice.Ly
    gx, gy = settings.grid_Nx, settings.grid_Ny
    GX, GY = np.meshgrid(np.linspace(0, Lx, gx, endpoint=False), np.linspace(0, Ly, gy, endpoint=False), indexing="xy")
    coeffs = np.fft.fftshift(np.fft.fft2(to_numpy(s.pattern.eps_r(GX, GY)))) / (gx * gy)
    m = np.arange(-2 * settings.Nx, 2 * settings.Nx + 1)
    n = np.arange(-2 * settings.Ny, 2 * settings.Ny + 1)
    return coeffs[gy // 2 + n[:, None], gx // 2 + m[None, :]], m, n, Lx, Ly


def fourier_eps(spec: MaskSpec, slices: Sequence[Slice], s: Slice, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """eps at the points (X, Y), rebuilt from the truncated Fourier series the solver uses."""
    sub, m, n, Lx, Ly = _fourier_terms(spec, slices, s)
    phase_x = np.exp(2j * np.pi * np.multiply.outer(m, X) / Lx)
    phase_y = np.exp(2j * np.pi * np.multiply.outer(n, Y) / Ly)
    return np.einsum("nm,m...,n...->...", sub, phase_x, phase_y)


def fourier_eps_grid(spec: MaskSpec, slices: Sequence[Slice], s: Slice, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """fourier_eps on the grid xs x ys, shape (len(ys), len(xs)).

    The series separates per axis, so memory scales with harmonics x (len(xs) + len(ys))
    rather than harmonics x pixels.
    """
    sub, m, n, Lx, Ly = _fourier_terms(spec, slices, s)
    phase_x = np.exp(2j * np.pi * np.outer(m, xs) / Lx)
    phase_y = np.exp(2j * np.pi * np.outer(n, ys) / Ly)
    return phase_y.T @ sub @ phase_x


def eps_section(spec: MaskSpec, slices: Sequence[Slice], axis: str, offset: float,
                lateral: np.ndarray, z: np.ndarray, fourier: bool) -> np.ndarray:
    """Complex permittivity on a depth x lateral grid (truncated Fourier series in patterned slices if `fourier`)."""
    values = np.empty((z.size, lateral.size), dtype=complex)
    values[z < 0.0] = spec.material(spec.superstrate).eps
    values[z >= slices[-1].z_bottom] = spec.material(spec.substrate).eps
    X, Y = _line_points(axis, lateral, offset)
    for s, rows in _slice_rows(slices, z):
        line = fourier_eps(spec, slices, s, X, Y) if fourier and s.patterned else exact_eps(s, X, Y)
        values[rows] = line[None, :]
    return values


def eps_plane(spec: MaskSpec, slices: Sequence[Slice], s: Slice, xs: np.ndarray, ys: np.ndarray,
              fourier: bool) -> np.ndarray:
    """Complex permittivity of one slice on an x-y grid; shape (len(ys), len(xs))."""
    if fourier and s.patterned:
        return fourier_eps_grid(spec, slices, s, xs, ys)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    return np.broadcast_to(exact_eps(s, X, Y), X.shape).astype(complex)


def convolution_matrix(spec: MaskSpec, slices: Sequence[Slice], s: Slice) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The slice's Toeplitz permittivity matrix [eps] and the harmonic indices (mx, my) of its rows."""
    lattice, settings = solver_settings(spec, list(slices))
    mx, my = _harmonic_indices(settings.Nx, settings.Ny)
    E_conv, _, _ = _build_convolution_matrices_for_layer(Layer(s.thickness, s.pattern), lattice, settings, mx, my)
    return to_numpy(E_conv), to_numpy(mx), to_numpy(my)


# ---- fields ----------------------------------------------------------------------------

FIELD_QUANTITIES = ("|E|²", "|Ex|", "|Ey|", "|Ez|", "Re Ex", "Re Ey", "Re Ez")


def field_quantity(E: Dict[str, np.ndarray], quantity: str) -> np.ndarray:
    if quantity == "|E|²":
        return np.abs(E["x"]) ** 2 + np.abs(E["y"]) ** 2 + np.abs(E["z"]) ** 2
    component = quantity[-1].lower()
    return np.abs(E[component]) if quantity.startswith("|") else E[component].real


def field_section(solution, axis: str, offset: float, lateral: np.ndarray, z: np.ndarray,
                  amplitudes: Optional[Dict[str, np.ndarray]] = None) -> Dict[str, np.ndarray]:
    """E components on a depth x lateral grid in the x-z (axis="x") or y-z plane.

    `amplitudes` may carry `solution.amplitudes(z)` from an earlier call; it is the
    expensive part, so moving the section sideways then only redoes the phase sums.
    """
    amp = solution.amplitudes(z) if amplitudes is None else amplitudes
    Kx, Ky = to_numpy(solution.Kx), to_numpy(solution.Ky)
    along, across = (Kx, Ky) if axis == "x" else (Ky, Kx)
    phase_lateral = np.exp(-1j * solution.k0 * np.outer(along, np.asarray(lateral, dtype=float)))
    phase_offset = np.exp(-1j * solution.k0 * across * offset)
    return {c: (amp["s" + c] * phase_offset) @ phase_lateral for c in "xyz"}


def field_plane(solution, xs: np.ndarray, ys: np.ndarray, depth: float) -> Dict[str, np.ndarray]:
    """E components on an x-y grid at `depth`; shape (len(ys), len(xs))."""
    return solution.efield_xy(xs, ys, depth)


def absorption_by_layer(solution, slices: Sequence[Slice]) -> Dict[str, float]:
    """Absorbed fraction of the incident power, summed per named layer (repeats and steps merged)."""
    totals: Dict[str, float] = defaultdict(float)
    for s, a in zip(slices, solution.layer_absorption(), strict=True):
        totals[s.layer_name] += float(a)
    return dict(totals)


def mode_kz(solution, slice_index: int) -> np.ndarray:
    """Propagation constants kz/k0 of a slice's eigenmodes (lam = j kz; Im kz < 0 decays)."""
    return -1j * to_numpy(solution.layers[slice_index].modes.lam)


# ---- diffraction orders ------------------------------------------------------------------


def _finite(value: float) -> Optional[float]:
    value = float(value)
    return value if math.isfinite(value) else None


def order_records(solution) -> List[dict]:
    """Per-order table: directions, efficiencies, and reflected TE/TM amplitudes at z = 0.

    Keeps propagating orders and any order carrying power; sorted by (n, m). NaN values
    (evanescent amplitudes and angles) become None.
    """
    res = solution.result
    h, eff = res["harmonics"], res["efficiencies"]
    t = solution.order_table()
    R, T = np.real(eff["R"]), np.real(eff["T"])
    keep = t["r_propagating"] | t["t_propagating"] | (R > 1e-12) | (T > 1e-12)
    rows = []
    for i in np.flatnonzero(keep):
        rows.append(dict(
            m=int(h["mx"][i]), n=int(h["my"][i]),
            r_theta_deg=_finite(t["r_theta_deg"][i]), r_phi_deg=_finite(t["r_phi_deg"][i]),
            R=float(R[i]), T=float(T[i]),
            r_te_abs=_finite(np.abs(t["r_te"][i])), r_te_phase_deg=_finite(np.degrees(np.angle(t["r_te"][i]))),
            r_tm_abs=_finite(np.abs(t["r_tm"][i])), r_tm_phase_deg=_finite(np.degrees(np.angle(t["r_tm"][i]))),
            r_propagating=bool(t["r_propagating"][i]), t_propagating=bool(t["t_propagating"][i]),
        ))
    return sorted(rows, key=lambda r: (r["n"], r["m"]))


def pupil_points(solution, n_ref: float) -> dict:
    """Propagating reflected orders in direction-cosine space (kx, ky)/(k0 n).

    Phase is taken from the order's TE component for TE-dominant incidence, else TM.
    """
    h = solution.result["harmonics"]
    Kx, Ky = to_numpy(solution.Kx).real, to_numpy(solution.Ky).real
    R = np.real(solution.result["efficiencies"]["R"])
    t = solution.order_table()
    prop = t["r_propagating"]
    inc = solution.problem.inc
    basis = "TE" if inc.pTE >= inc.pTM else "TM"
    phase = np.degrees(np.angle(t["r_te"] if basis == "TE" else t["r_tm"]))
    i0 = solution.zero_order_index
    return dict(
        m=h["mx"][prop].tolist(), n=h["my"][prop].tolist(),
        sx=(Kx[prop] / n_ref).tolist(), sy=(Ky[prop] / n_ref).tolist(),
        R=R[prop].tolist(), phase_deg=[_finite(p) for p in phase[prop]],
        center=[float(Kx[i0] / n_ref), float(Ky[i0] / n_ref)], basis=basis,
    )


def captured_power(solution, n_ref: float, na_mask: float) -> float:
    """Reflected power inside a mask-side NA circle centred on the specular order."""
    Kx, Ky = to_numpy(solution.Kx).real, to_numpy(solution.Ky).real
    i0 = solution.zero_order_index
    inside = np.hypot(Kx - Kx[i0], Ky - Ky[i0]) / n_ref <= na_mask + 1e-12
    return float(np.sum(np.real(solution.result["efficiencies"]["R"])[inside]))


# ---- sweeps ---------------------------------------------------------------------------------


def default_sweep_range(key: str, spec: MaskSpec) -> Tuple[float, float, int]:
    """Reasonable (start, stop, points) for a sweep parameter of `spec`."""
    ill, pat = spec.illumination, spec.pattern
    if key == "theta_deg":
        return 0.0, 12.0, 13
    if key == "phi_deg":
        return 0.0, 90.0, 10
    if key == "wavelength_nm":
        w = ill.wavelength / NM
        return round(w * 0.97, 3), round(w * 1.03, 3), 25
    if key in ("cd_x_nm", "cd_y_nm"):
        v = (pat.cd_x if key == "cd_x_nm" else pat.cd_y) / NM
        return round(v * 0.8, 2), round(v * 1.2, 2), 11
    if key == "pitch_x_nm":
        v = pat.pitch_x / NM
        return round(max(v * 0.75, pat.cd_x / NM + 1), 2), round(v * 1.5, 2), 11
    if key == "swa_deg":
        return 80.0, 90.0, 11
    if key == "harmonics":
        top = max(spec.numerics.nx, 2)
        return 1.0, float(top), int(top)
    if key.startswith("thickness:"):
        name = key.split(":", 1)[1]
        t = next(l.thickness for l in spec.layers if l.name == name) / NM
        return round(t * 0.5, 3), round(t * 1.5, 3), 11
    raise KeyError(key)


def sweep_values(key: str, start: float, stop: float, points: int) -> List[float]:
    """Evenly spaced sweep values; harmonic counts are rounded to distinct non-negative integers."""
    values = np.linspace(start, stop, max(int(points), 1))
    if key == "harmonics":
        return [float(v) for v in np.unique(np.clip(np.round(values), 0, None).astype(int))]
    return [float(v) for v in values]
