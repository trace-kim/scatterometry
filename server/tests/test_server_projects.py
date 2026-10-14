"""Project, geometry, and permittivity endpoints."""
from __future__ import annotations

import numpy as np
import pytest
from conftest import load_npz

from masksim import preset_project


def test_health_and_presets(client):
    assert client.get("/api/health").json()["status"] == "ok"
    presets = client.get("/api/presets").json()
    ids = [p["id"] for p in presets]
    assert "euv-lines" in ids and "euv-contacts" in ids

    project = client.get("/api/presets/euv-contacts").json()
    assert project["format"] == "masksim-project" and project["pattern"]["kind"] == "ch_square"
    assert client.get("/api/presets/nope").status_code == 404


def test_check_summarizes_valid_projects_and_lists_errors_for_invalid_ones(client, lines_project):
    body = client.post("/api/project/check", json=lines_project.model_dump(mode="json")).json()
    assert body["errors"] == []
    summary = body["summary"]
    assert summary["periodic_axes"] == "x" and summary["harmonics"] == 9
    assert summary["slice_count"] == len(body["slices"]) == 5 + 1 + 80
    assert summary["total_thickness_nm"] == pytest.approx(60 + 2.5 + 40 * 6.89)
    keys = {p["key"] for p in body["sweep_parameters"]}
    assert {"theta_deg", "cd_x_nm", "thickness:Absorber"} <= keys

    broken = lines_project.model_copy(deep=True)
    broken.layers[0].material = "Unobtainium"
    body = client.post("/api/project/check", json=broken.model_dump(mode="json")).json()
    assert body["summary"] is None and any("Unobtainium" in e for e in body["errors"])

    schema_error = client.post("/api/project/check", json={**lines_project.model_dump(mode="json"), "layers": 3})
    assert schema_error.status_code == 422


def test_normalize_fills_defaults_and_reports_bad_documents(client):
    minimal = {"materials": [{"name": "Air", "n": 1}], "superstrate": "Air", "substrate": "Air",
               "layers": [{"name": "L", "material": "Air", "thickness_nm": 10}]}
    project = client.post("/api/project/normalize", json=minimal).json()
    assert project["format"] == "masksim-project" and project["pattern"]["kind"] == "ls_v"
    assert project["layers"][0]["swa_deg"] == 90 and project["materials"][0]["k"] == 0

    newer = client.post("/api/project/normalize", json={**minimal, "version": 99})
    assert newer.status_code == 422 and "newer" in newer.json()["detail"]["errors"][0]
    broken = client.post("/api/project/normalize", json={**minimal, "layers": [{"name": "L"}]})
    assert broken.status_code == 422 and any("material" in e for e in broken.json()["detail"]["errors"])


def test_geometry_maps_and_boxes(client, lines_project):
    project = lines_project.model_dump(mode="json")
    section = load_npz(client.post("/api/geometry/section", json={
        "project": project, "axis": "x", "periods": 2, "z_min_nm": -10, "z_max_nm": 80, "n_lateral": 64, "n_z": 30}))
    assert section["material"].shape == (30, 64) and section["material"].dtype == np.uint8
    names = [m["name"] for m in project["materials"]]
    assert set(np.unique(section["material"])) <= set(range(len(names)))
    assert section["lateral_nm"][-1] < 256 and section["z_nm"][0] == -10

    plane = load_npz(client.post("/api/geometry/plane", json={"project": project, "slice": 2, "n": 32}))
    assert plane["material"].shape == (32, 32)
    assert set(np.unique(plane["material"])) == {names.index("TaBN"), names.index("Vacuum")}

    boxes = client.post("/api/geometry/boxes", json={"project": project, "periods": 1, "n": 32}).json()
    assert boxes["size_nm"][0] == 128 and len(boxes["boxes"]) > 80

    invalid = client.post("/api/geometry/plane", json={"project": project, "slice": 999})
    assert invalid.status_code == 400


def test_dielectric_views(client, lines_project):
    project = lines_project.model_dump(mode="json")
    request = {"project": project, "periods": 1, "z_min_nm": 0, "z_max_nm": 60, "n_lateral": 48, "n_z": 12}
    exact = load_npz(client.post("/api/dielectric/section", json=request))["eps"]
    fourier = load_npz(client.post("/api/dielectric/section", json={**request, "fourier": True}))["eps"]
    assert exact.dtype == np.complex64 and exact.shape == fourier.shape == (12, 48)
    assert not np.allclose(exact, fourier)  # Gibbs ringing of the truncated series

    conv = load_npz(client.post("/api/dielectric/convolution", json={"project": project, "slice": 0}))
    # At 6 deg the pupil-centred window sits one order towards k_t = 0.
    assert conv["matrix"].shape == (9, 9) and list(conv["mx"]) == list(range(-3, 6))


def test_invalid_projects_are_rejected_by_view_endpoints(client):
    project = preset_project("euv-lines")
    project.pattern.cd_x_nm = 500
    response = client.post("/api/geometry/section", json={"project": project.model_dump(mode="json")})
    assert response.status_code == 422 and any("CD" in e for e in response.json()["detail"]["errors"])
