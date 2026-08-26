# Repository Guidelines

## Project Structure & Module Organization

The implementation lives under `rcwa/rcwa/`. Core data models are in `models.py`; `solver.py` coordinates wave-vector expansion, convolution matrices, eigenmodes, S-matrices, fields, and efficiency calculations. `backend.py` selects NumPy or an available CUDA-backed CuPy installation. Public imports are collected in `rcwa/rcwa/__init__.py`. At `rcwa/`, `compare_rcwa_fresnel.py` is the main numerical validation script, while `main.py` is an interactive EUV simulation and plotting example. There is currently no dedicated `tests/` or assets directory. Do not commit generated `__pycache__/` files.

## Setup, Validation, and Development Commands

Run commands from the repository root unless noted:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install numpy matplotlib pytest
cd rcwa
python -m pytest -q
python compare_rcwa_fresnel.py
python main.py
python -m compileall rcwa
```

Pytest runs the automated regression suite. The comparison script checks homogeneous RCWA results against Fresnel/TMM calculations. `main.py` runs an angle sweep and opens Matplotlib windows. `compileall` provides a quick syntax/import-tree check. CuPy is optional and detected automatically; set `RCWA_GPU_REQUIRED=1` only when a missing GPU should be treated as an error.

## Coding Style & Naming Conventions

Use Python with four-space indentation and PEP 8 spacing. Follow the existing conventions: `snake_case` for functions and variables, leading underscores for internal helpers, `PascalCase` for dataclasses and solver types, and uppercase names for fixed simulation constants. Add type hints to new public APIs and short module/class docstrings where behavior is not obvious. Keep backend-sensitive array operations on the module returned by `get_array_module()` rather than importing NumPy inside solver internals.

## Testing Guidelines

No automated test framework or coverage threshold is configured. For every numerical change, run `compare_rcwa_fresnel.py` and inspect RCWA/Fresnel differences plus power conservation (`R + T`, allowing absorption where applicable). New tests should use `pytest`, live in `rcwa/tests/`, and be named `test_<behavior>.py`; favor small zero-order cases with explicit tolerances.

## Numerical Conventions

Use SI units for documented examples and radians for angles passed to APIs. Lossy media follow `n_complex = n - i*k`, so loss gives a negative imaginary permittivity. The `nk_to_n` and `nk_to_eps` helpers accept either sign for `k` and normalize it to a passive medium. Preserve harmonic ordering and array shapes when modifying matrix routines.

## Commit & Pull Request Guidelines

No Git history is available in this checkout. Use concise, imperative commit subjects, optionally scoped (for example, `solver: stabilize evanescent modes`). Pull requests should explain the physical or numerical change, list validation commands and tolerances, link related issues, and attach plots only when output curves or visualization behavior changes.
