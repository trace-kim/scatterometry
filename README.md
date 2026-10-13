# Scatterometry and mask simulation

This repository holds tools for EUV photomask scatterometry:
- an RCWA solver (`rcwa/rcwa`)
- a photomask simulation layer (`rcwa/masksim`)
- camera-image analysis for measured diffraction spots (`rcwa/analyze_scatterometry.py`)
- a web-based **mask simulator** (`server/` + `web/`)

## Mask simulator

What you can do:
- Define a photomask stack: materials with n/k, layers, repeated groups such as Mo/Si pairs, line/space or contact-hole patterns, and sidewall angles cut into staircase steps.
- Look at the geometry in 2D and 3D, and at the permittivity both exact and as RCWA sees it.
- Solve it, then inspect:
  - diffraction orders, with the pupil and the projection NA
  - fields inside the mask, including an animated time phase
  - power flow and absorption per layer
  - parameter sweeps

### Run it

Requirements: Python 3.12+ (the repo uses `.venv` with uv) and Node 22 with pnpm.

```powershell
.venv\Scripts\python.exe -m pip install uv           # once, if uv is missing
.venv\Scripts\uv.exe sync --inexact --all-packages   # Python packages (editable)
cd web; pnpm install; pnpm build; cd ..              # build the UI once
.venv\Scripts\python.exe -m maskserver               # opens http://127.0.0.1:8000
```

`python -m maskserver --host 0.0.0.0` makes it reachable from other machines on the network. Runs and their results live in the server's memory until it restarts. Projects are saved as `.masksim.json` files from the File menu, and the browser also keeps an autosave.

### Develop

- **UI with hot reload:** run `python -m maskserver --no-browser --reload`, and in `web/` run `pnpm dev`, then open http://localhost:5180.
- **Tests:** `python -m pytest -q`; in `web/`, `pnpm test` and `pnpm test:e2e`.
- **Adding a plot without TypeScript:** write a function in `server/maskserver/python_views.py`.

See `CLAUDE.md` for architecture and conventions, and `docs/adr/0001-ui-stack.md` for why the stack is what it is.
