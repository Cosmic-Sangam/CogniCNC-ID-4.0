"""Telemetry data schema for the virtual CNC factory.

Fields are divided into two groups:
* **Model features** — the six fields the AI4I-trained models expect.
* **Simulator-only fields** — generated for dashboard display and
  scenario realism but NOT fed to the ML models.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class TelemetrySample:
    """One telemetry reading from one machine at one point in time."""

    # Identity
    timestamp: str          # ISO-8601 string
    machine_id: str         # e.g. "TC-01"
    machine_name: str       # e.g. "CNC Turning Center"
    state: str              # IDLE | RUNNING | WARNING | FAULT | MAINTENANCE

    # Model features (must match AI4I training schema exactly)
    model_type: str         # "L" | "M" | "H"
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: float

    # Simulator-only fields (display / analytics, NOT model input)
    vibration_mm_s: float
    power_kw: float
    production_count: int
    cycle_time_s: float
    uptime_min: float
    downtime_min: float

    def to_model_features(self) -> Dict[str, float | str]:
        """Return a dict with exactly the six feature names the model expects."""
        return {
            "Type": self.model_type,
            "Air temperature [K]": round(self.air_temperature_k, 2),
            "Process temperature [K]": round(self.process_temperature_k, 2),
            "Rotational speed [rpm]": round(self.rotational_speed_rpm, 1),
            "Torque [Nm]": round(self.torque_nm, 2),
            "Tool wear [min]": round(self.tool_wear_min, 2),
        }

    def to_dict(self) -> Dict:
        return asdict(self)