from __future__ import annotations

import numpy as np
import pytest

from rcwa import (
    ExternalRegion,
    FresnelProblem,
    FresnelSolver,
    IncidentWave,
    Lattice,
    RCWAProblem,
    RCWASettings,
    RCWASolver,
    eps_to_n,
    nk_to_eps,
    nk_to_n,
)
from rcwa.linalg import _outgoing_sqrt


@pytest.mark.parametrize("k", [0.1, -0.1])
def test_extinction_sign_is_normalized_to_passive_medium(k: float) -> None:
    expected_n = 1.7 - 0.1j

    assert nk_to_n(1.7, k) == expected_n
    assert nk_to_eps(1.7, k) == expected_n**2
    assert eps_to_n(nk_to_eps(1.7, k)) == pytest.approx(expected_n)


def test_outgoing_sqrt_selects_passive_and_evanescent_roots() -> None:
    roots = _outgoing_sqrt(np.array([(1.7 - 0.1j) ** 2, -4.0 + 0j]))

    np.testing.assert_allclose(roots, np.array([1.7 - 0.1j, -2.0j]))


@pytest.mark.parametrize("polarization", ["s", "p"])
@pytest.mark.parametrize("angle_deg", [0.0, 30.0, 60.0])
def test_absorbing_external_interface_matches_fresnel(
    polarization: str,
    angle_deg: float,
) -> None:
    wavelength = 550e-9
    theta = np.deg2rad(angle_deg)
    n_substrate = 1.7 - 0.1j
    incident = IncidentWave(
        wavelength=wavelength,
        theta=theta,
        pTE=float(polarization == "s"),
        pTM=float(polarization == "p"),
    )
    problem = RCWAProblem(
        lattice=Lattice(Lx=1e-6),
        inc=incident,
        region_ref=ExternalRegion(eps_r=1.0),
        region_trn=ExternalRegion(eps_r=n_substrate**2),
        layers=[],
        settings=RCWASettings(Nx=0, Ny=0, grid_Nx=1, grid_Ny=1),
    )

    rcwa = RCWASolver().solve(problem)["power"]
    fresnel = FresnelSolver().solve(
        FresnelProblem(
            wavelength=wavelength,
            theta=theta,
            n_inc=1.0,
            n_sub=n_substrate,
            layers=[],
            polarization=polarization,
        )
    )

    assert rcwa["R_total"] == pytest.approx(fresnel["R"], abs=1e-12)
    assert rcwa["T_total"] == pytest.approx(fresnel["T"], abs=1e-12)
    assert rcwa["RT_total"] == pytest.approx(1.0, abs=1e-12)
    assert rcwa["A_total"] == pytest.approx(0.0, abs=1e-12)
