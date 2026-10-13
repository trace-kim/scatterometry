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

    @property
    def serves_web(self) -> bool:
        return self.web_dist is not None and (self.web_dist / "index.html").is_file()
