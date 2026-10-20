"""CogniCNC - Industry 4.0 Smart CNC Monitoring, Predictive Maintenance
and Explainable AI Platform.

This package provides the core modules used by the Streamlit dashboard
and the training/inference scripts.

Phase 0 exposes only the configuration loader and the logging setup.
Later phases will register additional submodules (simulator, models,
database, services, dashboard).
"""

from __future__ import annotations

__version__ = "0.1.0-phase0"
__all__ = ["__version__"]