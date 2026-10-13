"""Shared request helpers: job lookup, project checks, slice summaries."""
from __future__ import annotations

from typing import List, Optional, Tuple

from fastapi import HTTPException, Request

from masksim import NM, MaskSpec, Project, Slice, build_slices, validate
from rcwa import NearFieldSolution

from .jobs import Job, JobManager, JobNotFound
from .schemas import SliceInfo


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def checked_spec(project: Project) -> Tuple[MaskSpec, List[Slice]]:
    """The project's MaskSpec and slices, or HTTP 422 listing what is wrong with it."""
    spec = project.to_spec()
    errors = validate(spec)
    if not errors:
        try:
            return spec, build_slices(spec)
        except (ValueError, KeyError) as exc:
            errors = [str(exc)]
    raise HTTPException(status_code=422, detail={"errors": errors})


def pick_slice(slices: List[Slice], index: int) -> Slice:
    if not 0 <= index < len(slices):
        raise HTTPException(status_code=400, detail=f"slice index {index} out of range (0-{len(slices) - 1})")
    return slices[index]


def find_job(jobs: JobManager, job_id: str, kind: str) -> Job:
    try:
        job = jobs.get(job_id)
    except JobNotFound:
        raise HTTPException(status_code=404, detail=f"no {kind} {job_id!r} (finished jobs expire)") from None
    if job.kind != kind:
        raise HTTPException(status_code=404, detail=f"{job_id!r} is a {job.kind}, not a {kind}")
    return job


def finished_run(jobs: JobManager, run_id: str) -> Job:
    job = find_job(jobs, run_id, "run")
    if job.status != "done" or job.result is None:
        raise HTTPException(status_code=409, detail=f"run {run_id!r} is {job.status}")
    return job


def run_solution(job: Job, pol: Optional[str]) -> Tuple[str, NearFieldSolution]:
    solutions = job.result.solutions
    pol = pol or next(iter(solutions))
    if pol not in solutions:
        raise HTTPException(status_code=400, detail=f"run has no {pol} solution (has {', '.join(solutions)})")
    return pol, solutions[pol]


def slice_infos(slices: List[Slice]) -> List[SliceInfo]:
    return [
        SliceInfo(
            index=i, label=s.label, layer_name=s.layer_name, material=s.material, fill=s.fill,
            z_top_nm=s.z_top / NM, thickness_nm=s.thickness / NM, patterned=s.patterned,
            cd_x_nm=s.cd[0] / NM if s.cd else None, cd_y_nm=s.cd[1] / NM if s.cd else None,
        )
        for i, s in enumerate(slices)
    ]
