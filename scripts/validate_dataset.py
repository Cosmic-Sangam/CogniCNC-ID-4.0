"""Download (if needed) and validate the UCI AI4I 2020 dataset.

Usage
-----
    python scripts/validate_dataset.py
"""

from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cognicnc.config import load_config
from cognicnc.logging_config import configure_logging, get_logger
from cognicnc.data_pipeline.preprocessing import (
    load_dataset,
    validate_columns,
    inspect_dataset,
)

UCI_DOWNLOAD_URL = (
    "https://archive.ics.uci.edu/static/public/601/"
    "ai4i+2020+predictive+maintenance+dataset.zip"
)
CSV_FILENAME = "ai4i2020.csv"


def download_dataset(raw_dir: Path) -> Path:
    """Download and extract the AI4I dataset into *raw_dir*."""
    csv_path = raw_dir / CSV_FILENAME
    if csv_path.is_file():
        print(f"Dataset already exists at {csv_path} — skipping download.")
        return csv_path

    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "ai4i2020.zip"

    print(f"Downloading AI4I 2020 dataset from UCI ...")
    print(f"  URL : {UCI_DOWNLOAD_URL}")
    try:
        urllib.request.urlretrieve(UCI_DOWNLOAD_URL, str(zip_path))
    except Exception as exc:
        print(f"\n[ERROR] Download failed: {exc}")
        print(
            "\nManual download instructions:\n"
            "  1. Visit https://archive.ics.uci.edu/dataset/601/\n"
            "  2. Download the zip file.\n"
            f"  3. Extract '{CSV_FILENAME}' into: {raw_dir}\n"
        )
        raise

    print(f"Extracting {zip_path.name} ...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith(CSV_FILENAME):
                with zf.open(member) as src, open(csv_path, "wb") as dst:
                    dst.write(src.read())
                break
        else:
            raise FileNotFoundError(
                f"'{CSV_FILENAME}' not found inside the downloaded zip. "
                f"Contents: {zf.namelist()}"
            )

    zip_path.unlink(missing_ok=True)
    print(f"Dataset saved to {csv_path}")
    return csv_path


def main() -> int:
    configure_logging()
    logger = get_logger("cognicnc.ml")
    cfg = load_config()

    raw_dir = cfg.resolved_path("data_raw")
    logger.info("Dataset directory: %s", raw_dir)

    csv_path = download_dataset(raw_dir)

    df = load_dataset(csv_path)

    role_map = validate_columns(df)
    print(f"\nColumn role mapping:")
    for role, col in role_map.items():
        print(f"  {role:<20s} -> {col}")

    report = inspect_dataset(df)

    logger.info("Dataset validation complete.")
    print("\n[OK] Dataset is valid and ready for model training.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())