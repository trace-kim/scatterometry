"""Photomask stack wrapper around the RCWA solver: materials, patterns, slicing, presets.

Submodules: `project` (versioned JSON documents, nm/deg), `views` (numerical data behind
the UI views), `runner` (solve/sweep orchestration with progress), `plots` (Plotly
figures for notebooks; needs the optional `plots` extra).
"""
from .geometry import HoleArrayPattern, LineSpacePattern, MaskPattern, UniformPattern
from .presets import PRESETS
from .project import PRESET_IDS, Project, load_project, preset_project
from .runner import RunResult, solve_spec, sweep_records
from .stack import (
    NM,
    PATTERN_KINDS,
    Illumination,
    LayerSpec,
    MaskSpec,
    Material,
    Numerics,
    PatternSpec,
    Slice,
    build_problem,
    build_slices,
    expand_layers,
    solver_settings,
    sweep_parameters,
    unit_cell,
    validate,
    with_parameter,
)

__all__ = [
    "HoleArrayPattern", "LineSpacePattern", "MaskPattern", "UniformPattern",
    "PRESETS", "PRESET_IDS", "NM", "PATTERN_KINDS",
    "Illumination", "LayerSpec", "MaskSpec", "Material", "Numerics", "PatternSpec", "Slice",
    "Project", "load_project", "preset_project",
    "RunResult", "solve_spec", "sweep_records",
    "build_problem", "build_slices", "expand_layers", "solver_settings", "sweep_parameters",
    "unit_cell", "validate", "with_parameter",
]
