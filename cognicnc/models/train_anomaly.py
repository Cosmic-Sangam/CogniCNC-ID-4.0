"""Unsupervised anomaly detection — Isolation Forest.

The detector is trained exclusively on **normal** operating samples
(Machine failure == 0). At inference time it assigns an anomaly score
to each observation; scores below a calibrated threshold are flagged.

Important: an anomaly flag is NOT a confirmed failure. It indicates
that the observation deviates from the learned normal operating
profile.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from cognicnc.data_pipeline.preprocessing import (
    FEATURE_COLUMNS,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
)

logger = logging.getLogger("cognicnc.ml")


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_isolation_forest(
    X_train_normal: np.ndarray,
    contamination: float = 0.05,
    random_seed: int = 42,
) -> IsolationForest:
    """Fit an Isolation Forest on preprocessed normal data."""
    logger.info(
        "Training Isolation Forest on %d normal samples (contamination=%.3f)",
        len(X_train_normal), contamination,
    )
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        max_samples="auto",
        random_state=random_seed,
        n_jobs=-1,
    )
    model.fit(X_train_normal)
    logger.info("Isolation Forest training complete.")
    return model


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_anomaly_detector(
    model: IsolationForest,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> Dict[str, Any]:
    """Evaluate the anomaly detector against the binary test labels.

    Isolation Forest returns -1 for anomalies and +1 for normal.
    We convert to 0/1 (1 = anomaly) for metric computation.

    Caveat: this evaluation uses the supervised failure labels as a
    proxy for "anomalous". Real anomalies may not always correspond
    to labelled failures, and vice versa.
    """
    raw_preds = model.predict(X_test)
    y_pred = (raw_preds == -1).astype(int)

    scores = model.decision_function(X_test)

    metrics: Dict[str, Any] = {
        "model_name": "IsolationForest",
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "test_samples": int(len(y_test)),
        "test_anomalies_flagged": int(y_pred.sum()),
        "test_actual_failures": int(y_test.sum()),
        "mean_anomaly_score_normal": round(float(scores[y_test == 0].mean()), 4),
        "mean_anomaly_score_failure": round(float(scores[y_test == 1].mean()), 4),
    }

    print(f"\n{'~' * 50}")
    print(f"  Isolation Forest (Anomaly Detection)")
    print(f"{'~' * 50}")
    print(
        "  Note: anomaly != confirmed failure. These metrics use the\n"
        "  supervised failure label as a proxy for evaluation only."
    )
    print()
    print(classification_report(y_test, y_pred, target_names=["Normal", "Anomaly"]))
    print(f"  Mean score (normal)  : {metrics['mean_anomaly_score_normal']}")
    print(f"  Mean score (failure) : {metrics['mean_anomaly_score_failure']}")
    cm = metrics["confusion_matrix"]
    print(f"  Confusion Matrix:")
    print(f"    TN={cm[0][0]:>5d}   FP={cm[0][1]:>5d}")
    print(f"    FN={cm[1][0]:>5d}   TP={cm[1][1]:>5d}")
    print(f"{'~' * 50}")

    logger.info(
        "Anomaly evaluation — P=%.3f R=%.3f F1=%.3f  flagged=%d actual=%d",
        metrics["precision"], metrics["recall"], metrics["f1"],
        metrics["test_anomalies_flagged"], metrics["test_actual_failures"],
    )
    return metrics


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------

def save_anomaly_artifacts(
    model: IsolationForest,
    metrics: Dict[str, Any],
    output_dir: str | Path,
    contamination: float = 0.05,
    random_seed: int = 42,
) -> Path:
    """Save the Isolation Forest model and metadata."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / "anomaly_model.joblib"
    meta_path = output_dir / "metadata.json"

    joblib.dump(model, model_path)
    logger.info("Saved anomaly model to %s", model_path)

    metadata = {
        "model_type": "IsolationForest",
        "framework": "scikit-learn",
        "sklearn_version": sklearn.__version__,
        "feature_names": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "contamination": contamination,
        "random_seed": random_seed,
        "metrics": metrics,
        "note": (
            "Anomaly scores are relative to the normal training distribution. "
            "An anomaly flag is not a confirmed failure."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info("Saved anomaly metadata to %s", meta_path)

    return model_path


def load_anomaly_model(artifact_dir: str | Path) -> Tuple[IsolationForest, Dict]:
    """Load a saved Isolation Forest and its metadata."""
    artifact_dir = Path(artifact_dir)
    model_path = artifact_dir / "anomaly_model.joblib"
    meta_path = artifact_dir / "metadata.json"

    if not model_path.is_file():
        raise FileNotFoundError(f"Anomaly model not found: {model_path}")
    if not meta_path.is_file():
        raise FileNotFoundError(f"Anomaly metadata not found: {meta_path}")

    model = joblib.load(model_path)
    with meta_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)

    logger.info("Loaded anomaly model from %s", artifact_dir)
    return model, metadata