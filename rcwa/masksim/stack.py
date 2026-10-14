"""Photomask stack description, sidewall staircase slicing, and RCWAProblem assembly.

Lengths are meters; angles in the specs are degrees (converted to radians for the
solver). Layers are listed from the incident side downward.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, replace
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from rcwa import (
    ExternalRegion,
    IncidentWave,
    Lattice,
    Layer,
    RCWAProblem,
    RCWASettings,
    nk_to_eps,
)

from rcwa.convolution import pupil_centre_shift

from .geometry import HoleArrayPattern, LineSpacePattern, MaskPattern, UniformPattern

NM = 1e-9

# Size limits checked by validate(), so that one request to maskserver cannot exhaust
# memory or CPU. They sit far above real masks: an EUV multilayer stack is ~90 slices,
# and the presets use at most 121 harmonics.
MAX_SLICES = 1000
MAX_HARMONICS = 2601        # (2Nx+1)(2Ny+1) as the solver uses them, e.g. Nx = Ny = 25
MAX_GRID_SAMPLES = 2 ** 20  # real-space samples per slice for the Fourier transform
MAX_MATERIALS = 256         # maskserver sends material indices as uint8

PATTERN_KINDS: Dict[str, str] = {
    "none": "Unpatterned (blank)",
    "ls_v": "L/S vertical (lines along y)",
    "ls_h": "L/S horizontal (lines along x)",
    "ch_square": "C/H square array",
    "ch_staggered": "C/H staggered array",
}


@dataclass(frozen=True)
class Material:
    """Optical constants at the simulation wavelength (n - i*k; k >= 0 absorbs)."""
    name: str
    n: float
    k: float

    @property
    def eps(self) -> complex:
        return nk_to_eps(self.n, self.k)


@dataclass(frozen=True)
class LayerSpec:
    """One row of the stack table."""
    name: str
    material: str
    thickness: float
    patterned: bool = False
    swa_deg: float = 90.0  # sidewall angle of the layer material; < 90 widens it with depth
    steps: int = 1         # staircase slices used when swa_deg != 90
    group: str = ""        # contiguous rows sharing a group repeat together as a block


@dataclass(frozen=True)
class PatternSpec:
    """Lateral pattern applied to every patterned layer.

    L/S uses pitch_x/cd_x (width of the layer-material line) in either orientation.
    C/H uses both axes; the CD is the opening width for tone="holes" and the island
    width for tone="pillars". Staggered: pitch_y is the row spacing and alternate rows
    shift by pitch_x/2.
    """
    kind: str = "ls_v"
    pitch_x: float = 128 * NM
    pitch_y: float = 128 * NM
    cd_x: float = 64 * NM
    cd_y: float = 64 * NM
    hole_shape: str = "rect"   # "rect" | "ellipse"
    tone: str = "holes"        # "holes" | "pillars"
    fill: str = "Vacuum"       # material in spaces/openings
    cd_reference: str = "top"  # where the CD applies within the patterned stack: top | middle | bottom


@dataclass(frozen=True)
class Illumination:
    wavelength: float = 13.5 * NM
    theta_deg: float = 6.0     # angle of incidence from the normal
    phi_deg: float = 0.0       # azimuth; 0 = plane of incidence x-z
    polarization: str = "TE"   # "TE" | "TM" | "TE+TM"


@dataclass(frozen=True)
class Numerics:
    nx: int = 15  # harmonics on each side of the window centre (L/S uses nx along its periodic axis)
    ny: int = 15
    grid: int = 0  # real-space samples per periodic axis; 0 = automatic
    # "pupil": centre the order window on k_t = 0, so oblique incidence keeps every
    # propagating order; "specular": the classic -N..N around the specular order.
    centering: str = "pupil"


@dataclass(frozen=True)
class MaskSpec:
    materials: Tuple[Material, ...]
    superstrate: str  # incident medium
    substrate: str    # exit medium
    layers: Tuple[LayerSpec, ...]
    repeats: Tuple[Tuple[str, int], ...] = ()
    pattern: PatternSpec = PatternSpec()
    illumination: Illumination = Illumination()
    numerics: Numerics = Numerics()

    def material(self, name: str) -> Material:
        for m in self.materials:
            if m.name == name:
                return m
        raise KeyError(f"unknown material {name!r}")

    def polarizations(self) -> Tuple[str, ...]:
        pol = self.illumination.polarization
        return ("TE", "TM") if pol == "TE+TM" else (pol,)


@dataclass(frozen=True)
class Slice:
    """One RCWA layer (z-invariant) produced from a LayerSpec."""
    layer_name: str
    material: str           # host material
    fill: str               # material of openings/spaces (== material when unpatterned)
    z_top: float
    thickness: float
    pattern: MaskPattern
    step: int = 0
    steps: int = 1
    cd: Optional[Tuple[float, float]] = None  # feature widths at the slice centre

    @property
    def z_bottom(self) -> float:
        return self.z_top + self.thickness

    @property
    def patterned(self) -> bool:
        return self.cd is not None

    @property
    def label(self) -> str:
        return f"{self.layer_name} [{self.step + 1}/{self.steps}]" if self.steps > 1 else self.layer_name


def unit_cell(pattern: PatternSpec) -> Tuple[float, float]:
    if pattern.kind.startswith("ch"):
        return pattern.pitch_x, pattern.pitch_y * (2.0 if pattern.kind == "ch_staggered" else 1.0)
    return pattern.pitch_x, pattern.pitch_x


def _layer_blocks(spec: MaskSpec) -> Iterator[Tuple[Tuple[LayerSpec, ...], int]]:
    """Runs of contiguous rows sharing a repeat group, each with its repeat count (1 when ungrouped)."""
    counts = dict(spec.repeats)
    rows = tuple(spec.layers)
    i = 0
    while i < len(rows):
        group = rows[i].group.strip()
        j = i + 1
        while group and j < len(rows) and rows[j].group.strip() == group:
            j += 1
        yield rows[i:j], (max(1, int(counts.get(group, 1))) if group else 1)
        i = j


def expand_layers(spec: MaskSpec) -> List[LayerSpec]:
    """Unroll repeat groups: each run of contiguous rows sharing a group name repeats as a block."""
    out: List[LayerSpec] = []
    for block, count in _layer_blocks(spec):
        out.extend(block * count)
    return out


def sidewall_slope(swa_deg: float) -> float:
    """Width change of the layer material per unit depth (both walls)."""
    if not 0.0 < swa_deg < 180.0:
        raise ValueError("sidewall angle must lie strictly between 0 and 180 degrees")
    if abs(swa_deg - 90.0) < 1e-9:
        return 0.0
    return 2.0 / math.tan(math.radians(swa_deg))


def _steps(layer: LayerSpec, patterned: bool) -> int:
    """How many slices build_slices cuts `layer` into (`patterned`: the spec has a pattern)."""
    if patterned and layer.patterned and sidewall_slope(layer.swa_deg) != 0.0:
        return max(1, int(layer.steps))
    return 1


def slice_counts(spec: MaskSpec) -> Tuple[int, int]:
    """(all, patterned) slice counts of build_slices(spec), computed without expanding the stack.

    Needs valid sidewall angles, which validate() checks before calling it.
    """
    patterned = spec.pattern.kind != "none"
    total = cut = 0
    for block, count in _layer_blocks(spec):
        for layer in block:
            n = count * _steps(layer, patterned)
            total += n
            if patterned and layer.patterned:
                cut += n
    return total, cut


def dense_slice_count(spec: MaskSpec) -> int:
    """Slices from the top through the lowest patterned one, without expanding the stack.

    NearFieldSolver keeps a dense matrix for each of these interfaces; homogeneous slices
    below the last patterned one stay O(Nh).
    """
    if spec.pattern.kind == "none":
        return 0
    position = lowest = 0
    for block, count in _layer_blocks(spec):
        steps = [_steps(layer, True) for layer in block]
        offset = 0
        for layer, n in zip(block, steps, strict=True):
            offset += n
            if layer.patterned:
                lowest = position + (count - 1) * sum(steps) + offset
        position += count * sum(steps)
    return lowest


def _make_pattern(pat: PatternSpec, eps_host: complex, eps_fill: complex, cd_x: float, cd_y: float) -> MaskPattern:
    if pat.kind == "ls_v":
        return LineSpacePattern(pat.pitch_x, cd_x, eps_host, eps_fill, axis="x")
    if pat.kind == "ls_h":
        return LineSpacePattern(pat.pitch_x, cd_x, eps_host, eps_fill, axis="y")
    return HoleArrayPattern(
        pat.pitch_x, pat.pitch_y, cd_x, cd_y, eps_host, eps_fill,
        staggered=pat.kind == "ch_staggered", shape=pat.hole_shape, tone=pat.tone,
    )


def build_slices(spec: MaskSpec) -> List[Slice]:
    """Expand repeats and cut patterned layers into staircase slices.

    The layer-material width varies linearly with depth inside each patterned layer
    (slope from its sidewall angle) and continuously across consecutive patterned
    layers. The specified CD holds at `cd_reference`; each slice uses the width at
    its mid-depth.
    """
    pat = spec.pattern
    layers = expand_layers(spec)
    patterned = pat.kind != "none"

    segments = []  # (start, end, slope) in patterned-depth coordinates
    depth = 0.0
    for layer in layers:
        if patterned and layer.patterned:
            segments.append((depth, depth + layer.thickness, sidewall_slope(layer.swa_deg)))
            depth += layer.thickness

    def growth(zeta: float) -> float:
        return sum(slope * (min(max(zeta, z0), z1) - z0) for z0, z1, slope in segments)

    zeta_ref = {"top": 0.0, "middle": 0.5 * depth, "bottom": depth}[pat.cd_reference]
    # Openings shrink where the layer material widens.
    sign = -1.0 if (pat.kind.startswith("ch") and pat.tone == "holes") else 1.0
    Lx, Ly = unit_cell(pat)
    eps_fill = spec.material(pat.fill).eps if patterned else 0.0

    slices: List[Slice] = []
    z = 0.0
    zeta = 0.0
    for layer in layers:
        eps_host = spec.material(layer.material).eps
        if patterned and layer.patterned:
            n = _steps(layer, patterned)
            dt = layer.thickness / n
            for j in range(n):
                delta = sign * (growth(zeta + (j + 0.5) * dt) - growth(zeta_ref))
                cd_x = min(max(pat.cd_x + delta, 0.0), Lx)
                cd_y = min(max(pat.cd_y + delta, 0.0), Ly)
                slices.append(Slice(
                    layer.name, layer.material, pat.fill, z + j * dt, dt,
                    _make_pattern(pat, eps_host, eps_fill, cd_x, cd_y), j, n, (cd_x, cd_y),
                ))
            zeta += layer.thickness
        else:
            slices.append(Slice(layer.name, layer.material, layer.material, z, layer.thickness,
                                UniformPattern(eps_host)))
        z += layer.thickness
    return slices


def solver_settings(spec: MaskSpec, slices: Optional[Sequence[Slice]] = None) -> Tuple[Lattice, RCWASettings]:
    """Unit cell and truncation for the solver; works from the spec alone when `slices` is omitted."""
    pat, num = spec.pattern, spec.numerics
    Lx, Ly = unit_cell(pat)
    if slices is None:
        patterned = pat.kind != "none" and any(layer.patterned for layer in spec.layers)
    else:
        patterned = any(s.patterned for s in slices)
    if not patterned:
        nx = ny = 0
    elif pat.kind == "ls_v":
        nx, ny = num.nx, 0
    elif pat.kind == "ls_h":
        nx, ny = 0, num.nx
    else:
        nx, ny = num.nx, num.ny
    base = num.grid or (512 if nx == 0 or ny == 0 else 128)

    def samples(n: int) -> int:
        return 1 if n == 0 else max(base, 4 * n + 1)

    shift_x = shift_y = 0
    if num.centering == "pupil" and (nx or ny):
        ill = spec.illumination
        n_inc = cmath.sqrt(spec.material(spec.superstrate).eps).real
        sin_t = n_inc * math.sin(math.radians(ill.theta_deg))
        kx = sin_t * math.cos(math.radians(ill.phi_deg))
        ky = sin_t * math.sin(math.radians(ill.phi_deg))
        shift_x = pupil_centre_shift(kx, ill.wavelength / Lx, nx)
        shift_y = pupil_centre_shift(ky, ill.wavelength / Ly, ny)
    return Lattice(Lx=Lx, Ly=Ly), RCWASettings(Nx=nx, Ny=ny, grid_Nx=samples(nx), grid_Ny=samples(ny),
                                               shift_x=shift_x, shift_y=shift_y)


def build_problem(spec: MaskSpec, polarization: Optional[str] = None,
                  slices: Optional[List[Slice]] = None) -> RCWAProblem:
    slices = build_slices(spec) if slices is None else slices
    lattice, settings = solver_settings(spec, slices)
    ill = spec.illumination
    pTE, pTM = {"TE": (1.0, 0.0), "TM": (0.0, 1.0)}[polarization or spec.polarizations()[0]]
    return RCWAProblem(
        lattice=lattice,
        inc=IncidentWave(
            wavelength=ill.wavelength, theta=math.radians(ill.theta_deg),
            phi=math.radians(ill.phi_deg), pTE=pTE, pTM=pTM,
        ),
        region_ref=ExternalRegion(eps_r=spec.material(spec.superstrate).eps),
        region_trn=ExternalRegion(eps_r=spec.material(spec.substrate).eps),
        layers=[Layer(thickness=s.thickness, pattern=s.pattern) for s in slices],
        settings=settings,
    )


def validate(spec: MaskSpec) -> List[str]:
    """Human-readable problems that would make the spec unsolvable."""
    errors: List[str] = []
    names = [m.name for m in spec.materials]
    if len(set(names)) != len(names):
        errors.append("Material names must be unique.")
    known = set(names)
    pat = spec.pattern
    used = {spec.superstrate, spec.substrate} | {layer.material for layer in spec.layers}
    if pat.kind != "none":
        used.add(pat.fill)
    errors += [f"Unknown material '{m}'." for m in sorted(used - known)]
    if not spec.layers:
        errors.append("The stack needs at least one layer.")
    for layer in spec.layers:
        if not layer.thickness > 0.0:
            errors.append(f"Layer '{layer.name}' needs a positive thickness.")
        if not 0.0 < layer.swa_deg < 180.0:
            errors.append(f"Layer '{layer.name}': sidewall angle must be between 0 and 180 deg.")
        if layer.steps < 1:
            errors.append(f"Layer '{layer.name}': steps must be at least 1.")
    if pat.kind != "none":
        Lx, Ly = unit_cell(pat)
        if not (pat.pitch_x > 0 and pat.pitch_y > 0):
            errors.append("Pitches must be positive.")
        if not 0.0 <= pat.cd_x <= Lx or (pat.kind.startswith("ch") and not 0.0 <= pat.cd_y <= Ly):
            errors.append("CD must be between 0 and the pitch.")
    if spec.illumination.wavelength <= 0.0:
        errors.append("Wavelength must be positive.")
    if not 0.0 <= spec.illumination.theta_deg < 90.0:
        errors.append("Angle of incidence must be in [0, 90) deg.")
    if len(spec.materials) > MAX_MATERIALS:
        errors.append(f"At most {MAX_MATERIALS} materials are supported.")
    num = spec.numerics
    if num.centering not in ("pupil", "specular"):
        errors.append(f"Unknown order centering '{num.centering}'; use 'pupil' or 'specular'.")
    if num.nx < 0 or num.ny < 0:
        errors.append("Harmonic orders must be non-negative.")
    if num.grid < 0:
        errors.append("Grid must be 0 (automatic) or a positive sample count.")
    if errors:
        return errors

    # Size limits, computed from counts alone so that absurd inputs fail fast.
    slices, _ = slice_counts(spec)
    if slices > MAX_SLICES:
        errors.append(f"The stack expands to {slices:,} slices; at most {MAX_SLICES:,} are supported. "
                      "Reduce repeat counts or sidewall steps.")
    _, settings = solver_settings(spec)
    harmonics = (2 * settings.Nx + 1) * (2 * settings.Ny + 1)
    if harmonics > MAX_HARMONICS:
        errors.append(f"{harmonics:,} harmonics; at most {MAX_HARMONICS:,} are supported. Reduce Nx/Ny.")
    samples = settings.grid_Nx * settings.grid_Ny
    if samples > MAX_GRID_SAMPLES:
        errors.append(f"The sampling grid has {samples:,} points; at most {MAX_GRID_SAMPLES:,} are supported.")
    return errors


# ---- parameter sweeps -------------------------------------------------------

SWEEP_PARAMETERS: Dict[str, str] = {
    "theta_deg": "Angle of incidence θ (deg)",
    "phi_deg": "Azimuth φ (deg)",
    "wavelength_nm": "Wavelength (nm), n/k held fixed",
    "cd_x_nm": "CD x (nm)",
    "cd_y_nm": "CD y (nm)",
    "pitch_x_nm": "Pitch x (nm), CD held fixed",
    "swa_deg": "Sidewall angle of patterned layers (deg)",
    "harmonics": "Harmonics N (convergence check)",
}


def sweep_parameters(spec: MaskSpec) -> Dict[str, str]:
    """Sweepable parameters for this spec, including one thickness entry per named layer."""
    params = dict(SWEEP_PARAMETERS)
    if not spec.pattern.kind.startswith("ch"):
        params.pop("cd_y_nm")
    if spec.pattern.kind == "none":
        for key in ("cd_x_nm", "pitch_x_nm", "swa_deg", "harmonics"):
            params.pop(key, None)
    for name in dict.fromkeys(layer.name for layer in spec.layers):
        params[f"thickness:{name}"] = f"Thickness of '{name}' (nm)"
    return params


def with_parameter(spec: MaskSpec, key: str, value: float) -> MaskSpec:
    """Copy of `spec` with one sweep parameter set (lengths in nm)."""
    ill, pat = spec.illumination, spec.pattern
    if key == "theta_deg":
        return replace(spec, illumination=replace(ill, theta_deg=value))
    if key == "phi_deg":
        return replace(spec, illumination=replace(ill, phi_deg=value))
    if key == "wavelength_nm":
        return replace(spec, illumination=replace(ill, wavelength=value * NM))
    if key == "cd_x_nm":
        return replace(spec, pattern=replace(pat, cd_x=value * NM))
    if key == "cd_y_nm":
        return replace(spec, pattern=replace(pat, cd_y=value * NM))
    if key == "pitch_x_nm":
        return replace(spec, pattern=replace(pat, pitch_x=value * NM))
    if key == "swa_deg":
        layers = tuple(replace(layer, swa_deg=value) if layer.patterned else layer for layer in spec.layers)
        return replace(spec, layers=layers)
    if key == "harmonics":
        return replace(spec, numerics=replace(spec.numerics, nx=int(value), ny=int(value)))
    if key.startswith("thickness:"):
        name = key.split(":", 1)[1]
        layers = tuple(replace(layer, thickness=value * NM) if layer.name == name else layer for layer in spec.layers)
        return replace(spec, layers=layers)
    raise KeyError(key)
