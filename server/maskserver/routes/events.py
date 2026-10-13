"""Job list and the Server-Sent-Events stream the UI uses for live progress."""
from __future__ import annotations

import json
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..deps import get_jobs
from ..jobs import JobManager, JobNotFound
from ..schemas import JobInfo

router = APIRouter(tags=["events"])


@router.get("/jobs", response_model=List[JobInfo])
def list_jobs(jobs: Annotated[JobManager, Depends(get_jobs)]) -> List[dict]:
    return [job.info() for job in jobs.list()]


@router.get("/jobs/{job_id}", response_model=JobInfo)
def get_job(job_id: str, jobs: Annotated[JobManager, Depends(get_jobs)]) -> dict:
    """Status of a run or sweep by id."""
    try:
        return jobs.get(job_id).info()
    except JobNotFound:
        raise HTTPException(status_code=404, detail=f"no job {job_id!r} (finished jobs expire)") from None


@router.get("/events")
async def events(request: Request) -> EventSourceResponse:
    """SSE stream. Event types:

    - `snapshot`: {jobs: JobInfo[]} once on connect (resync after reconnects)
    - `job`: {job: JobInfo} on every status change and at most 10x/s while running
    - `sweep-records`: {job_id, records: SweepRecord[]} after each sweep value
    """
    broker = request.app.state.broker
    jobs: JobManager = request.app.state.jobs
    queue = broker.subscribe()

    async def stream():
        try:
            yield {"event": "snapshot", "data": json.dumps({"jobs": [job.info() for job in jobs.list()]})}
            while True:
                event = await queue.get()
                yield {"event": event["type"], "data": json.dumps(event)}
        finally:
            broker.unsubscribe(queue)

    return EventSourceResponse(stream(), ping=15)
