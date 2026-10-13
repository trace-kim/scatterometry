"""Background solver jobs: queueing, progress, cooperative cancellation, retention.

Jobs run on a small thread pool. NumPy/LAPACK release the GIL during the heavy
linear algebra, so the API stays responsive while a solve runs, and finished
solutions stay in this process for on-demand field evaluation. Cancellation is
cooperative: the solver's progress callback raises JobCancelled between steps.

Everything else talks to the JobManager interface, so moving the work into worker
processes later only touches this module.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, is_dataclass
from typing import Callable, List, Literal, Optional, Tuple

from masksim import Project, RunResult, solve_spec, sweep_records

from .events import EventBroker

log = logging.getLogger("maskserver.jobs")

JobKind = Literal["run", "sweep"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
FINISHED = ("done", "failed", "cancelled")
# Derived data kept per finished job. The UI's field views need a few MB; one amplitude
# grid at the largest allowed request size can reach a GB, and that is not kept.
CACHE_BYTES = 256 * 2**20


def _nbytes(value: object) -> int:
    """Array bytes in a cached value (an array or a dict of arrays)."""
    items = value.values() if isinstance(value, dict) else (value,)
    return sum(getattr(item, "nbytes", 0) for item in items)


def _array_bytes(root: object) -> int:
    """Bytes of the distinct arrays reachable from `root` through dataclasses, dicts, lists and tuples."""
    seen, total, stack = set(), 0, [root]
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        nbytes = getattr(obj, "nbytes", None)
        if isinstance(nbytes, int):
            total += nbytes
        elif isinstance(obj, dict):
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple)):
            stack.extend(obj)
        elif is_dataclass(obj) and not isinstance(obj, type) and hasattr(obj, "__dict__"):
            stack.extend(vars(obj).values())  # includes attributes set after construction
    return total


class JobCancelled(Exception):
    pass


class JobNotFound(KeyError):
    pass


@dataclass
class Job:
    id: str
    kind: JobKind
    project: Project
    params: dict = field(default_factory=dict)
    status: JobStatus = "queued"
    progress: float = 0.0
    message: str = "Queued"
    error: Optional[str] = None
    created: float = field(default_factory=time.time)
    started: Optional[float] = None
    finished: Optional[float] = None
    result: Optional[RunResult] = None
    result_bytes: int = 0  # arrays held by `result`, counted against the retention limit
    records: List[dict] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    last_emit: float = 0.0
    digest: str = ""
    cache: "OrderedDict[tuple, Tuple[object, int]]" = field(default_factory=OrderedDict, repr=False)  # value, bytes
    cache_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.digest = self.digest or self.project.digest()

    def cached(self, key: tuple, compute: Callable[[], object], size: int = 8) -> object:
        """Memoize derived data of a finished job (e.g. field amplitudes on a depth grid).

        Keeps at most `size` entries and CACHE_BYTES of arrays; a larger entry is
        returned without being kept. Requests run on a thread pool; the lock also stops
        two of them computing the same entry at once.
        """
        with self.cache_lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key][0]
            value = compute()
            nbytes = _nbytes(value)
            if nbytes <= CACHE_BYTES:
                self.cache[key] = (value, nbytes)
                while len(self.cache) > size or sum(n for _, n in self.cache.values()) > CACHE_BYTES:
                    self.cache.popitem(last=False)
            return value

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED

    def info(self) -> dict:
        """JSON-safe status (no result arrays)."""
        out = dict(
            id=self.id, kind=self.kind, status=self.status, progress=self.progress, message=self.message,
            error=self.error, created=self.created, started=self.started, finished=self.finished,
            project_digest=self.digest, params=self.params,
        )
        if self.result is not None:
            out["summary"] = self.result.summary
            out["check"] = self.result.check
        if self.kind == "sweep":
            out["record_count"] = len(self.records)
        return out


class JobManager:
    def __init__(self, broker: EventBroker, max_workers: int = 1, keep: int = 6,
                 keep_bytes: Optional[int] = None) -> None:
        """`keep` finished jobs are retained, fewer if their results exceed `keep_bytes`."""
        self._broker = broker
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="solver")
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._keep = max(1, keep)
        self._keep_bytes = float("inf") if keep_bytes is None else keep_bytes

    # ---- public interface -------------------------------------------------------

    def submit_run(self, project: Project, crosscheck: bool = False) -> Job:
        job = self._add(Job(id=_new_id(), kind="run", project=project, params=dict(crosscheck=crosscheck)))

        def work(job: Job) -> None:
            job.result = solve_spec(project.to_spec(), crosscheck=crosscheck, progress=self._progress(job))

        self._executor.submit(self._execute, job, work)
        return job

    def submit_sweep(self, project: Project, parameter: str, values: List[float]) -> Job:
        job = self._add(Job(id=_new_id(), kind="sweep", project=project,
                            params=dict(parameter=parameter, values=list(values))))

        def work(job: Job) -> None:
            for batch in sweep_records(project.to_spec(), parameter, values, progress=self._progress(job)):
                with self._lock:
                    job.records.extend(batch)
                self._broker.publish(dict(type="sweep-records", job_id=job.id, records=batch))

        self._executor.submit(self._execute, job, work)
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    def list(self, kind: Optional[JobKind] = None) -> List[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if kind is None or j.kind == kind]

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        job.cancel_event.set()
        if job.status == "queued":
            self._finish(job, "cancelled", "Cancelled")
        return job

    def remove(self, job_id: str) -> None:
        job = self.cancel(job_id)
        if job.is_finished:
            with self._lock:
                self._jobs.pop(job_id, None)

    def wait(self, job_id: str, timeout: float = 60.0) -> Job:
        """Block until the job finishes (tests and scripts)."""
        deadline = time.monotonic() + timeout
        job = self.get(job_id)
        while not job.is_finished:
            if time.monotonic() > deadline:
                raise TimeoutError(job_id)
            time.sleep(0.02)
        return job

    def shutdown(self) -> None:
        for job in self.list():
            job.cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ---- internals ------------------------------------------------------------------

    def _add(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
        self._emit(job, force=True)
        return job

    def _execute(self, job: Job, work: Callable[[Job], None]) -> None:
        if job.cancel_event.is_set():
            if not job.is_finished:
                self._finish(job, "cancelled", "Cancelled")
            return
        job.status, job.started, job.message = "running", time.time(), "Starting"
        self._emit(job, force=True)
        try:
            work(job)
        except JobCancelled:
            self._finish(job, "cancelled", "Cancelled")
        except Exception as exc:  # report every failure to the client
            log.error("job %s failed\n%s", job.id, traceback.format_exc())
            job.error = f"{type(exc).__name__}: {exc}"
            self._finish(job, "failed", "Failed")
        else:
            job.progress = 1.0
            job.result_bytes = _array_bytes(job.result) if job.result is not None else 0
            self._finish(job, "done", "Done")

    def _finish(self, job: Job, status: JobStatus, message: str) -> None:
        job.status, job.message, job.finished = status, message, time.time()
        self._emit(job, force=True)
        self._prune()

    def _progress(self, job: Job) -> Callable[[float, str], None]:
        def report(fraction: float, message: str) -> None:
            if job.cancel_event.is_set():
                raise JobCancelled(job.id)
            job.progress, job.message = max(job.progress, min(float(fraction), 1.0)), message
            self._emit(job)

        return report

    def _emit(self, job: Job, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - job.last_emit >= 0.1:
            job.last_emit = now
            self._broker.publish(dict(type="job", job=job.info()))

    def _prune(self) -> None:
        """Forget the oldest finished jobs beyond `keep`, or while their results exceed `keep_bytes`.

        The newest finished job always stays, so its results can still be viewed.
        """
        with self._lock:
            finished = sorted((j for j in self._jobs.values() if j.is_finished), key=lambda j: j.finished or 0.0)
            count, total = len(finished), sum(j.result_bytes for j in finished)
            for job in finished[:-1]:
                if count <= self._keep and total <= self._keep_bytes:
                    break
                self._jobs.pop(job.id, None)
                count, total = count - 1, total - job.result_bytes


def _new_id() -> str:
    return uuid.uuid4().hex[:12]
