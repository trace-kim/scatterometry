"""Solve and sweep orchestration with progress reporting (UI-agnostic).

`progress(fraction, message)` callbacks may raise to abort; job runners use that for
cancellation. Nothing here knows about threads, HTTP, or the UI.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence

import numpy as np

from rcwa import NearFieldSolution, NearFieldSolver, RCWASolver

from .stack import MaskSpec, Slice, build_problem, build_slices, with_parameter

ProgressFn = Callable[[float, str], None]


def _noop(fraction: float, message: str) -> None:
    pass


@dataclass
class RunResult:
    """A solved mask: one NearFieldSolution per polarization, sharing one slicing."""
    spec: MaskSpec
    slices: List[Slice]
    solutions: Dict[str, NearFieldSolution]
    elapsed: float
    check: Optional[dict] = None
    summary: dict = field(default_factory=dict)


def solve_spec(spec: MaskSpec, *, crosscheck: bool = False, progress: Optional[ProgressFn] = None) -> RunResult:
    """Solve every polarization of `spec`, optionally cross-checking against RCWASolver."""
    report = progress or _noop
    slices = build_slices(spec)
    pols = spec.polarizations()
    share = 0.9 if crosscheck else 1.0
    solutions: Dict[str, NearFieldSolution] = {}
    t0 = time.perf_counter()
    for i, pol in enumerate(pols):
        def sub(fraction: float, message: str, i: int = i, pol: str = pol) -> None:
            report(share * (i + fraction) / len(pols), f"{pol}: {message}")

        solutions[pol] = NearFieldSolver().solve(build_problem(spec, pol, slices), progress=sub)
    elapsed = time.perf_counter() - t0

    check = None
    if crosscheck:
        report(share, "Cross-check with RCWASolver")
        pol = pols[0]
        t1 = time.perf_counter()
        reference = RCWASolver().solve(build_problem(spec, pol, slices))["efficiencies"]
        ours = solutions[pol].result["efficiencies"]
        check = dict(pol=pol, seconds=time.perf_counter() - t1,
                     dR=float(np.max(np.abs(reference["R"] - ours["R"]))),
                     dT=float(np.max(np.abs(reference["T"] - ours["T"]))))
    report(1.0, "Done")

    summary = dict(
        elapsed=elapsed,
        power={pol: {k: float(sol.result["power"][k]) for k in ("R_total", "T_total", "A_total")}
               for pol, sol in solutions.items()},
        harmonics=int(next(iter(solutions.values())).Kx.size),
        slices=len(slices),
    )
    return RunResult(spec, slices, solutions, elapsed, check, summary)


def sweep_records(spec: MaskSpec, key: str, values: Sequence[float], *,
                  progress: Optional[ProgressFn] = None) -> Iterator[List[dict]]:
    """Solve `spec` with parameter `key` set to each value; yield that value's records.

    Records hold the reflected efficiency of every order (m, n) per polarization, the
    phase of the order's own TE (or TM) amplitude, and one total row with m = n = None.
    """
    report = progress or _noop
    n_values = max(len(values), 1)
    for i, value in enumerate(values):
        s_spec = with_parameter(spec, key, float(value))
        pols = s_spec.polarizations()
        records: List[dict] = []
        for j, pol in enumerate(pols):
            def sub(fraction: float, message: str, i: int = i, j: int = j, n_pols: int = len(pols),
                    value: float = value) -> None:
                report((i + (j + fraction) / n_pols) / n_values, f"{key} = {value:g}: {message}")

            sol = NearFieldSolver().solve(build_problem(s_spec, pol), keep_fields=False, progress=sub)
            res, table = sol.result, sol.order_table()
            h = res["harmonics"]
            amp = table["r_te"] if pol == "TE" else table["r_tm"]
            R = np.real(res["efficiencies"]["R"])
            for k, (m, n) in enumerate(zip(h["mx"], h["my"], strict=True)):
                phase = float(np.degrees(np.angle(amp[k]))) if np.isfinite(amp[k]) else None
                records.append(dict(value=float(value), pol=pol, m=int(m), n=int(n), R=float(R[k]), phase_deg=phase))
            records.append(dict(value=float(value), pol=pol, m=None, n=None,
                                R=float(res["power"]["R_total"]), phase_deg=None))
        yield records
