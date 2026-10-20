"""Supervised failure prediction — training and evaluation.

Models
------
* Logistic Regression (baseline)
* Random Forest (primary candidate)

Both are wrapped in a scikit-learn Pipeline that includes the
preprocessing step, so the saved artifact is a single self-contained
object that can accept raw feature DataFrames at inference time.
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from cognicnc.data_pipeline.preprocessing import (
    FEATURE_COLUMNS,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    build_preprocessor,
)

logger = logging.getLogger("cognicnc.ml")


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

def make_logistic_regression_pipeline(random_seed: int = 42) -> Pipeline:
    """Logistic Regression baseline with preprocessing."""
    return Pipeline([
        ("preprocessor", build_preprocessor()),
        (
            "classifier",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=random_seed,
                solver="lbfgs",
            ),
        ),
    ])


def make_random_forest_pipeline(random_seed: int = 42) -> Pipeline:
    """Random Forest with preprocessing."""
    return Pipeline([
        ("preprocessor", build_preprocessor()),
        (
            "classifier",
            RandomForestClassifier(
                n_estimators=200,
                max_depth=12,
                min_samples_split=5,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=random_seed,
                n_jobs=-1,
            ),
        ),
    ])


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_pipeline(
    pipeline: Pipeline,
    X_train_raw,
    y_train: np.ndarray,
    model_name: str,
) -> Pipeline:
    """Fit a full pipeline (preprocessor + classifier) on raw training data."""
    logger.info("Training %s on %d samples ...", model_name, len(y_train))
    pipeline.fit(X_train_raw, y_train)
    logger.info("%s training complete.", model_name)
    return pipeline


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_model(
    pipeline: Pipeline,
    X_test_raw,
    y_test: np.ndarray,
    model_name: str,
) -> Dict[str, Any]:
    """Evaluate a trained pipeline and return a metrics dictionary."""
    y_pred = pipeline.predict(X_test_raw)
    y_proba = pipeline.predict_proba(X_test_raw)[:, 1]

    metrics: Dict[str, Any] = {
        "model_name": model_name,
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, y_proba)), 4),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "test_samples": int(len(y_test)),
        "test_failures": int(y_test.sum()),
    }

    print(f"\n{'~' * 50}")
    print(f"  {model_name}")
    print(f"{'~' * 50}")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Failure"]))
    print(f"  ROC-AUC        : {metrics['roc_auc']}")
    print(f"  Confusion Matrix:")
    cm = metrics["confusion_matrix"]
    print(f"    TN={cm[0][0]:>5d}   FP={cm[0][1]:>5d}")
    print(f"    FN={cm[1][0]:>5d}   TP={cm[1][1]:>5d}")
    print(f"{'~' * 50}")

    logger.info(
        "%s evaluation — P=%.3f R=%.3f F1=%.3f AUC=%.3f",
        model_name, metrics["precision"], metrics["recall"],
        metrics["f1"], metrics["roc_auc"],
    )
    return metrics


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------

def save_failure_artifacts(
    pipeline: Pipeline,
    metrics: Dict[str, Any],
    output_dir: str | Path,
    random_seed: int = 42,
) -> Path:
    """Save the trained pipeline and metadata to disk."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / "failure_pipeline.joblib"
    meta_path = output_dir / "metadata.json"

    joblib.dump(pipeline, model_path)
    logger.info("Saved failure pipeline to %s", model_path)

    metadata = {
        "model_type": type(pipeline.named_steps["classifier"]).__name__,
        "framework": "scikit-learn",
        "sklearn_version": sklearn.__version__,
        "feature_names": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "target_name": TARGET_COLUMN,
        "random_seed": random_seed,
        "metrics": metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info("Saved metadata to %s", meta_path)

    return model_path


def load_failure_pipeline(artifact_dir: str | Path) -> Tuple[Pipeline, Dict]:
    """Load a saved failure prediction pipeline and its metadata."""
    artifact_dir = Path(artifact_dir)
    model_path = artifact_dir / "failure_pipeline.joblib"
    meta_path = artifact_dir / "metadata.json"

    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not meta_path.is_file():
        raise FileNotFoundError(f"Metadata not found: {meta_path}")

    pipeline = joblib.load(model_path)
    with meta_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)

    logger.info(
        "Loaded failure pipeline (%s) from %s",
        metadata.get("model_type", "unknown"), artifact_dir,
    )
    return pipeline, metadata