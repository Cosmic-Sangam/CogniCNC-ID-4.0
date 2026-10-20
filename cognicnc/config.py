"""Centralized configuration loading for CogniCNC.

Responsibilities
----------------
* Locate the project root deterministically (the folder containing the
  `config/` directory), independent of the current working directory.
* Load the three YAML configuration files: ``settings.yaml``,
  ``machines.yaml``, ``thresholds.yaml``.
* Validate the minimum required keys so that missing/renamed keys fail
  loudly instead of silently returning ``None`` deep inside the app.
* Resolve all configured paths to absolute paths rooted at the project
  root, and ensure the writable directories exist.
* Cache the loaded configuration so repeated calls are cheap and
  consistent (important for Streamlit's rerun behaviour in later phases).

Public API
----------
* ``AppConfig``            - typed container returned by ``load_config``.
* ``load_config()``        - load (and cache) the configuration.
* ``get_project_root()``   - absolute Path to the project root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml


# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------

def get_project_root() -> Path:
    """Return the absolute path to the CogniCNC project root.

    The project root is defined as the first ancestor of this file that
    contains a ``config`` directory. This is robust against the user
    launching Python/Streamlit from any working directory.
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "config").is_dir():
            return parent
    # Fallback: two levels up from this file (cognicnc/ -> project root)
    return here.parent.parent


# ---------------------------------------------------------------------------
# Typed configuration container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """Immutable container for the parsed configuration.

    Fields map 1:1 to the top-level YAML sections. Nested data is kept
    as plain dictionaries for Phase 0 to avoid over-engineering before
    we know the exact shape we need in later phases.
    """
    project_root: Path
    settings: Dict[str, Any]
    machines: List[Dict[str, Any]] = field(default_factory=list)
    thresholds: Dict[str, Any] = field(default_factory=dict)

    # -- Convenience accessors ------------------------------------------------
    @property
    def app_name(self) -> str:
        return str(self.settings.get("app", {}).get("name", "CogniCNC"))

    @property
    def app_version(self) -> str:
        return str(self.settings.get("app", {}).get("version", "0.0.0"))

    @property
    def environment(self) -> str:
        return str(self.settings.get("app", {}).get("environment", "development"))

    @property
    def random_seed(self) -> int:
        return int(self.settings.get("app", {}).get("random_seed", 42))

    def resolved_path(self, key: str) -> Path:
        """Return an absolute Path for a key under ``settings.paths``."""
        paths = self.settings.get("paths", {})
        if key not in paths:
            raise KeyError(f"Path key '{key}' not defined in settings.yaml under 'paths'.")
        return (self.project_root / paths[key]).resolve()


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Required configuration file is missing: {path}")
    with path.open("r", encoding="utf-8") as fh:
        try:
            return yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc


def _validate_settings(settings: Dict[str, Any]) -> None:
    required_top = ("app", "paths", "logging")
    missing = [k for k in required_top if k not in settings]
    if missing:
        raise KeyError(
            f"settings.yaml is missing required top-level keys: {missing}"
        )

    required_paths = (
        "data_raw", "data_processed", "data_simulated",
        "artifacts_pm", "artifacts_anomaly", "assets_machines", "logs",
    )
    missing_paths = [k for k in required_paths if k not in settings["paths"]]
    if missing_paths:
        raise KeyError(
            f"settings.yaml 'paths' section is missing keys: {missing_paths}"
        )


def _validate_machines(machines_doc: Any) -> List[Dict[str, Any]]:
    if not isinstance(machines_doc, dict) or "machines" not in machines_doc:
        raise KeyError("machines.yaml must contain a top-level 'machines' list.")
    machines = machines_doc["machines"]
    if not isinstance(machines, list) or not machines:
        raise ValueError("machines.yaml 'machines' must be a non-empty list.")

    seen_ids = set()
    expected_ids = {"TC-01", "MC-01", "DR-01", "GR-01", "VIS-01"}
    for m in machines:
        for req in ("id", "name", "type", "position_in_line"):
            if req not in m:
                raise KeyError(f"Machine entry missing '{req}': {m}")
        if m["id"] in seen_ids:
            raise ValueError(f"Duplicate machine id in machines.yaml: {m['id']}")
        seen_ids.add(m["id"])

    missing_expected = expected_ids - seen_ids
    if missing_expected:
        raise ValueError(
            f"machines.yaml is missing required machine ids: {sorted(missing_expected)}"
        )
    return machines


def _ensure_writable_dirs(cfg: AppConfig) -> None:
    """Create directories that the application writes to at runtime."""
    for key in ("data_raw", "data_processed", "data_simulated",
                "artifacts_pm", "artifacts_anomaly", "assets_machines", "logs"):
        cfg.resolved_path(key).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Public loader (cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load, validate and cache the full application configuration."""
    root = get_project_root()
    config_dir = root / "config"

    settings = _load_yaml(config_dir / "settings.yaml") or {}
    _validate_settings(settings)

    machines_doc = _load_yaml(config_dir / "machines.yaml") or {}
    machines = _validate_machines(machines_doc)

    thresholds_doc = _load_yaml(config_dir / "thresholds.yaml") or {}
    if not isinstance(thresholds_doc, dict):
        raise ValueError("thresholds.yaml must be a mapping at the top level.")

    cfg = AppConfig(
        project_root=root,
        settings=settings,
        machines=machines,
        thresholds=thresholds_doc,
    )
    _ensure_writable_dirs(cfg)
    return cfg