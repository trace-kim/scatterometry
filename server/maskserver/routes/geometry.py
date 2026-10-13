"""Stack geometry: material maps of cross-sections and slices, and 3D boxes."""
from __future__ import annotations

from fastapi import APIRouter, Response

from masksim import NM, unit_cell, views

from ..arrays import NPZ_RESPONSES, as_index, nm, npz_response
from ..deps import checked_spec, pick_slice
from ..schemas import BoxesRequest, BoxesResponse, PlaneRequest, SectionRequest

router = APIRouter(tags=["geometry"])


@router.post("/geometry/section", response_class=Response, responses=NPZ_RESPONSES)
def geometry_section(req: SectionRequest) -> Response:
    """Material map of an x-z or y-z cross-section.

    NPZ: `material` (uint8, n_z x n_lateral, index into project.materials), `lateral_nm`, `z_nm`.
    """
    spec, slices = checked_spec(req.project)
    lateral, z = views.section_axes(spec, req.axis, req.periods, req.z_min_nm * NM, req.z_max_nm * NM,
                                    req.n_lateral, req.n_z)
    index = views.section_index(spec, slices, req.axis, req.offset_nm * NM, lateral, z)
    return npz_response(material=as_index(index), lateral_nm=nm(lateral), z_nm=nm(z))


@router.post("/geometry/plane", response_class=Response, responses=NPZ_RESPONSES)
def geometry_plane(req: PlaneRequest) -> Response:
    """Material map of one slice seen from above.

    NPZ: `material` (uint8, n x n; rows follow y), `x_nm`, `y_nm`.
    """
    spec, slices = checked_spec(req.project)
    s = pick_slice(slices, req.slice)
    xs, ys = views.plane_axes(spec, req.periods, req.n)
    return npz_response(material=as_index(views.plane_index(spec, s, xs, ys)), x_nm=nm(xs), y_nm=nm(ys))


@router.post("/geometry/boxes", response_model=BoxesResponse)
def geometry_boxes(req: BoxesRequest) -> BoxesResponse:
    """Boxes tiling the stack down to z_max_nm (default: the whole stack) for the 3D view."""
    spec, slices = checked_spec(req.project)
    z_max = slices[-1].z_bottom if req.z_max_nm is None else req.z_max_nm * NM
    names = views.material_names(spec)
    boxes = [[float(names.index(material))] + [v / NM for v in box]
             for material, *box in views.stack_boxes(spec, slices, req.periods, z_max, req.n)]
    Lx, Ly = unit_cell(spec.pattern)
    return BoxesResponse(materials=names, boxes=boxes,
                         size_nm=[req.periods * Lx / NM, req.periods * Ly / NM, min(z_max, slices[-1].z_bottom) / NM])
