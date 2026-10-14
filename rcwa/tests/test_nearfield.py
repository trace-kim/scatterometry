"""NearFieldSolver: agreement with RCWASolver, field continuity, and power balance."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from masksim import Material, LayerSpec, MaskSpec, Numerics, PatternSpec, Illumination, build_problem, NM
from masksim.presets import duv_attpsm_lines, euv_blank, euv_contacts, euv_lines
from rcwa import NearFieldSolver, RCWASolver
from rcwa.backend import get_array_module, to_numpy


def _cases():
    lines = euv_lines()
    contacts = euv_contacts()
    return {
        "euv-lines-te": replace(lines, numerics=Numerics(nx=8, ny=0)),
        "euv-lines-tm-conical": replace(
            lines, numerics=Numerics(nx=6, ny=0),
            illumination=replace(lines.illumination, phi_deg=25.0, polarization="TM"),
        ),
        "euv-staggered-holes-conical": replace(
            contacts, numerics=Numerics(nx=2, ny=2),
            pattern=replace(contacts.pattern, kind="ch_staggered", hole_shape="ellipse"),
            illumination=replace(contacts.illumination, phi_deg=20.0, polarization="TM"),
        ),
        "euv-holes-grazing": replace(
            contacts, numerics=Numerics(nx=3, ny=3),
            illumination=replace(contacts.illumination, theta_deg=85.0, polarization="TE"),
        ),
        "euv-blank": euv_blank(),
        "duv-attpsm": replace(duv_attpsm_lines(), numerics=Numerics(nx=8, ny=0)),
    }


CASES = _cases()


@pytest.fixture(scope="module")
def solutions():
    return {name: NearFieldSolver().solve(build_problem(spec)) for name, spec in CASES.items()}


@pytest.mark.parametrize("name", list(CASES))
def test_efficiencies_match_reference_solver(name, solutions):
    reference = RCWASolver().solve(build_problem(CASES[name]))
    result = solutions[name].result

    np.testing.assert_allclose(result["efficiencies"]["R"], reference["efficiencies"]["R"], rtol=0, atol=1e-10)
    np.testing.assert_allclose(result["efficiencies"]["T"], reference["efficiencies"]["T"], rtol=0, atol=1e-10)


@pytest.mark.parametrize("name", list(CASES))
def test_tangential_fields_are_continuous(name, solutions):
    sol = solutions[name]
    xp = get_array_module()
    components = ("sx", "sy", "ux", "uy")

    def assert_same(a, b):
        scale = max(max(np.max(np.abs(a[c])) for c in components), 1.0)
        for c in components:
            np.testing.assert_allclose(np.asarray(a[c]), np.asarray(b[c]), rtol=0, atol=1e-9 * scale)

    first, last = sol.layers[0], sol.layers[-1]
    to_np = lambda d: {c: to_numpy(v) for c, v in d.items()}
    assert_same(to_np(sol._reflection_region(xp.asarray([0.0]))), to_np(sol._layer_amplitudes(first, xp.asarray([0.0]))))
    assert_same(to_np(sol._transmission_region(xp.asarray([0.0]))),
                to_np(sol._layer_amplitudes(last, xp.asarray([last.thickness]))))
    for upper, lower in zip(sol.layers[:-1], sol.layers[1:]):
        assert_same(to_np(sol._layer_amplitudes(upper, xp.asarray([upper.thickness]))),
                    to_np(sol._layer_amplitudes(lower, xp.asarray([0.0]))))


@pytest.mark.parametrize("name", list(CASES))
def test_power_flux_balances_reflection_transmission_and_absorption(name, solutions):
    sol = solutions[name]
    power = sol.result["power"]
    flux = sol.power_flux(sol.z_interfaces)
    absorbed = sol.layer_absorption()

    assert flux[0] == pytest.approx(1.0 - power["R_total"], abs=1e-10)
    assert flux[-1] == pytest.approx(power["T_total"], abs=1e-10)
    assert absorbed.sum() == pytest.approx(power["A_total"], abs=1e-10)
    assert absorbed.min() > -1e-10


def test_lossless_grating_conserves_power_through_the_stack():
    spec = MaskSpec(
        materials=(Material("Air", 1.0, 0.0), Material("Glass", 1.5, 0.0), Material("Film", 2.0, 0.0)),
        superstrate="Air",
        substrate="Glass",
        layers=(LayerSpec("Grating", "Film", 150 * NM, patterned=True, swa_deg=80.0, steps=4),
                LayerSpec("Buffer", "Film", 50 * NM)),
        pattern=PatternSpec(kind="ls_v", pitch_x=600 * NM, cd_x=250 * NM, fill="Air"),
        illumination=Illumination(wavelength=500 * NM, theta_deg=20.0, phi_deg=10.0, polarization="TM"),
        numerics=Numerics(nx=10, ny=0),
    )
    sol = NearFieldSolver().solve(build_problem(spec))
    flux = sol.power_flux(np.linspace(-50 * NM, sol.total_thickness + 50 * NM, 41))

    assert sol.result["power"]["RT_total"] == pytest.approx(1.0, abs=1e-10)
    np.testing.assert_allclose(flux, sol.result["power"]["T_total"], rtol=0, atol=1e-9)


def test_specular_order_table_matches_incident_geometry(solutions):
    sol = solutions["euv-lines-te"]
    table = sol.order_table()
    i0 = sol.zero_order_index

    assert table["r_theta_deg"][i0] == pytest.approx(6.0, abs=1e-9)
    assert table["r_phi_deg"][i0] == pytest.approx(0.0, abs=1e-9)
    # TE incidence on lines parallel to y keeps every in-plane order TE.
    propagating = table["r_propagating"]
    assert np.all(np.abs(table["r_tm"][propagating]) < 1e-9)
    # Specular order in vacuum: R_0 = |r|^2, all of it TE.
    assert np.abs(table["r_te"][i0]) ** 2 == pytest.approx(sol.result["efficiencies"]["R"][i0], rel=1e-9)
