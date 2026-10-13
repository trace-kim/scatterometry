"""masksim.project: versioned documents, unit conversion, and digests."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from masksim import NM, PRESET_IDS, PRESETS, Project, load_project, preset_project


@pytest.mark.parametrize("name", list(PRESETS))
def test_presets_round_trip_through_project_documents(name):
    spec = PRESETS[name]()
    back = preset_project(PRESET_IDS[name]).to_spec()

    assert back.materials == spec.materials
    assert (back.superstrate, back.substrate, back.repeats) == (spec.superstrate, spec.substrate, spec.repeats)
    for a, b in zip(back.layers, spec.layers, strict=True):
        assert (a.name, a.material, a.patterned, a.swa_deg, a.steps, a.group) == \
               (b.name, b.material, b.patterned, b.swa_deg, b.steps, b.group)
        assert a.thickness == pytest.approx(b.thickness, rel=1e-12)
    for field in ("pitch_x", "pitch_y", "cd_x", "cd_y"):
        assert getattr(back.pattern, field) == pytest.approx(getattr(spec.pattern, field), rel=1e-12)
    assert back.illumination.wavelength == pytest.approx(spec.illumination.wavelength, rel=1e-12)
    assert back.numerics == spec.numerics


def test_documents_use_nanometres_and_survive_json():
    project = preset_project("euv-lines")
    data = json.loads(project.model_dump_json())

    assert data["format"] == "masksim-project" and data["version"] == 1
    assert data["layers"][0]["thickness_nm"] == 60.0
    assert data["pattern"]["pitch_x_nm"] == 128.0
    assert load_project(json.dumps(data)) == project
    assert project.to_spec().layers[0].thickness == pytest.approx(60 * NM)


def test_digest_tracks_physics_only():
    project = preset_project("euv-lines")
    renamed = project.model_copy(update={"name": "other"})
    recolored = project.model_copy(deep=True)
    recolored.materials[1].color = "#ff0000"
    thicker = project.model_copy(deep=True)
    thicker.layers[0].thickness_nm = 61.0

    assert project.digest() == renamed.digest() == recolored.digest()
    assert project.digest() != thicker.digest()


def test_loader_rejects_foreign_or_newer_documents():
    data = preset_project("euv-blank").model_dump(mode="json")

    with pytest.raises(ValueError, match="newer"):
        load_project({**data, "version": 2})
    with pytest.raises(ValueError, match="not a"):
        load_project({**data, "format": "something-else"})
    with pytest.raises(ValidationError):
        load_project({**data, "unexpected": 1})
    with pytest.raises(ValidationError):
        Project.model_validate({**data, "pattern": {**data["pattern"], "kind": "zigzag"}})
