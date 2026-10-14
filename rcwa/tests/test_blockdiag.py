"""DiagBlocks (2x2 blocks of diagonals) against dense algebra, and the solver's fast path."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from masksim import Numerics, build_problem
from masksim.presets import euv_contacts
from rcwa import Layer, NearFieldSolver
from rcwa.blockdiag import DiagBlocks, eye_minus, homogeneous_modes
from rcwa.patterns import HomogeneousPattern
from rcwa.smatrix import SMatrix, _redheffer_star

RNG = np.random.default_rng(7)
NH = 5


def _random_blocks() -> DiagBlocks:
    return DiagBlocks(RNG.normal(size=(NH, 2, 2)) + 1j * RNG.normal(size=(NH, 2, 2)) + 2 * np.eye(2))


def test_products_inverse_and_solve_match_dense():
    A, B = _random_blocks(), _random_blocks()
    dA, dB = A.to_dense(), B.to_dense()
    M = RNG.normal(size=(2 * NH, 3)) + 1j * RNG.normal(size=(2 * NH, 3))
    v = M[:, 0]
    np.testing.assert_allclose((A @ B).to_dense(), dA @ dB, atol=1e-13)
    np.testing.assert_allclose(A @ M, dA @ M, atol=1e-13)
    np.testing.assert_allclose(A @ v, dA @ v, atol=1e-13)
    np.testing.assert_allclose(M.T @ A, M.T @ dA, atol=1e-13)
    np.testing.assert_allclose(dB @ A, dB @ dA, atol=1e-13)
    np.testing.assert_allclose(A.inv().to_dense(), np.linalg.inv(dA), atol=1e-12)
    np.testing.assert_allclose(A.solve(M), np.linalg.solve(dA, M), atol=1e-12)
    np.testing.assert_allclose(eye_minus(A).to_dense(), np.eye(2 * NH) - dA, atol=1e-13)
    np.testing.assert_allclose(DiagBlocks.diagonal(v).to_dense(), np.diag(v), atol=0)


def test_star_product_of_structured_smatrices_matches_dense():
    SA = SMatrix(*(_random_blocks() * 0.3 for _ in range(4)))
    SB = SMatrix(*(_random_blocks() * 0.3 for _ in range(4)))
    fast = _redheffer_star(SA, SB)
    dense = _redheffer_star(SMatrix(*(b.to_dense() for b in vars(SA).values())),
                            SMatrix(*(b.to_dense() for b in vars(SB).values())))
    assert isinstance(fast.S11, DiagBlocks)
    for name in ("S11", "S12", "S21", "S22"):
        np.testing.assert_allclose(getattr(fast, name).to_dense(), getattr(dense, name), atol=1e-12)


def test_homogeneous_modes_solve_the_layer_eigenproblem():
    Kx = np.linspace(-1.4, 1.2, NH).astype(complex)
    Ky = np.linspace(0.3, -0.9, NH).astype(complex)
    eps, mu = 0.88 - 0.03j, 1.0
    kz = np.sqrt(mu * eps - Kx**2 - Ky**2)
    kz = np.where(kz.imag > 0, -kz, kz)
    W, V, lam = homogeneous_modes(Kx, Ky, eps, mu, kz)
    assert np.all(lam.real >= 0)
    # P Q W = W lam^2 for the homogeneous P and Q of Step 7 (E = eps I, U = mu I).
    I, Kx2, Ky2, KxKy = np.eye(NH), np.diag(Kx**2), np.diag(Ky**2), np.diag(Kx * Ky)
    P = np.block([[KxKy / eps, mu * I - Kx2 / eps], [Ky2 / eps - mu * I, -KxKy / eps]])
    Q = np.block([[KxKy / mu, eps * I - Kx2 / mu], [Ky2 / mu - eps * I, -KxKy / mu]])
    np.testing.assert_allclose(P @ Q @ W.to_dense(), W.to_dense() @ np.diag(lam**2), atol=1e-12)
    np.testing.assert_allclose(V.to_dense(), Q @ W.to_dense() @ np.diag(1 / lam), atol=1e-12)


class _Opaque(HomogeneousPattern):
    """A homogeneous pattern that hides it, forcing the dense eigen-solve path."""

    def uniform_eps(self):
        return None


def test_fast_path_matches_the_dense_path_with_fields():
    spec = euv_contacts()
    spec = replace(spec, numerics=Numerics(nx=2, ny=2),
                   illumination=replace(spec.illumination, theta_deg=80.0, phi_deg=15.0, polarization="TM"))
    problem = build_problem(spec)
    dense_layers = [
        Layer(thickness=lay.thickness, pattern=_Opaque(lay.pattern.uniform_eps()), mu_r=lay.mu_r)
        if lay.pattern.uniform_eps() is not None else lay
        for lay in problem.layers
    ]
    fast = NearFieldSolver().solve(problem)
    slow = NearFieldSolver().solve(replace(problem, layers=dense_layers))
    for key in ("R", "T"):
        np.testing.assert_allclose(fast.result["efficiencies"][key], slow.result["efficiencies"][key], atol=1e-11)
    z = np.linspace(-5e-9, fast.total_thickness + 5e-9, 23)
    a, b = fast.amplitudes(z), slow.amplitudes(z)
    scale = max(np.max(np.abs(v)) for v in a.values())
    for c in a:
        np.testing.assert_allclose(a[c], b[c], atol=1e-9 * scale)
