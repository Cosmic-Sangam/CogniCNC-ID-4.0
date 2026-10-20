"""Dataset loading, column validation, and leakage-safe preprocessing.

The UCI AI4I 2020 dataset uses ``Machine failure`` as the binary target
and five separate binary columns (TWF, HDF, PWF, OSF, RNF) for failure
modes. There is NO single ``Failure Type`` column.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

logger = logging.getLogger("cognicnc.ml")

# ---------------------------------------------------------------------------
# Column schema — matches the ACTUAL UCI AI4I 2020 CSV (14 columns)
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS: Dict[str, str] = {
    "udi":              "UDI",
    "product_id":       "Product ID",
    "type":             "Type",
    "air_temp":         "Air temperature [K]",
    "process_temp":     "Process temperature [K]",
    "rotational_speed": "Rotational speed [rpm]",
    "torque":           "Torque [Nm]",
    "tool_wear":        "Tool wear [min]",
    "target":           "Machine failure",
    "twf":              "TWF",
    "hdf":              "HDF",
    "pwf":              "PWF",
    "osf":              "OSF",
    "rnf":              "RNF",
}

DROP_COLUMNS = {
    "UDI", "Product ID",
    "Machine failure",
    "TWF", "HDF", "PWF", "OSF", "RNF",
}

FEATURE_COLUMNS: List[str] = [
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

CATEGORICAL_FEATURES = ["Type"]
NUMERIC_FEATURES = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

FAILURE_MODE_COLUMNS: List[str] = ["TWF", "HDF", "PWF", "OSF", "RNF"]

TARGET_COLUMN = "Machine failure"


# ---------------------------------------------------------------------------
# Dataset loading and validation
# ---------------------------------------------------------------------------

def load_dataset(csv_path: str | Path) -> pd.DataFrame:
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")
    df = pd.read_csv(csv_path)
    logger.info("Loaded dataset from %s  shape=%s", csv_path, df.shape)
    return df


def validate_columns(df: pd.DataFrame) -> Dict[str, str]:
    actual = set(df.columns)
    expected = set(EXPECTED_COLUMNS.values())
    missing = expected - actual
    if missing:
        raise ValueError(
            f"Dataset is missing expected columns: {sorted(missing)}\n"
            f"Actual columns: {sorted(actual)}"
        )
    extra = actual - expected
    if extra:
        logger.warning("Unexpected extra columns (ignored): %s", sorted(extra))
    role_map = {role: col for role, col in EXPECTED_COLUMNS.items()}
    logger.info("Column validation passed. %d columns matched.", len(role_map))
    return role_map


def inspect_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    report["shape"] = df.shape
    report["dtypes"] = df.dtypes.astype(str).to_dict()
    report["missing_values"] = df.isnull().sum().to_dict()
    report["duplicates"] = int(df.duplicated().sum())

    if TARGET_COLUMN in df.columns:
        target_counts = df[TARGET_COLUMN].value_counts().to_dict()
        report["target_distribution"] = target_counts
        total = len(df)
        report["failure_rate_pct"] = round(target_counts.get(1, 0) / total * 100, 2)

    failure_mode_counts: Dict[str, int] = {}
    for col in FAILURE_MODE_COLUMNS:
        if col in df.columns:
            failure_mode_counts[col] = int(df[col].sum())
    report["failure_mode_counts"] = failure_mode_counts

    if all(c in df.columns for c in FAILURE_MODE_COLUMNS):
        mode_sum = df[FAILURE_MODE_COLUMNS].sum(axis=1)
        report["rows_with_multiple_modes"] = int((mode_sum > 1).sum())
        report["rows_with_no_mode_but_failure"] = int(
            ((mode_sum == 0) & (df[TARGET_COLUMN] == 1)).sum()
        )

    report["numeric_summary"] = df[FEATURE_COLUMNS].describe().to_dict()

    print("\n" + "=" * 65)
    print("  AI4I 2020 DATASET INSPECTION REPORT")
    print("=" * 65)
    print(f"  Shape            : {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"  Duplicates       : {report['duplicates']}")
    print(f"  Missing values   : {sum(report['missing_values'].values())}")
    print()
    print("  Column types:")
    for col, dtype in report["dtypes"].items():
        print(f"    {col:<30s} {dtype}")
    print()
    if TARGET_COLUMN in df.columns:
        print(f"  Target distribution ({TARGET_COLUMN}):")
        for val, count in sorted(report["target_distribution"].items()):
            pct = count / len(df) * 100
            label = "Normal" if val == 0 else "Failure"
            print(f"    {label} ({val})  : {count:>6d}  ({pct:.2f}%)")
        print(f"  Failure rate     : {report['failure_rate_pct']}%")
        print()
    if failure_mode_counts:
        print("  Failure mode counts (binary indicator columns):")
        for mode, count in failure_mode_counts.items():
            pct = count / len(df) * 100
            print(f"    {mode:<6s}: {count:>5d}  ({pct:.2f}%)")
        if "rows_with_multiple_modes" in report:
            print(f"  Rows with >1 mode active : {report['rows_with_multiple_modes']}")
            print(f"  Failure rows with 0 modes: {report['rows_with_no_mode_but_failure']}")
        print()
    print("  Numeric feature ranges:")
    for col in NUMERIC_FEATURES:
        if col in df.columns:
            lo, hi = df[col].min(), df[col].max()
            mean = df[col].mean()
            print(f"    {col:<30s}  min={lo:>8.1f}  mean={mean:>8.1f}  max={hi:>8.1f}")
    print("=" * 65 + "\n")
    return report


# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------

def build_preprocessor() -> ColumnTransformer:
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OrdinalEncoder(categories=[["L", "M", "H"]]), CATEGORICAL_FEATURES),
            ("num", StandardScaler(), NUMERIC_FEATURES),
        ],
        remainder="drop",
    )
    return preprocessor


def split_and_preprocess(
    df: pd.DataFrame,
    test_size: float = 0.2,
    random_seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, ColumnTransformer]:
    X_raw = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].values
    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X_raw, y, test_size=test_size, random_state=random_seed, stratify=y,
    )
    logger.info(
        "Train/test split: train=%d, test=%d, failure_rate_train=%.2f%%",
        len(y_train), len(y_test), y_train.mean() * 100,
    )
    preprocessor = build_preprocessor()
    X_train = preprocessor.fit_transform(X_train_raw)
    X_test = preprocessor.transform(X_test_raw)
    logger.info("Preprocessor fitted. Feature shape: %s", X_train.shape)
    return X_train, X_test, y_train, y_test, preprocessor


def get_normal_training_data(
    df: pd.DataFrame,
    preprocessor: ColumnTransformer,
    test_size: float = 0.2,
    random_seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    X_raw = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].values
    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X_raw, y, test_size=test_size, random_state=random_seed, stratify=y,
    )
    normal_mask = y_train == 0
    X_train_normal = preprocessor.transform(X_train_raw[normal_mask])
    X_test = preprocessor.transform(X_test_raw)
    logger.info(
        "Normal training data: %d samples (from %d total)",
        len(X_train_normal), len(y_train),
    )
    return X_train_normal, X_test, y_test