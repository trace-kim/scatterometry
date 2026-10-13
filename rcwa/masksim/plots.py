"""Plotly figure builders for notebooks (lengths shown in nm, depth pointing down).

The numbers come from masksim.views; this module only styles them. The web UI does
not use it.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Optional, Sequence

import numpy as np
import plotly.graph_objects as go

from .stack import NM, MaskSpec, Slice
from .views import (
    FIELD_QUANTITIES,
    absorption_by_layer,
    convolution_matrix,
    edge_mask,
    eps_plane,
    eps_section,
    field_plane,
    field_quantity,
    field_section,
    mode_kz,
    plane_axes,
    plane_index,
    pupil_points,
    section_axes,
    section_index,
    slice_at,
    stack_boxes,
)

__all__ = [
    "FIELD_QUANTITIES", "absorption_by_layer", "material_colors", "stack_section_figure", "stack_topview_figure",
    "stack_3d_figure", "eps_section_figure", "eps_topview_figure", "convolution_matrix_figure",
    "field_section_figure", "field_topview_figure", "flux_figure", "eigenvalue_figure", "pupil_figure",
]

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#EECA3B",
           "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC"]
CLEAR = "#DCE6F0"


def material_colors(spec: MaskSpec) -> Dict[str, str]:
    colors, i = {}, 0
    for m in spec.materials:
        if m.n == 1.0 and m.k == 0.0:
            colors[m.name] = CLEAR
        else:
            colors[m.name] = PALETTE[i % len(PALETTE)]
            i += 1
    return colors


def _categorical_heatmap(spec: MaskSpec, index: np.ndarray, x_nm: np.ndarray, y_nm: np.ndarray) -> go.Heatmap:
    names = [m.name for m in spec.materials]
    colors = material_colors(spec)
    used = sorted(np.unique(index))
    compact = np.searchsorted(used, index)
    k = len(used)
    scale = []
    for i, u in enumerate(used):
        scale += [(i / k, colors[names[u]]), ((i + 1) / k, colors[names[u]])]
    return go.Heatmap(
        x=x_nm, y=y_nm, z=compact, zmin=-0.5, zmax=k - 0.5, colorscale=scale,
        colorbar=dict(tickvals=list(range(k)), ticktext=[names[u] for u in used], title="material"),
        hovertemplate="x=%{x:.1f} nm<br>depth=%{y:.2f} nm<extra></extra>",
    )


def _edge_overlay(edges: np.ndarray, x_nm: np.ndarray, y_nm: np.ndarray, color: str = "white") -> go.Heatmap:
    return go.Heatmap(
        x=x_nm, y=y_nm, z=edges.astype(float), zmin=0, zmax=1, showscale=False, hoverinfo="skip",
        colorscale=[(0, "rgba(0,0,0,0)"), (1, color)],
    )


def _depth_layout(fig: go.Figure, lateral_label: str, title: str) -> go.Figure:
    fig.update_layout(title=title, xaxis_title=f"{lateral_label} (nm)", yaxis_title="depth z (nm)",
                      margin=dict(l=10, r=10, t=40, b=10), height=480)
    fig.update_yaxes(autorange="reversed")
    return fig


def _square_layout(fig: go.Figure, title: str, height: int = 440) -> go.Figure:
    fig.update_layout(title=title, xaxis_title="x (nm)", yaxis_title="y (nm)", height=height,
                      margin=dict(l=10, r=10, t=40, b=10))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def stack_section_figure(spec: MaskSpec, slices: Sequence[Slice], axis: str, offset: float,
                         periods: float, z_min: float, z_max: float) -> go.Figure:
    lateral, z = section_axes(spec, axis, periods, z_min, z_max)
    index = section_index(spec, slices, axis, offset, lateral, z)
    fig = go.Figure(_categorical_heatmap(spec, index, lateral / NM, z / NM))
    other = "y" if axis == "x" else "x"
    return _depth_layout(fig, axis, f"Cross-section {axis}-z at {other} = {offset / NM:.1f} nm")


def stack_topview_figure(spec: MaskSpec, s: Slice, periods: float, n: int = 240) -> go.Figure:
    xs, ys = plane_axes(spec, periods, n)
    fig = go.Figure(_categorical_heatmap(spec, plane_index(spec, s, xs, ys), xs / NM, ys / NM))
    return _square_layout(fig, f"Top view: {s.label} (depth {s.z_top / NM:.1f}–{s.z_bottom / NM:.1f} nm)", 480)


_BOX_FACES = np.array([
    (0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
    (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
])


def stack_3d_figure(spec: MaskSpec, slices: Sequence[Slice], periods: float, z_max: float,
                    n: int = 160) -> go.Figure:
    """Interactive 3D view: homogeneous layers as slabs, patterned slices as extruded pixel runs."""
    boxes = defaultdict(list)
    for material, *box in stack_boxes(spec, slices, periods, z_max, n):
        boxes[material].append(box)
    colors = material_colors(spec)
    fig = go.Figure()
    for material, items in boxes.items():
        b = np.asarray(items) / NM
        x0, x1, y0, y1, z0, z1 = b.T
        corners = np.stack([
            np.stack([x0, y0, z0], 1), np.stack([x1, y0, z0], 1), np.stack([x1, y1, z0], 1), np.stack([x0, y1, z0], 1),
            np.stack([x0, y0, z1], 1), np.stack([x1, y0, z1], 1), np.stack([x1, y1, z1], 1), np.stack([x0, y1, z1], 1),
        ], axis=1).reshape(-1, 3)
        faces = (_BOX_FACES[None, :, :] + 8 * np.arange(len(b))[:, None, None]).reshape(-1, 3)
        fig.add_trace(go.Mesh3d(
            x=corners[:, 0], y=corners[:, 1], z=-corners[:, 2], i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            color=colors[material], name=material, showlegend=True, flatshading=True,
            lighting=dict(ambient=0.55, diffuse=0.8, specular=0.1), hoverinfo="name",
        ))
    fig.update_layout(
        scene=dict(xaxis_title="x (nm)", yaxis_title="y (nm)", zaxis_title="−depth (nm)", aspectmode="data"),
        height=560, margin=dict(l=0, r=0, t=30, b=0), legend=dict(itemsizing="constant"),
    )
    return fig


def eps_section_figure(spec: MaskSpec, slices: Sequence[Slice], axis: str, offset: float, periods: float,
                       z_min: float, z_max: float, part: str, fourier: bool) -> go.Figure:
    lateral, z = section_axes(spec, axis, periods, z_min, z_max, n_lateral=360, n_z=320)
    values = eps_section(spec, slices, axis, offset, lateral, z, fourier)
    data = values.real if part == "Re" else values.imag
    fig = go.Figure(go.Heatmap(x=lateral / NM, y=z / NM, z=data, colorscale="RdBu_r",
                               colorbar=dict(title=f"{part}(ε)"),
                               hovertemplate="x=%{x:.1f} nm<br>depth=%{y:.2f} nm<br>%{z:.5f}<extra></extra>"))
    kind = "truncated Fourier series" if fourier else "exact geometry"
    return _depth_layout(fig, axis, f"{part}(ε) — {kind}")


def eps_topview_figure(spec: MaskSpec, slices: Sequence[Slice], s: Slice, periods: float, part: str,
                       fourier: bool, n: int = 160) -> go.Figure:
    xs, ys = plane_axes(spec, periods, n)
    values = eps_plane(spec, slices, s, xs, ys, fourier)
    data = values.real if part == "Re" else values.imag
    fig = go.Figure(go.Heatmap(x=xs / NM, y=ys / NM, z=data, colorscale="RdBu_r", colorbar=dict(title=f"{part}(ε)")))
    return _square_layout(fig, f"{part}(ε) in {s.label}", 420)


def convolution_matrix_figure(spec: MaskSpec, slices: Sequence[Slice], s: Slice) -> go.Figure:
    E_conv, mx, my = convolution_matrix(spec, slices, s)
    magnitude = np.log10(np.abs(E_conv) + 1e-16)
    labels = [f"({m},{n})" for m, n in zip(mx, my)]
    fig = go.Figure(go.Heatmap(z=magnitude, x=labels, y=labels, colorscale="Viridis", zmin=max(-6, magnitude.min()),
                               colorbar=dict(title="log10|ε_pq|")))
    fig.update_layout(title=f"Convolution matrix [ε] for {s.label} ({len(labels)}×{len(labels)})",
                      xaxis_title="harmonic q (m, n)", yaxis_title="harmonic p (m, n)", height=480,
                      margin=dict(l=10, r=10, t=40, b=10))
    fig.update_yaxes(autorange="reversed")
    return fig


def _field_trace(data: np.ndarray, x_nm: np.ndarray, y_nm: np.ndarray, quantity: str) -> go.Heatmap:
    signed = quantity.startswith("Re")
    limit = float(np.max(np.abs(data))) or 1.0
    return go.Heatmap(
        x=x_nm, y=y_nm, z=data, colorscale="RdBu_r" if signed else "Inferno",
        zmin=-limit if signed else 0.0, zmax=limit, colorbar=dict(title=quantity),
        hovertemplate="x=%{x:.1f} nm<br>y=%{y:.2f} nm<br>%{z:.4g}<extra></extra>",
    )


def field_section_figure(spec: MaskSpec, slices: Sequence[Slice], solution, axis: str, offset: float,
                         periods: float, z_min: float, z_max: float, quantity: str) -> go.Figure:
    lateral, z = section_axes(spec, axis, periods, z_min, z_max, n_lateral=320, n_z=360)
    data = field_quantity(field_section(solution, axis, offset, lateral, z), quantity)
    fig = go.Figure(_field_trace(data, lateral / NM, z / NM, quantity))
    edge_color = "rgba(0,0,0,0.7)" if quantity.startswith("Re") else "rgba(120,200,255,0.9)"
    fig.add_trace(_edge_overlay(edge_mask(section_index(spec, slices, axis, offset, lateral, z)),
                                lateral / NM, z / NM, color=edge_color))
    return _depth_layout(fig, axis, f"{quantity} (incident amplitude = 1)")


def field_topview_figure(spec: MaskSpec, slices: Sequence[Slice], solution, depth: float, periods: float,
                         quantity: str, n: int = 160) -> go.Figure:
    xs, ys = plane_axes(spec, periods, n)
    fig = go.Figure(_field_trace(field_quantity(field_plane(solution, xs, ys, depth), quantity),
                                 xs / NM, ys / NM, quantity))
    s = slice_at(slices, depth)
    if s is not None and s.patterned:
        fig.add_trace(_edge_overlay(edge_mask(plane_index(spec, s, xs, ys)), xs / NM, ys / NM,
                                    color="rgba(120,200,255,0.9)"))
    return _square_layout(fig, f"{quantity} at depth {depth / NM:.1f} nm")


def flux_figure(solution, slices: Sequence[Slice], z_min: float, z_max: float) -> go.Figure:
    z = np.linspace(z_min, z_max, 600)
    fig = go.Figure(go.Scatter(x=solution.power_flux(z), y=z / NM, mode="lines", name="net downward flux"))
    for s in slices:
        if z_min <= s.z_top <= z_max and (s.patterned or s.step == 0):
            fig.add_hline(y=s.z_top / NM, line=dict(color="rgba(128,128,128,0.25)", width=1))
    fig.update_layout(title="Power flow vs depth (1 = incident)", xaxis_title="normalized flux",
                      yaxis_title="depth z (nm)", height=440, margin=dict(l=10, r=10, t=40, b=10))
    fig.update_yaxes(autorange="reversed")
    return fig


def eigenvalue_figure(solution, layer_index: int, label: str) -> go.Figure:
    kz = mode_kz(solution, layer_index)
    fig = go.Figure(go.Scatter(x=kz.real, y=kz.imag, mode="markers", marker=dict(size=7),
                               hovertemplate="Re kz=%{x:.4f}<br>Im kz=%{y:.4f}<extra></extra>"))
    fig.update_layout(title=f"Mode propagation constants kz/k0 in {label}", xaxis_title="Re(kz/k0)",
                      yaxis_title="Im(kz/k0)  (negative = decaying)", height=420, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def pupil_figure(solution, n_ref: float, na_mask: Optional[float]) -> go.Figure:
    """Propagating reflected orders in direction-cosine space, with an optional mask-side NA circle."""
    p = pupil_points(solution, n_ref)
    t = np.linspace(0, 2 * np.pi, 200)
    fig = go.Figure(go.Scatter(x=np.cos(t), y=np.sin(t), mode="lines", line=dict(color="gray", dash="dot"),
                               name="propagation cutoff", hoverinfo="skip"))
    if na_mask:
        cx, cy = p["center"]
        fig.add_trace(go.Scatter(x=cx + na_mask * np.cos(t), y=cy + na_mask * np.sin(t), mode="lines",
                                 line=dict(color="#E45756"), name="mask-side NA", hoverinfo="skip"))
    R = np.asarray(p["R"])
    phase = np.array([np.nan if v is None else v for v in p["phase_deg"]])
    size = 8 + 40 * np.sqrt(np.clip(R, 0, None) / max(R.max(initial=0.0), 1e-30))
    fig.add_trace(go.Scatter(
        x=p["sx"], y=p["sy"], mode="markers", name="reflected orders",
        marker=dict(size=size, color=phase, colorscale="Twilight", cmin=-180, cmax=180,
                    colorbar=dict(title="phase (deg)"), line=dict(width=1, color="black")),
        text=[f"({m},{n})" for m, n in zip(p["m"], p["n"])],
        customdata=np.stack([R, phase], axis=1),
        hovertemplate="order %{text}<br>R=%{customdata[0]:.4g}<br>phase=%{customdata[1]:.1f}°<extra></extra>",
    ))
    fig.update_layout(title="Reflected orders (size ∝ √R, color = phase)",
                      xaxis_title="kx / (k0 n)", yaxis_title="ky / (k0 n)", height=480,
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig
