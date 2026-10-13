from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from maskserver.app import create_app
from maskserver.settings import Settings
from masksim import preset_project


@pytest.fixture(scope="module")
def client():
    app = create_app(Settings(web_dist=None, max_jobs=1, keep_results=8))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def lines_project():
    """EUV L/S preset with few harmonics so solves take milliseconds."""
    project = preset_project("euv-lines")
    project.numerics.nx = 4
    return project


def load_npz(response) -> dict:
    assert response.status_code == 200, response.text
    with np.load(io.BytesIO(response.content)) as data:
        return {k: data[k] for k in data.files}


def wait_done(client, kind: str, job_id: str, timeout: float = 120.0) -> dict:
    client.app.state.jobs.wait(job_id, timeout)
    info = client.get(f"/api/{kind}/{job_id}").json()
    return info["job"] if kind == "sweeps" else info
