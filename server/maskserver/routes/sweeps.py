"""Parameter sweeps: one solve per value and polarization, streamed as records."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from masksim import sweep_parameters, validate, with_parameter
from masksim.views import sweep_values

from ..deps import AppSettings, checked_spec, find_job, get_jobs, require_memory
from ..jobs import JobManager
from ..schemas import JobInfo, SweepRecord, SweepRequest, SweepResult

router = APIRouter(tags=["sweeps"])
Jobs = Annotated[JobManager, Depends(get_jobs)]


@router.post("/sweeps", response_model=JobInfo, status_code=202)
def submit_sweep(req: SweepRequest, jobs: Jobs, settings: AppSettings) -> dict:
    """Start a sweep; records also arrive live as `sweep-records` events on /api/events.

    Every point is validated up front (a harmonics sweep must respect the same limits as a run).
    """
    spec, _ = checked_spec(req.project)
    labels = sweep_parameters(spec)
    if req.parameter not in labels:
        raise HTTPException(status_code=422, detail={"errors": [f"cannot sweep {req.parameter!r} for this project"]})
    values = sweep_values(req.parameter, req.start, req.stop, req.points)
    points = [with_parameter(spec, req.parameter, value) for value in values]
    for value, point in zip(values, points, strict=True):
        errors = validate(point)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": [
                f"{labels[req.parameter]} = {value:g}: {error}" for error in errors
            ]})
    require_memory(points, settings)
    return jobs.submit_sweep(req.project, req.parameter, values).info()


@router.get("/sweeps/{sweep_id}", response_model=SweepResult)
def get_sweep(sweep_id: str, jobs: Jobs) -> SweepResult:
    job = find_job(jobs, sweep_id, "sweep")
    parameter = job.params["parameter"]
    labels = sweep_parameters(job.project.to_spec())
    return SweepResult(job=JobInfo(**job.info()), parameter=parameter, label=labels.get(parameter, parameter),
                       records=[SweepRecord(**r) for r in list(job.records)])


@router.delete("/sweeps/{sweep_id}", response_model=JobInfo)
def delete_sweep(sweep_id: str, jobs: Jobs) -> dict:
    """Cancel a queued or running sweep; forget a finished one."""
    info = find_job(jobs, sweep_id, "sweep").info()
    jobs.remove(sweep_id)
    return info
