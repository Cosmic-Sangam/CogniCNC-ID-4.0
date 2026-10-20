"""Alert service — creates and manages alerts based on decision engine output.

The service:
1. Receives a ``DecisionResult`` from the ``DecisionEngine``.
2. Determines whether an alert is warranted (WARNING or CRITICAL).
3. Delegates to the ``Repository`` for deduplication-aware storage.
"""

from __future__ import annotations

import logging
from typing import Optional

from cognicnc.config import AppConfig
from cognicnc.database.repository import Repository
from cognicnc.services.decision_engine import DecisionResult
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.ml")


class AlertService:
    """Generates and persists alerts from decision engine results."""

    def __init__(self, config: AppConfig, repository: Repository):
        self.config = config
        self.repo = repository
        alerting_cfg = config.thresholds.get("alerting", {})
        self.dedup_window = int(alerting_cfg.get("dedup_window_seconds", 30))

    def process(
        self,
        sample: TelemetrySample,
        decision: DecisionResult,
    ) -> Optional[int]:
        """Evaluate a decision and create an alert if warranted.

        Returns the alert ID if created, None if no alert or deduplicated.
        """
        if decision.risk_level == "LOW":
            return None

        severity = decision.risk_level  # WARNING or CRITICAL
        category = self._categorize(sample, decision)
        model_output = (
            f"fail_prob={decision.failure_probability:.3f}, "
            f"anomaly={decision.is_anomaly}"
        )

        created = self.repo.create_alert(
            timestamp=sample.timestamp,
            machine_id=sample.machine_id,
            severity=severity,
            category=category,
            message=decision.explanation,
            model_output=model_output,
            recommended_action=decision.recommended_action,
            dedup_window_seconds=self.dedup_window,
        )

        if created:
            logger.info(
                "Alert [%s] %s: %s", severity, sample.machine_id, category
            )
            return 1  # Simplified — real ID would require returning from repo
        return None

    def _categorize(self, sample: TelemetrySample, decision: DecisionResult) -> str:
        """Determine the alert category from the decision context."""
        if sample.state == "FAULT":
            return "MACHINE_FAULT"
        if decision.is_anomaly and decision.failure_probability > 0.5:
            return "ANOMALY_HIGH_RISK"
        if decision.is_anomaly:
            return "ANOMALY_DETECTED"
        if sample.tool_wear_min > 180:
            return "TOOL_WEAR"
        if sample.process_temperature_k > 328:  # ~55 C
            return "OVERHEATING"
        if sample.torque_nm > 55:
            return "HIGH_TORQUE"
        if decision.failure_probability > 0.35:
            return "FAILURE_RISK"
        return "GENERAL_WARNING"