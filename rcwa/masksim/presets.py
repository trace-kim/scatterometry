"""Built-in material tables and example mask stacks.

EUV (13.5 nm): Mo, Si, Ru, and TaN are the values used in this repo's examples.
The other entries are rounded literature values (CXRO-based), so verify them before
quantitative use. DUV (193 nm) values are common textbook numbers for 6% MoSi
att-PSM, Cr, and fused silica.
"""
from __future__ import annotations

from typing import Callable, Dict

from .stack import NM, Illumination, LayerSpec, MaskSpec, Material, Numerics, PatternSpec

EUV_MATERIALS = (
    Material("Vacuum", 1.0, 0.0),
    Material("Mo", 0.923791, 0.0064358),
    Material("Si", 0.99900154, 0.0018265),
    Material("Ru", 0.8864, 0.017066),
    Material("MoSi2", 0.969, 0.0043),
    Material("TaBN", 0.95, 0.031),
    Material("TaN", 0.92599, 0.04363),
    Material("Ni", 0.948, 0.073),
    Material("SiO2", 0.978, 0.0108),
)

DUV_MATERIALS = (
    Material("Air", 1.0, 0.0),
    Material("Quartz", 1.5631, 0.0),
    Material("MoSi", 2.343, 0.586),
    Material("Cr", 0.84, 1.65),
)

_EUV_MIRROR = (
    LayerSpec("Cap", "Ru", 2.5 * NM),
    LayerSpec("ML Si", "Si", 4.18 * NM, group="ML"),
    LayerSpec("ML Mo", "Mo", 2.71 * NM, group="ML"),
)


def euv_lines() -> MaskSpec:
    return MaskSpec(
        materials=EUV_MATERIALS,
        superstrate="Vacuum",
        substrate="Si",
        layers=(LayerSpec("Absorber", "TaBN", 60 * NM, patterned=True, swa_deg=85.0, steps=5),) + _EUV_MIRROR,
        repeats=(("ML", 40),),
        pattern=PatternSpec(kind="ls_v", pitch_x=128 * NM, cd_x=64 * NM, fill="Vacuum"),
        illumination=Illumination(wavelength=13.5 * NM, theta_deg=6.0, phi_deg=0.0, polarization="TE"),
        numerics=Numerics(nx=15, ny=15),
    )


def euv_contacts() -> MaskSpec:
    return MaskSpec(
        materials=EUV_MATERIALS,
        superstrate="Vacuum",
        substrate="Si",
        layers=(LayerSpec("Absorber", "TaBN", 60 * NM, patterned=True, swa_deg=88.0, steps=3),) + _EUV_MIRROR,
        repeats=(("ML", 40),),
        pattern=PatternSpec(kind="ch_square", pitch_x=128 * NM, pitch_y=128 * NM,
                            cd_x=64 * NM, cd_y=64 * NM, fill="Vacuum"),
        illumination=Illumination(wavelength=13.5 * NM, theta_deg=6.0, phi_deg=0.0, polarization="TE"),
        numerics=Numerics(nx=5, ny=5),
    )


def euv_blank() -> MaskSpec:
    return MaskSpec(
        materials=EUV_MATERIALS,
        superstrate="Vacuum",
        substrate="Si",
        layers=_EUV_MIRROR,
        repeats=(("ML", 40),),
        pattern=PatternSpec(kind="none"),
        illumination=Illumination(wavelength=13.5 * NM, theta_deg=6.0, phi_deg=0.0, polarization="TE"),
        numerics=Numerics(nx=0, ny=0),
    )


def duv_attpsm_lines() -> MaskSpec:
    return MaskSpec(
        materials=DUV_MATERIALS,
        superstrate="Quartz",  # illuminated through the blank
        substrate="Air",
        layers=(LayerSpec("Shifter", "MoSi", 68 * NM, patterned=True),),
        pattern=PatternSpec(kind="ls_v", pitch_x=400 * NM, cd_x=200 * NM, fill="Air"),
        illumination=Illumination(wavelength=193 * NM, theta_deg=0.0, phi_deg=0.0, polarization="TE"),
        numerics=Numerics(nx=15, ny=15),
    )


PRESETS: Dict[str, Callable[[], MaskSpec]] = {
    "EUV · TaBN L/S on Ru/MoSi multilayer": euv_lines,
    "EUV · TaBN contact holes (square)": euv_contacts,
    "EUV · blank multilayer mirror": euv_blank,
    "DUV 193 nm · 6% MoSi att-PSM L/S": duv_attpsm_lines,
}
