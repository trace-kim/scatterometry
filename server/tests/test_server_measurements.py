from __future__ import annotations

import numpy as np
from conftest import load_npz
from fastapi.testclient import TestClient

from maskserver.app import create_app
from maskserver.settings import Settings
from masksim.spe import write_spe

FRAMES = (np.arange(3 * 4 * 6).reshape(3, 4, 6) * 10).astype(np.uint16)


def upload(client, data: bytes, name: str = "ccd.spe"):
    return client.post("/api/measurements", params={"name": name}, content=data,
                       headers={"content-type": "application/octet-stream"})


def test_upload_and_read_frames(client):
    response = upload(client, write_spe(FRAMES, exposure_s=0.2, sensor_origin=(8, 2), binning=(2, 2),
                                        timestamps_s=[0, 1, 3]))
    assert response.status_code == 201, response.text
    info = response.json()
    assert info["name"] == "ccd.spe" and info["frames"] == 3 and info["dtype"] == "uint16"
    assert info["regions"] == [{"index": 0, "width": 6, "height": 4, "x": 8, "y": 2, "x_binning": 2, "y_binning": 2}]
    assert info["summary"]["exposure_s"] == 0.2
    mid = info["id"]
    assert any(m["id"] == mid for m in client.get("/api/measurements").json())

    frame = load_npz(client.get(f"/api/measurements/{mid}/frame", params={"index": 2}))
    assert frame["counts"].dtype == np.uint16
    np.testing.assert_array_equal(frame["counts"], FRAMES[2])
    np.testing.assert_allclose(frame["x_px"][:2], [8.5, 10.5])  # 2x binned sensor pixels 8-9, 10-11
    mean = load_npz(client.get(f"/api/measurements/{mid}/frame", params={"average": True}))
    np.testing.assert_allclose(mean["counts"], FRAMES.mean(axis=0))

    trace = client.get(f"/api/measurements/{mid}/trace").json()
    assert trace["total"] == [float(f.sum()) for f in FRAMES]
    assert trace["time_s"] == [0, 1, 3] and trace["frame_numbers"] == [1, 2, 3]
    settings = client.get(f"/api/measurements/{mid}/settings").json()
    assert {"path": "DataHistories/DataHistory/Origin@software", "value": "masksim.spe"} in settings

    assert client.get(f"/api/measurements/{mid}/frame", params={"index": 3}).status_code == 400
    assert client.get(f"/api/measurements/{mid}/frame", params={"region": 1}).status_code == 400
    assert client.delete(f"/api/measurements/{mid}").status_code == 204
    assert client.get(f"/api/measurements/{mid}").status_code == 404


def test_unreadable_upload_is_422(client):
    response = upload(client, b"\0" * 5000, "junk.spe")
    assert response.status_code == 422
    assert "junk.spe: not an SPE file" in response.json()["detail"]["errors"][0]


def test_upload_limit_and_retention():
    data = write_spe(FRAMES)
    settings = Settings(web_dist=None, max_body_mb=0.001, max_upload_mb=len(data) / 2**20,
                        max_measurements_gb=1.5 * len(data) / 2**30)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/project/check", content=b"x" * 2000).status_code == 413  # other routes keep 1 kB
        first = upload(client, data).json()["id"]
        second = upload(client, data).json()["id"]
        # Only one file fits the retention budget; the newest stays.
        assert [m["id"] for m in client.get("/api/measurements").json()] == [second]
        assert client.get(f"/api/measurements/{first}").status_code == 404
        assert upload(client, data + b"\0").status_code == 413
