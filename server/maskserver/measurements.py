"""Uploaded measurement files (CCD frames), kept in memory like finished runs.

Arrays are read-only views of the uploaded bytes, so a measurement costs about its file
size. The oldest are dropped once the total exceeds the budget (the newest always stays);
a server restart forgets them all, and the UI then clears its stale selection.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, TypeVar

from masksim.spe import SpeFile

T = TypeVar("T")


class MeasurementNotFound(KeyError):
    pass


@dataclass(eq=False)
class Measurement:
    id: str
    name: str
    size_bytes: int
    spe: SpeFile
    created: float = field(default_factory=time.time)
    _cache: Dict[object, object] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def cached(self, key: object, compute: Callable[[], T]) -> T:
        """Derived data (frame averages, traces) computed once per measurement."""
        with self._lock:
            if key in self._cache:
                return self._cache[key]  # type: ignore[return-value]
        value = compute()
        with self._lock:
            return self._cache.setdefault(key, value)  # type: ignore[return-value]


class MeasurementStore:
    def __init__(self, keep_bytes: int) -> None:
        self.keep_bytes = keep_bytes
        self._items: "OrderedDict[str, Measurement]" = OrderedDict()
        self._lock = threading.Lock()

    def add(self, name: str, spe: SpeFile, size_bytes: int) -> Measurement:
        item = Measurement(id=uuid.uuid4().hex[:12], name=name, size_bytes=size_bytes, spe=spe)
        with self._lock:
            self._items[item.id] = item
            total = sum(m.size_bytes for m in self._items.values())
            while total > self.keep_bytes and len(self._items) > 1:
                _, dropped = self._items.popitem(last=False)
                total -= dropped.size_bytes
        return item

    def get(self, measurement_id: str) -> Measurement:
        with self._lock:
            try:
                return self._items[measurement_id]
            except KeyError:
                raise MeasurementNotFound(measurement_id) from None

    def list(self) -> List[Measurement]:
        with self._lock:
            return list(self._items.values())

    def remove(self, measurement_id: str) -> None:
        with self._lock:
            if self._items.pop(measurement_id, None) is None:
                raise MeasurementNotFound(measurement_id)
