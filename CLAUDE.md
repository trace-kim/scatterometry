# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

The repository holds EUV-photomask scatterometry tooling and a web-based mask simulator.

- **`rcwa/rcwa/`**: the RCWA (rigorous coupled-wave analysis) solver package.
  - `fresnel.py` is the Fresnel/TMM ground truth for unpatterned stacks.
  - `nearfield.py` is a solver variant that also reconstructs fields inside the stack.
- **`rcwa/masksim/`**: the photomask layer.
  - Specs and slicing: `stack.py`, `geometry.py`, `presets.py`.
  - `project.py`: versioned project documents, in nm and degrees.
  - `views.py`: the numbers behind every UI view.
  - `runner.py`: solve and sweep orchestration with progress reporting.
  - `plots.py`: Plotly figures for notebooks.
- **`server/maskserver/`**: FastAPI backend for the web UI (jobs, array endpoints, live events). It also serves the built UI.
- **`web/`**: React/TypeScript UI. Its stack and the reasons behind it are in `docs/adr/0001-ui-stack.md`.
- **Scripts in `rcwa/`**:
  - `main.py`: a forward-model angle sweep with a detector-scan simulation.
  - `analyze_scatterometry.py`: diffraction-spot detection in camera images. It does not import `rcwa`.
  - `compare_rcwa_fresnel.py`: RCWA vs TMM report.

## Commands

Python uses the repo-root `.venv`, managed by uv. The workspace is defined in the root `pyproject.toml` and locked in `uv.lock`. The web UI uses pnpm in `web/`.

```powershell
# one-time setup
.venv\Scripts\uv.exe sync --inexact --all-packages  # editable rcwa-masksim + maskserver + dev tools
cd web; pnpm install; pnpm build                     # UI into web/dist

# run the app (serves web/dist and the API, opens a browser)
python -m maskserver                                 # http://127.0.0.1:8000; --host 0.0.0.0 shares it on the LAN
# UI development with hot reload (two terminals)
python -m maskserver --no-browser --reload           # API on :8000
cd web; pnpm dev                                     # UI on :5180, proxies /api to :8000

# tests
python -m pytest -q                                  # rcwa/tests + server/tests, ~5 s, from any directory
python -m pytest -q rcwa/tests/test_nearfield.py::test_tangential_fields_are_continuous
cd web; pnpm test                                    # Vitest unit tests (src/**/*.test.ts)
cd web; pnpm test:e2e                                # build, then Playwright on installed Edge against a server on :8765
cd web; pnpm typecheck; pnpm lint                    # tsc -b, Biome
.venv\Scripts\ruff.exe check server rcwa/masksim/project.py rcwa/masksim/views.py rcwa/masksim/runner.py

# after changing API models (server/maskserver/schemas.py, masksim/project.py)
cd web; pnpm api:gen                                 # dumps openapi.json with Python, regenerates src/api/gen

# scripts (run from rcwa/)
python -X utf8 compare_rcwa_fresnel.py               # RCWA vs Fresnel/TMM report
$env:MPLBACKEND = "Agg"; python main.py              # angle sweep without blocking plot windows
python analyze_scatterometry.py                      # configured only by scatterometry_config.json
```

- **Pytest import mode.** Keep the default (prepend) mode. `--import-mode=importlib` names tests `rcwa.tests.*` and shadows the real `rcwa` package. Test file names must therefore be unique across `rcwa/tests` and `server/tests`.
- **Imports from anywhere.** The editable install puts `rcwa/` on `sys.path`, so `rcwa`, `masksim`, and the script modules import from any working directory. Before the install, tests had to run from `rcwa/`.
- **`-X utf8`.** The Windows locale is cp949, and `compare_rcwa_fresnel.py` prints `✓`, which raises `UnicodeEncodeError` without UTF-8 mode.
- **BLAS threads.** The bundled OpenBLAS (0.3.34, 12 threads) makes mid-size LU solves about 40× slower. Every Redheffer star product calls `solve`, so 2D (C/H) problems crawl.
  - maskserver caps threads with threadpoolctl (`MASKSIM_BLAS_THREADS`, default 4).
  - Scripts must set `OPENBLAS_NUM_THREADS=4` before numpy is imported.
- **Minimum release age.** pnpm 11 holds back packages released very recently. Pin an older release instead of adding `minimumReleaseAgeExclude` entries.
- **TypeScript 6.0.x is pinned on purpose.** TS 7 (npm "latest") lacks the compiler API that `@hey-api/openapi-ts` needs. Biome, not ESLint, does linting.
- **Ruff scope.** The new Python code is ruff-clean. Legacy modules (`solver.py`, the scripts) are not, so don't mass-reformat them.
- **Expected GPU warning.** `import rcwa` emits `UserWarning: [RCWA] GPU not available`. `RCWA_GPU_REQUIRED=1` makes a missing GPU an import error.
- **Script output.** `analyze_scatterometry.py` resolves relative paths against its JSON config and writes demo outputs into `rcwa/` (not gitignored).

## Validation expectations

- New Python tests go in `rcwa/tests/test_<behavior>.py` (numerics, masksim) or `server/tests/test_server_<behavior>.py` (API).
  - Prefer small zero-order (`Nx=Ny=0`) RCWA cases checked against `FresnelSolver`. Existing tests use `abs=1e-12`.
  - Server tests use the FastAPI `TestClient` (httpx2 transport) with small harmonic counts so solves take milliseconds.
- After any numerical change, also run `compare_rcwa_fresnel.py`. RCWA and TMM agree to ~1e-15. Its "✓" thresholds (1e-4/1e-3) are far looser and it always exits 0, so read the ΔR/ΔT values, not the checkmark.
- `tests/test_nearfield.py` pins `NearFieldSolver` to `RCWASolver` per order (1e-10). It also checks tangential E/H continuity at every interface and the power balance: flux = 1 − R at the top, T at the bottom, and Σ layer absorption = A.
- UI changes:
  - Unit-test pure logic (array decoding, colorizing, store behaviour) with Vitest.
  - Cover user flows in `web/e2e`. Those tests fail on any console error except the known three.js deprecation.

## RCWA solver architecture

`RCWASolver.solve(problem)` in `solver.py` runs the lecture's Steps 0–14 (module docstrings cite step numbers):

| Steps | Module | What |
|---|---|---|
| 2–3 | `convolution.py` | sample `pattern.eps_r(X, Y)` on a grid, FFT, Toeplitz convolution matrices |
| 4 | `wavevector.py` | wave-vector expansion |
| 5, 7 | `eigenmodes.py` | layer eigenproblem |
| 6, 8–10 | `smatrix.py` | Redheffer star, connection S-matrices |
| 11–12 | `fields.py` | fields |
| 13–14 | `efficiencies.py` | diffraction efficiencies |

- **The layer eigenproblem exists twice.** `RCWASolver` inlines it in `solver.py`, while `NearFieldSolver` calls `eigenmodes._layer_eigenmodes`, which returns `(W, V, lam)`. Change both; the cross-solver tests catch divergence. `eigenmodes._layer_scattering_matrix` (without `_with_lam`) is a stub that raises.
- **Laurent's rule only.** `_build_convolution_matrices_for_layer` also returns `E_inv_conv` (`[1/ε]`), but both solvers discard it and invert `E_conv`.
- **Harmonic flattening** (`_harmonic_indices`): `mx` varies fastest. Transverse vectors have length `2*Nh`, stacked `[x-block; y-block]`.
- **Order window.** Orders run `shift-N … shift+N` per axis (`RCWASettings.shift_x/shift_y`, default 0; `|shift| ≤ N` keeps the specular order). masksim's `Numerics.centering="pupil"` (the default) sets the shift with `pupil_centre_shift`, the order nearest k_t = 0, so grazing incidence keeps every propagating order. The convolution matrices index by order differences, so any window works. `web/src/lib/stack.ts` (`orderWindow`, `minimumOrders`) mirrors the rule, including round-half-up; change both together.
- **Units.** Wave vectors are normalized by `k0`. Lengths enter only through `k0·thickness` and `λ/Λ`, so any consistent unit works; the code uses meters.
- **Layer order.** `layers[0]` touches the reflection (incident) region and `layers[-1]` the transmission region. Global S = `Sref ⋆ Sdev ⋆ Strn`, and the zero-thickness gap medium is vacuum.
- **Periodicity.** `Ny = 0` means a 1D grating (`gy` forced to 0, `Ly` ignored). `Nx = 0, Ny > 0` works for y-periodic patterns. The real-space grid needs `grid_N ≥ 4N + 1` per axis.
- **Results.** `solve()` returns NumPy arrays.
  - `res["power"]` has `R_total`, `T_total`, `RT_total`, and `A_total = 1 − R − T`.
  - `res["efficiencies"]["per_order_R"/"per_order_T"]` are dicts keyed by `(m, n)`.
- **Backend-sensitive code** uses `xp = get_array_module()`. `fresnel.py` and `analyze_scatterometry.py` are NumPy-only by design.

### NearFieldSolver (`nearfield.py`)

- **Homogeneous fast path.** Layers whose `pattern.uniform_eps()` is not None, the gap and the external regions get analytic modes stored as `blockdiag.DiagBlocks` (2×2 blocks of diagonals, `(Nh, 2, 2)`). Their S-matrices and star products are O(Nh); `_redheffer_star` and `_solve` dispatch on the type and densify mixed cases. Only patterned slices pay O(Nh³), which made the 80-slice Mo/Si stack about 8× faster. `RCWASolver` stays all-dense as the independent reference.
- It takes the same `RCWAProblem` and returns the same `result` dict. Equal `Layer`s share one eigen-solve and one S-matrix, so a 40-pair multilayer costs two eigen-solves.
- **Progress and cancellation.** `solve(..., progress=fn)` reports `fn(fraction, message)` after each distinct eigen-solve and at the cascade and field stages. The callback may raise to abort; maskserver cancels jobs this way.
- **Field reconstruction.** A bottom-up cascade keeps `R_down[k]`. A top-down pass then gives each layer's `c⁺` (at its top) and `d⁻` (at its bottom), so every `exp(−λk₀ζ)` stays bounded.
- **`NearFieldSolution` API:** `amplitudes(z)`, `efield_xz/yz/xy`, `power_flux`, `layer_absorption`, `order_table`. Depth z is 0 at the top surface and positive into the stack. `amplitudes(z)` is the expensive part; `masksim.views.field_section` accepts precomputed amplitudes.

## Sign conventions (correctness-critical)

- **Propagation.** Fields go as `exp(-1j*kz*z)` with time dependence `exp(+jωt)`. Forward passive and evanescent waves need `Im(kz) ≤ 0`, and real roots take `Re(kz) ≥ 0`. Use `linalg._outgoing_sqrt`; `Kz_ref` is the negated root.
- **Layer eigenvalues** `λ = j·kz` take the principal root, `Re(λ) ≥ 0`.
- **Magnetic field.** Normalized as `u = −j·η0·H`. Inside a layer, `s = W(fwd + bwd)` and `u = V(bwd − fwd)`.
- **Loss.** `n_complex = n − 1j·k`, so absorbing media have `Im(ε) < 0`. `nk_to_eps`/`nk_to_n` use `|k|`.
- **Diffraction orders.** `Kx_m = Kx_inc − m·λ/Λx`. `main.py`'s `perR_to_angle_efficiency` relies on this sign.
- **Polarization.** `pTE=1, pTM=0` matches Fresnel `'s'`, and `pTE=0, pTM=1` matches `'p'`. At normal incidence TE is ŷ. The UI's time snapshot is `Re(E·e^{jωt})`.

## masksim

- **Specs** are frozen dataclasses (`MaskSpec`, `LayerSpec`, `PatternSpec`, ...) in meters and degrees.
  - Contiguous `LayerSpec` rows that share a `group` repeat as a block.
  - L/S uses `pitch_x`/`cd_x` for both orientations, with harmonics from `numerics.nx`.
  - Staggered C/H has a `pitch_x × 2·pitch_y` cell.
- **Slicing (`build_slices`).**
  - A non-90° sidewall angle cuts a patterned layer into `steps` slices, each using the CD at its mid-depth.
  - The width varies continuously across patterned layers, and the CD holds at `cd_reference`.
  - Holes shrink where the host material widens.
- **Patterns (`geometry.py`)** are area-averaged (anti-aliased) frozen dataclasses, so the solver cache works.
- **Project documents (`project.py`).** Pydantic models in nm and degrees, carrying `format` and `version`.
  - `to_spec()` / `from_spec()` convert to and from `MaskSpec`.
  - Upgrades from older versions belong in `load_project()`.
  - `digest()` hashes the physics only (not the name or display colors). The UI compares it with a run's digest to flag stale results.
  - Preset ids are the factory names with dashes (`euv-lines`, `euv-contacts`, `euv-blank`, `duv-attpsm-lines`).
- **`views.py`** holds the UI data products in meters: section and plane material maps, 3D boxes, exact versus Fourier ε, convolution matrices, field sections and planes, order records, the pupil, and default sweep ranges. `plots.py` and maskserver both build on it.
- **`runner.py`.** `solve_spec` returns a `RunResult` (solutions per polarization plus a summary). `sweep_records` yields one record batch per value.

## Server (`server/maskserver`)

- **Configuration.** `create_app(Settings)` builds the app. Settings come from `MASKSIM_*` environment variables (`BLAS_THREADS`, `MAX_JOBS`, `KEEP_RESULTS`, `WEB_DIST`, ...). The CLI flags of `python -m maskserver` set them.
- **Jobs (`jobs.py`).**
  - A thread pool (`max_jobs`, default 1) runs them, and progress callbacks raise `JobCancelled` to cancel.
  - Finished jobs (the `keep_results` most recent) and their solutions live in memory only, so a server restart forgets them. The UI then clears its stale run and sweep ids.
  - `Job.cached()` memoizes per-run derived data, such as field amplitudes per depth grid, which makes moving a section sideways cheap. It keeps at most `CACHE_BYTES` (256 MB) per job.
  - Moving the work into worker processes would only touch this module.
- **Resource limits.** No single request may exhaust the machine; it has no authentication and can be shared on the LAN.
  - `masksim.validate` refuses specs over `MAX_SLICES`, `MAX_HARMONICS`, `MAX_GRID_SAMPLES` or `MAX_MATERIALS` (constants in `stack.py`). It works from counts (`slice_counts`) without expanding the stack. Every endpoint that takes a project validates it first.
  - Runs and sweeps are refused when `masksim.memory_estimate` exceeds `MASKSIM_MAX_SOLVE_GB` (default 12, `--max-solve-gb`). The estimate is within a few percent of measured peaks. Sweeps validate every point up front.
  - Request bodies over `MASKSIM_MAX_BODY_MB` (default 8) get HTTP 413.
  - Finished runs are dropped oldest-first once their solutions exceed `MASKSIM_MAX_RESULTS_GB` (default 4), measured array by array. The newest result always stays.
  - At most `MASKSIM_REQUEST_THREADS` (default 8) requests compute at once, which caps the memory of concurrent views.
  - Run views evaluate depths in chunks (`views.DEPTH_CHUNK`) unless the amplitude grid fits the job cache, so their memory doesn't grow with n_z × harmonics.
  - Keep the solver's memory model in `memory_estimate` in sync with `NearFieldSolver`. It holds a dense 2Nh×2Nh matrix per interface only from the top through the lowest patterned slice (`stack.dense_slice_count`); homogeneous slices below it are O(Nh).
- **Arrays.** Array endpoints return uncompressed `.npz`: complex64 fields, uint8 material indices, and float64 axes in nm. GZip skips them, because float data barely compresses and gzip cost 50–150 ms per field plane. JSON responses are gzipped.
- **Live events.** `GET /api/events` (SSE) emits `snapshot`, `job` (≤10 per second while running), and `sweep-records`.
- **API models** live in `schemas.py`; all lengths are in nm.
  - `/api/project/check` returns domain problems in `errors`, so the editor can show them while typing.
  - View endpoints answer an invalid project with 422 `{detail: {errors: [...]}}`.
  - `/api/project/normalize` fills defaults and upgrades every opened file.
- **Python views (`python_views.py`).** `@python_view(id, title, needs="project"|"run")` functions return an ECharts option dict. They appear in the UI's "Python views" panel, so a new plot needs no TypeScript.

## Web UI (`web/`)

- **Stack** (see the ADR):
  - React 19 with TypeScript 6 and Vite 8.
  - shadcn/ui on Base UI ("Mira" preset, Hugeicons) and Tailwind 4.
  - ECharts 6 for charts and 2D maps; three.js (@react-three/fiber, drei) for 3D.
  - dockview for the workspace and AG Grid Community for tables.
  - zustand + immer for state, TanStack Query for server data.
- **Layout.** `src/api` (client, hooks, SSE, generated types), `src/state` (project store with patch undo, view settings, session), `src/lib` (npz, colormaps, colorize, field, stack), `src/viz` (EChart, Heatmap, Stack3D, theme), `src/panels`, `src/workspace`. View panels and the 3D view load lazily, and vendor libraries split into chunks in `vite.config.ts`.
- **Setup panel** (dock id `stack`, titled "Setup"): `panels/StackPanel.tsx` with its sections in `panels/stack/`.
  - Sections, in order: layer stack, pattern, illumination, accuracy, materials. Each header carries a live summary plus problem or warning badges; open/closed state lives in `state/view.ts` (`setup.open`).
  - The footer runs the project through `useRunControl` (shared with the top bar) and lists blocking problems; clicking one opens its section.
  - Pure logic is in `lib/stack.ts`, unit-tested in `lib/stack.test.ts`:
    - repeat-group blocks (mirroring `masksim.stack._layer_blocks`), and layer moves that step over whole groups instead of splitting them
    - propagating orders, in the solver's sign convention, and the minimum N that keeps them
    - `problemSection`, which maps `masksim.stack.validate()` messages to sections by their wording. Add a case and a test there when adding or rewording a message.
- **Pupil card modes.** "Pupil" plots direction cosines, where the orders form a lattice. "Camera" (`panels/PupilCamera.tsx`, math in `lib/camera.ts`) is the same orthographic projection taken along the camera axis, in the pupil's frame rotated by the minimal rotation from z (identical to the pupil at θ = 0), so scale, orientation and style match; at grazing incidence the lattice columns become arcs. The flat sensor (distance, size, aim) appears as its exact footprint, and on-sensor tests use the gnomonic projection. Both modes share `panels/orderMap.ts`. ECharts needs axes even before data arrives, or it throws and blanks the app.
- **Data flow.**
  - Project store edits produce TanStack Query keys from `physicsKey(project)`; geometry and ε refetch as you type.
  - Results are keyed by run id and never refetched.
  - Field quantities, time phase, colormaps and scales are computed in the browser (`lib/field`, `lib/colorize`), so they redraw instantly (60 fps phase animation).
  - Heatmaps are CPU-colorized canvases drawn by an ECharts custom series.
- **Gotchas:**
  - **Slider.** Base UI's `thumbAlignment="edge"` hides thumbs until measured, which never happens inside hidden dock panels, so `components/ui/slider.tsx` uses `center`. Slider widths need `data-horizontal:w-*` classes to override the component's `data-horizontal:w-full`.
  - **Design tokens** are OKLCH CSS variables (`src/index.css`). Canvas renderers get RGB through `viz/theme.ts`, which detects dark mode by watching the `<html>` class, because next-themes switches it after children render. AG Grid and dockview read the variables directly.
  - **AG Grid modules** are registered individually in `components/data-grid.tsx` (the full set is about 1.2 MB). A grid feature not yet used (filtering, CSV export, ...) needs its module added; development builds name missing modules in the console.
  - **Grid edits** use `readOnlyEdit` + `onCellEditRequest`, because rows come from an immer-frozen store.
  - **Element sizes.** `useElementSize()` returns a callback ref. Panels render their charts only once data arrives, and a RefObject read in a mount effect never measured them; that left the pupil plot at its 10 px minimum.
  - **Undo.** `editProject(recipe, key)` collapses edits with the same key within 1.2 s into one undo step.
  - **Persistence.**
    - The project autosaves to localStorage, and saving to a file is an explicit action.
    - View settings persist in localStorage (`state/view.ts`; a shallow merge gives new fields their defaults).
    - Run and sweep ids live in sessionStorage.
  - **Generated files** (`src/api/gen`, `openapi.json`) come from `pnpm api:gen`; never edit them by hand.

## Scatterometry image pipeline

`analyze_scatterometry.py` runs `load_config` → `detect_spots` → `spots_to_signal` → `save_csv` + `diagnostic_figure`.

- **Background.** Either uniform (median/MAD) or a 2D Legendre polynomial (total degree ≤ 12) fitted with iterative sigma clipping, optionally in log10 space. Noise is always re-estimated in linear intensity, and the detection threshold is `threshold_sigma × noise` above background.
- **Spots.** 8-connected components (pure-Python flood fill), sorted by x. Order 0 is the brightest spot, or the one nearest `zero_order_x`.
- **Differing defaults.** `detect_spots` and `estimate_background_map` default to `fit_domain="linear"`, while `load_config` and the JSON use `"log10"`. String options are validated in both `load_config` and the functions; update both when adding one.
