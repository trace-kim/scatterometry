"""Runs and sweeps through the HTTP API, plus the job manager's event stream."""
from __future__ import annotations

import time

import numpy as np
import pytest
from conftest import load_npz, wait_done

from maskserver.events import EventBroker
from maskserver.jobs import JobManager
from masksim import preset_project


@pytest.fixture(scope="module")
def finished_run(client):
    project = preset_project("euv-lines")
    project.numerics.nx = 4
    project.illumination.polarization = "TE+TM"
    job = client.post("/api/runs", json={"project": project.model_dump(mode="json"), "crosscheck": True}).json()
    assert job["status"] in ("queued", "running")
    info = wait_done(client, "runs", job["id"])
    assert info["status"] == "done", info
    return info


def test_run_summary_and_cross_check(finished_run):
    summary = finished_run["summary"]
    assert set(summary["power"]) == {"TE", "TM"}
    assert finished_run["check"]["dR"] < 1e-10
    assert finished_run["progress"] == 1.0


def test_orders_pupil_flux_absorption_and_modes(client, finished_run):
    run = f"/api/runs/{finished_run['id']}"
    power = finished_run["summary"]["power"]["TM"]

    orders = client.get(f"{run}/orders", params={"pol": "TM"}).json()["orders"]
    assert sum(o["R"] for o in orders) == pytest.approx(power["R_total"], abs=1e-12)

    pupil = client.get(f"{run}/pupil", params={"pol": "TM", "na": 0.33, "reduction": 4}).json()
    assert pupil["na_mask"] == pytest.approx(0.0825) and 0 < pupil["captured"] <= power["R_total"]

    flux = client.get(f"{run}/flux", params={"pol": "TM", "n": 50}).json()
    assert flux["flux"][0] == pytest.approx(1 - power["R_total"], abs=1e-9)
    assert len(flux["interfaces_nm"]) >= 80

    absorption = client.get(f"{run}/absorption", params={"pol": "TM"}).json()
    assert sum(l["absorbed"] for l in absorption["layers"]) == pytest.approx(power["A_total"], abs=1e-9)

    modes = client.get(f"{run}/modes", params={"slice": 0}).json()
    assert modes["pol"] == "TE" and len(modes["kz_re"]) == 2 * 9


def test_field_section_and_plane_arrays(client, finished_run):
    run = f"/api/runs/{finished_run['id']}"
    section = load_npz(client.get(f"{run}/field/section", params={
        "axis": "x", "periods": 1, "z_min_nm": -5, "z_max_nm": 70, "n_lateral": 40, "n_z": 30}))
    assert section["Ex"].shape == section["material"].shape == (30, 40)
    assert section["Ey"].dtype == np.complex64
    # TE at phi = 0: E is along y.
    assert np.abs(section["Ey"]).max() > 100 * np.abs(section["Ex"]).max()

    plane = load_npz(client.get(f"{run}/field/plane", params={"depth_nm": 30, "n": 16, "pol": "TM"}))
    assert plane["Ex"].shape == (16, 16) and plane["x_nm"].size == 16


def test_queued_runs_conflict_and_cancel(client):
    project = preset_project("euv-contacts")
    project.numerics.nx = project.numerics.ny = 6
    body = {"project": project.model_dump(mode="json")}
    first = client.post("/api/runs", json=body).json()
    second = client.post("/api/runs", json=body).json()

    assert client.get(f"/api/runs/{second['id']}/orders").status_code == 409
    client.delete(f"/api/runs/{second['id']}")
    client.delete(f"/api/runs/{first['id']}")
    jobs = client.app.state.jobs
    assert jobs.wait(first["id"], 120).status == "cancelled"
    assert client.get("/api/runs/does-not-exist").status_code == 404


def test_sweeps_stream_records(client):
    project = preset_project("euv-lines")
    project.numerics.nx = 3
    job = client.post("/api/sweeps", json={"project": project.model_dump(mode="json"),
                                           "parameter": "theta_deg", "start": 5, "stop": 6, "points": 2}).json()
    info = wait_done(client, "sweeps", job["id"])
    assert info["status"] == "done"

    result = client.get(f"/api/sweeps/{job['id']}").json()
    assert result["label"].startswith("Angle of incidence")
    assert len(result["records"]) == 2 * (7 + 1)
    totals = [r for r in result["records"] if r["m"] is None]
    assert [r["value"] for r in totals] == [5.0, 6.0]

    bad = client.post("/api/sweeps", json={"project": project.model_dump(mode="json"), "parameter": "cd_y_nm",
                                          "start": 1, "stop": 2})
    assert bad.status_code == 422


class RecordingBroker(EventBroker):
    def __init__(self):
        super().__init__()
        self.events = []

    def publish(self, event):
        self.events.append(event)


def test_job_manager_emits_status_progress_and_sweep_events():
    broker = RecordingBroker()
    jobs = JobManager(broker, max_workers=1, keep=2)
    project = preset_project("euv-lines")
    project.numerics.nx = 2
    try:
        run = jobs.submit_run(project)
        sweep = jobs.submit_sweep(project, "theta_deg", [4.0, 5.0])
        jobs.wait(run.id, 60)
        jobs.wait(sweep.id, 60)
    finally:
        jobs.shutdown()

    statuses = [e["job"]["status"] for e in broker.events if e["type"] == "job" and e["job"]["id"] == run.id]
    assert statuses[0] == "queued" and statuses[-1] == "done" and "running" in statuses
    batches = [e for e in broker.events if e["type"] == "sweep-records"]
    assert len(batches) == 2 and batches[0]["job_id"] == sweep.id


def test_finished_jobs_are_pruned_beyond_the_retention_limit():
    jobs = JobManager(EventBroker(), max_workers=1, keep=1)
    project = preset_project("euv-blank")
    try:
        _first, second = jobs.submit_run(project), jobs.submit_run(project)
        jobs.wait(second.id, 60)
        time.sleep(0.05)
        assert [j.id for j in jobs.list()] == [second.id]
    finally:
        jobs.shutdown()


def test_python_views_list_and_evaluate(client, finished_run):
    views = {v["id"]: v for v in client.get("/api/python-views").json()}
    assert {"eps-spectrum", "intensity-depth", "orders-vs-angle"} <= set(views)

    project = preset_project("euv-lines")
    project.numerics.nx = 4
    body = {"project": project.model_dump(mode="json")}
    spectrum = client.post("/api/python-views/eps-spectrum", json=body).json()["option"]
    assert spectrum["series"][0]["type"] == "bar" and len(spectrum["series"][0]["data"]) > 1

    assert client.post("/api/python-views/intensity-depth", json=body).status_code == 409
    for view_id in ("intensity-depth", "orders-vs-angle"):
        option = client.post(f"/api/python-views/{view_id}", json={**body, "run_id": finished_run["id"]}).json()
        assert option["option"]["series"][0]["data"], view_id
    assert client.post("/api/python-views/nope", json=body).status_code == 404
