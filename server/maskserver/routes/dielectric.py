"""Permittivity as the geometry defines it and as the truncated Fourier series RCWA uses."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Response

from masksim import NM, views

from ..arrays import NPZ_RESPONSES, as_complex64, nm, npz_response
from ..deps import checked_spec, pick_slice
from ..schemas import DielectricPlaneRequest, DielectricSectionRequest, SliceRequest

router = APIRouter(tags=["dielectric"])


@router.post("/dielectric/section", response_class=Response, responses=NPZ_RESPONSES)
def dielectric_section(req: DielectricSectionRequest) -> Response:
    """Complex permittivity on a cross-section (Fourier-truncated in patterned slices if `fourier`).

    NPZ: `eps` (complex64, n_z x n_lateral), `lateral_nm`, `z_nm`.
    """
    spec, slices = checked_spec(req.project)
    lateral, z = views.section_axes(spec, req.axis, req.periods, req.z_min_nm * NM, req.z_max_nm * NM,
                                    req.n_lateral, req.n_z)
    eps = views.eps_section(spec, slices, req.axis, req.offset_nm * NM, lateral, z, req.fourier)
    return npz_response(eps=as_complex64(eps), lateral_nm=nm(lateral), z_nm=nm(z))


@router.post("/dielectric/plane", response_class=Response, responses=NPZ_RESPONSES)
def dielectric_plane(req: DielectricPlaneRequest) -> Response:
    """Complex permittivity of one slice seen from above.

    NPZ: `eps` (complex64, n x n; rows follow y), `x_nm`, `y_nm`.
    """
    spec, slices = checked_spec(req.project)
    s = pick_slice(slices, req.slice)
    xs, ys = views.plane_axes(spec, req.periods, req.n)
    return npz_response(eps=as_complex64(views.eps_plane(spec, slices, s, xs, ys, req.fourier)),
                        x_nm=nm(xs), y_nm=nm(ys))


@router.post("/dielectric/convolution", response_class=Response, responses=NPZ_RESPONSES)
def dielectric_convolution(req: SliceRequest) -> Response:
    """The slice's convolution (Toeplitz) matrix [eps].

    NPZ: `matrix` (complex64, Nh x Nh), `mx`, `my` (int16 harmonic indices of rows/columns).
    """
    spec, slices = checked_spec(req.project)
    matrix, mx, my = views.convolution_matrix(spec, slices, pick_slice(slices, req.slice))
    return npz_response(matrix=as_complex64(matrix), mx=np.asarray(mx, dtype=np.int16),
                        my=np.asarray(my, dtype=np.int16))
