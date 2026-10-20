"""On-demand anomaly check: "is anything abnormal on my Mac / in my usage?".

Runs the same explainable rules as the desktop's proactive monitor, without
cooldown, so the answer reflects the current state. Local and read-only.
"""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.insights.detector import InsightDetector
from jarvis.metrics.store import MetricsStore
from jarvis.tools.system_metrics import SystemMetricsProbe
from jarvis.usage.store import UsageStore


class InsightsCapability:
    def __init__(self, detector: InsightDetector | None = None):
        if detector is None:
            detector = InsightDetector(metrics=MetricsStore(), usage=UsageStore(),
                                       probe=SystemMetricsProbe())
        self.detector = detector

    def check(self, include_tokens: bool = True) -> ToolResult:
        try:
            found = self.detector.scan(include_tokens=bool(include_tokens))
        except Exception as error:
            return ToolResult.failure("check_anomalies", f"Vérification impossible : {error}",
                                      error_code="insights_unavailable")
        if not found:
            return ToolResult.success(
                "check_anomalies",
                "Rien d'anormal : processeur, mémoire, disque et consommation de "
                "tokens sont dans les clous.",
                insights=[])
        message = " ".join(i.message for i in found)
        return ToolResult.success("check_anomalies", message,
                                  insights=[i.to_dict() for i in found])
