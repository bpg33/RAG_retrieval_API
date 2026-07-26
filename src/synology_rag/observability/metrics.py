"""Lightweight in-process metrics.

Phase 1 records summary statistics locally (no external metrics backend, no
Redis). Values are approximate and intended for local operability, not billing.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _Histogram:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def observe(self, value_ms: float) -> None:
        self.count += 1
        self.total_ms += value_ms
        self.max_ms = max(self.max_ms, value_ms)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


@dataclass
class Metrics:
    """Thread-safe counters and latency histograms."""

    _counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _histograms: dict[str, _Histogram] = field(default_factory=lambda: defaultdict(_Histogram))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe_ms(self, name: str, value_ms: float) -> None:
        with self._lock:
            self._histograms[name].observe(value_ms)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "latency_ms": {
                    name: {
                        "count": hist.count,
                        "avg": round(hist.avg_ms, 2),
                        "max": round(hist.max_ms, 2),
                    }
                    for name, hist in self._histograms.items()
                },
            }


metrics = Metrics()
