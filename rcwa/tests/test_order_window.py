"""The pupil-centred harmonic window: placement, agreement with the specular window, and grazing incidence."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from masksim import Numerics, build_problem, solver_settings, validate
from masksim.presets import euv_contacts, euv_lines
from rcwa import NearFieldSolver, RCWASolver
from rcwa.convolution import _harmonic_indices, pupil_centre_shift


def test_shift_centres_the_window_on_the_pupil_and_keeps_the_specular_order():
    assert pupil_centre_shift(0.0, 0.1, 5) == 0
    assert pupil_centre_shift(np.sin(np.radians(85)), 13.5 / 128, 15) == 9
    assert pupil_centre_shift(np.sin(np.radians(85)), 13.5 / 128, 4) == 4  # clamped: (0, 0) stays inside
    assert pupil_centre_shift(-0.5, 0.1, 15) == -5
    mx, my = _harmonic_indices(2, 1, shift_x=2, shift_y=-1)
    assert sorted(set(mx.tolist())) == [0, 1, 2, 3, 4] and sorted(set(my.tolist())) == [-2, -1, 0]
    with pytest.raises(ValueError):
        _harmonic_indices(2, 2, shift_x=3)


def _grazing_holes(n: int, centering: str):
    spec = euv_contacts()
    return replace(spec, numerics=Numerics(nx=n, ny=1, centering=centering),
                   pattern=replace(spec.pattern, kind="ch_square", pitch_x=64e-9, pitch_y=64e-9,
                                   cd_x=32e-9, cd_y=32e-9),
                   illumination=replace(spec.illumination, theta_deg=85.0, polarization="TE"))


def test_grazing_incidence_keeps_every_propagating_order():
    # 64 nm pitch at 13.5 nm and 85 deg: orders m = 0..9 propagate, all on one side.
    centred = _grazing_holes(5, "pupil")
    _, settings = solver_settings(centred)
    assert settings.shift_x == 5 and settings.shift_y == 0
    sol = NearFieldSolver().solve(build_problem(centred), keep_fields=False)
    table = sol.order_table()
    m = sol.result["harmonics"]["mx"][table["r_propagating"]]
    assert m.min() == 0 and m.max() == 9
    # The classic window misses m = 6..9 with the same number of harmonics.
    classic = NearFieldSolver().solve(build_problem(_grazing_holes(5, "specular")), keep_fields=False)
    assert classic.result["harmonics"]["mx"][classic.order_table()["r_propagating"]].max() == 5


def test_reference_solver_uses_the_same_window():
    problem = build_problem(_grazing_holes(3, "pupil"))
    assert problem.settings.shift_x == 3
    ours = NearFieldSolver().solve(problem, keep_fields=False).result["efficiencies"]
    reference = RCWASolver().solve(problem)["efficiencies"]
    np.testing.assert_allclose(ours["R"], reference["R"], rtol=0, atol=1e-10)


def test_windows_agree_where_both_hold_every_propagating_order():
    # 6 deg L/S: both windows contain all propagating orders, so the results converge together.
    spec = euv_lines()
    results = {}
    for centering in ("pupil", "specular"):
        s = replace(spec, numerics=Numerics(nx=40, ny=0, centering=centering))
        results[centering] = NearFieldSolver().solve(build_problem(s), keep_fields=False).result["power"]["R_total"]
    assert results["pupil"] == pytest.approx(results["specular"], abs=1e-3)


def test_unknown_centering_is_reported():
    spec = replace(euv_lines(), numerics=Numerics(nx=4, centering="middle"))
    assert any("centering" in error for error in validate(spec))
