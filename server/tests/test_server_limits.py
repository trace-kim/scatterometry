"""Requests that would exhaust memory are refused before any work starts."""
from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from maskserver import jobs
from maskserver.app import create_app
from maskserver.settings import Settings
from masksim import preset_project


@pytest.fixture(scope="module")
def tight_client():
    """A server with a 1 MiB solve budget and 1 MiB request bodies."""
    app = create_app(Settings(web_dist=None, max_solve_gb=2**-10, max_body_mb=1))
    with TestClient(app) as c:
        yield c


def _doc(project) -> dict:
    return project.model_dump(mode="json")


def test_check_reports_oversized_stacks_quickly(client):
    project = preset_project("euv-lines")
    group = next(layer.group for layer in project.layers if layer.group)
    project.repeats[group] = 10**6
    start = time.perf_counter()
    body = client.post("/api/project/check", json=_doc(project)).json()
    assert time.perf_counter() - start < 2.0
    assert any("slices" in error for error in body["errors"]), body


def test_views_refuse_oversized_harmonics(client):
    project = preset_project("euv-contacts")
    project.numerics.nx = project.numerics.ny = 1000
    response = client.post("/api/dielectric/convolution", json={"project": _doc(project), "slice": 0})
    assert response.status_code == 422
    assert any("harmonics" in error for error in response.json()["detail"]["errors"])


def test_sweep_points_are_validated_up_front(client):
    sweep = {"project": _doc(preset_project("euv-lines")), "parameter": "harmonics",
             "start": 1, "stop": 5000, "points": 3}
    response = client.post("/api/sweeps", json=sweep)
    assert response.status_code == 422
    assert any("harmonics" in error for error in response.json()["detail"]["errors"])


def test_solves_over_the_memory_budget_are_refused(tight_client):
    project = _doc(preset_project("euv-contacts"))  # estimated ~150 MB
    response = tight_client.post("/api/runs", json={"project": project})
    assert response.status_code == 422
    assert "MASKSIM_MAX_SOLVE_GB" in response.json()["detail"]["errors"][0]
    sweep = {"project": project, "parameter": "theta_deg", "start": 0, "stop": 10, "points": 3}
    assert tight_client.post("/api/sweeps", json=sweep).status_code == 422
    assert tight_client.get("/api/jobs").json() == []


def test_oversized_bodies_are_refused(tight_client):
    headers = {"content-type": "application/json"}
    body = b'{"name": "' + b"x" * 2**21 + b'"}'
    assert tight_client.post("/api/project/normalize", content=body, headers=headers).status_code == 413

    def chunks():  # streamed without a Content-Length
        for _ in range(3):
            yield b" " * 2**20

    assert tight_client.post("/api/project/normalize", content=chunks(), headers=headers).status_code == 413
    assert tight_client.get("/api/health").status_code == 200


def test_job_cache_is_bounded_by_bytes(monkeypatch):
    monkeypatch.setattr(jobs, "CACHE_BYTES", 1000)
    job = jobs.Job(id="j", kind="run", project=preset_project("euv-lines"))
    for key in "abc":  # 400 bytes each
        job.cached((key,), lambda: {"x": np.zeros(50)})
    assert list(job.cache) == [("b",), ("c",)]
    too_big = {"x": np.zeros(200)}
    assert job.cached(("d",), lambda: too_big) is too_big
    assert list(job.cache) == [("b",), ("c",)]
