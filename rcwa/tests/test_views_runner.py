"""masksim.views and masksim.runner: UI data products and solve orchestration."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from masksim import NM, Numerics, build_slices, solve_spec, sweep_parameters, sweep_records, views
from masksim.presets import duv_attpsm_lines, euv_blank, euv_contacts, euv_lines


@pytest.fixture(scope="module")
def lines_run():
    spec = replace(euv_lines(), numerics=Numerics(nx=6, ny=0))
    spec = replace(spec, illumination=replace(spec.illumination, polarization="TE+TM"))
    return solve_spec(spec, crosscheck=True)


def test_solve_spec_reports_monotonic_progress_and_cross_checks(lines_run):
    seen = []
    spec = replace(euv_lines(), numerics=Numerics(nx=4, ny=0))
    solve_spec(spec, progress=lambda f, m: seen.append(f))

    assert seen == sorted(seen) and seen[-1] == 1.0
    assert set(lines_run.solutions) == {"TE", "TM"}
    assert lines_run.check["dR"] < 1e-10 and lines_run.check["dT"] < 1e-10
    assert lines_run.summary["power"]["TE"]["R_total"] == pytest.approx(
        lines_run.solutions["TE"].result["power"]["R_total"])


def test_progress_callback_can_cancel_a_solve():
    class Stop(Exception):
        pass

    def stop_after_first(fraction, message):
        if fraction > 0.0:
            raise Stop

    with pytest.raises(Stop):
        solve_spec(replace(euv_contacts(), numerics=Numerics(nx=2, ny=2)), progress=stop_after_first)


def test_order_records_cover_all_reflected_power(lines_run):
    sol = lines_run.solutions["TE"]
    rows = views.order_records(sol)

    assert sum(r["R"] for r in rows) == pytest.approx(sol.result["power"]["R_total"], abs=1e-12)
    assert [(r["n"], r["m"]) for r in rows] == sorted((r["n"], r["m"]) for r in rows)
    assert all(v is None or np.isfinite(v) for r in rows for v in r.values() if isinstance(v, float))
    specular = next(r for r in rows if r["m"] == 0 and r["n"] == 0)
    assert specular["r_theta_deg"] == pytest.approx(6.0)


def test_pupil_points_and_captured_power(lines_run):
    sol = lines_run.solutions["TE"]
    n_ref = views.incident_index(lines_run.spec)
    p = views.pupil_points(sol, n_ref)

    assert p["center"][0] == pytest.approx(np.sin(np.radians(6.0)))
    assert len(p["sx"]) == len(p["R"]) == len(p["m"])
    assert views.captured_power(sol, n_ref, 2.0) == pytest.approx(sum(p["R"]), abs=1e-12)
    specular = sol.result["efficiencies"]["R"][sol.zero_order_index].real
    assert views.captured_power(sol, n_ref, 1e-6) == pytest.approx(specular)


def test_stack_boxes_tile_unpatterned_and_patterned_stacks():
    blank = euv_blank()
    slices = build_slices(blank)
    boxes = views.stack_boxes(blank, slices, periods=1.0, z_max=1.0)
    assert len(boxes) == len(slices)
    assert sum(b[6] - b[5] for b in boxes) == pytest.approx(slices[-1].z_bottom)

    lines = euv_lines()
    patterned = views.stack_boxes(lines, build_slices(lines), periods=2.0, z_max=60 * NM, n=64)
    assert {b[0] for b in patterned} == {"TaBN"}  # vacuum spaces are omitted
    assert all(0.0 <= b[1] < b[2] <= 256 * NM for b in patterned)


def test_fourier_eps_matches_exact_for_homogeneous_slices_and_conv_diagonal_is_mean():
    spec = duv_attpsm_lines()
    slices = build_slices(spec)
    lateral, z = views.section_axes(spec, "x", 1.0, -10 * NM, 80 * NM, n_lateral=64, n_z=40)
    exact = views.eps_section(spec, slices, "x", 0.0, lateral, z, fourier=False)
    fourier = views.eps_section(spec, slices, "x", 0.0, lateral, z, fourier=True)
    homogeneous = (z < 0) | (z >= slices[-1].z_bottom)
    np.testing.assert_allclose(fourier[homogeneous], exact[homogeneous])

    E, mx, my = views.convolution_matrix(spec, slices, slices[0])
    assert E.shape == (mx.size, mx.size)
    xs = (np.arange(400) + 0.5) * 400 * NM / 400
    mean_eps = np.mean(views.exact_eps(slices[0], xs, np.zeros_like(xs)))
    assert np.diag(E) == pytest.approx(np.full(mx.size, mean_eps), rel=1e-3)


def test_sweeps_yield_one_record_set_per_value_with_totals():
    spec = replace(euv_lines(), numerics=Numerics(nx=3, ny=0))
    values = [5.0, 6.0]
    batches = list(sweep_records(spec, "theta_deg", values))

    assert len(batches) == 2
    totals = [r for r in batches[1] if r["m"] is None]
    assert len(totals) == 1 and totals[0]["value"] == 6.0
    assert totals[0]["R"] == pytest.approx(sum(r["R"] for r in batches[1] if r["m"] is not None))


@pytest.mark.parametrize("make", [euv_lines, euv_contacts, euv_blank])
def test_every_sweep_parameter_has_a_default_range(make):
    spec = make()
    for key in sweep_parameters(spec):
        start, stop, points = views.default_sweep_range(key, spec)
        assert start < stop and points >= 1
    assert views.sweep_values("harmonics", 1, 5, 9) == [1.0, 2.0, 3.0, 4.0, 5.0]
