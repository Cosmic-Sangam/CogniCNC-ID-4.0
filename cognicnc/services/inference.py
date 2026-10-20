"""Inference service — loads Phase 1 artifacts and runs predictions.

The service bridges the simulator output and the trained models:
1. Accepts a ``TelemetrySample`` from the simulator.
2. Extracts the six model-compatible features via ``to_model_features()``.
3. Runs the failure-prediction pipeline (which includes its own
   preprocessor) to get failure probability.
4. Runs the Isolation Forest anomaly detector (using the preprocessor
   extracted from the failure pipeline) to get an anomaly score.
5. Returns a combined prediction dictionary.

The adapter ensures that simulator-only fields (vibration, power, etc.)
are NEVER passed to the ML models.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from cognicnc.config import AppConfig
from cognicnc.models.train_failure import load_failure_pipeline
from cognicnc.models.train_anomaly import load_anomaly_model
from cognicnc.simulator.telemetry import TelemetrySample

logger = logging.getLogger("cognicnc.ml")


class InferenceService:
    """Unified inference interface for failure prediction and anomaly detection."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._failure_pipeline = None
        self._anomaly_model = None
        self._preprocessor = None
        self._failure_meta: Dict[str, Any] = {}
        self._anomaly_meta: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all model artifacts from disk."""
        pm_dir = self.config.resolved_path("artifacts_pm")
        ad_dir = self.config.resolved_path("artifacts_anomaly")

        self._failure_pipeline, self._failure_meta = load_failure_pipeline(pm_dir)
        self._anomaly_model, self._anomaly_meta = load_anomaly_model(ad_dir)

        # Extract the preprocessor from the failure pipeline for anomaly scoring.
        # The anomaly model was trained on preprocessed data, so we need the
        # same transformation at inference time.
        self._preprocessor = self._failure_pipeline.named_steps["preprocessor"]

        self._loaded = True
        logger.info(
            "InferenceService loaded: failure=%s, anomaly=%s",
            self._failure_meta.get("model_type"),
            self._anomaly_meta.get("model_type"),
        )

    def predict(self, sample: TelemetrySample) -> Dict[str, Any]:
        """Run failure prediction and anomaly detection on one telemetry sample.

        Returns
        -------
        dict with keys:
            failure_probability : float  (0.0 – 1.0)
            failure_prediction  : int    (0 or 1)
            anomaly_score       : float  (lower = more anomalous)
            is_anomaly          : bool
            model_type          : str
            feature_values      : dict   (the six features sent to the model)
        """
        if not self._loaded:
            self.load()

        features = sample.to_model_features()
        df = pd.DataFrame([features])

        # --- Failure prediction -----------------------------------------
        failure_proba = float(self._failure_pipeline.predict_proba(df)[0, 1])
        failure_pred = int(self._failure_pipeline.predict(df)[0])

        # --- Anomaly detection ------------------------------------------
        X_preprocessed = self._preprocessor.transform(df)
        anomaly_score = float(self._anomaly_model.decision_function(X_preprocessed)[0])
        is_anomaly = bool(self._anomaly_model.predict(X_preprocessed)[0] == -1)

        result = {
            "failure_probability": round(failure_proba, 4),
            "failure_prediction": failure_pred,
            "anomaly_score": round(anomaly_score, 4),
            "is_anomaly": is_anomaly,
            "model_type": self._failure_meta.get("model_type", "unknown"),
            "feature_values": features,
        }

        logger.debug(
            "Inference [%s] fail_prob=%.3f anomaly_score=%.3f is_anomaly=%s",
            sample.machine_id, failure_proba, anomaly_score, is_anomaly,
        )
        return result

    def predict_batch(self, samples: list[TelemetrySample]) -> list[Dict[str, Any]]:
        """Run inference on multiple samples."""
        return [self.predict(s) for s in samples]

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def failure_model_info(self) -> Dict[str, Any]:
        return self._failure_meta

    @property
    def anomaly_model_info(self) -> Dict[str, Any]:
        return self._anomaly_meta