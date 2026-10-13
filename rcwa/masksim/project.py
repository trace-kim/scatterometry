"""Versioned, JSON-friendly project documents (lengths in nm, angles in degrees).

A Project is what the web UI edits, saves, and sends to the server. `to_spec()`
converts it to the SI-unit MaskSpec used by the solver layer, so internal refactors of
the dataclasses never change the file format. Saved files carry `format` and
`version`; `load_project()` is where upgrades from older versions belong.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .presets import PRESETS
from .stack import NM, Illumination, LayerSpec, MaskSpec, Material, Numerics, PatternSpec

FORMAT = "masksim-project"
VERSION = 1

PatternKind = Literal["none", "ls_v", "ls_h", "ch_square", "ch_staggered"]


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterialDoc(_Doc):
    name: str
    n: float
    k: float = 0.0
    color: Optional[str] = None  # display only; not part of the physics


class LayerDoc(_Doc):
    name: str
    material: str
    thickness_nm: float
    patterned: bool = False
    swa_deg: float = 90.0
    steps: int = 1
    group: str = ""


class PatternDoc(_Doc):
    kind: PatternKind = "ls_v"
    pitch_x_nm: float = 128.0
    pitch_y_nm: float = 128.0
    cd_x_nm: float = 64.0
    cd_y_nm: float = 64.0
    hole_shape: Literal["rect", "ellipse"] = "rect"
    tone: Literal["holes", "pillars"] = "holes"
    fill: str = "Vacuum"
    cd_reference: Literal["top", "middle", "bottom"] = "top"


class IlluminationDoc(_Doc):
    wavelength_nm: float = 13.5
    theta_deg: float = 6.0
    phi_deg: float = 0.0
    polarization: Literal["TE", "TM", "TE+TM"] = "TE"


class NumericsDoc(_Doc):
    nx: int = 15
    ny: int = 15
    grid: int = 0


class Project(_Doc):
    format: Literal["masksim-project"] = FORMAT
    version: Literal[1] = VERSION
    name: str = "Untitled"
    materials: List[MaterialDoc]
    superstrate: str
    substrate: str
    layers: List[LayerDoc]
    repeats: Dict[str, int] = Field(default_factory=dict)
    pattern: PatternDoc = Field(default_factory=PatternDoc)
    illumination: IlluminationDoc = Field(default_factory=IlluminationDoc)
    numerics: NumericsDoc = Field(default_factory=NumericsDoc)

    def to_spec(self) -> MaskSpec:
        p, ill, num = self.pattern, self.illumination, self.numerics
        return MaskSpec(
            materials=tuple(Material(m.name, m.n, m.k) for m in self.materials),
            superstrate=self.superstrate,
            substrate=self.substrate,
            layers=tuple(
                LayerSpec(l.name, l.material, l.thickness_nm * NM, l.patterned, l.swa_deg, l.steps, l.group.strip())
                for l in self.layers
            ),
            repeats=tuple((group, int(count)) for group, count in self.repeats.items()),
            pattern=PatternSpec(
                kind=p.kind, pitch_x=p.pitch_x_nm * NM, pitch_y=p.pitch_y_nm * NM, cd_x=p.cd_x_nm * NM,
                cd_y=p.cd_y_nm * NM, hole_shape=p.hole_shape, tone=p.tone, fill=p.fill,
                cd_reference=p.cd_reference,
            ),
            illumination=Illumination(wavelength=ill.wavelength_nm * NM, theta_deg=ill.theta_deg,
                                      phi_deg=ill.phi_deg, polarization=ill.polarization),
            numerics=Numerics(nx=num.nx, ny=num.ny, grid=num.grid),
        )

    @classmethod
    def from_spec(cls, spec: MaskSpec, name: str = "Untitled") -> "Project":
        p, ill, num = spec.pattern, spec.illumination, spec.numerics
        return cls(
            name=name,
            materials=[MaterialDoc(name=m.name, n=m.n, k=m.k) for m in spec.materials],
            superstrate=spec.superstrate,
            substrate=spec.substrate,
            layers=[
                LayerDoc(name=l.name, material=l.material, thickness_nm=_nm(l.thickness), patterned=l.patterned,
                         swa_deg=l.swa_deg, steps=l.steps, group=l.group)
                for l in spec.layers
            ],
            repeats=dict(spec.repeats),
            pattern=PatternDoc(
                kind=p.kind, pitch_x_nm=_nm(p.pitch_x), pitch_y_nm=_nm(p.pitch_y), cd_x_nm=_nm(p.cd_x),
                cd_y_nm=_nm(p.cd_y), hole_shape=p.hole_shape, tone=p.tone, fill=p.fill, cd_reference=p.cd_reference,
            ),
            illumination=IlluminationDoc(wavelength_nm=_nm(ill.wavelength), theta_deg=ill.theta_deg,
                                         phi_deg=ill.phi_deg, polarization=ill.polarization),
            numerics=NumericsDoc(nx=num.nx, ny=num.ny, grid=num.grid),
        )

    def digest(self) -> str:
        """Hash of everything that affects the physics (not the name or display colors)."""
        physics = self.model_dump(mode="json", exclude={"name": True, "materials": {"__all__": {"color"}}})
        return hashlib.sha256(json.dumps(physics, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def _nm(meters: float) -> float:
    return round(meters / NM, 9)


def load_project(data: Union[str, bytes, Dict[str, Any]]) -> Project:
    """Parse a saved project document, upgrading older versions (none exist yet)."""
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    if data.get("format", FORMAT) != FORMAT:
        raise ValueError(f"not a {FORMAT} document")
    if data.get("version", VERSION) > VERSION:
        raise ValueError(f"project version {data['version']} is newer than this software ({VERSION})")
    return Project.model_validate(data)


PRESET_IDS: Dict[str, str] = {name: factory.__name__.replace("_", "-") for name, factory in PRESETS.items()}


def preset_project(preset_id: str) -> Project:
    """Built-in preset as a project document; ids are the factory names, e.g. 'euv-lines'."""
    for name, factory in PRESETS.items():
        if PRESET_IDS[name] == preset_id:
            return Project.from_spec(factory(), name=name)
    raise KeyError(preset_id)
