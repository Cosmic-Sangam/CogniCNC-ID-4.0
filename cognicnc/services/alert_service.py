# """Alert service — creates and manages alerts based on decision engine output.

# The service:
# 1. Receives a ``DecisionResult`` from the ``DecisionEngine``.
# 2. Determines whether an alert is warranted (WARNING or CRITICAL).
# 3. Delegates to the ``Repository`` for deduplication-aware storage.
# """

# from __future__ import annotations

# import logging
# from typing import Optional

# from cognicnc.config import AppConfig
# from cognicnc.database.repository import Repository
# from cognicnc.services.decision_engine import DecisionResult
# from cognicnc.simulator.telemetry import TelemetrySample

# logger = logging.getLogger("cognicnc.ml")


# class AlertService:
#     """Generates and persists alerts from decision engine results."""

#     def __init__(self, config: AppConfig, repository: Repository):
#         self.config = config
#         self.repo = repository
#         alerting_cfg = config.thresholds.get("alerting", {})
#         self.dedup_window = int(alerting_cfg.get("dedup_window_seconds", 30))

#     def process(
#         self,
#         sample: TelemetrySample,
#         decision: DecisionResult,
#     ) -> Optional[int]:
#         """Evaluate a decision and create an alert if warranted.

#         Returns the alert ID if created, None if no alert or deduplicated.
#         """
#         if decision.risk_level == "LOW":
#             return None

#         severity = decision.risk_level  # WARNING or CRITICAL
#         category = self._categorize(sample, decision)
#         model_output = (
#             f"fail_prob={decision.failure_probability:.3f}, "
#             f"anomaly={decision.is_anomaly}"
#         )

#         created = self.repo.create_alert(
#             timestamp=sample.timestamp,
#             machine_id=sample.machine_id,
#             severity=severity,
#             category=category,
#             message=decision.explanation,
#             model_output=model_output,
#             recommended_action=decision.recommended_action,
#             dedup_window_seconds=self.dedup_window,
#         )

#         if created:
#             logger.info(
#                 "Alert [%s] %s: %s", severity, sample.machine_id, category
#             )
#             return 1  # Simplified — real ID would require returning from repo
#         return None

#     def _categorize(self, sample: TelemetrySample, decision: DecisionResult) -> str:
#         """Determine the alert category from the decision context."""
#         if sample.state == "FAULT":
#             return "MACHINE_FAULT"
#         if decision.is_anomaly and decision.failure_probability > 0.5:
#             return "ANOMALY_HIGH_RISK"
#         if decision.is_anomaly:
#             return "ANOMALY_DETECTED"
#         if sample.tool_wear_min > 180:
#             return "TOOL_WEAR"
#         if sample.process_temperature_k > 328:  # ~55 C
#             return "OVERHEATING"
#         if sample.torque_nm > 55:
#             return "HIGH_TORQUE"
#         if decision.failure_probability > 0.35:
#             return "FAILURE_RISK"
#         return "GENERAL_WARNING"









"""Alert service — creates and manages alerts based on decision engine output.

The service:
1. Receives a ``DecisionResult`` from the ``DecisionEngine``.
2. Determines whether an alert is warranted (WARNING or CRITICAL).
3. Delegates to the ``Repository`` for deduplication-aware storage.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from cognicnc.config import AppConfig
from cognicnc.database.repository import Repository
from cognicnc.services.decision_engine import DecisionResult
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.ml")


def _get_val(obj: Any, *keys: str, default: Any = 0.0) -> Any:
    """Safe helper to extract fields from dicts or objects with multiple potential property names."""
    if obj is None:
        return default
    for key in keys:
        if isinstance(obj, dict) and key in obj:
            return obj[key]
        if hasattr(obj, key):
            val = getattr(obj, key)
            if hasattr(val, "value"):  # Handle Enums like MachineState
                return val.value
            return val
    return default


class AlertService:
    """Generates and persists alerts from decision engine results."""

    def __init__(self, config: AppConfig, repository: Repository):
        self.config = config
        self.repo = repository
        
        alerting_cfg = {}
        if hasattr(config, "thresholds") and isinstance(config.thresholds, dict):
            alerting_cfg = config.thresholds.get("alerting", {})
        elif hasattr(config, "settings") and isinstance(config.settings, dict):
            alerting_cfg = config.settings.get("alerting", {})
            
        self.dedup_window = int(alerting_cfg.get("dedup_window_seconds", 30))

    def process(
        self,
        sample: Any,
        decision: DecisionResult,
    ) -> Optional[int]:
        """Evaluate a decision and create an alert if warranted.

        Returns 1 if created, None if no alert (LOW risk) or deduplicated.
        """
        risk_level = getattr(decision, "risk_level", "LOW")
        if risk_level == "LOW":
            return None

        severity = risk_level  # WARNING or CRITICAL
        category = self._categorize(sample, decision)
        
        fail_prob = getattr(decision, "failure_probability", 0.0)
        is_anomaly = getattr(decision, "is_anomaly", False)

        model_output = (
            f"fail_prob={fail_prob:.3f}, "
            f"anomaly={is_anomaly}"
        )

        timestamp = str(_get_val(sample, "timestamp", "timestamp_iso", default=""))
        machine_id = str(_get_val(sample, "machine_id", default="UNKNOWN"))
        explanation = str(getattr(decision, "explanation", "Elevated operational risk detected."))
        action = str(getattr(decision, "recommended_action", "Inspect machine operating parameters."))

        created = self.repo.create_alert(
            timestamp=timestamp,
            machine_id=machine_id,
            severity=severity,
            category=category,
            message=explanation,
            model_output=model_output,
            recommended_action=action,
            dedup_window_seconds=self.dedup_window,
        )

        if created:
            logger.info("Alert [%s] %s: %s", severity, machine_id, category)
            return 1
        return None

    def _categorize(self, sample: Any, decision: DecisionResult) -> str:
        """Determine the alert category safely from the decision and telemetry context."""
        state = str(_get_val(sample, "state", default="RUNNING")).upper()
        tool_wear = float(_get_val(sample, "tool_wear_min", "tool_wear", default=0.0))
        temp_k = float(_get_val(sample, "process_temperature_k", "process_temp", "Process temperature [K]", default=300.0))
        torque = float(_get_val(sample, "torque_nm", "torque", "Torque [Nm]", default=40.0))
        
        fail_prob = float(getattr(decision, "failure_probability", 0.0))
        is_anomaly = bool(getattr(decision, "is_anomaly", False))

        if state == "FAULT":
            return "MACHINE_FAULT"
        if is_anomaly and fail_prob > 0.5:
            return "ANOMALY_HIGH_RISK"
        if is_anomaly:
            return "ANOMALY_DETECTED"
        if tool_wear > 180:
            return "TOOL_WEAR"
        if temp_k > 328:  # ~55 C (328.15 K)
            return "OVERHEATING"
        if torque > 55:
            return "HIGH_TORQUE"
        if fail_prob > 0.35:
            return "FAILURE_RISK"
        return "GENERAL_WARNING"