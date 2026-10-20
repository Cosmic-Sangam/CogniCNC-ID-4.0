"""Phase 1 tests — preprocessing, model training, artifact round-trip.

Uses a small synthetic dataset so tests run fast without downloading
the real AI4I data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cognicnc.data_pipeline.preprocessing import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    FAILURE_MODE_COLUMNS,
    build_preprocessor,
    validate_columns,
)
from cognicnc.models.train_failure import (
    make_logistic_regression_pipeline,
    make_random_forest_pipeline,
    save_failure_artifacts,
    load_failure_pipeline,
)
from cognicnc.models.train_anomaly import (
    train_isolation_forest,
    save_anomaly_artifacts,
    load_anomaly_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    """Small synthetic dataset mimicking the ACTUAL AI4I structure."""
    rng = np.random.default_rng(42)
    n = 500
    types = rng.choice(["L", "M", "H"], n)
    targets = rng.choice([0, 1], n, p=[0.93, 0.07])

    # Five separate binary failure-mode columns
    twf = np.zeros(n, dtype=int)
    hdf = np.zeros(n, dtype=int)
    pwf = np.zeros(n, dtype=int)
    osf = np.zeros(n, dtype=int)
    rnf = np.zeros(n, dtype=int)

    failure_cols = [twf, hdf, pwf, osf, rnf]
    for i in range(n):
        if targets[i] == 1:
            mode = rng.integers(0, 5)
            failure_cols[mode][i] = 1

    return pd.DataFrame({
        "UDI": range(1, n + 1),
        "Product ID": [f"P{i:05d}" for i in range(1, n + 1)],
        "Type": types,
        "Air temperature [K]": rng.normal(300, 2, n),
        "Process temperature [K]": rng.normal(310, 1.5, n),
        "Rotational speed [rpm]": rng.normal(1500, 200, n),
        "Torque [Nm]": rng.normal(40, 10, n),
        "Tool wear [min]": rng.uniform(0, 250, n),
        TARGET_COLUMN: targets,
        "TWF": twf,
        "HDF": hdf,
        "PWF": pwf,
        "OSF": osf,
        "RNF": rnf,
    })


# ---------------------------------------------------------------------------
# Column validation
# ---------------------------------------------------------------------------

def test_validate_columns_passes(synthetic_df):
    role_map = validate_columns(synthetic_df)
    assert "target" in role_map
    assert role_map["target"] == TARGET_COLUMN


def test_validate_columns_rejects_missing(synthetic_df):
    bad_df = synthetic_df.drop(columns=["Torque [Nm]"])
    with pytest.raises(ValueError, match="missing expected columns"):
        validate_columns(bad_df)


# ---------------------------------------------------------------------------
# Preprocessor
# ---------------------------------------------------------------------------

def test_preprocessor_output_shape(synthetic_df):
    preprocessor = build_preprocessor()
    X = preprocessor.fit_transform(synthetic_df[FEATURE_COLUMNS])
    assert X.shape == (len(synthetic_df), len(FEATURE_COLUMNS))


# ---------------------------------------------------------------------------
# Failure pipelines
# ---------------------------------------------------------------------------

def test_logistic_regression_pipeline(synthetic_df):
    pipe = make_logistic_regression_pipeline(random_seed=42)
    X = synthetic_df[FEATURE_COLUMNS]
    y = synthetic_df[TARGET_COLUMN].values
    pipe.fit(X, y)
    preds = pipe.predict(X)
    assert preds.shape == y.shape
    assert set(preds).issubset({0, 1})


def test_random_forest_pipeline(synthetic_df):
    pipe = make_random_forest_pipeline(random_seed=42)
    X = synthetic_df[FEATURE_COLUMNS]
    y = synthetic_df[TARGET_COLUMN].values
    pipe.fit(X, y)
    proba = pipe.predict_proba(X)[:, 1]
    assert proba.shape == y.shape
    assert np.all((proba >= 0) & (proba <= 1))


# ---------------------------------------------------------------------------
# Anomaly detector
# ---------------------------------------------------------------------------

def test_isolation_forest_training(synthetic_df):
    preprocessor = build_preprocessor()
    X_all = preprocessor.fit_transform(synthetic_df[FEATURE_COLUMNS])
    y = synthetic_df[TARGET_COLUMN].values
    X_normal = X_all[y == 0]

    model = train_isolation_forest(X_normal, contamination=0.05, random_seed=42)
    preds = model.predict(X_all)
    assert set(preds).issubset({-1, 1})


# ---------------------------------------------------------------------------
# Artifact round-trip
# ---------------------------------------------------------------------------

def test_failure_artifact_round_trip(synthetic_df, tmp_path):
    pipe = make_random_forest_pipeline(random_seed=42)
    X = synthetic_df[FEATURE_COLUMNS]
    y = synthetic_df[TARGET_COLUMN].values
    pipe.fit(X, y)

    metrics = {"f1": 0.85, "precision": 0.90, "recall": 0.80, "roc_auc": 0.92}
    save_failure_artifacts(pipe, metrics, tmp_path / "pm", random_seed=42)

    loaded_pipe, loaded_meta = load_failure_pipeline(tmp_path / "pm")
    assert loaded_meta["model_type"] == "RandomForestClassifier"
    assert loaded_meta["feature_names"] == FEATURE_COLUMNS

    preds_orig = pipe.predict(X)
    preds_loaded = loaded_pipe.predict(X)
    np.testing.assert_array_equal(preds_orig, preds_loaded)


def test_anomaly_artifact_round_trip(synthetic_df, tmp_path):
    preprocessor = build_preprocessor()
    X_all = preprocessor.fit_transform(synthetic_df[FEATURE_COLUMNS])
    y = synthetic_df[TARGET_COLUMN].values
    X_normal = X_all[y == 0]

    model = train_isolation_forest(X_normal, random_seed=42)
    metrics = {"f1": 0.50, "precision": 0.40, "recall": 0.60}
    save_anomaly_artifacts(model, metrics, tmp_path / "ad", random_seed=42)

    loaded_model, loaded_meta = load_anomaly_model(tmp_path / "ad")
    assert loaded_meta["model_type"] == "IsolationForest"

    preds_orig = model.predict(X_all)
    preds_loaded = loaded_model.predict(X_all)
    np.testing.assert_array_equal(preds_orig, preds_loaded)