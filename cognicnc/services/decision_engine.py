"""Decision engine — converts raw model output into actionable decisions.

The engine combines:
* Failure probability from the supervised model.
* Anomaly flag from the Isolation Forest.
* Machine state from the simulator.

It produces:
* A risk level (LOW / WARNING / CRITICAL).
* A human-readable explanation.
* A recommended maintenance action.

Thresholds come from ``config/thresholds.yaml``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

from cognicnc.config import AppConfig
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.ml")


@dataclass
class DecisionResult:
    risk_level: str           # LOW | WARNING | CRITICAL
    failure_probability: float
    is_anomaly: bool
    explanation: str
    recommended_action: str


class DecisionEngine:
    """Combines model outputs into risk assessments and recommendations."""

    def __init__(self, config: AppConfig):
        thresholds = config.thresholds.get("thresholds", {})
        pred_cfg = config.thresholds.get("prediction", {})

        self.fail_warn = float(pred_cfg.get("failure_probability", {}).get("warning", 0.35))
        self.fail_crit = float(pred_cfg.get("failure_probability", {}).get("critical", 0.65))

        self.temp_warn = float(thresholds.get("temperature", {}).get("warning_c", 55.0)) + 273.15
        self.temp_crit = float(thresholds.get("temperature", {}).get("critical_c", 70.0)) + 273.15
        self.torque_warn = float(thresholds.get("torque", {}).get("warning_nm", 55.0))
        self.wear_warn = float(thresholds.get("tool_wear_minutes", {}).get("warning", 180))
        self.wear_crit = float(thresholds.get("tool_wear_minutes", {}).get("critical", 220))

    def evaluate(
        self,
        sample: TelemetrySample,
        prediction: Dict[str, Any],
    ) -> DecisionResult:
        """Evaluate a telemetry sample + prediction and return a decision."""
        fail_prob = prediction.get("failure_probability", 0.0)
        is_anomaly = prediction.get("is_anomaly", False)

        # --- Determine risk level ----------------------------------------
        risk_score = 0
        reasons = []

        if fail_prob >= self.fail_crit:
            risk_score += 3
            reasons.append(f"failure probability {fail_prob:.1%} exceeds critical threshold")
        elif fail_prob >= self.fail_warn:
            risk_score += 2
            reasons.append(f"failure probability {fail_prob:.1%} exceeds warning threshold")

        if is_anomaly:
            risk_score += 2
            reasons.append("anomaly detector flagged unusual operating pattern")

        if sample.process_temperature_k > self.temp_crit:
            risk_score += 2
            reasons.append(f"process temperature {sample.process_temperature_k - 273.15:.1f} C exceeds critical limit")
        elif sample.process_temperature_k > self.temp_warn:
            risk_score += 1
            reasons.append(f"process temperature {sample.process_temperature_k - 273.15:.1f} C exceeds warning limit")

        if sample.torque_nm > self.torque_warn:
            risk_score += 1
            reasons.append(f"torque {sample.torque_nm:.1f} Nm exceeds warning limit")

        if sample.tool_wear_min > self.wear_crit:
            risk_score += 2
            reasons.append(f"tool wear {sample.tool_wear_min:.0f} min exceeds critical limit")
        elif sample.tool_wear_min > self.wear_warn:
            risk_score += 1
            reasons.append(f"tool wear {sample.tool_wear_min:.0f} min exceeds warning limit")

        if sample.state == "FAULT":
            risk_score += 3
            reasons.append("machine is in FAULT state")

        # Map score to level
        if risk_score >= 5:
            risk_level = "CRITICAL"
        elif risk_score >= 2:
            risk_level = "WARNING"
        else:
            risk_level = "LOW"

        # --- Explanation -------------------------------------------------
        if reasons:
            explanation = "Risk elevated: " + "; ".join(reasons) + "."
        else:
            explanation = "All parameters within normal operating range."

        # --- Recommended action ------------------------------------------
        action = self._recommend_action(risk_level, sample, fail_prob, is_anomaly)

        return DecisionResult(
            risk_level=risk_level,
            failure_probability=fail_prob,
            is_anomaly=is_anomaly,
            explanation=explanation,
            recommended_action=action,
        )

    def _recommend_action(
        self,
        risk_level: str,
        sample: TelemetrySample,
        fail_prob: float,
        is_anomaly: bool,
    ) -> str:
        if risk_level == "CRITICAL":
            if sample.state == "FAULT":
                return "Immediate shutdown required. Schedule emergency maintenance."
            if sample.tool_wear_min > self.wear_crit:
                return "Replace cutting tool immediately. Schedule maintenance window."
            return "Reduce load and schedule immediate inspection. High failure risk."

        if risk_level == "WARNING":
            actions = []
            if sample.tool_wear_min > self.wear_warn:
                actions.append("plan tool replacement within next shift")
            if sample.process_temperature_k > self.temp_warn:
                actions.append("check coolant flow and reduce feed rate")
            if is_anomaly:
                actions.append("inspect machine for unusual vibration or noise")
            if fail_prob >= self.fail_warn:
                actions.append("increase monitoring frequency")
            if actions:
                return "Warning: " + "; ".join(actions) + "."
            return "Monitor closely. Parameters approaching warning thresholds."

        return "No action required. Continue normal operation."