"""Request and response models of the HTTP API (lengths in nm, angles in degrees).

Array-valued responses are .npz archives (see arrays.py); their contents are listed in
each endpoint's docstring. Everything here ends up in the OpenAPI schema that the web
client's TypeScript types are generated from.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from masksim import Project

Axis = Literal["x", "y"]
Polarization = Literal["TE", "TM"]


# ---- projects ---------------------------------------------------------------------


class PresetInfo(BaseModel):
    id: str
    name: str


class SliceInfo(BaseModel):
    index: int
    label: str
    layer_name: str
    material: str
    fill: str
    z_top_nm: float
    thickness_nm: float
    patterned: bool
    cd_x_nm: Optional[float] = None
    cd_y_nm: Optional[float] = None


class SweepParameter(BaseModel):
    key: str
    label: str
    start: float
    stop: float
    points: int


class StackSummary(BaseModel):
    total_thickness_nm: float
    slice_count: int
    patterned_slice_count: int
    unit_cell_nm: List[float]
    periodic_axes: Literal["none", "x", "y", "xy"]
    harmonics: int
    matrix_size: int
    grid: List[int]
    polarizations: List[Polarization]


class CheckResult(BaseModel):
    """Validation of a project plus everything the stack editor shows about it."""
    digest: str
    errors: List[str]
    summary: Optional[StackSummary] = None
    slices: List[SliceInfo] = []
    sweep_parameters: List[SweepParameter] = []


# ---- view requests (project-based) --------------------------------------------------------


class SectionParams(BaseModel):
    axis: Axis = "x"
    offset_nm: float = 0.0
    periods: float = Field(2.0, gt=0, le=8)
    z_min_nm: float = -20.0
    z_max_nm: float = 100.0
    n_lateral: int = Field(400, ge=8, le=2048)
    n_z: int = Field(400, ge=8, le=4096)


class SectionRequest(SectionParams):
    project: Project


class DielectricSectionRequest(SectionRequest):
    fourier: bool = False


class PlaneRequest(BaseModel):
    project: Project
    slice: int = Field(0, ge=0)
    periods: float = Field(2.0, gt=0, le=8)
    n: int = Field(200, ge=8, le=1024)


class DielectricPlaneRequest(PlaneRequest):
    fourier: bool = False


class SliceRequest(BaseModel):
    project: Project
    slice: int = Field(0, ge=0)


class BoxesRequest(BaseModel):
    project: Project
    periods: float = Field(2.0, gt=0, le=8)
    z_max_nm: Optional[float] = None
    n: int = Field(160, ge=8, le=512)


class BoxesResponse(BaseModel):
    """Axis-aligned boxes [material index, x0, x1, y0, y1, z0, z1] in nm; clear materials omitted."""
    materials: List[str]
    boxes: List[List[float]]
    size_nm: List[float]


# ---- jobs ---------------------------------------------------------------------------------


class RunRequest(BaseModel):
    project: Project
    crosscheck: bool = False


class SweepRequest(BaseModel):
    project: Project
    parameter: str
    start: float
    stop: float
    points: int = Field(11, ge=1, le=401)


class JobInfo(BaseModel):
    id: str
    kind: Literal["run", "sweep"]
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: float
    message: str
    error: Optional[str] = None
    created: float
    started: Optional[float] = None
    finished: Optional[float] = None
    project_digest: str
    params: Dict[str, Any] = {}
    summary: Optional[Dict[str, Any]] = None
    check: Optional[Dict[str, Any]] = None
    record_count: Optional[int] = None


class SweepRecord(BaseModel):
    value: float
    pol: Polarization
    m: Optional[int] = None
    n: Optional[int] = None
    R: float
    phase_deg: Optional[float] = None


class SweepResult(BaseModel):
    job: JobInfo
    parameter: str
    label: str
    records: List[SweepRecord]


# ---- run results ----------------------------------------------------------------------------


class OrderRow(BaseModel):
    m: int
    n: int
    r_theta_deg: Optional[float] = None
    r_phi_deg: Optional[float] = None
    R: float
    T: float
    r_te_abs: Optional[float] = None
    r_te_phase_deg: Optional[float] = None
    r_tm_abs: Optional[float] = None
    r_tm_phase_deg: Optional[float] = None
    r_propagating: bool
    t_propagating: bool


class OrdersResponse(BaseModel):
    pol: Polarization
    orders: List[OrderRow]


class PupilResponse(BaseModel):
    """Propagating reflected orders in direction-cosine space (kx, ky)/(k0 n_incident)."""
    pol: Polarization
    n_ref: float
    basis: Polarization
    m: List[int]
    n: List[int]
    sx: List[float]
    sy: List[float]
    R: List[float]
    phase_deg: List[Optional[float]]
    center: List[float]
    na_mask: Optional[float] = None
    captured: Optional[float] = None


class FluxResponse(BaseModel):
    pol: Polarization
    z_nm: List[float]
    flux: List[float]
    interfaces_nm: List[float]


class LayerAbsorption(BaseModel):
    name: str
    absorbed: float


class AbsorptionResponse(BaseModel):
    pol: Polarization
    layers: List[LayerAbsorption]
    R: float
    T: float
    A: float


class ModesResponse(BaseModel):
    pol: Polarization
    slice: int
    label: str
    kz_re: List[float]
    kz_im: List[float]


# ---- measurements ---------------------------------------------------------------------------


class MeasurementRegion(BaseModel):
    """A region of interest; x, y (0-based sensor pixels) and binning locate it on the sensor."""
    index: int
    width: int
    height: int
    x: int
    y: int
    x_binning: int
    y_binning: int


class MeasurementInfo(BaseModel):
    id: str
    name: str
    format: Literal["spe"]
    version: float
    size_bytes: int
    created: float
    dtype: str
    frames: int
    regions: List[MeasurementRegion]
    sensor: Optional[List[int]] = None
    summary: Dict[str, Any] = {}
    warnings: List[str] = []
    timestamp_events: List[str] = []
    setting_count: int


class SettingRow(BaseModel):
    path: str
    value: str


class MeasurementTrace(BaseModel):
    """Per-frame statistics of one region; `time_s` is the first time stamp event, relative to frame 0."""
    region: int
    frame: List[int]
    total: List[float]
    max: List[float]
    time_s: Optional[List[float]] = None
    frame_numbers: Optional[List[int]] = None
