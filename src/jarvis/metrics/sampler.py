"""Background machine-metrics sampler.

A plain object with a `tick()` the desktop drives from a QTimer (every ~20s), so
history accrues whenever Jarvis is running. Kept Qt-free and side-effect-light:
one snapshot, one row, failures swallowed so a transient probe error never
breaks the timer.
"""

from __future__ import annotations

import time
from typing import Callable

from jarvis.metrics.store import MetricsStore
from jarvis.tools.system_metrics import SystemMetricsProbe


class MetricsSampler:
    def __init__(self, probe: SystemMetricsProbe | None = None,
                 store: MetricsStore | None = None,
                 clock: Callable[[], float] | None = None):
        self.probe = probe if probe is not None else SystemMetricsProbe()
        self.store = store if store is not None else MetricsStore()
        self._clock = clock if clock is not None else time.time

    def available(self) -> bool:
        return self.probe.available()

    def tick(self) -> dict | None:
        """Record one sample. cpu_interval=None keeps it non-blocking (CPU is
        measured against the previous call). Returns the sample or None."""
        if not self.probe.available():
            return None
        try:
            sample = self.probe.snapshot(cpu_interval=None)
            self.store.record(sample)
            return sample
        except Exception:
            return None
