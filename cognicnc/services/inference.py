"""ML Inference Service — Failure prediction and anomaly detection.

Wraps the trained scikit-learn pipelines and provides a unified
prediction interface for the dashboard and decision engine.

Graceful degradation: if model artifacts are missing, returns safe
default predictions instead of crashing the application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields as dc_fields
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from cognicnc.config import AppConfig
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.inference")

# Feature columns matching the UCI AI4I 2020 training schema
FEATURE_COLUMNS = [
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

# Type encoding (must match training)
TYPE_MAP = {"L": 0, "M": 1, "H": 2}

# Nominal ranges from AI4I dataset (for explanation)
NOMINAL_RANGES = {
    "Air temperature [K]": (295.0, 305.0),
    "Process temperature [K]": (305.0, 315.0),
    "Rotational speed [rpm]": (1168.0, 2886.0),
    "Torque [Nm]": (3.8, 76.6),
    "Tool wear [min]": (0.0, 253.0),
}


@dataclass
class PredictionResult:
    """Container for inference output.

    Supports BOTH attribute access (pred.failure_probability)
    AND dict-style access (pred["failure_probability"], pred.get(...),
    "failure_probability" in pred) so all existing code works unchanged.

    Also proxies into feature_values so pred["Type"] works.
    """
    failure_probability: float = 0.0
    anomaly_score: float = 0.0
    is_anomaly: bool = False
    risk_level: str = "LOW"
    feature_values: Dict[str, Any] = field(default_factory=dict)
    feature_deviations: Dict[str, str] = field(default_factory=dict)
    model_loaded: bool = True
    explanation: str = ""

    def __getitem__(self, key: str) -> Any:
        # 1. Check own attributes first
        if hasattr(self, key):
            return getattr(self, key)
        # 2. Fall back to feature_values dict
        if key in self.feature_values:
            return self.feature_values[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.feature_values.get(key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key) or key in self.feature_values

    def __iter__(self):
        for f in dc_fields(self):
            yield f.name

    def keys(self):
        return [f.name for f in dc_fields(self)]


class InferenceService:
    """Unified ML inference for failure prediction and anomaly detection."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._failure_pipeline = None
        self._failure_meta: Dict[str, Any] = {}
        self._anomaly_model = None
        self._anomaly_meta: Dict[str, Any] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Load trained model artifacts from disk."""
        from cognicnc.models.train_failure import load_failure_pipeline
        from cognicnc.models.train_anomaly import load_anomaly_model

        project_root = Path(__file__).resolve().parent.parent.parent

        pm_dir = project_root / "artifacts" / "predictive_maintenance"
        ad_dir = project_root / "artifacts" / "anomaly_detection"

        try:
            self._failure_pipeline, self._failure_meta = load_failure_pipeline(pm_dir)
            logger.info("Failure prediction pipeline loaded from %s", pm_dir)
        except FileNotFoundError as e:
            logger.warning("Failure model not found: %s", e)
            self._failure_pipeline = None

        try:
            self._anomaly_model, self._anomaly_meta = load_anomaly_model(ad_dir)
            logger.info("Anomaly detection model loaded from %s", ad_dir)
        except FileNotFoundError as e:
            logger.warning("Anomaly model not found: %s", e)
            self._anomaly_model = None

        self._loaded = (
            self._failure_pipeline is not None
            or self._anomaly_model is not None
        )

        if self._loaded:
            logger.info("InferenceService ready (failure=%s, anomaly=%s)",
                        self._failure_pipeline is not None,
                        self._anomaly_model is not None)
        else:
            logger.warning(
                "InferenceService running in DEMO MODE — no trained models. "
                "Run 'python scripts/train_models.py' to train."
            )

    def _extract_features(self, sample: TelemetrySample) -> Dict[str, Any]:
        """Extract the 6 ML features from a telemetry sample."""
        if hasattr(sample, "to_model_features"):
            return sample.to_model_features()

        return {
            "Type": getattr(sample, "model_type", "M"),
            "Air temperature [K]": getattr(sample, "air_temperature_k", 300.0),
            "Process temperature [K]": getattr(sample, "process_temperature_k", 310.0),
            "Rotational speed [rpm]": getattr(sample, "rotational_speed_rpm", 1500.0),
            "Torque [Nm]": getattr(sample, "torque_nm", 40.0),
            "Tool wear [min]": getattr(sample, "tool_wear_min", 50.0),
        }

    def _compute_deviations(self, features: Dict[str, Any]) -> Dict[str, str]:
        """Compare feature values against nominal AI4I ranges."""
        deviations = {}
        for feat_name, (low, high) in NOMINAL_RANGES.items():
            val = features.get(feat_name)
            if val is None:
                continue
            val = float(val)
            if val > high * 1.05:
                deviations[feat_name] = f"⬆ HIGH ({val:.1f}, limit {high:.1f})"
            elif val < low * 0.95:
                deviations[feat_name] = f"⬇ LOW ({val:.1f}, limit {low:.1f})"
            else:
                deviations[feat_name] = f"✓ Normal ({val:.1f})"
        return deviations

    def _default_prediction(self, sample: TelemetrySample) -> PredictionResult:
        """Return a rule-based fallback prediction when models aren't loaded."""
        features = self._extract_features(sample)
        deviations = self._compute_deviations(features)

        risk_score = 0.0
        process_temp = float(features.get("Process temperature [K]", 310.0))
        torque = float(features.get("Torque [Nm]", 40.0))
        tool_wear = float(features.get("Tool wear [min]", 50.0))

        if process_temp > 313.0:
            risk_score += 0.3
        if process_temp > 318.0:
            risk_score += 0.3
        if torque > 60.0:
            risk_score += 0.2
        if tool_wear > 180.0:
            risk_score += 0.2
        if tool_wear > 220.0:
            risk_score += 0.2

        risk_score = min(risk_score, 1.0)

        if risk_score > 0.6:
            risk_level = "CRITICAL"
        elif risk_score > 0.3:
            risk_level = "WARNING"
        else:
            risk_level = "LOW"

        numeric_features = {
            k: (str(features.get(k, "M")) if k == "Type" else float(v))
            for k, v in features.items()
            if k in FEATURE_COLUMNS
        }

        return PredictionResult(
            failure_probability=risk_score,
            anomaly_score=0.0,
            is_anomaly=risk_score > 0.5,
            risk_level=risk_level,
            feature_values=numeric_features,
            feature_deviations=deviations,
            model_loaded=False,
            explanation=(
                "⚠️ DEMO MODE: Rule-based estimation (no trained model). "
                "Run 'python scripts/train_models.py' for ML predictions."
            ),
        )

    def predict(self, sample: TelemetrySample) -> PredictionResult:
        """Run inference on a single telemetry sample."""
        if not self._loaded:
            try:
                self.load()
            except Exception as e:
                logger.debug("Model load failed: %s. Using fallback.", e)

        if not self._loaded:
            return self._default_prediction(sample)

        features = self._extract_features(sample)
        deviations = self._compute_deviations(features)

        # Build feature dict with proper numeric float conversions for sklearn pipeline
        feature_dict: Dict[str, float] = {}
        for col in FEATURE_COLUMNS:
            val = features.get(col, 0)
            if col == "Type":
                feature_dict[col] = float(TYPE_MAP.get(str(val), 1))
            else:
                feature_dict[col] = float(val)

        # Create DataFrame with explicit float64 casting to prevent isnan errors
        X = pd.DataFrame([feature_dict], columns=FEATURE_COLUMNS).astype(float)

        # --- Failure Prediction ---
        failure_prob = 0.0
        if self._failure_pipeline is not None:
            try:
                proba = self._failure_pipeline.predict_proba(X)
                failure_prob = float(proba[0][1]) if proba.shape[1] > 1 else float(proba[0][0])
            except Exception as e:
                logger.warning("Failure prediction error: %s", e)

        # --- Anomaly Detection ---
        anomaly_score = 0.0
        is_anomaly = False
        if self._anomaly_model is not None:
            try:
                pred = self._anomaly_model.predict(X.values)
                is_anomaly = bool(pred[0] == -1)
                scores = self._anomaly_model.decision_function(X.values)
                anomaly_score = float(scores[0])
            except Exception as e:
                logger.warning("Anomaly detection error: %s", e)

        # --- Risk Level ---
        if failure_prob > 0.7 or (is_anomaly and failure_prob > 0.4):
            risk_level = "CRITICAL"
        elif failure_prob > 0.4 or is_anomaly:
            risk_level = "WARNING"
        else:
            risk_level = "LOW"

        # --- Explanation ---
        high_risk_features = [
            f"{k}: {v}" for k, v in deviations.items()
            if "HIGH" in v or "LOW" in v
        ]
        if high_risk_features:
            explanation = "Key risk drivers: " + "; ".join(high_risk_features)
        else:
            explanation = "All features within nominal operating range."

        # Keep original string value for 'Type' in feature_values as expected by tests
        numeric_features = {}
        for col in FEATURE_COLUMNS:
            val = features.get(col, 0)
            if col == "Type":
                numeric_features[col] = str(val)
            else:
                numeric_features[col] = float(val)

        return PredictionResult(
            failure_probability=round(failure_prob, 4),
            anomaly_score=round(anomaly_score, 4),
            is_anomaly=is_anomaly,
            risk_level=risk_level,
            feature_values=numeric_features,
            feature_deviations=deviations,
            model_loaded=True,
            explanation=explanation,
        )