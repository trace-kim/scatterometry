"""Size limits in masksim.validate, slice counting, and the solve memory estimate."""
import time
import tracemalloc
from dataclasses import replace

import numpy as np
import pytest

from masksim import (
    MAX_GRID_SAMPLES,
    MAX_HARMONICS,
    PRESET_IDS,
    PRESETS,
    build_slices,
    memory_estimate,
    slice_counts,
    solve_spec,
    solver_settings,
    validate,
    views,
)
from masksim.presets import euv_contacts, euv_lines


def _sloped(spec, steps, swa=82.0):
    return replace(spec, layers=tuple(replace(layer, swa_deg=swa, steps=steps) if layer.patterned else layer
                                      for layer in spec.layers))


CASES = {PRESET_IDS[name]: factory() for name, factory in PRESETS.items()}
CASES["euv-lines-sloped"] = _sloped(euv_lines(), steps=7)
CASES["euv-contacts-sloped"] = _sloped(euv_contacts(), steps=3)


@pytest.mark.parametrize("case", list(CASES))
def test_slice_counts_and_settings_match_the_built_slices(case):
    spec = CASES[case]
    slices = build_slices(spec)
    assert slice_counts(spec) == (len(slices), sum(s.patterned for s in slices))
    assert solver_settings(spec) == solver_settings(spec, slices)


def test_oversized_inputs_fail_validation_without_expanding_the_stack():
    spec = euv_lines()
    group = next(layer.group for layer in spec.layers if layer.group)
    numerics = spec.numerics
    cases = [
        ("slices", replace(spec, repeats=((group, 10**6),))),
        ("slices", _sloped(spec, steps=10**6)),
        ("harmonics", replace(spec, numerics=replace(numerics, nx=MAX_HARMONICS))),
        ("grid", replace(spec, numerics=replace(numerics, grid=MAX_GRID_SAMPLES + 1))),
        ("non-negative", replace(spec, numerics=replace(numerics, nx=-1))),
    ]
    for fragment, case in cases:
        start = time.perf_counter()
        errors = validate(case)
        assert time.perf_counter() - start < 0.5, fragment
        assert any(fragment in error for error in errors), errors


def test_memory_estimate_tracks_the_measured_peak():
    spec = euv_lines()
    spec = replace(spec, numerics=replace(spec.numerics, nx=20),
                   illumination=replace(spec.illumination, polarization="TE+TM"))
    tracemalloc.start()
    try:
        solve_spec(spec)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert 0.8 * peak < memory_estimate(spec) < 1.25 * peak


def test_fourier_plane_matches_pointwise_synthesis():
    spec = euv_contacts()
    slices = build_slices(spec)
    s = next(s for s in slices if s.patterned)
    xs = np.linspace(-30e-9, 150e-9, 9)
    ys = np.linspace(0.0, 120e-9, 6)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    np.testing.assert_allclose(views.fourier_eps_grid(spec, slices, s, xs, ys),
                               views.fourier_eps(spec, slices, s, X, Y), rtol=0, atol=1e-10)
