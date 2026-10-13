"""masksim: stack expansion, sidewall slicing, pattern geometry, and solver settings."""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from masksim import (
    NM,
    HoleArrayPattern,
    LayerSpec,
    LineSpacePattern,
    Numerics,
    PatternSpec,
    build_problem,
    build_slices,
    expand_layers,
    validate,
    with_parameter,
)
from masksim.presets import euv_blank, euv_lines
from rcwa import NearFieldSolver


def _grid(Lx, Ly, nx, ny):
    x = np.linspace(0.0, Lx, nx, endpoint=False)
    y = np.linspace(0.0, Ly, ny, endpoint=False)
    return np.meshgrid(x, y, indexing="xy")


def test_repeat_groups_unroll_contiguous_blocks_in_order():
    spec = euv_blank()
    layers = expand_layers(spec)

    assert len(layers) == 1 + 2 * 40
    assert [layer.name for layer in layers[:5]] == ["Cap", "ML Si", "ML Mo", "ML Si", "ML Mo"]
    assert sum(layer.thickness for layer in layers) == pytest.approx((2.5 + 40 * 6.89) * NM)


@pytest.mark.parametrize("reference, ref_depth", [("top", 0.0), ("middle", 30.0), ("bottom", 60.0)])
@pytest.mark.parametrize("kind, tone, sign", [("ls_v", "holes", 1.0), ("ch_square", "holes", -1.0), ("ch_square", "pillars", 1.0)])
def test_sidewall_slices_follow_linear_cd_profile(reference, ref_depth, kind, tone, sign):
    spec = euv_lines()
    spec = replace(
        spec,
        layers=(LayerSpec("Absorber", "TaBN", 60 * NM, patterned=True, swa_deg=80.0, steps=3),) + spec.layers[1:],
        pattern=replace(spec.pattern, kind=kind, tone=tone, cd_x=50 * NM, cd_y=40 * NM, cd_reference=reference),
    )
    patterned = [s for s in build_slices(spec) if s.patterned]
    slope = 2.0 / math.tan(math.radians(80.0))

    assert [s.thickness for s in patterned] == pytest.approx([20 * NM] * 3)
    for s, mid in zip(patterned, (10.0, 30.0, 50.0)):
        assert s.cd[0] == pytest.approx((50.0 + sign * slope * (mid - ref_depth)) * NM)
        if kind.startswith("ch"):
            assert s.cd[1] == pytest.approx((40.0 + sign * slope * (mid - ref_depth)) * NM)


def test_cd_profile_is_continuous_across_patterned_layers():
    spec = euv_lines()
    spec = replace(spec, layers=(
        LayerSpec("ARC", "TaN", 10 * NM, patterned=True, swa_deg=70.0, steps=2),
        LayerSpec("Absorber", "TaBN", 40 * NM, patterned=True, swa_deg=90.0, steps=5),
    ) + spec.layers[1:])
    patterned = [s for s in build_slices(spec) if s.patterned]
    widen = 2.0 / math.tan(math.radians(70.0)) * 10.0

    assert len(patterned) == 3  # vertical walls need a single slice
    assert patterned[-1].cd[0] == pytest.approx((64.0 + widen) * NM)


def test_area_averaged_patterns_have_exact_fill_fractions_off_grid():
    X, Y = _grid(100 * NM, 100 * NM, 64, 1)
    lines = LineSpacePattern(100 * NM, 33.3 * NM, 2.0, 1.0)
    assert np.mean(lines.eps_r(X, Y).real) == pytest.approx(1.0 + 0.333, abs=1e-12)

    X, Y = _grid(90 * NM, 70 * NM, 64, 48)
    holes = HoleArrayPattern(90 * NM, 70 * NM, 41.7 * NM, 23.3 * NM, 2.0, 1.0)
    assert np.mean(holes.host_fraction(X, Y, 90 * NM / 64, 70 * NM / 48)) == pytest.approx(
        1.0 - (41.7 * 23.3) / (90 * 70), abs=1e-12)

    X, Y = _grid(90 * NM, 140 * NM, 64, 96)
    staggered = HoleArrayPattern(90 * NM, 70 * NM, 41.7 * NM, 23.3 * NM, 2.0, 1.0, staggered=True)
    assert np.mean(staggered.feature_fraction(X, Y, 90 * NM / 64, 140 * NM / 96)) == pytest.approx(
        2 * (41.7 * 23.3) / (90 * 140), abs=1e-12)


def test_solver_settings_follow_pattern_orientation():
    spec = replace(euv_lines(), numerics=Numerics(nx=7, ny=4))

    vertical = build_problem(spec).settings
    horizontal = build_problem(replace(spec, pattern=replace(spec.pattern, kind="ls_h"))).settings
    staggered = build_problem(replace(spec, pattern=replace(spec.pattern, kind="ch_staggered", pitch_y=100 * NM)))

    assert (vertical.Nx, vertical.Ny, vertical.grid_Ny) == (7, 0, 1)
    assert (horizontal.Nx, horizontal.Ny, horizontal.grid_Nx) == (0, 7, 1)
    assert (staggered.settings.Nx, staggered.settings.Ny) == (7, 4)
    assert staggered.lattice.Ly == pytest.approx(200 * NM)
    assert build_problem(euv_blank()).settings.Nx == 0


def test_horizontal_lines_are_vertical_lines_rotated_by_ninety_degrees():
    spec = replace(euv_lines(), numerics=Numerics(nx=6, ny=0))
    rotated = replace(
        spec,
        pattern=replace(spec.pattern, kind="ls_h"),
        illumination=replace(spec.illumination, phi_deg=90.0),
    )
    vertical = NearFieldSolver().solve(build_problem(spec), keep_fields=False).result["efficiencies"]
    horizontal = NearFieldSolver().solve(build_problem(rotated), keep_fields=False).result["efficiencies"]

    for (m, n), value in vertical["per_order_R"].items():
        assert horizontal["per_order_R"][(n, m)] == pytest.approx(value, abs=1e-9)


def test_validate_reports_unknown_materials_and_oversized_cd():
    spec = euv_lines()
    broken = replace(
        spec,
        layers=(replace(spec.layers[0], material="Unobtainium"),) + spec.layers[1:],
        pattern=replace(spec.pattern, cd_x=200 * NM),
    )

    errors = validate(broken)

    assert validate(spec) == []
    assert any("Unobtainium" in e for e in errors)
    assert any("CD" in e for e in errors)


def test_with_parameter_updates_named_layers_and_patterned_sidewalls():
    spec = euv_lines()

    thicker = with_parameter(spec, "thickness:ML Mo", 3.0)
    steeper = with_parameter(spec, "swa_deg", 88.0)

    assert [layer.thickness for layer in thicker.layers if layer.name == "ML Mo"] == [3.0 * NM]
    assert [layer.swa_deg for layer in steeper.layers] == [88.0, 90.0, 90.0, 90.0]
    assert with_parameter(spec, "harmonics", 9).numerics.nx == 9
