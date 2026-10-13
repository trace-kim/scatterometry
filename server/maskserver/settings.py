"""Server configuration; every field can be set with a MASKSIM_* environment variable."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MASKSIM_")

    host: str = "127.0.0.1"
    port: int = 8000
    # OpenBLAS's default thread count makes mid-size LU solves ~40x slower on this
    # class of machine; 4 threads is the measured sweet spot.
    blas_threads: int = 4
    max_jobs: int = 1        # solver jobs running at once; the rest queue
    keep_results: int = 6    # finished jobs kept in memory (2D solutions take tens of MB)
    web_dist: Optional[Path] = REPO_ROOT / "web" / "dist"  # built UI served at "/" when present
    cors_origins: List[str] = []
    # Requests over these limits are refused (HTTP 422/413) rather than exhausting memory.
    max_solve_gb: float = 12.0  # estimated peak of one solve (masksim.memory_estimate)
    max_body_mb: float = 8.0    # request bodies; project documents are a few kB
    # Finished runs' solutions are dropped oldest-first beyond this (the newest always stays).
    max_results_gb: float = 4.0
    request_threads: int = 8    # requests computed at once; bounds the memory of concurrent views

    @property
    def serves_web(self) -> bool:
        return self.web_dist is not None and (self.web_dist / "index.html").is_file()
