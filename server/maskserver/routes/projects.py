"""Presets and project validation."""
from __future__ import annotations

from typing import Annotated, Any, Dict, List

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from masksim import (
    NM,
    PRESET_IDS,
    PRESETS,
    Project,
    build_slices,
    load_project,
    preset_project,
    solver_settings,
    sweep_parameters,
)
from masksim import validate as validate_spec
from masksim.views import default_sweep_range

from ..deps import slice_infos
from ..schemas import CheckResult, PresetInfo, StackSummary, SweepParameter

router = APIRouter(tags=["projects"])


@router.get("/presets", response_model=List[PresetInfo])
def list_presets() -> List[PresetInfo]:
    return [PresetInfo(id=PRESET_IDS[name], name=name) for name in PRESETS]


@router.get("/presets/{preset_id}", response_model=Project)
def get_preset(preset_id: str) -> Project:
    try:
        return preset_project(preset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no preset {preset_id!r}") from None


@router.post("/project/normalize", response_model=Project)
def normalize_project(document: Annotated[Dict[str, Any], Body()]) -> Project:
    """Parse a saved project file: fill defaults and upgrade older versions.

    The UI sends every opened file through here, so it never has to know the defaults
    or the version history itself.
    """
    try:
        return load_project(document)
    except ValidationError as exc:
        errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise HTTPException(status_code=422, detail={"errors": errors}) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"errors": [str(exc)]}) from None


@router.post("/project/check", response_model=CheckResult)
def check_project(project: Project) -> CheckResult:
    """Validate a project and describe the slices the solver would receive.

    Domain problems (unknown materials, CD larger than the pitch, ...) come back as
    `errors`, not as an HTTP error, so the editor can show them while the user types.
    """
    digest = project.digest()
    spec = project.to_spec()
    errors = validate_spec(spec)
    if errors:
        return CheckResult(digest=digest, errors=errors)
    try:
        slices = build_slices(spec)
    except (ValueError, KeyError) as exc:
        return CheckResult(digest=digest, errors=[str(exc)])

    lattice, settings = solver_settings(spec, slices)
    harmonics = (2 * settings.Nx + 1) * (2 * settings.Ny + 1)
    if settings.Nx and settings.Ny:
        axes = "xy"
    elif settings.Nx or settings.Ny:
        axes = "x" if settings.Nx else "y"
    else:
        axes = "none"
    summary = StackSummary(
        total_thickness_nm=slices[-1].z_bottom / NM,
        slice_count=len(slices),
        patterned_slice_count=sum(s.patterned for s in slices),
        unit_cell_nm=[lattice.Lx / NM, lattice.Ly / NM],
        periodic_axes=axes,
        harmonics=harmonics,
        matrix_size=2 * harmonics,
        grid=[settings.grid_Nx, settings.grid_Ny],
        polarizations=list(spec.polarizations()),
    )
    parameters = []
    for key, label in sweep_parameters(spec).items():
        start, stop, points = default_sweep_range(key, spec)
        parameters.append(SweepParameter(key=key, label=label, start=start, stop=stop, points=points))
    return CheckResult(digest=digest, errors=[], summary=summary, slices=slice_infos(slices),
                       sweep_parameters=parameters)
