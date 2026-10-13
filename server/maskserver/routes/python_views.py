"""Python-defined views (see maskserver.python_views)."""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from masksim import Project

from ..deps import checked_spec, finished_run, get_jobs, run_solution
from ..jobs import JobManager
from ..python_views import REGISTRY, ViewContext
from ..schemas import Polarization

router = APIRouter(tags=["python views"])


class PythonViewInfo(BaseModel):
    id: str
    title: str
    description: str
    needs: str


class PythonViewRequest(BaseModel):
    project: Project
    run_id: Optional[str] = None
    pol: Optional[Polarization] = None


class PythonViewResult(BaseModel):
    option: Dict[str, Any]


@router.get("/python-views", response_model=List[PythonViewInfo])
def list_python_views() -> List[PythonViewInfo]:
    return [PythonViewInfo(id=v.id, title=v.title, description=v.description, needs=v.needs) for v in REGISTRY.values()]


@router.post("/python-views/{view_id}", response_model=PythonViewResult)
def evaluate_python_view(view_id: str, req: PythonViewRequest,
                         jobs: Annotated[JobManager, Depends(get_jobs)]) -> PythonViewResult:
    """Evaluate a view; "run" views use the given run (its own project, not `project`)."""
    view = REGISTRY.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"no Python view {view_id!r}")
    if view.needs == "run":
        if not req.run_id:
            raise HTTPException(status_code=409, detail="this view needs a finished run")
        job = finished_run(jobs, req.run_id)
        pol, solution = run_solution(job, req.pol)
        ctx = ViewContext(job.project, job.result.spec, job.result.slices, pol, solution)
    else:
        spec, slices = checked_spec(req.project)
        ctx = ViewContext(req.project, spec, slices, req.pol)
    try:
        return PythonViewResult(option=view.build(ctx))
    except Exception as exc:  # a broken user view should not look like a server crash
        raise HTTPException(status_code=500, detail=f"view {view_id!r} failed: {type(exc).__name__}: {exc}") from exc
