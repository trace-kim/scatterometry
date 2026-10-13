"""Solver runs: submission, status, cancellation, and every result view of a finished run."""
from __future__ import annotations

from typing import Annotated, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, Query, Response

from masksim import NM, Project, views

from ..arrays import NPZ_RESPONSES, as_complex64, as_index, nm, npz_response
from ..deps import checked_spec, find_job, finished_run, get_jobs, pick_slice, run_solution, slice_infos
from ..jobs import JobManager
from ..schemas import (
    AbsorptionResponse,
    FluxResponse,
    JobInfo,
    LayerAbsorption,
    ModesResponse,
    OrderRow,
    OrdersResponse,
    Polarization,
    PupilResponse,
    RunRequest,
    SectionParams,
    SliceInfo,
)

router = APIRouter(tags=["runs"])
Jobs = Annotated[JobManager, Depends(get_jobs)]
Pol = Annotated[Optional[Polarization], Query(description="Defaults to the run's first polarization")]


class FieldSectionParams(SectionParams):
    pol: Optional[Polarization] = None


@router.post("/runs", response_model=JobInfo, status_code=202)
def submit_run(req: RunRequest, jobs: Jobs) -> dict:
    checked_spec(req.project)
    return jobs.submit_run(req.project, crosscheck=req.crosscheck).info()


@router.get("/runs", response_model=List[JobInfo])
def list_runs(jobs: Jobs) -> List[dict]:
    return [job.info() for job in jobs.list("run")]


@router.get("/runs/{run_id}", response_model=JobInfo)
def get_run(run_id: str, jobs: Jobs) -> dict:
    return find_job(jobs, run_id, "run").info()


@router.delete("/runs/{run_id}", response_model=JobInfo)
def delete_run(run_id: str, jobs: Jobs) -> dict:
    """Cancel a queued or running run; forget a finished one."""
    job = find_job(jobs, run_id, "run")
    info = job.info()
    jobs.remove(run_id)
    return info


@router.get("/runs/{run_id}/project", response_model=Project)
def run_project(run_id: str, jobs: Jobs) -> Project:
    return find_job(jobs, run_id, "run").project


@router.get("/runs/{run_id}/slices", response_model=List[SliceInfo])
def run_slices(run_id: str, jobs: Jobs) -> List[SliceInfo]:
    return slice_infos(finished_run(jobs, run_id).result.slices)


@router.get("/runs/{run_id}/orders", response_model=OrdersResponse)
def run_orders(run_id: str, jobs: Jobs, pol: Pol = None) -> OrdersResponse:
    pol, sol = run_solution(finished_run(jobs, run_id), pol)
    return OrdersResponse(pol=pol, orders=[OrderRow(**row) for row in views.order_records(sol)])


@router.get("/runs/{run_id}/pupil", response_model=PupilResponse)
def run_pupil(run_id: str, jobs: Jobs, pol: Pol = None,
              na: Annotated[float, Query(ge=0, le=2, description="Wafer-side NA; 0 = none")] = 0.0,
              reduction: Annotated[float, Query(gt=0)] = 4.0) -> PupilResponse:
    job = finished_run(jobs, run_id)
    pol, sol = run_solution(job, pol)
    n_ref = views.incident_index(job.result.spec)
    na_mask = na / reduction if na > 0 else None
    captured = views.captured_power(sol, n_ref, na_mask) if na_mask else None
    return PupilResponse(pol=pol, n_ref=n_ref, na_mask=na_mask, captured=captured, **views.pupil_points(sol, n_ref))


@router.get("/runs/{run_id}/flux", response_model=FluxResponse)
def run_flux(run_id: str, jobs: Jobs, pol: Pol = None, z_min_nm: Optional[float] = None,
             z_max_nm: Optional[float] = None, n: Annotated[int, Query(ge=2, le=4000)] = 600) -> FluxResponse:
    """Net downward power through a unit cell vs depth (1 = incident)."""
    job = finished_run(jobs, run_id)
    pol, sol = run_solution(job, pol)
    slices = job.result.slices
    z0 = -20 * NM if z_min_nm is None else z_min_nm * NM
    z1 = slices[-1].z_bottom + 20 * NM if z_max_nm is None else z_max_nm * NM
    z = np.linspace(z0, z1, n)
    interfaces = sorted({s.z_top for s in slices if z0 <= s.z_top <= z1 and (s.patterned or s.step == 0)})
    return FluxResponse(pol=pol, z_nm=nm(z).tolist(), flux=sol.power_flux(z).tolist(),
                        interfaces_nm=[v / NM for v in interfaces])


@router.get("/runs/{run_id}/absorption", response_model=AbsorptionResponse)
def run_absorption(run_id: str, jobs: Jobs, pol: Pol = None) -> AbsorptionResponse:
    """Absorbed fraction of the incident power per named layer, plus R, T, A totals."""
    job = finished_run(jobs, run_id)
    pol, sol = run_solution(job, pol)
    power = sol.result["power"]
    layers = [LayerAbsorption(name=k, absorbed=v) for k, v in views.absorption_by_layer(sol, job.result.slices).items()]
    return AbsorptionResponse(pol=pol, layers=layers, R=power["R_total"], T=power["T_total"], A=power["A_total"])


@router.get("/runs/{run_id}/modes", response_model=ModesResponse)
def run_modes(run_id: str, jobs: Jobs, slice: Annotated[int, Query(ge=0)] = 0, pol: Pol = None) -> ModesResponse:
    """Eigenmode propagation constants kz/k0 of one slice."""
    job = finished_run(jobs, run_id)
    pol, sol = run_solution(job, pol)
    s = pick_slice(job.result.slices, slice)
    kz = views.mode_kz(sol, slice)
    return ModesResponse(pol=pol, slice=slice, label=s.label, kz_re=kz.real.tolist(), kz_im=kz.imag.tolist())


@router.get("/runs/{run_id}/field/section", response_class=Response, responses=NPZ_RESPONSES)
def run_field_section(run_id: str, jobs: Jobs, params: Annotated[FieldSectionParams, Query()]) -> Response:
    """E field on an x-z or y-z cross-section (incident amplitude 1).

    NPZ: `Ex`, `Ey`, `Ez` (complex64, n_z x n_lateral), `material` (uint8 map for boundaries),
    `lateral_nm`, `z_nm`.
    """
    job = finished_run(jobs, run_id)
    pol, sol = run_solution(job, params.pol)
    spec, slices = job.result.spec, job.result.slices
    lateral, z = views.section_axes(spec, params.axis, params.periods, params.z_min_nm * NM, params.z_max_nm * NM,
                                    params.n_lateral, params.n_z)
    amplitudes = job.cached(("amplitudes", pol, params.z_min_nm, params.z_max_nm, params.n_z),
                            lambda: sol.amplitudes(z))
    E = views.field_section(sol, params.axis, params.offset_nm * NM, lateral, z, amplitudes)
    index = views.section_index(spec, slices, params.axis, params.offset_nm * NM, lateral, z)
    return npz_response(Ex=as_complex64(E["x"]), Ey=as_complex64(E["y"]), Ez=as_complex64(E["z"]),
                        material=as_index(index), lateral_nm=nm(lateral), z_nm=nm(z))


@router.get("/runs/{run_id}/field/plane", response_class=Response, responses=NPZ_RESPONSES)
def run_field_plane(run_id: str, jobs: Jobs, depth_nm: float, pol: Pol = None,
                    periods: Annotated[float, Query(gt=0, le=8)] = 2.0,
                    n: Annotated[int, Query(ge=8, le=1024)] = 200) -> Response:
    """E field on an x-y plane at `depth_nm` (negative = above the mask).

    NPZ: `Ex`, `Ey`, `Ez` (complex64, n x n; rows follow y), `material` (uint8), `x_nm`, `y_nm`.
    """
    job = finished_run(jobs, run_id)
    _, sol = run_solution(job, pol)
    spec, slices = job.result.spec, job.result.slices
    xs, ys = views.plane_axes(spec, periods, n)
    depth = depth_nm * NM
    E = views.field_plane(sol, xs, ys, depth)
    s = views.slice_at(slices, depth)
    if s is not None:
        index = views.plane_index(spec, s, xs, ys)
    else:
        medium = spec.superstrate if depth < 0 else spec.substrate
        index = np.full((ys.size, xs.size), views.material_names(spec).index(medium))
    return npz_response(Ex=as_complex64(E["x"]), Ey=as_complex64(E["y"]), Ez=as_complex64(E["z"]),
                        material=as_index(index), x_nm=nm(xs), y_nm=nm(ys))
