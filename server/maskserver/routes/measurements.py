"""Measurement files: upload (raw body), metadata, frames as arrays, per-frame statistics."""
from __future__ import annotations

from typing import Annotated, List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool

from masksim.spe import SpeError, SpeRegion, read_spe

from ..arrays import NPZ_RESPONSES, npz_response
from ..measurements import Measurement, MeasurementNotFound, MeasurementStore
from ..schemas import MeasurementInfo, MeasurementRegion, MeasurementTrace, SettingRow

router = APIRouter(tags=["measurements"])


def get_store(request: Request) -> MeasurementStore:
    return request.app.state.measurements


Store = Annotated[MeasurementStore, Depends(get_store)]


def find(store: MeasurementStore, measurement_id: str) -> Measurement:
    try:
        return store.get(measurement_id)
    except MeasurementNotFound:
        raise HTTPException(status_code=404, detail=f"no measurement {measurement_id!r} (uploads expire)") from None


def pick_region(item: Measurement, index: int) -> SpeRegion:
    regions = item.spe.regions
    if not 0 <= index < len(regions):
        raise HTTPException(status_code=400, detail=f"region {index} out of range (0-{len(regions) - 1})")
    return regions[index]


def info(item: Measurement) -> MeasurementInfo:
    spe = item.spe
    return MeasurementInfo(
        id=item.id, name=item.name, format="spe", version=spe.version, size_bytes=item.size_bytes,
        created=item.created, dtype=spe.dtype.name, frames=spe.n_frames,
        regions=[MeasurementRegion(index=i, width=r.width, height=r.height, x=r.x, y=r.y, x_binning=r.x_binning,
                                   y_binning=r.y_binning) for i, r in enumerate(spe.regions)],
        sensor=list(spe.sensor) if spe.sensor else None, summary=spe.summary, warnings=spe.warnings,
        timestamp_events=list(spe.timestamps), setting_count=len(spe.settings),
    )


@router.post(
    "/measurements", response_model=MeasurementInfo, status_code=201,
    openapi_extra={"requestBody": {"required": True, "content": {"application/octet-stream": {
        "schema": {"type": "string", "format": "binary"}}}}},
)
async def upload_measurement(request: Request, store: Store,
                             name: Annotated[str, Query(max_length=255)] = "measurement.spe") -> MeasurementInfo:
    """Upload an SPE file as the raw request body (up to MASKSIM_MAX_UPLOAD_MB)."""
    body = await request.body()
    try:
        spe = await run_in_threadpool(read_spe, body)
    except SpeError as exc:
        raise HTTPException(status_code=422, detail={"errors": [f"{name}: {exc}"]}) from None
    return info(store.add(name, spe, len(body)))


@router.get("/measurements", response_model=List[MeasurementInfo])
def list_measurements(store: Store) -> List[MeasurementInfo]:
    return [info(item) for item in store.list()]


@router.get("/measurements/{measurement_id}", response_model=MeasurementInfo)
def get_measurement(measurement_id: str, store: Store) -> MeasurementInfo:
    return info(find(store, measurement_id))


@router.delete("/measurements/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: str, store: Store) -> Response:
    try:
        store.remove(measurement_id)
    except MeasurementNotFound:
        raise HTTPException(status_code=404, detail=f"no measurement {measurement_id!r}") from None
    return Response(status_code=204)


@router.get("/measurements/{measurement_id}/settings", response_model=List[SettingRow])
def measurement_settings(measurement_id: str, store: Store) -> List[SettingRow]:
    """Every acquisition setting the file records, as (path, value) rows."""
    return [SettingRow(path=p, value=v) for p, v in find(store, measurement_id).spe.settings]


@router.get("/measurements/{measurement_id}/frame", response_class=Response, responses=NPZ_RESPONSES)
def measurement_frame(
    measurement_id: str, store: Store,
    region: Annotated[int, Query(ge=0)] = 0,
    index: Annotated[int, Query(ge=0)] = 0,
    average: bool = False,
) -> Response:
    """One frame of a region, or the mean of all its frames (`average`).

    NPZ: `counts` (height x width, the file's pixel type; float32 for averages; row 0 is
    the first row read out), `x_px`, `y_px` (pixel centres in sensor pixels).
    """
    item = find(store, measurement_id)
    r = pick_region(item, region)
    if average:
        counts = item.cached(("mean", region), lambda: r.data.mean(axis=0, dtype=np.float64).astype(np.float32))
    elif index >= item.spe.n_frames:
        raise HTTPException(status_code=400, detail=f"frame {index} out of range (0-{item.spe.n_frames - 1})")
    else:
        counts = np.ascontiguousarray(r.data[index])
    xs, ys = r.pixel_axes()
    return npz_response(counts=counts, x_px=xs.astype(np.float64), y_px=ys.astype(np.float64))


@router.get("/measurements/{measurement_id}/trace", response_model=MeasurementTrace)
def measurement_trace(measurement_id: str, store: Store, region: Annotated[int, Query(ge=0)] = 0) -> MeasurementTrace:
    """Total and peak counts of every frame of a region (with time stamps when recorded)."""
    item = find(store, measurement_id)
    r = pick_region(item, region)

    def compute() -> MeasurementTrace:
        flat = r.data.reshape(r.data.shape[0], -1)
        spe = item.spe
        time_s = None
        if spe.timestamps:
            stamps = next(iter(spe.timestamps.values()))
            time_s = (stamps - stamps[0]).tolist()
        return MeasurementTrace(
            region=region, frame=list(range(flat.shape[0])), total=flat.sum(axis=1, dtype=np.float64).tolist(),
            max=flat.max(axis=1).astype(np.float64).tolist(), time_s=time_s,
            frame_numbers=spe.frame_numbers.tolist() if spe.frame_numbers is not None else None,
        )

    return item.cached(("trace", region), compute)
