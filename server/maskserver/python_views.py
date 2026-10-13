"""Views written in Python: functions that return an ECharts option (a JSON-able dict).

This is the quickest way to add a plot without touching TypeScript: decorate a function
with @python_view and it appears in the web UI's "Python views" panel. The option is
rendered as-is with the app's chart theme, so leave colors and fonts out unless they
carry meaning. A view that needs instant interaction (sliders, linked hover) can later
graduate to a dedicated panel in web/src/panels.

    @python_view("my-view", "My view", needs="run")
    def my_view(ctx: ViewContext) -> dict:
        return {"xAxis": {...}, "yAxis": {...}, "series": [...]}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Literal, Optional

import numpy as np

from masksim import NM, MaskSpec, Project, Slice, views
from rcwa import NearFieldSolution

Needs = Literal["project", "run"]


@dataclass
class ViewContext:
    project: Project
    spec: MaskSpec
    slices: List[Slice]
    pol: Optional[str] = None
    solution: Optional[NearFieldSolution] = None  # set for views that need a run


@dataclass
class PythonView:
    id: str
    title: str
    description: str
    needs: Needs
    build: Callable[[ViewContext], dict]


REGISTRY: Dict[str, PythonView] = {}


def python_view(view_id: str, title: str, *, needs: Needs = "project", description: str = ""):
    def register(build: Callable[[ViewContext], dict]) -> Callable[[ViewContext], dict]:
        text = " ".join((description or build.__doc__ or "").split())
        REGISTRY[view_id] = PythonView(view_id, title, text, needs, build)
        return build

    return register


def _axis(name: str, kind: str = "value", **extra) -> dict:
    return {"type": kind, "name": name, "nameLocation": "middle", "nameGap": 30, **extra}


# ---- built-in examples -------------------------------------------------------------------


@python_view("eps-spectrum", "Fourier spectrum of ε (first patterned slice)")
def eps_spectrum(ctx: ViewContext) -> dict:
    """|ε_m| of the harmonics the convolution matrix contains for the first patterned slice; slowly
    decaying spectra need more harmonics."""
    patterned = [s for s in ctx.slices if s.patterned]
    if not patterned:
        return {"title": {"text": "No patterned slice", "left": "center", "top": "middle"}}
    E, mx, my = views.convolution_matrix(ctx.spec, ctx.slices, patterned[0])
    centre = int(np.flatnonzero((mx == 0) & (my == 0))[0])
    column = np.abs(E[:, centre])  # ε(m_p - 0): the coefficients |m| <= N, |n| <= N
    labels = [f"({m},{n})" for m, n in zip(mx, my, strict=True)]
    keep = column > 0
    return {
        "grid": {"left": 70, "right": 20, "top": 30, "bottom": 50},
        "tooltip": {"trigger": "axis"},
        "xAxis": _axis("harmonic (m, n)", "category", data=[l for l, k in zip(labels, keep, strict=True) if k]),
        "yAxis": {**_axis("|ε_mn|", "log"), "nameGap": 52},
        "series": [{"type": "bar", "data": [float(v) for v in column[keep]], "barMaxWidth": 18}],
    }


@python_view("intensity-depth", "Cell-averaged intensity vs depth", needs="run")
def intensity_depth(ctx: ViewContext) -> dict:
    """Mean |E|² over the unit cell at each depth. By Parseval it is the sum of |E|² over the
    plane-wave harmonics, so it needs no lateral sampling."""
    sol = ctx.solution
    z = np.linspace(-30 * NM, sol.total_thickness + 20 * NM, 900)
    amp = sol.amplitudes(z)
    mean = np.sum(np.abs(amp["sx"]) ** 2 + np.abs(amp["sy"]) ** 2 + np.abs(amp["sz"]) ** 2, axis=1)
    return {
        "grid": {"left": 60, "right": 20, "top": 20, "bottom": 50},
        "tooltip": {"trigger": "axis"},
        "xAxis": _axis("depth z (nm)", min=round(float(z[0] / NM), 3), max=round(float(z[-1] / NM), 3)),
        "yAxis": {**_axis("⟨|E|²⟩ over the cell"), "nameGap": 42},
        "dataZoom": [{"type": "inside", "xAxisIndex": 0}],
        "series": [{"type": "line", "showSymbol": False, "data": np.stack([z / NM, mean], axis=1).tolist()}],
    }


@python_view("orders-vs-angle", "Reflected orders vs exit angle", needs="run")
def orders_vs_angle(ctx: ViewContext) -> dict:
    """Efficiency of each propagating reflected order against its polar exit angle."""
    rows = [r for r in views.order_records(ctx.solution) if r["r_propagating"] and r["R"] > 0]
    return {
        "grid": {"left": 70, "right": 20, "top": 20, "bottom": 50},
        "tooltip": {"trigger": "item"},
        "xAxis": _axis("exit angle θ (deg)", min=0, max=90),
        "yAxis": {**_axis("efficiency", "log"), "nameGap": 52},
        "series": [{
            "type": "scatter",
            "symbolSize": 9,
            "data": [{"value": [r["r_theta_deg"], r["R"]], "name": f"({r['m']},{r['n']})"} for r in rows],
            "label": {"show": True, "formatter": "{b}", "position": "top", "fontSize": 9},
        }],
    }
