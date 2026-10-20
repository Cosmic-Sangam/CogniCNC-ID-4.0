"""Train, evaluate, and save all Phase 1 ML models.

Usage
-----
    python scripts/train_models.py

Prerequisites
-------------
    Run ``python scripts/validate_dataset.py`` first.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sklearn.model_selection import train_test_split

from cognicnc.config import load_config
from cognicnc.logging_config import configure_logging, get_logger
from cognicnc.data_pipeline.preprocessing import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    load_dataset,
    validate_columns,
    split_and_preprocess,
    get_normal_training_data,
)
from cognicnc.models.train_failure import (
    make_logistic_regression_pipeline,
    make_random_forest_pipeline,
    train_pipeline,
    evaluate_model,
    save_failure_artifacts,
)
from cognicnc.models.train_anomaly import (
    train_isolation_forest,
    evaluate_anomaly_detector,
    save_anomaly_artifacts,
)


def main() -> int:
    configure_logging()
    logger = get_logger("cognicnc.ml")
    cfg = load_config()

    random_seed = cfg.random_seed
    csv_path = cfg.resolved_path("data_raw") / "ai4i2020.csv"

    if not csv_path.is_file():
        logger.error("Dataset not found at %s. Run validate_dataset.py first.", csv_path)
        print(f"\n[ERROR] Dataset not found: {csv_path}")
        print("Run:  python scripts/validate_dataset.py\n")
        return 1

    # ------------------------------------------------------------------
    # 1. Load & validate
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  CogniCNC — Phase 1 Model Training")
    print("=" * 65)

    df = load_dataset(csv_path)
    validate_columns(df)

    # ------------------------------------------------------------------
    # 2. Split & preprocess (leakage-safe)
    # ------------------------------------------------------------------
    print("\n[Step 1/5] Splitting dataset and fitting preprocessor ...")
    X_train, X_test, y_train, y_test, preprocessor = split_and_preprocess(
        df, test_size=0.2, random_seed=random_seed,
    )

    # Raw DataFrames for the Pipeline-based approach (Pipeline contains
    # its own preprocessor, so it needs un-preprocessed input).
    indices = train_test_split(
        range(len(df)), test_size=0.2, random_state=random_seed,
        stratify=df[TARGET_COLUMN],
    )
    train_idx, test_idx = indices[0], indices[1]
    X_train_raw = df[FEATURE_COLUMNS].iloc[train_idx]
    X_test_raw = df[FEATURE_COLUMNS].iloc[test_idx]
    y_train_raw = df[TARGET_COLUMN].iloc[train_idx].values
    y_test_raw = df[TARGET_COLUMN].iloc[test_idx].values

    # ------------------------------------------------------------------
    # 3. Train failure classifiers
    # ------------------------------------------------------------------
    print("\n[Step 2/5] Training Logistic Regression baseline ...")
    lr_pipeline = make_logistic_regression_pipeline(random_seed)
    lr_pipeline = train_pipeline(lr_pipeline, X_train_raw, y_train_raw, "Logistic Regression")
    lr_metrics = evaluate_model(lr_pipeline, X_test_raw, y_test_raw, "Logistic Regression")

    print("\n[Step 3/5] Training Random Forest ...")
    rf_pipeline = make_random_forest_pipeline(random_seed)
    rf_pipeline = train_pipeline(rf_pipeline, X_train_raw, y_train_raw, "Random Forest")
    rf_metrics = evaluate_model(rf_pipeline, X_test_raw, y_test_raw, "Random Forest")

    # Select best model by F1 (most relevant for imbalanced data)
    if rf_metrics["f1"] >= lr_metrics["f1"]:
        best_name = "Random Forest"
        best_pipeline = rf_pipeline
        best_metrics = rf_metrics
    else:
        best_name = "Logistic Regression"
        best_pipeline = lr_pipeline
        best_metrics = lr_metrics

    print(f"\n  >> Best model: {best_name} (F1 = {best_metrics['f1']})")

    # ------------------------------------------------------------------
    # 4. Train anomaly detector
    # ------------------------------------------------------------------
    print("\n[Step 4/5] Training Isolation Forest (anomaly detection) ...")
    X_train_normal, X_test_anom, y_test_anom = get_normal_training_data(
        df, preprocessor, test_size=0.2, random_seed=random_seed,
    )
    anomaly_model = train_isolation_forest(
        X_train_normal, contamination=0.05, random_seed=random_seed,
    )
    anomaly_metrics = evaluate_anomaly_detector(anomaly_model, X_test_anom, y_test_anom)

    # ------------------------------------------------------------------
    # 5. Save artifacts
    # ------------------------------------------------------------------
    print("\n[Step 5/5] Saving artifacts ...")
    pm_dir = cfg.resolved_path("artifacts_pm")
    ad_dir = cfg.resolved_path("artifacts_anomaly")

    save_failure_artifacts(best_pipeline, best_metrics, pm_dir, random_seed)
    save_anomaly_artifacts(anomaly_model, anomaly_metrics, ad_dir, random_seed)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  TRAINING COMPLETE")
    print("=" * 65)
    print(f"  Failure model      : {best_name}")
    print(f"    Precision        : {best_metrics['precision']}")
    print(f"    Recall           : {best_metrics['recall']}")
    print(f"    F1               : {best_metrics['f1']}")
    print(f"    ROC-AUC          : {best_metrics['roc_auc']}")
    print(f"  Anomaly detector   : Isolation Forest")
    print(f"    Precision        : {anomaly_metrics['precision']}")
    print(f"    Recall           : {anomaly_metrics['recall']}")
    print(f"    F1               : {anomaly_metrics['f1']}")
    print(f"\n  Artifacts saved to:")
    print(f"    {pm_dir}")
    print(f"    {ad_dir}")
    print("=" * 65 + "\n")

    logger.info("Phase 1 training complete. Best failure model: %s", best_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())