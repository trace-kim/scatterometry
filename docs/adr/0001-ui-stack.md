# ADR 0001: Web UI stack for the mask simulator

- **Status:** accepted, implemented 2026-10-13
- **Supersedes:** the Streamlit prototype (deleted on 2026-10-13, never committed)

## Context

The mask simulator wraps the RCWA solver for photomask stacks. It needs:
- a stack, material and pattern editor
- 2D and 3D geometry views
- the permittivity as RCWA represents it
- fields inside the mask, diffraction orders, and parameter sweeps

The longer-term direction is an S-Litho-like feature set (aerial images, process windows, fitting to scatterometry measurements). The UI should eventually be shared with colleagues through a browser.

Requirements that shaped the choice:

1. **Long-lived and restyleable.** The stack is expected to stay fixed, and the UX will be iterated many times. Visual design must be under our control.
2. **Instant redraw** for view changes (quantity, colormap, depth, time phase), including over a network once colleagues use it.
3. **Multi-user later.** Results must stay on a server, with jobs, progress, and cancellation.
4. **Python remains the home of the physics.** New plots should be possible without TypeScript.

Streamlit was rejected for its behaviour: every interaction reran the whole script and recomputed all tabs, which forced key and state workarounds.

A desktop Qt stack (PySide6 + pyqtgraph + PyVista) was seriously considered. It lost because browser access for colleagues is a goal and the UX will be iterated heavily: Qt first would have meant building the UI twice.

## Decision

| Part | Choice | Why |
|---|---|---|
| UI framework | React 19 + TypeScript 6.0 (Vite 8 SPA) | Every library below is first-class on React. TS 7 is held back because its native compiler lacks the JS API that codegen and typescript-eslint need. |
| Components | shadcn/ui on Base UI (`@base-ui/react`), "Mira" preset, Tailwind 4 | We own the component source, so redesigns are edits rather than overrides. Base UI provides the behaviour and accessibility, including a drag-to-scrub number field. Mantine was rejected: you restyle it but don't own its markup, and its overrides break across major versions. |
| Charts and 2D maps | ECharts 6 | It saves about 1,500 lines compared with our own d3/visx plot kit, and is fast and themeable. Heatmaps are CPU-colorized canvases drawn by an ECharts custom series, so they get axes, zoom and pan for free. Plotly was dropped: it is styled from outside, its interactions don't match the heatmaps, and it adds about 1.4 MB gzipped. |
| 3D | three.js + @react-three/fiber + drei | Instanced meshes per material and clipping planes, lazy-loaded. vtk.js stays in reserve for volume rendering. |
| Workspace | dockview | Panels can be docked, split, tabbed and floated, and the layout is saved. |
| Tables | AG Grid Community | Typed cell editors and row dragging. Clipboard range copy/paste is an Enterprise feature, so pasting from Excel needs a custom handler. |
| State | zustand + immer | One immutable project document with patch-based undo. Rapid edits coalesce, and the same document serves as the project file and the cache key. |
| Server data | TanStack Query | Caching, cancellation of superseded requests, and keep-previous-data while scrubbing. |
| API types | FastAPI → OpenAPI → @hey-api/openapi-ts (types only) | Python and the UI can't drift apart. The generator is replaceable, because the OpenAPI schema is the contract. |
| Backend | FastAPI, Pydantic 2, uvicorn, sse-starlette | Typed API with live job events over Server-Sent Events (one-way, plain HTTP). |
| Jobs | In-house thread-pool `JobManager` | Celery doesn't support Windows, and RQ/arq need Redis. Cancellation is cooperative through the solver's progress hook, and results stay in memory next to the solutions. Moving to worker processes would only touch `jobs.py`. |
| Transport | Uncompressed `.npz` (complex64, uint8, float64 axes) | Standard, self-describing, and opens directly in numpy. Gzip is skipped for float arrays because it costs time without saving bytes. |
| Project files | Versioned Pydantic documents in nm/degrees (`masksim/project.py`) | Kept separate from the internal SI dataclasses, so refactors never break saved files. |
| Tooling | uv (+ `uv.lock`), pnpm 11, Biome, ruff; pytest, Vitest, Playwright on installed Edge | Reproducible environments and one fast linter per language. |

### One-way and two-way doors

These are expensive to change: React, TypeScript, the shadcn/Base UI component layer, the API and project schemas, the `.npz` transport, and the result and job model.

These are contained and swappable:
- ECharts (charts only), AG Grid (a few tables), dockview (the shell)
- the type generator, the job executor implementation, the linters

## Consequences

- **Instant views.** Quantity, colormap, scale, and the time phase are computed in the browser from complex field components, and the phase animation runs at 60 fps. New field planes cost 10–15 ms (top views) or about 20 ms (cross-sections at a new offset) on the server.
- **Per-feature cost.** A new interactive view touches three layers: a Python function in `masksim.views`, an endpoint, and a panel. Quick plots can skip the TypeScript through `maskserver/python_views.py`.
- **Theming.** The CSS-variable tokens in `web/src/index.css` are the single theme source for shadcn, AG Grid, dockview, ECharts, and three.js.
- **Retention.** Results are in server memory only: they are lost on restart and limited to the most recent `MASKSIM_KEEP_RESULTS` jobs.

## Deferred

- **Shareable links** with TanStack Router, so URLs carry state. Only needed once projects and runs live on the server.
- **Persistent storage.** SQLAlchemy + Alembic, SQLite first, then PostgreSQL, plus an on-disk result store keyed by `Project.digest()` and the solver version.
- **Authentication** through company single sign-on at a reverse proxy; the app would read identity headers.
- **Process-pool jobs** for parallel sweeps.
- **GPU field synthesis.** Ship harmonic amplitudes and sum them in a shader, if network redraws ever become the bottleneck.
- **A desktop installer.** Electron with a bundled Python, or simply installing the web app from the browser.

## Verification at adoption

Versions and peer dependencies were checked on npm and PyPI on 2026-10-12 against Python 3.13. Notable constraints found:
- typescript-eslint requires TS < 6.1.
- h5web and Glide Data Grid support only React 18.
- plotly.py 7.1 bundles plotly.js 4.1.

The implementation is covered by:
- 82 Python tests (solver, masksim, API)
- Vitest unit tests
- Playwright end-to-end tests that solve 1D and 2D presets, edit with undo, run a sweep, and open every panel without console errors
