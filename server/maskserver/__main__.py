"""Command line entry point: `python -m maskserver` (or the `maskserver` script)."""
from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path
from typing import List, Optional

from .settings import REPO_ROOT, Settings


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="maskserver", description="Serve the RCWA mask simulator (API and web UI).")
    parser.add_argument("--host", help="interface to bind (default 127.0.0.1; 0.0.0.0 shares it on the network)")
    parser.add_argument("--port", type=int, help="port (default 8000)")
    parser.add_argument("--blas-threads", type=int, help="BLAS threads per solve (default 4)")
    parser.add_argument("--max-jobs", type=int, help="solver jobs running at once (default 1)")
    parser.add_argument("--max-solve-gb", type=float, help="refuse solves estimated to need more memory (default 12)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the UI in a browser")
    parser.add_argument("--reload", action="store_true", help="restart on Python source changes (development)")
    args = parser.parse_args(argv)

    # The app is built by uvicorn (possibly in a reloader subprocess), so options travel
    # as the MASKSIM_* environment variables that Settings reads.
    for name, value in (("HOST", args.host), ("PORT", args.port), ("BLAS_THREADS", args.blas_threads),
                        ("MAX_JOBS", args.max_jobs), ("MAX_SOLVE_GB", args.max_solve_gb)):
        if value is not None:
            os.environ[f"MASKSIM_{name}"] = str(value)
    settings = Settings()

    import uvicorn

    url = f"http://{'127.0.0.1' if settings.host in ('0.0.0.0', '::') else settings.host}:{settings.port}/"
    if settings.serves_web and not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    note = "" if settings.serves_web else "  (API only: build the UI with `pnpm build` in web/)"
    print(f"Mask simulator at {url}{note}")
    uvicorn.run(
        "maskserver.app:create_app", factory=True, host=settings.host, port=settings.port,
        reload=args.reload, reload_dirs=[str(Path(__file__).parent), str(REPO_ROOT / "rcwa")] if args.reload else None,
        log_level="info",
    )


if __name__ == "__main__":
    main()
